"""Prepare persistence on a disposable virtual USB from an ISO, then cold-boot twice.

No physical disks and no delivered persistent .img needed. All writable disk
files live in a temporary Linux cache directory and are removed on completion.
"""
import argparse
import hashlib
import json
import pathlib
import shutil
import subprocess
import tempfile
import uuid
from persistence_smoke import boot_phase

ROOT = pathlib.Path(__file__).resolve().parents[1]


def check(iso, firmware=None, desktop='niri'):
    iso = iso.resolve()
    output = ROOT/'build';output.mkdir(exist_ok=True)
    cache = pathlib.Path.home()/'.cache/kestrel-linux';cache.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='firstboot-usb-test-', dir=cache) as work:
        raw = pathlib.Path(work)/'flashed-iso.raw'
        shutil.copyfile(iso, raw)
        with raw.open('r+b') as stream:
            stream.truncate(max(4*1024**3, iso.stat().st_size+256*1024**2))
        disk = pathlib.Path(work)/'test.qcow2'
        subprocess.run(['qemu-img', 'create', '-f', 'qcow2', '-F', 'raw', '-b', str(raw), str(disk)], check=True)
        token = str(uuid.uuid4())
        for phase in ('prepare', 'write', 'read'):
            boot_phase(disk, phase, token, output, firmware, timeout=600, desktop=desktop)
    with iso.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    mode = 'uefi' if firmware else 'bios'
    (output/f'linux-firstboot-{mode}.json').write_text(json.dumps({
        'iso_sha256': digest, 'boot_usb_partition_created': True,
        'cold_boot_persistence': True, 'physical_disk_tested': False}, indent=2)+'\n')
    print('ISO-only first-boot USB saving: prepare + cold write + cold read: PASS')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--iso', type=pathlib.Path, default=ROOT/'rovaos.iso')
    parser.add_argument('--firmware', type=pathlib.Path)
    parser.add_argument('--desktop', choices=('xfce', 'niri'), default='niri')
    args = parser.parse_args();check(args.iso, args.firmware, args.desktop)
