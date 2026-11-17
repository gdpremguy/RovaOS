import pathlib
import json
import struct
import unittest
import xml.etree.ElementTree as ET

ROOT = pathlib.Path(__file__).resolve().parents[1]
INCLUDES = ROOT/'linux/includes.chroot'
CONFIG = INCLUDES/'etc/xdg/xfce4/xfconf/xfce-perchannel-xml'


class VisualIdentityTests(unittest.TestCase):
    def test_horizon_identity_and_original_wallpaper_are_packaged(self):
        brand = json.loads((INCLUDES/'usr/share/rova/branding.json').read_text())
        self.assertEqual(brand['desktop_name'], 'Horizon')
        self.assertIn('Name=Rova Horizon',
                      (INCLUDES/'usr/share/themes/Rova-Summit/index.theme').read_text())
        assets = ROOT/'assets/wallpapers'
        png = (assets/'rova-horizon.png').read_bytes()
        self.assertEqual(png[:8], b'\x89PNG\r\n\x1a\n')
        self.assertEqual(struct.unpack('>II', png[16:24]), (3840, 2160))
        ET.parse(assets/'rova-horizon.svg')
        self.assertIn('no third-party', (assets/'HORIZON-NOTICE.txt').read_text())
        for script in ('build.sh', 'refresh_niri.sh'):
            text = (ROOT/'linux'/script).read_text()
            for asset in ('rova-horizon.png', 'rova-horizon.svg', 'HORIZON-NOTICE.txt'):
                self.assertIn(asset, text)

    def test_horizon_default_preserves_custom_wallpaper_priority(self):
        default = '/usr/share/backgrounds/rova/rova-horizon.png'
        helper = (INCLUDES/'usr/local/libexec/kestrel-wallpaper').read_text()
        self.assertIn("if not image.is_file():", helper)
        self.assertIn(".local/share/kestrel/wallpaper.png", helper)
        for path in ('usr/local/libexec/kestrel-wallpaper',
                     'usr/local/libexec/kestrel-desktop-init',
                     'usr/local/bin/kestrel-tools',
                     'etc/xdg/xfce4/xfconf/xfce-perchannel-xml/xfce4-desktop.xml'):
            self.assertIn(default, (INCLUDES/path).read_text(encoding='utf-8'))

    def test_theme_selected_by_defaults_and_first_login(self):
        self.assertIn('Rova-Summit', (CONFIG/'xsettings.xml').read_text())
        self.assertIn('string Rova-Summit', (INCLUDES/'usr/local/libexec/kestrel-desktop-init').read_text())
        theme = INCLUDES/'usr/share/themes/Rova-Summit'
        self.assertTrue((theme/'index.theme').is_file())
        self.assertIn('Arc-Dark/gtk-3.0/gtk.css', (theme/'gtk-3.0/gtk.css').read_text())
        self.assertIn('#64c6c1', (theme/'gtk-3.0/gtk.css').read_text())

    def test_dock_and_status_panel_plugins_exist(self):
        panel = ET.parse(CONFIG/'xfce4-panel.xml').getroot()
        panels = panel.find("property[@name='panels']")
        plugins = panel.find("property[@name='plugins']")
        self.assertEqual([v.get('value') for v in panels.findall('value')], ['1', '2'])
        for desktop_panel in panels.findall('property'):
            ids = desktop_panel.find("property[@name='plugin-ids']")
            for value in ids:
                self.assertIsNotNone(plugins.find(f"property[@name='plugin-{value.get('value')}']"))

    def test_control_center_can_scroll_at_fractional_scaling(self):
        source = (INCLUDES/'usr/local/bin/kestrel-control-center').read_text()
        self.assertIn('Gtk.ScrolledWindow()', source)
        self.assertIn('Your space. Your pace.', (INCLUDES/'usr/share/rova/branding.json').read_text())
        self.assertIn('load_content()', source)
        self.assertIn("screen.get_height()-80", source)
