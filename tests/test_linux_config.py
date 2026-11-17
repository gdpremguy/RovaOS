import configparser
import json
import pathlib
import shutil
import subprocess
import unittest
import xml.etree.ElementTree as ET

ROOT = pathlib.Path(__file__).resolve().parents[1]
LINUX = ROOT / 'linux'
INCLUDES = LINUX / 'includes.chroot'


class LinuxImageConfigTests(unittest.TestCase):
    def test_real_wireless_browser_and_live_packages(self):
        packages = {line.strip() for line in (LINUX / 'packages.list.chroot').read_text().splitlines()
                    if line.strip() and not line.startswith('#')}
        required = {'linux-image-amd64', 'firmware-iwlwifi', 'network-manager',
                    'network-manager-gnome', 'wpasupplicant', 'firefox-esr',
                    'ca-certificates', 'systemd-timesyncd', 'live-boot', 'live-config',
                    'lightdm', 'xfce4', 'xserver-xorg-input-libinput',
                    'librsvg2-common', 'xfce4-power-manager-plugins'}
        self.assertLessEqual(required, packages)
        self.assertNotIn('openssh-server', packages)
        self.assertFalse(any('installer' in package for package in packages))

    def test_no_installer_or_old_clock_workaround(self):
        configure = (LINUX / 'configure.sh').read_text()
        self.assertIn('--debian-installer false', configure)
        self.assertIn('--binary-images iso-hybrid', configure)
        self.assertIn('non-free-firmware', configure)
        self.assertIn('Australia/Adelaide', configure)
        hook = (LINUX / 'customize.hook.chroot').read_text()
        self.assertNotIn('CLOCK_DEFAULT_CORRECTION', hook)
        self.assertIn('systemd-timesyncd.service', hook)
        self.assertIn('iwlwifi.ko', hook)

    def test_desktop_xml_and_automount_disabled(self):
        for path in INCLUDES.rglob('*.xml'):
            with self.subTest(path=path.name):
                ET.parse(path)
        path = INCLUDES / 'etc/xdg/xfce4/xfconf/xfce-perchannel-xml/thunar-volman.xml'
        props = {p.attrib['name']: p.attrib['value'] for p in ET.parse(path).getroot()}
        self.assertEqual(props['automount-drives'], 'false')
        self.assertEqual(props['automount-media'], 'false')
        panel = ET.parse(INCLUDES / 'etc/xdg/xfce4/xfconf/xfce-perchannel-xml/xfce4-panel.xml')
        names = {p.attrib.get('value') for p in panel.iter('property')}
        self.assertIn('systray', names)
        self.assertIn('clock', names)

    def test_browser_policy_does_not_bypass_tls(self):
        path = INCLUDES / 'usr/lib/firefox-esr/distribution/policies.json'
        policies = json.loads(path.read_text())['policies']
        self.assertTrue(policies['Homepage']['URL'].startswith('file:///usr/share/rova/'))
        self.assertNotIn('Certificates', policies)
        self.assertNotIn('Preferences', policies)
        smoke = (INCLUDES / 'usr/local/libexec/kestrel-smoke-report').read_text()
        self.assertNotIn('--insecure', smoke)
        self.assertNotIn('--no-sandbox', smoke)
        self.assertIn('https://example.com/', smoke)
        self.assertIn('runuser -u kestrel', smoke)

    def test_only_opt_in_test_vm_runs_smoke(self):
        unit = (INCLUDES / 'etc/systemd/system/kestrel-smoke-report.service').read_text()
        self.assertIn('ExecCondition=/usr/local/libexec/kestrel-smoke-enabled', unit)
        condition = (INCLUDES / 'usr/local/libexec/kestrel-smoke-enabled').read_text()
        self.assertIn('KestrelOS-Test', condition)
        self.assertIn('KestrelOS-Network-Smoke', condition)

    def test_autostart_and_desktop_entries(self):
        for path in INCLUDES.rglob('*.desktop'):
            parser = configparser.ConfigParser(interpolation=None)
            parser.read(path)
            self.assertIn('Desktop Entry', parser)
            self.assertIn('Exec', parser['Desktop Entry'])
        self.assertEqual(len(list((INCLUDES / 'etc/xdg/autostart').glob('*nm*'))), 1)

    @unittest.skipUnless(shutil.which('bash'), 'requires bash')
    def test_shell_syntax(self):
        scripts = [LINUX / 'build.sh', LINUX / 'configure.sh', LINUX / 'customize.hook.chroot',
                   INCLUDES / 'usr/local/bin/kestrel-network-report',
                   INCLUDES / 'usr/local/libexec/kestrel-smoke-enabled',
                   INCLUDES / 'usr/local/libexec/kestrel-smoke-report',
                   INCLUDES / 'usr/local/libexec/kestrel-desktop-init',
                   INCLUDES / 'usr/local/libexec/kestrel-persistence-smoke',
                   INCLUDES / 'usr/local/libexec/kestrel-persistence-smoke-enabled',
                   INCLUDES / 'usr/local/bin/kestrel-apps']
        for script in scripts:
            with self.subTest(script=script.name):
                subprocess.run(['bash', '-n'], input=script.read_bytes(), check=True)
