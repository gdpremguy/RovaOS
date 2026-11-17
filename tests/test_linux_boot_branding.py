import importlib.util
import pathlib
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('brand_boot', ROOT/'linux/brand_boot.py')
brand = importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(brand)


class BootBrandingTests(unittest.TestCase):
    def test_branding_retains_kernel_initrd_and_recovery_entry(self):
        with tempfile.TemporaryDirectory() as directory:
            binary = pathlib.Path(directory)
            for folder in ('boot/grub/live-theme', 'isolinux'):
                (binary/folder).mkdir(parents=True)
            content = ('menuentry "Live system (amd64)" {\nlinux /live/vmlinuz persistence-label=kestrel-rw\ninitrd /live/initrd.img\n}\n'
                       'menuentry "Live system (amd64 fail-safe mode)" {}\n')
            (binary/'boot/grub/grub.cfg').write_text(content)
            (binary/'isolinux/live.cfg').write_text(content)
            (binary/'isolinux/menu.cfg').write_text('menu title Debian\ninclude live.cfg\n')
            (binary/'isolinux/isolinux.cfg').write_text('timeout 0\n')
            (binary/'boot/grub/config.cfg').write_text('set default=0\ninsmod play\nplay 960 440\n')
            (binary/'boot/grub/live-theme/theme.txt').write_text('title-text: ""\n')
            brand.brand(binary)
            result = (binary/'boot/grub/grub.cfg').read_text()
            self.assertIn('RovaOS', result)
            self.assertIn('troubleshooting', result)
            self.assertIn('linux /live/vmlinuz persistence-label=kestrel-rw', result)
            self.assertIn('initrd /live/initrd.img', result)
            self.assertTrue((binary/'isolinux/splash.png').read_bytes().startswith(b'\x89PNG'))
            self.assertNotIn('play ', (binary/'boot/grub/config.cfg').read_text())
            before = result;brand.brand(binary)
            self.assertEqual((binary/'boot/grub/grub.cfg').read_text(), before)
