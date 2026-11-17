"""Create a NEW regular-file USB image; never partition or format a real disk.

Preserves the hybrid ISO's BIOS code and EFI payload, relocates GPT backup
metadata, and appends an ext4 save partition populated without loop mounts.
"""
import argparse
import hashlib
import json
import os
import pathlib
import shutil
import stat
import struct
import subprocess
import tempfile
import uuid
import zlib

SECTOR = 512
MIB = 1024**2
GIB = 1024**3
LABEL = 'kestrel-rw'
# The label is a disk-format identifier, retained to recognise existing saves.
ISO_VOLUMES = (b'ROVA_LINUX', b'KESTREL_LINUX')
LINUX_FS = uuid.UUID('0fc63daf-8483-4772-8e79-3d69d8477de4').bytes_le
EFI_FS = uuid.UUID('c12a7328-f81f-11d2-ba4b-00a0c93ec93b').bytes_le
ROOT = pathlib.Path(__file__).resolve().parents[1]


def align(value, multiple=MIB):
    return (value+multiple-1)//multiple*multiple


def read_gpt(stream):
    stream.seek(SECTOR)
    header = bytearray(stream.read(SECTOR))
    if len(header) != SECTOR or header[:8] != b'EFI PART':
        raise ValueError('A GPT hybrid RovaOS ISO is required')
    size, expected = struct.unpack_from('<II', header, 12)
    if not 92 <= size <= SECTOR:
        raise ValueError('Invalid GPT header size')
    struct.pack_into('<I', header, 16, 0)
    if zlib.crc32(header[:size]) != expected:
        raise ValueError('GPT header checksum failed')
    table_lba, count, entry_size, crc = struct.unpack_from('<QIII', header, 72)
    if not 3 <= count <= 256 or entry_size != 128 or table_lba < 2 or table_lba*SECTOR+count*entry_size > 32768:
        raise ValueError('Unsupported GPT array layout')
    stream.seek(table_lba*SECTOR)
    entries = bytearray(stream.read(count*entry_size))
    if len(entries) != count*entry_size or zlib.crc32(entries) != crc:
        raise ValueError('GPT partition-array checksum failed')
    return header, entries


def header_bytes(template, current, backup, last_usable, table_lba, disk_guid, table_crc):
    result = bytearray(template)
    struct.pack_into('<I', result, 16, 0)
    struct.pack_into('<QQ', result, 24, current, backup)
    struct.pack_into('<Q', result, 48, last_usable)
    result[56:72] = disk_guid
    struct.pack_into('<Q', result, 72, table_lba)
    struct.pack_into('<I', result, 88, table_crc)
    size = struct.unpack_from('<I', result, 12)[0]
    struct.pack_into('<I', result, 16, zlib.crc32(result[:size]))
    return result


def create_image(source, output, persistence_bytes=2*GIB):
    source, output = pathlib.Path(source).resolve(), pathlib.Path(output).absolute()
    if not stat.S_ISREG(source.stat().st_mode):
        raise ValueError('Source must be a regular ISO file, never a device')
    if output.exists() or output.is_symlink() or any(pathlib.Path(str(output)+suffix).exists() for suffix in ('.partial','.json','.sha256')):
        raise FileExistsError('Refusing to overwrite an image that may contain saved data; choose a new filename')
    if str(output).startswith('/dev/'):
        raise ValueError('Physical device output is forbidden')
    if persistence_bytes < 64*MIB or persistence_bytes % MIB:
        raise ValueError('Persistence must be at least 64 MiB and MiB-aligned')
    if not shutil.which('mke2fs'):
        raise RuntimeError('mke2fs is required (Linux e2fsprogs package)')
    with source.open('rb') as stream:
        source_prefix=stream.read(32768);stream.seek(0)
        mbr = bytearray(stream.read(SECTOR))
        header, entries = read_gpt(stream)
        stream.seek(16*2048)
        pvd = stream.read(2048)
        if pvd[:7] != b'\x01CD001\x01' or pvd[40:72].strip() not in ISO_VOLUMES:
            raise ValueError('Only recognised RovaOS or compatible legacy live media is accepted')
        if mbr[510:512] != b'\x55\xaa' or any(mbr[478:494]):
            raise ValueError('Unexpected MBR, or partition slot 3 is already occupied')
        if entries[256:272] != bytes(16):
            raise ValueError('GPT partition slot 3 is already occupied')
    with source.open('rb') as stream:
        hasher = hashlib.sha256();found_label=False;found_scope=False;tail=b''
        while chunk := stream.read(4*MIB):
            hasher.update(chunk);scan=tail+chunk
            found_label |= b'persistence-label=kestrel-rw' in scan
            found_scope |= b'persistence-media=removable-usb' in scan
            tail=scan[-128:]
        digest=hasher.hexdigest()
    if not found_label or not found_scope:
        raise ValueError('ISO lacks the RovaOS removable-USB persistence boot options; rebuild it first')
    first = align(source.stat().st_size)//SECTOR
    blocks = persistence_bytes//SECTOR
    table_sectors = align(len(entries), SECTOR)//SECTOR
    total_bytes = align((first+blocks+table_sectors+1)*SECTOR)
    total_sectors = total_bytes//SECTOR
    if total_sectors > 0xffffffff:
        raise ValueError('Image exceeds the supported hybrid MBR size')
    backup_lba = total_sectors-1
    backup_table = backup_lba-table_sectors
    disk_guid, partition_guid, fs_guid = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    entry = bytearray(128)
    entry[:16] = LINUX_FS;entry[16:32] = partition_guid.bytes_le
    struct.pack_into('<QQQ', entry, 32, first, first+blocks-1, 0)
    name = 'Rova persistent settings'.encode('utf-16le')
    entry[56:56+len(name)] = name
    entries[256:384] = entry
    # The ISO's EFI payload is also described explicitly as an ESP for USB boot.
    if struct.unpack_from('<I', mbr, 446+16+8)[0] != struct.unpack_from('<Q', entries, 128+32)[0]:
        raise ValueError('EFI MBR/GPT start sectors differ')
    entries[128:144] = EFI_FS
    mbr[478:494] = struct.pack('<B3sB3sII', 0, b'\xfe\xff\xff', 0x83, b'\xfe\xff\xff', first, blocks)
    crc = zlib.crc32(entries)
    table_lba = struct.unpack_from('<Q', header, 72)[0]
    primary = header_bytes(header, 1, backup_lba, backup_table-1, table_lba, disk_guid.bytes_le, crc)
    secondary = header_bytes(header, backup_lba, 1, backup_table-1, backup_table, disk_guid.bytes_le, crc)
    partial = pathlib.Path(str(output)+'.partial')
    metadata = {'iso_sha256': digest, 'image_bytes': total_bytes, 'persistence_bytes': persistence_bytes,
                'persistence_start_sector': first, 'persistence_label': LABEL,
                'filesystem_uuid': str(fs_guid), 'disk_guid': str(disk_guid),
                'encrypted': False, 'minimum_usb_gb': (total_bytes+10**9-1)//10**9}
    owns_partial = False
    try:
        with partial.open('xb') as target:
            owns_partial = True
            with source.open('rb') as stream:
                copied=hashlib.sha256();first_chunk=True
                while chunk := stream.read(4*MIB):
                    if first_chunk and chunk[:32768] != source_prefix:
                        raise RuntimeError('Source ISO changed during image creation; no image published')
                    first_chunk=False;copied.update(chunk);target.write(chunk)
                if copied.hexdigest()!=digest:
                    raise RuntimeError('Source ISO changed during image creation; no image published')
                target.truncate(total_bytes)
        with tempfile.TemporaryDirectory(prefix='.kestrel-save-seed-', dir=output.parent) as seed:
            seed = pathlib.Path(seed)
            (seed/'persistence.conf').write_text('/ union\n')
            (seed/'ROVA-SAVING.txt').write_text(
                'RovaOS persistent USB. Full root overlay; settings, files, Wi-Fi profiles and browser data survive reboot.\n'
                'UNENCRYPTED: anyone with this USB can read saved data and credentials. Shut down before unplugging.\n')
            subprocess.run(['mke2fs', '-q', '-t', 'ext4', '-F', '-b', '4096', '-m', '1',
                            '-L', LABEL, '-U', str(fs_guid), '-E',
                            f'offset={first*SECTOR},nodiscard,lazy_itable_init=0,lazy_journal_init=0',
                            '-d', str(seed), str(partial), str(persistence_bytes//4096)], check=True)
        # Write partition metadata AFTER mke2fs, which may resize regular files.
        with partial.open('r+b') as target:
            target.truncate(total_bytes)
            target.seek(0);target.write(mbr)
            target.seek(SECTOR);target.write(primary)
            target.seek(table_lba*SECTOR);target.write(entries)
            target.seek(backup_table*SECTOR);target.write(entries)
            target.seek(backup_lba*SECTOR);target.write(secondary)
            target.flush();os.fsync(target.fileno())
        # Link creation refuses a concurrent existing destination; no saved image
        # can be silently replaced. Both paths reside in the same filesystem.
        os.link(partial, output)
        partial.unlink()
    except BaseException:
        if owns_partial:
            partial.unlink(missing_ok=True)
        raise
    with output.open('rb') as stream:
        metadata['image_sha256'] = hashlib.file_digest(stream, 'sha256').hexdigest()
    pathlib.Path(str(output)+'.json').write_text(json.dumps(metadata, indent=2)+'\n')
    pathlib.Path(str(output)+'.sha256').write_text(metadata['image_sha256']+'  '+output.name+'\n')
    print(f'Created {output}: {persistence_bytes/GIB:g} GiB persistent storage, no physical drive written.')
    return metadata


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--iso', type=pathlib.Path, default=ROOT/'rovaos.iso')
    parser.add_argument('--output', type=pathlib.Path, default=ROOT/'rovaos-persistent.img')
    parser.add_argument('--persistence-gib', type=int, default=2)
    args = parser.parse_args()
    create_image(args.iso, args.output, args.persistence_gib*GIB)
