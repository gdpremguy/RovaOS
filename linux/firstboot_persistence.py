"""Privileged first-boot backend. Can target ONLY this session's ISO boot USB.

No user-supplied device paths, ISO paths or shell commands are accepted.
Partition creation is append-only; the currently mounted ISO is never formatted.
"""
import argparse
import hashlib
import json
import os
import pathlib
import stat
import struct
import subprocess
import sys
import tempfile
import time

from setup_usb_persistence import inspect_usb, layout, read_gpt, SECTOR, MIB, LABEL


def find_boot_usb():
    media = {p.resolve() for p in (pathlib.Path('/run/live/medium'), pathlib.Path('/lib/live/mount/medium')) if p.exists()}
    matches = []
    for line in pathlib.Path('/proc/self/mountinfo').read_text().splitlines():
        fields = line.split();separator = fields.index('-')
        if pathlib.Path(fields[4]) in media and fields[separator+1] == 'iso9660' and 'ro' in fields[5].split(','):
            matches.append((pathlib.Path(fields[4]), fields[2]))
    if len(matches) != 1:
        raise ValueError('Cannot identify one read-only Rova boot medium. Saving setup is unavailable.')
    medium, dev_id = matches[0]
    node = (pathlib.Path('/sys/dev/block')/dev_id).resolve(strict=True)
    whole = node.parent.name if (node/'partition').exists() else node.name
    device = pathlib.Path('/dev')/whole
    info = device.stat()
    if not stat.S_ISBLK(info.st_mode):
        raise ValueError('Boot medium is not a physical USB disk')
    candidates = [p for p in pathlib.Path('/dev/disk/by-id').glob('usb-*')
                  if '-part' not in p.name and p.resolve() == device]
    if not candidates:
        raise ValueError('Boot medium is not a supported removable USB. Internal disks and virtual CD/DVD are refused.')
    selected = sorted(candidates)[0]
    checked, identity, size = inspect_usb(selected, readonly_boot_mount=medium)
    if checked != device:
        raise ValueError('Boot USB identity mismatch')
    return medium, selected, device, identity, size


def plan_boot():
    medium, selected, device, identity, size = find_boot_usb()
    # The original hybrid ISO's secondary GPT describes its exact byte extent.
    with device.open('rb') as stream:
        header, entries = read_gpt(stream)
        iso_bytes = (struct.unpack_from('<Q', header, 32)[0]+1)*SECTOR
        stream.seek(0);prefix = stream.read(32768)
    if iso_bytes > size or iso_bytes < MIB:
        raise ValueError('Invalid boot ISO extent')
    plan = layout(device, size, boot_source_bytes=iso_bytes)
    # Keep first-boot formatting bounded and leave larger sticks' extra space
    # untouched. This does not allocate a multi-GB download or image file.
    if plan['save_mib'] > 2048:
        plan = layout(device, size, 2048, boot_source_bytes=iso_bytes)
    description = {'usb': selected.name, 'device': str(device), 'capacity_bytes': size,
                   'save_mib': plan['save_mib'], 'first_sector': plan['first_sector'],
                   'identity': identity, 'prefix_sha256': hashlib.sha256(prefix).hexdigest()}
    fingerprint = hashlib.sha256(json.dumps(description, sort_keys=True).encode()).hexdigest()
    return medium, selected, device, identity, size, plan, description, fingerprint


def wait_for_partition(device, plan, timeout=60):
    """Wait for this partition only, not unrelated (or lock-blocked) udev jobs."""
    sysnode = pathlib.Path('/sys/class/block')/device.name
    deadline = time.monotonic()+timeout
    while True:
        partitions = [p for p in sysnode.iterdir() if (p/'partition').exists() and (p/'partition').read_text().strip() == '3']
        if len(partitions) > 1:
            raise ValueError('Ambiguous save partition; refusing to format')
        if partitions:
            partition = partitions[0]
            if int((partition/'start').read_text()) != plan['first_sector'] or int((partition/'size').read_text()) != plan['sectors']:
                raise ValueError('New save partition has unexpected boundaries; refusing to format')
            node = pathlib.Path('/dev')/partition.name
            if node.exists():
                info = node.stat()
                identity = (partition/'dev').read_text().strip()
                if not stat.S_ISBLK(info.st_mode) or f'{os.major(info.st_rdev)}:{os.minor(info.st_rdev)}' != identity:
                    raise ValueError('Save device does not match kernel partition identity; refusing to format')
                return node
        if time.monotonic() >= deadline:
            raise ValueError('Save partition did not appear before timeout; no filesystem formatted')
        time.sleep(.5)


def apply_boot(expected):
    medium, selected, device, identity, size, plan, description, fingerprint = plan_boot()
    if expected != fingerprint:
        raise ValueError('USB or partition layout changed since confirmation; nothing was written')
    for program in ('partx', 'mke2fs'):
        if not __import__('shutil').which(program):
            raise ValueError(f'Missing required program: {program}')
    # The boot partition is deliberately mounted read-only. Do not request an
    # exclusive whole-disk claim or reread/remove its active kernel partitions.
    import fcntl
    with device.open('r+b', buffering=0) as stream:
        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if inspect_usb(selected, readonly_boot_mount=medium) != (device, identity, size):
            raise ValueError('USB changed before metadata write')
        stream.seek(0)
        if hashlib.sha256(stream.read(32768)).hexdigest() != description['prefix_sha256']:
            raise ValueError('Partition metadata changed before write')
        record = {'usb': description, 'ranges': []}
        for offset, data in plan['patches']:
            stream.seek(offset)
            record['ranges'].append({'offset': offset, 'hex': stream.read(len(data)).hex()})
        backup = pathlib.Path('/run/kestrel-usb-partition-backup.json')
        with backup.open('x') as target:
            json.dump(record, target);target.flush();os.fsync(target.fileno())
        backup.chmod(0o600)
        for offset, data in plan['patches']:
            stream.seek(offset);stream.write(data)
        os.fsync(stream.fileno())
        # Add ONLY the new kernel partition. --rereadpt would fail because the
        # boot ISO is in use; deleting its existing partition mappings is unsafe.
        subprocess.run(['partx', '--add', '--nr', '3', str(device)], check=True, stdout=sys.stderr, stderr=sys.stderr)
        partition = wait_for_partition(device, plan)
        if inspect_usb(selected, readonly_boot_mount=medium) != (device, identity, size):
            raise ValueError('USB changed or new partition became mounted; refusing to format')
        with tempfile.TemporaryDirectory(prefix='kestrel-save-seed-', dir='/run') as seed:
            pathlib.Path(seed, 'persistence.conf').write_text('/ union\n')
            pathlib.Path(seed, 'kestrel-partition-backup.json').write_text(json.dumps(record))
            subprocess.run(['mke2fs', '-q', '-t', 'ext4', '-b', '4096', '-m', '1', '-L', LABEL,
                            '-E', 'nodiscard,lazy_itable_init=0,lazy_journal_init=0', '-d', seed,
                            str(partition)], check=True, stdout=sys.stderr, stderr=sys.stderr)
        os.fsync(stream.fileno())
    return {'created': True, 'reboot_required': True,
            'message': 'USB saving is ready. Restart to activate it. Current-session files are NOT migrated; copy important files elsewhere before restarting.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply-confirmed', metavar='PLAN_SHA256')
    args = parser.parse_args()
    try:
        if os.geteuid() != 0:
            raise ValueError('Root privilege is required')
        if args.apply_confirmed:
            result = apply_boot(args.apply_confirmed)
        else:
            *_, description, fingerprint = plan_boot()
            result = dict(description, confirmation=fingerprint)
        print(json.dumps(result))
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(json.dumps({'error': str(error), 'message': 'Setup stopped. Do not unplug while writes may be in progress. If metadata was written, keep /run/kestrel-usb-partition-backup.json for recovery.'}))
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
