import importlib.util
import ast
import json
import os
import pathlib
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
INCLUDES = ROOT/'linux/includes.chroot'
SPEC = importlib.util.spec_from_file_location('kestrel_session', INCLUDES/'usr/local/lib/kestrel/session.py')
session = importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(session)


@unittest.skipIf(os.name == 'nt', 'Linux filesystem/session helpers')
class KestrelDesktopTests(unittest.TestCase):
    def test_ram_overlay_is_never_claimed_as_persistent(self):
        outputs=[json.dumps({'filesystems':[{'options':'rw,upperdir=/run/live/overlay/rw'}]}),
                 json.dumps({'filesystems':[{'source':'tmpfs','fstype':'tmpfs','options':'rw'}]})]
        with mock.patch.object(session.os,'geteuid',return_value=0), mock.patch.object(session.subprocess,'check_output',side_effect=outputs):
            self.assertFalse(session.session_status()['persistent'])

    def test_only_writable_block_backed_upper_layer_is_persistent(self):
        outputs=[json.dumps({'filesystems':[{'options':'rw,upperdir=/run/live/overlay/rw'}]}),
                 json.dumps({'filesystems':[{'source':'/dev/sdb3[/rw]','fstype':'ext4','options':'rw,relatime'}]})]
        with mock.patch.object(session.os,'geteuid',return_value=0), mock.patch.object(session.subprocess,'check_output',side_effect=outputs):
            state=session.session_status()
        self.assertTrue(state['persistent']);self.assertGreater(state['free_bytes'],0)

    def test_failed_status_check_does_not_report_saved(self):
        with mock.patch.object(session.os,'geteuid',return_value=0), mock.patch.object(session.subprocess,'check_output',side_effect=OSError('missing')):
            self.assertFalse(session.session_status()['persistent'])

    @unittest.skipUnless(shutil.which('bash'), 'requires bash')
    def test_first_login_setup_never_overwrites_existing_preferences(self):
        with tempfile.TemporaryDirectory() as directory:
            home=pathlib.Path(directory);marker=home/'.config/kestrel/desktop-v2.ready'
            marker.parent.mkdir(parents=True);marker.write_text('customised user session\n')
            env=dict(os.environ,HOME=str(home))
            subprocess.run(['bash',str(INCLUDES/'usr/local/libexec/kestrel-desktop-init')],env=env,check=True)
            self.assertEqual(marker.read_text(),'customised user session\n')

    def test_persistence_search_is_restricted_to_named_removable_usb_filesystem(self):
        config=(ROOT/'linux/configure.sh').read_text()
        for option in ('persistence-label=kestrel-rw','persistence-storage=filesystem','persistence-media=removable-usb'):
            self.assertIn(option,config)
        self.assertNotIn('swap=true',config)

    def test_control_center_and_session_tools_parse_as_python(self):
        for name in ('kestrel-control-center','kestrel-session-status'):
            ast.parse((INCLUDES/'usr/local/bin'/name).read_text())
