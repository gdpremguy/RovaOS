import importlib.util
import json
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
LINUX = ROOT/'linux'
INCLUDES = LINUX/'includes.chroot'
sys.path.insert(0, str(LINUX))
import setup_usb_persistence as usb
from test_linux_persistence import fixture


class RovaBrandingTests(unittest.TestCase):
    def test_public_product_identity(self):
        brand = json.loads((INCLUDES/'usr/share/rova/branding.json').read_text())
        self.assertEqual(brand['product_name'], 'RovaOS')
        self.assertEqual(brand['control_center_title'], 'Rova Settings')
        release = (INCLUDES/'etc/os-release').read_text()
        self.assertIn('PRETTY_NAME="RovaOS"', release)
        self.assertIn('ID_LIKE=debian', release)
        self.assertNotIn('Kestrel', release)

    def test_rendered_guide_and_desktop_labels_have_no_old_brand(self):
        paths = [INCLUDES/'usr/share/rova/welcome.html', LINUX/'niri/fuzzel.ini', LINUX/'niri/waybar.json']
        for path in paths:
            text = path.read_text()
            self.assertNotIn('Kestrel', text, str(path))
            self.assertNotIn('K E S T R E L', text, str(path))
        self.assertIn('R  /  Rova', paths[-1].read_text())

    def test_public_commands_preserve_existing_launchers(self):
        hook = (LINUX/'customize.hook.chroot').read_text()
        self.assertIn('rova-${name#kestrel-}', hook)
        self.assertIn('ln -sfn kestrel-control-center /usr/local/bin/rova-settings', hook)
        self.assertTrue((INCLUDES/'usr/local/bin/kestrel-control-center').is_file())

    def test_new_outputs_cannot_overwrite_preserved_images(self):
        build = (LINUX/'build.sh').read_text()
        refresh = (LINUX/'refresh_niri.sh').read_text()
        self.assertIn('output=rovaos-xfce.iso', build)
        self.assertIn('output=rovaos.iso', build)
        self.assertIn('$repo_dir/rovaos.iso', refresh)
        make = (ROOT/'Makefile').read_text()
        self.assertIn('ROVA_DESKTOP=niri bash linux/build.sh', make)
        self.assertNotIn('rovaos-legacy', make)

    def test_refresh_includes_policy_and_current_persistence_backend(self):
        refresh = (LINUX/'refresh_niri.sh').read_text()
        self.assertIn('for helper in firstboot_persistence.py setup_usb_persistence.py make_persistent.py;', refresh)
        self.assertIn('chroot "$root" /bin/sh -c \'mkdir -p /usr/lib/firefox-esr/distribution && install -m644', refresh)

    def test_both_media_ids_keep_save_label_and_safety_checks(self):
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory)/'source.iso'
            for volume in (b'ROVA_LINUX', b'KESTREL_LINUX'):
                fixture(path)
                before = bytearray(path.read_bytes())
                before[32768+40:32768+72] = volume.ljust(32, b' ')
                path.write_bytes(before)
                plan = usb.layout(path, 128*usb.MIB, 64)
                self.assertEqual(plan['save_mib'], 64)
                self.assertEqual(path.read_bytes(), before)
                self.assertEqual(usb.LABEL, 'kestrel-rw')
                # Renaming the product must not weaken the removable-media guard.
                before[40000:40128] = b' '*128
                path.write_bytes(before)
                with self.assertRaises(ValueError):
                    usb.layout(path, 128*usb.MIB, 64)
            fixture(path)
            data = bytearray(path.read_bytes())
            data[32768+40:32768+72] = b'UNRELATED'.ljust(32, b' ')
            path.write_bytes(data)
            with self.assertRaises(ValueError):
                usb.layout(path, 128*usb.MIB, 64)
