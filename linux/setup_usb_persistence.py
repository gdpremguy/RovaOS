"""Add a save partition to an offline, DD-flashed Rova USB (Linux only).

Default is inspection only. --apply requires an interactive device-specific
confirmation. Never run against the USB you are currently booted from.
"""
import argparse
import hashlib
import json
import os
import pathlib
import platform
import shutil
import stat
import struct
import subprocess
import tempfile
import uuid
import zlib

from make_persistent import (SECTOR, MIB, LABEL, ISO_VOLUMES, LINUX_FS, EFI_FS, align,
                             read_gpt, header_bytes)


def layout(source, disk_bytes, save_mib=None, *, boot_source_bytes=None):
    """Pure regular-file planning; does not open or change any physical disk."""
    source = pathlib.Path(source)
    regular = stat.S_ISREG(source.stat().st_mode)
    if not regular and not (boot_source_bytes and stat.S_ISBLK(source.stat().st_mode)):
        raise ValueError('ISO source must be a regular file')
    source_size = source.stat().st_size if regular else boot_source_bytes
    if source_size < 32768+2048 or source_size >= disk_bytes:
        raise ValueError('Invalid ISO source size')
    with source.open('rb') as stream:
        prefix = stream.read(32768)
        header, entries = read_gpt(stream)
        stream.seek(32768)
        pvd = stream.read(2048)
    if pvd[:7] != b'\x01CD001\x01' or pvd[40:72].strip() not in ISO_VOLUMES:
        raise ValueError('Not recognised RovaOS or compatible legacy live media')
    if prefix[510:512] != b'\x55\xaa' or any(prefix[478:510]) or any(entries[256:]):
        raise ValueError('Only an unmodified ISO with two existing partitions is supported')
    # The boot options are embedded in the ISO, not inferred from its filename.
    found_label = found_scope = False
    tail = b''
    with source.open('rb') as stream:
        remaining = source_size
        while remaining:
            chunk = stream.read(min(4*MIB, remaining))
            if not chunk:
                raise ValueError('Truncated ISO source')
            remaining -= len(chunk)
            scan = tail+chunk
            found_label |= b'persistence-label=kestrel-rw' in scan
            found_scope |= b'persistence-media=removable-usb' in scan
            tail = scan[-128:]
    if not found_label or not found_scope:
        raise ValueError('ISO lacks restricted Rova USB persistence options')
    if disk_bytes % SECTOR or disk_bytes//SECTOR > 0xffffffff:
        raise ValueError('Unsupported disk size (512-byte sectors, at most 2 TiB)')
    first = align(source_size)//SECTOR
    for offset in (0, 128):
        start, end = struct.unpack_from('<QQ', entries, offset+32)
        if not start <= end < first:
            raise ValueError('Existing partition extends beyond the ISO')
    table_sectors = align(len(entries), SECTOR)//SECTOR
    backup_lba = disk_bytes//SECTOR-1
    backup_table = backup_lba-table_sectors
    available_mib = (backup_table-first)*SECTOR//MIB
    save_mib = available_mib if save_mib is None else save_mib
    if save_mib < 64 or save_mib > available_mib:
        raise ValueError(f'Save size must be 64..{available_mib} MiB')
    blocks = save_mib*MIB//SECTOR
    mbr = bytearray(prefix[:SECTOR])
    if struct.unpack_from('<I', mbr, 470)[0] != struct.unpack_from('<Q', entries, 160)[0]:
        raise ValueError('EFI MBR/GPT start sectors differ')
    entries[128:144] = EFI_FS
    entry = bytearray(128)
    entry[:16] = LINUX_FS
    entry[16:32] = uuid.uuid4().bytes_le
    struct.pack_into('<QQ', entry, 32, first, first+blocks-1)
    name = 'Rova persistent settings'.encode('utf-16le')
    entry[56:56+len(name)] = name
    entries[256:384] = entry
    mbr[478:494] = struct.pack('<B3sB3sII', 0, b'\xfe\xff\xff', 0x83, b'\xfe\xff\xff', first, blocks)
    crc = zlib.crc32(entries)
    table_lba = struct.unpack_from('<Q', header, 72)[0]
    guid = header[56:72]
    primary = header_bytes(header, 1, backup_lba, backup_table-1, table_lba, guid, crc)
    secondary = header_bytes(header, backup_lba, 1, backup_table-1, backup_table, guid, crc)
    patches = [(backup_table*SECTOR, bytes(entries)), (backup_lba*SECTOR, bytes(secondary)),
               (table_lba*SECTOR, bytes(entries)), (SECTOR, bytes(primary)), (0, bytes(mbr))]
    return {'first_sector': first, 'sectors': blocks, 'save_mib': save_mib,
            'disk_bytes': disk_bytes, 'prefix': prefix, 'patches': patches}


def mount_is_boot_iso(fields, medium):
    if medium is None:
        return False
    separator = fields.index('-')
    return (fields[4] == str(medium) and fields[separator+1] == 'iso9660'
            and 'ro' in fields[5].split(','))


def inspect_usb(path, *, readonly_boot_mount=None):
    """Require a stable USB whole-disk identity and no mounted/held children."""
    if platform.system() != 'Linux' or 'microsoft' in platform.release().lower():
        raise ValueError('Use native Linux, not Windows/WSL; never attach an internal disk to WSL for this')
    path = pathlib.Path(path)
    if path.parent != pathlib.Path('/dev/disk/by-id') or not path.name.startswith('usb-') or '-part' in path.name:
        raise ValueError('Select a whole-disk /dev/disk/by-id/usb-* path, never /dev/sdX or an internal disk')
    device = path.resolve(strict=True)
    info = device.stat()
    if not stat.S_ISBLK(info.st_mode):
        raise ValueError('Target is not a block device')
    sys = pathlib.Path('/sys/class/block')/device.name
    if (sys/'partition').exists() or (sys/'removable').read_text().strip() != '1':
        raise ValueError('Only removable whole USB disks are supported')
    if '/usb' not in str((sys/'device').resolve()):
        raise ValueError('Device is not attached through USB')
    if (sys/'queue/logical_block_size').read_text().strip() != '512':
        raise ValueError('Only 512-byte logical sectors are supported')
    if (sys/'ro').read_text().strip() != '0':
        raise ValueError('USB is read-only')
    nodes = [sys]+[p for p in sys.iterdir() if (p/'partition').exists()]
    ids = {p.joinpath('dev').read_text().strip() for p in nodes}
    for line in pathlib.Path('/proc/self/mountinfo').read_text().splitlines():
        if line.split()[2] in ids:
            fields = line.split()
            allowed = mount_is_boot_iso(fields, readonly_boot_mount)
            if not allowed:
                raise ValueError('USB or one of its partitions is mounted; boot another Linux and unmount it first')
    for line in pathlib.Path('/proc/swaps').read_text().splitlines()[1:]:
        swap = pathlib.Path(line.split()[0])
        swap_info = swap.stat()
        dev = swap_info.st_rdev if stat.S_ISBLK(swap_info.st_mode) else swap_info.st_dev
        if f'{os.major(dev)}:{os.minor(dev)}' in ids:
            raise ValueError('USB contains active swap')
    if any(list((p/'holders').iterdir()) for p in nodes):
        raise ValueError('USB is in use by device mapper/RAID')
    return device, info.st_rdev, int((sys/'size').read_text())*SECTOR


def verify_copy(source, target):
    """Require the flashed bytes to match the supplied ISO exactly."""
    digest = hashlib.sha256()
    with pathlib.Path(source).open('rb') as original:
        target.seek(0)
        while chunk := original.read(4*MIB):
            if target.read(len(chunk)) != chunk:
                raise ValueError('USB does not exactly match this ISO; use Rufus DD mode and the matching ISO')
            digest.update(chunk)
    return digest.hexdigest()


def setup(args):
    if platform.system() != 'Linux' or 'microsoft' in platform.release().lower():
        raise ValueError('Run on native Linux, not Windows or WSL')
    if os.geteuid() != 0:
        raise ValueError('Run with sudo on native Linux (inspection is read-only by default)')
    source = args.iso.resolve(strict=True)
    device, identity, size = inspect_usb(args.device)
    plan = layout(source, size, args.save_mib)
    with device.open('rb') as stream:
        digest = verify_copy(source, stream)
    print(f'USB: {args.device}\nDevice: {device}\nCapacity: {size/2**30:.2f} GiB')
    print(f'ISO SHA256: {digest}\nNew ext4 save partition: {plan["save_mib"]} MiB, label {LABEL}')
    print('Existing ISO/EFI partitions are retained. Remaining space used for saving WILL BE FORMATTED.')
    print('Saved files and Wi-Fi passwords are UNENCRYPTED. Nothing is written without --apply and confirmation.')
    if not args.apply:
        return
    for tool in ('mke2fs', 'blockdev', 'udevadm'):
        if not shutil.which(tool):
            raise ValueError(f'Missing tool: {tool}')
    phrase = f'CREATE SAVE ON {args.device.name}'
    if input(f'Type exactly: {phrase}\n> ') != phrase:
        raise ValueError('Cancelled; no changes made')
    if inspect_usb(args.device) != (device, identity, size):
        raise ValueError('USB identity changed; no changes made')
    # O_EXCL refuses an in-use block device. It is never opened for writing
    # until all checks and the device-specific interactive confirmation pass.
    fd = os.open(device, os.O_RDWR | os.O_EXCL)
    try:
        with os.fdopen(fd, 'r+b', closefd=False) as stream:
            if verify_copy(source, stream) != digest:
                raise ValueError('ISO changed; no changes made')
            # Save every overwritten metadata range before writing anything.
            # This is a tiny recovery record, not a USB-sized disk image.
            backup = []
            for offset, data in plan['patches']:
                stream.seek(offset)
                backup.append({'offset': offset, 'hex': stream.read(len(data)).hex()})
            with tempfile.NamedTemporaryFile(mode='w', prefix='kestrel-usb-metadata-', suffix='.json',
                                             dir=args.backup_dir, delete=False) as record:
                json.dump({'device': str(args.device), 'iso_sha256': digest, 'ranges': backup}, record)
                record.flush();os.fsync(record.fileno())
                print(f'Metadata backup: {record.name}')
            for offset, data in plan['patches']:
                stream.seek(offset);stream.write(data)
            stream.flush();os.fsync(stream.fileno())
    finally:
        os.close(fd)
    subprocess.run(['blockdev', '--rereadpt', str(device)], check=True)
    subprocess.run(['udevadm', 'settle', '--timeout=15'], check=True)
    if inspect_usb(args.device) != (device, identity, size):
        raise ValueError('USB changed or became mounted; refusing to format')
    sys = pathlib.Path('/sys/class/block')/device.name
    partitions = [p for p in sys.iterdir() if (p/'partition').exists() and (p/'partition').read_text().strip() == '3']
    if len(partitions) != 1:
        raise ValueError('New partition not visible. Stop; do not format another device')
    partition = partitions[0]
    if int((partition/'start').read_text()) != plan['first_sector'] or int((partition/'size').read_text()) != plan['sectors']:
        raise ValueError('New partition boundaries differ; refusing to format')
    with tempfile.TemporaryDirectory(prefix='kestrel-save-seed-') as seed:
        pathlib.Path(seed, 'persistence.conf').write_text('/ union\n')
        subprocess.run(['mke2fs', '-t', 'ext4', '-b', '4096', '-m', '1', '-L', LABEL,
                        '-E', 'nodiscard,lazy_itable_init=0,lazy_journal_init=0',
                        '-d', seed, str(pathlib.Path('/dev')/partition.name)], check=True)
    print('Save partition created. Safely eject, then boot the Rova USB. Check Storage for "Persistent USB".')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--iso', type=pathlib.Path, required=True)
    parser.add_argument('--device', type=pathlib.Path, required=True)
    parser.add_argument('--save-mib', type=int, help='default: all remaining whole MiB')
    parser.add_argument('--backup-dir', type=pathlib.Path, default=pathlib.Path.cwd())
    parser.add_argument('--apply', action='store_true', help='requires interactive confirmation')
    args = parser.parse_args()
    try:
        setup(args)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        parser.exit(1, f'Stopped: {error}\nIf partition metadata was already written, do not retry blindly or format another partition.\n')
