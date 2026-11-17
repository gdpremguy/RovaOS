import argparse
import contextlib
import importlib.util
import io
import pathlib
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'linux'))
import setup_usb_persistence as usb
from test_linux_persistence import fixture


class USBPersistenceSetupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.iso = pathlib.Path(self.temp.name)/'source.iso'
        fixture(self.iso)

    def test_plan_preserves_boot_code_and_places_save_after_iso(self):
        before = self.iso.read_bytes()
        plan = usb.layout(self.iso, 256*usb.MIB, 64)
        self.assertEqual(self.iso.read_bytes(), before)
        self.assertEqual(plan['first_sector'], usb.MIB//512)
        self.assertEqual(plan['sectors'], 64*usb.MIB//512)
        patches = dict(plan['patches'])
        self.assertEqual(patches[0][:446], before[:446])
        self.assertEqual(patches[0][446:478], before[446:478])
        header = bytearray(patches[512])
        crc = struct.unpack_from('<I', header, 16)[0]
        struct.pack_into('<I', header, 16, 0)
        self.assertEqual(zlib.crc32(header[:92]), crc)
        entries = patches[1024]
        self.assertEqual(entries[256:272], usb.LINUX_FS)
        self.assertEqual(entries[128:144], usb.EFI_FS)
        self.assertEqual(entries[:128], before[1024:1152])
        self.assertEqual(struct.unpack_from('<I', header, 88)[0], zlib.crc32(entries))
        self.assertLess((plan['first_sector']+plan['sectors'])*512, 256*usb.MIB)

    def test_default_consumes_remaining_space_not_fixed_two_gib(self):
        plan = usb.layout(self.iso, 256*usb.MIB)
        self.assertEqual(plan['save_mib'], 254)

    def test_too_small_large_or_negative_save_is_rejected(self):
        for disk, save in ((32*usb.MIB, None), (256*usb.MIB, 300), (256*usb.MIB, -1), (256*usb.MIB, 0)):
            with self.subTest(disk=disk, save=save), self.assertRaises(ValueError):
                usb.layout(self.iso, disk, save)

    def test_existing_extra_partition_and_bad_gpt_rejected(self):
        data = bytearray(self.iso.read_bytes());data[540] ^= 1
        self.iso.write_bytes(data)
        with self.assertRaises(ValueError):
            usb.layout(self.iso, 256*usb.MIB)
        fixture(self.iso)
        data = bytearray(self.iso.read_bytes());data[478] = 1
        self.iso.write_bytes(data)
        with self.assertRaises(ValueError):
            usb.layout(self.iso, 256*usb.MIB)

    def test_requires_exact_flashed_bytes(self):
        before = self.iso.read_bytes()
        usb.verify_copy(self.iso, io.BytesIO(before+b'free disk space'))
        with self.assertRaises(ValueError):
            usb.verify_copy(self.iso, io.BytesIO(before[:-1]+b'x'))

    @unittest.skipUnless((ROOT/'kestrelos-linux.iso').is_file(), 'built ISO not available')
    def test_actual_delivered_iso_accepts_append_only_layout(self):
        source = ROOT/'kestrelos-linux.iso'
        plan = usb.layout(source, usb.align(source.stat().st_size)+256*usb.MIB, 64)
        self.assertGreaterEqual(plan['first_sector']*512, source.stat().st_size)
        self.assertEqual(plan['save_mib'], 64)

    @unittest.skipUnless(shutil.which('mke2fs') and shutil.which('debugfs'), 'requires e2fsprogs')
    def test_real_ext4_seed_in_file_only_no_physical_disk(self):
        disk = pathlib.Path(self.temp.name)/'synthetic-usb.img'
        seed = pathlib.Path(self.temp.name)/'seed';seed.mkdir()
        (seed/'persistence.conf').write_text('/ union\n')
        disk_bytes = 128*usb.MIB
        plan = usb.layout(self.iso, disk_bytes, 64)
        with disk.open('wb') as stream:
            stream.write(self.iso.read_bytes());stream.truncate(disk_bytes)
        subprocess.run(['mke2fs', '-q', '-t', 'ext4', '-F', '-b', '4096', '-L', usb.LABEL,
                        '-E', f'offset={plan["first_sector"]*512},nodiscard',
                        '-d', str(seed), str(disk), str(64*usb.MIB//4096)], check=True)
        with disk.open('r+b') as stream:
            stream.truncate(disk_bytes)
            for offset, data in plan['patches']:
                stream.seek(offset);stream.write(data)
            stream.seek(0)
            header, entries = usb.read_gpt(stream)
            first, last = struct.unpack_from('<QQ', entries, 256+32)
            self.assertEqual(first, plan['first_sector'])
            self.assertEqual(last-first+1, plan['sectors'])
            stream.seek(first*512)
            save = pathlib.Path(self.temp.name)/'save.ext4'
            with save.open('wb') as target:
                for _ in range(64):
                    target.write(stream.read(usb.MIB))
        contents = subprocess.check_output(['debugfs', '-R', 'cat /persistence.conf', str(save)], text=True)
        self.assertEqual(contents, '/ union\n')

    def test_device_selection_rejects_internal_paths_and_partitions(self):
        with mock.patch.object(usb.platform, 'system', return_value='Linux'), mock.patch.object(usb.platform, 'release', return_value='native'):
            for path in ('/dev/sda', '/dev/nvme0n1', '/dev/disk/by-id/ata-internal', '/dev/disk/by-id/usb-stick-part1'):
                with self.subTest(path=path), self.assertRaises(ValueError):
                    usb.inspect_usb(path)

    def test_wsl_is_explicitly_rejected(self):
        with mock.patch.object(usb.platform, 'system', return_value='Linux'), mock.patch.object(usb.platform, 'release', return_value='microsoft-standard-WSL2'):
            with self.assertRaises(ValueError):
                usb.inspect_usb('/dev/disk/by-id/usb-test')

    def test_inspection_mode_never_opens_for_writing_or_formats(self):
        args = argparse.Namespace(iso=self.iso, device=pathlib.Path('/dev/disk/by-id/usb-test'), save_mib=64, apply=False)
        with mock.patch.object(usb.platform, 'system', return_value='Linux'), mock.patch.object(usb.platform, 'release', return_value='native'), mock.patch.object(usb.os, 'geteuid', return_value=0, create=True), mock.patch.object(usb, 'inspect_usb', return_value=(self.iso, 123, 256*usb.MIB)), mock.patch.object(usb.os, 'open') as opened, mock.patch.object(usb.subprocess, 'run') as run, contextlib.redirect_stdout(io.StringIO()):
            usb.setup(args)
        opened.assert_not_called()
        run.assert_not_called()
