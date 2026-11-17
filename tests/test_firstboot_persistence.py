import pathlib
import os
import stat
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'linux'))
import firstboot_persistence as firstboot
from setup_usb_persistence import mount_is_boot_iso
from test_linux_persistence import fixture


class FirstBootPersistenceTests(unittest.TestCase):
    def partition_wait(self, *, present=True, start=2048, sectors=4096,
                       mode=stat.S_IFBLK, identity=None, node_present=True):
        device = pathlib.Path('/dev/sdb')
        partition = mock.MagicMock()
        partition.name = 'sdb3'
        values = {'partition': '3', 'start': str(start), 'size': str(sectors), 'dev': '8:19'}
        partition.__truediv__.side_effect = lambda key: mock.Mock(
            exists=mock.Mock(return_value=True), read_text=mock.Mock(return_value=values[key]))
        sysnode = mock.MagicMock()
        sysnode.iterdir.return_value = [partition] if present else []
        sysroot = mock.MagicMock()
        sysroot.__truediv__.return_value = sysnode
        node = mock.Mock()
        node.exists.return_value = node_present
        node.stat.return_value = mock.Mock(st_mode=mode, st_rdev=os.makedev(8, 19) if identity is None else identity)
        devroot = mock.MagicMock()
        devroot.__truediv__.return_value = node
        with mock.patch.object(firstboot.pathlib, 'Path', side_effect=lambda path: {
                '/sys/class/block': sysroot, '/dev': devroot}[path]):
            result = firstboot.wait_for_partition(device, {'first_sector': 2048, 'sectors': 4096}, timeout=0)
        self.assertIs(result, node)

    @unittest.skipUnless(hasattr(os, 'makedev'), 'requires Unix device numbers')
    def test_partition_wait_accepts_matching_kernel_block_device(self):
        self.partition_wait()

    @unittest.skipUnless(hasattr(os, 'makedev'), 'requires Unix device numbers')
    def test_partition_wait_times_out_without_partition_or_device(self):
        for options in ({'present': False}, {'node_present': False}):
            with self.subTest(options=options), self.assertRaisesRegex(ValueError, 'timeout'):
                self.partition_wait(**options)

    @unittest.skipUnless(hasattr(os, 'makedev'), 'requires Unix device numbers')
    def test_partition_wait_refuses_wrong_geometry(self):
        for options in ({'start': 4096}, {'sectors': 8192}):
            with self.subTest(options=options), self.assertRaisesRegex(ValueError, 'boundaries'):
                self.partition_wait(**options)

    @unittest.skipUnless(hasattr(os, 'makedev'), 'requires Unix device numbers')
    def test_partition_wait_refuses_wrong_device_identity_or_type(self):
        for options in ({'identity': os.makedev(8, 20)}, {'mode': stat.S_IFREG}):
            with self.subTest(options=options), self.assertRaisesRegex(ValueError, 'identity'):
                self.partition_wait(**options)

    def test_only_readonly_boot_iso_mount_is_exempted(self):
        valid = '1 0 8:17 / /run/live/medium ro,relatime - iso9660 /dev/sdb1 ro'.split()
        medium = pathlib.PurePosixPath('/run/live/medium')
        self.assertTrue(mount_is_boot_iso(valid, medium))
        self.assertFalse(mount_is_boot_iso(valid, None))
        for field, value in ((4, '/media/other'), (5, 'rw,relatime'), (7, 'ext4')):
            changed = valid.copy();changed[field] = value
            self.assertFalse(mount_is_boot_iso(changed, medium))

    def test_confirmation_is_bound_to_current_boot_usb_and_layout(self):
        with tempfile.TemporaryDirectory() as directory:
            source = pathlib.Path(directory)/'boot.iso';fixture(source)
            found = (pathlib.Path('/run/live/medium'), pathlib.Path('/dev/disk/by-id/usb-test'), source, 123, 4*1024**3)
            with mock.patch.object(firstboot, 'find_boot_usb', return_value=found):
                *_, description, fingerprint = firstboot.plan_boot()
                self.assertEqual(description['save_mib'], 2048)
                with mock.patch.object(firstboot.subprocess, 'run') as run:
                    with self.assertRaisesRegex(ValueError, 'changed since confirmation'):
                        firstboot.apply_boot('wrong-confirmation')
                    run.assert_not_called()
                *_, _, again = firstboot.plan_boot()
                self.assertEqual(fingerprint, again)
            changed = (*found[:-1], 3*1024**3)
            with mock.patch.object(firstboot, 'find_boot_usb', return_value=changed):
                *_, _, other = firstboot.plan_boot()
                self.assertNotEqual(other, fingerprint)

    def test_backend_never_accepts_arbitrary_device_argument(self):
        source = (ROOT/'linux/firstboot_persistence.py').read_text()
        self.assertNotIn("add_argument('--device'", source)
        self.assertIn("'--add', '--nr', '3'", source)
        self.assertNotIn("['blockdev', '--rereadpt'", source)
