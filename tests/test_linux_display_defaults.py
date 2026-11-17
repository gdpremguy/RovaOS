import importlib.machinery
import importlib.util
import pathlib
import tempfile
import unittest
import xml.etree.ElementTree as ET
from unittest import mock
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[1]
INCLUDES = ROOT/'linux/includes.chroot'
loader = importlib.machinery.SourceFileLoader('display_default', str(INCLUDES/'usr/local/libexec/kestrel-display-default'))
spec = importlib.util.spec_from_loader(loader.name, loader)
display = importlib.util.module_from_spec(spec)
loader.exec_module(display)


class DisplayDefaultTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.env = mock.patch.dict(display.os.environ, XDG_CONFIG_HOME=self.temp.name)
        self.env.start();self.addCleanup(self.env.stop)
        self.sleep = mock.patch.object(display.time, 'sleep')
        self.sleep.start();self.addCleanup(self.sleep.stop)

    def test_whole_desktop_inverse_scale_and_framebuffer(self):
        with mock.patch.object(display, 'run', return_value=mock.Mock(stdout='eDP-1 connected primary 1920x1200+0+0 (normal)\n')) as run:
            display.main()
        run.assert_any_call('xrandr', '--output', 'eDP-1', '--scale', '0.8x0.8', '--fb', '1536x960')

    def test_user_profile_is_never_overridden(self):
        profile = pathlib.Path(self.temp.name)/'xfce4/xfconf/xfce-perchannel-xml/displays.xml'
        profile.parent.mkdir(parents=True);profile.write_text('<channel/>')
        with mock.patch.object(display, 'run') as run:
            display.main()
        run.assert_not_called()

    def test_small_screen_and_multi_monitor_are_left_alone(self):
        for text in ('eDP-1 connected 800x600+0+0\n',
                     'eDP-1 connected 1920x1200+0+0\nHDMI-1 connected 1920x1080+1920+0\n',
                     'eDP-1 disconnected\n'):
            with self.subTest(text=text), mock.patch.object(display, 'run', return_value=mock.Mock(stdout=text)) as run:
                display.main()
                self.assertEqual(run.call_count, 1)

    def test_rejected_transform_restores_native_scale(self):
        with mock.patch.object(display, 'run', side_effect=[mock.Mock(stdout='eDP-1 connected 1920x1200+0+0\n'),
                               subprocess.CalledProcessError(1, 'xrandr'), mock.Mock()]) as run:
            with self.assertRaises(subprocess.CalledProcessError):
                display.main()
        run.assert_called_with('xrandr', '--output', 'eDP-1', '--scale', '1x1', '--fb', '1920x1200')

    def test_compositor_disabled_without_dpi_override(self):
        directory = INCLUDES/'etc/xdg/xfce4/xfconf/xfce-perchannel-xml'
        props = {p.get('name'): p.get('value') for p in ET.parse(directory/'xfwm4.xml').iter('property')}
        self.assertEqual(props['use_compositing'], 'false')
        self.assertNotIn('DPI', (directory/'xsettings.xml').read_text())

    def test_adelaide_current_offset_and_explicit_ntp(self):
        from datetime import datetime, timedelta
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
        config = (INCLUDES/'etc/systemd/timesyncd.conf.d/50-kestrel.conf').read_text()
        self.assertIn('NTP=0.au.pool.ntp.org', config)
        try:
            ZoneInfo('Australia/Adelaide')
        except ZoneInfoNotFoundError:
            self.skipTest('requires system timezone database or tzdata package')
        self.assertEqual(datetime(2026, 11, 14, tzinfo=ZoneInfo('Australia/Adelaide')).utcoffset(), timedelta(hours=10, minutes=30))
