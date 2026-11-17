import pathlib
import importlib.util
import json
import os
import tarfile
import tempfile
import unittest
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('kestrel_desktop', ROOT/'linux/includes.chroot/usr/local/lib/kestrel/desktop.py')
desktop = importlib.util.module_from_spec(spec)
spec.loader.exec_module(desktop)
spec_boot = importlib.util.spec_from_file_location('kestrel_brand', ROOT/'linux/brand_boot.py')
brand = importlib.util.module_from_spec(spec_boot)
spec_boot.loader.exec_module(brand)


class NiriDesktopTests(unittest.TestCase):
    def test_new_columns_use_available_width(self):
        config = (ROOT / 'linux/niri/config.kdl').read_text()
        self.assertIn('default-column-width { proportion 1.0; }', config)

    def test_systemd_components_are_not_spawned_twice(self):
        config = (ROOT / 'linux/niri/config.kdl').read_text()
        for component in ('waybar', 'mako'):
            self.assertNotIn(f'spawn-at-startup "{component}"', config)

    def window(self, identity, workspace=1, column=1, floating=False):
        return {'id': identity, 'workspace_id': workspace, 'is_floating': floating,
                'layout': {'pos_in_scrolling_layout': [column, 1]}}

    def test_dynamic_tiling_and_close(self):
        one = self.window(1)
        two = self.window(2, column=2)
        self.assertEqual(desktop.tile_plan([one]), {1: 100})
        self.assertEqual(desktop.tile_plan([one, two]), {1: 50, 2: 50})
        self.assertEqual(desktop.tile_plan([two]), {2: 100})

    def test_dialogs_workspaces_and_stacked_windows(self):
        windows = [self.window(1), self.window(2, floating=True), self.window(3),
                   self.window(4, workspace=2)]
        self.assertEqual(desktop.tile_plan(windows), {1: 100, 4: 100})

    def test_status_and_space_warning(self):
        self.assertEqual(desktop.status_module({'persistent': False, 'description': 'temporary'})['class'], 'temporary')
        value = {'persistent': True, 'description': 'saved', 'free_bytes': 2**30, 'total_bytes': 2**31}
        self.assertEqual(desktop.status_module(value)['class'], 'persistent')
        value['free_bytes'] = 2**20
        self.assertEqual(desktop.status_module(value)['class'], 'low-space')

    def test_backup_refuses_home_and_same_filesystem(self):
        with tempfile.TemporaryDirectory() as root:
            home = pathlib.Path(root)/'home';home.mkdir()
            dest = pathlib.Path(root)/'dest';dest.mkdir()
            for destination in (home, home/'nested', dest):
                with self.assertRaises(ValueError):
                    desktop.backup_home(home, destination)

    @unittest.skipUnless(pathlib.Path('/dev/shm').is_dir(), 'requires two disposable Linux filesystems')
    def test_backup_contents_and_symlink_safety(self):
        with tempfile.TemporaryDirectory(dir='/var/tmp') as root, tempfile.TemporaryDirectory(dir='/dev/shm') as target:
            home = pathlib.Path(root)/'home';home.mkdir()
            if home.stat().st_dev == pathlib.Path(target).stat().st_dev:
                self.skipTest('temporary paths use the same filesystem')
            (home/'notes').write_text('hello')
            (home/'.cache').mkdir();(home/'.cache/ignored').write_text('cache')
            outside = pathlib.Path(root)/'secret';outside.write_text('not in backup')
            (home/'link').symlink_to(outside)
            archive = desktop.backup_home(home, target)
            with tarfile.open(archive) as result:
                self.assertEqual(set(result.getnames()), {'home/notes', 'home/link'})
                self.assertTrue(result.getmember('home/link').issym())
                self.assertEqual(result.extractfile('home/notes').read(), b'hello')
            self.assertFalse(list(pathlib.Path(target).glob('*.partial')))

    def test_reset_preserves_old_config_and_uses_clean_defaults(self):
        with tempfile.TemporaryDirectory() as root:
            home = pathlib.Path(root)/'home'
            config = home/'.config/niri';config.mkdir(parents=True)
            (config/'config.kdl').write_text('old')
            (config/'outputs.kdl').write_text('broken output')
            defaults = pathlib.Path(root)/'defaults';defaults.mkdir()
            (defaults/'config.kdl').write_text('clean')
            saved = desktop.reset_desktop(home, defaults)
            self.assertEqual((saved/'outputs.kdl').read_text(), 'broken output')
            self.assertEqual((config/'config.kdl').read_text(), 'clean')
            self.assertFalse((config/'outputs.kdl').exists())

    def test_recovery_boot_payloads(self):
        arguments = 'boot=live username=kestrel persistence persistence-label=kestrel-rw persistence-media=removable-usb'
        grub = 'menuentry "Kestrel" {\n linux /live/kernel '+arguments+' findiso=${iso_path}\n initrd /live/initrd\n}\n'
        result = brand.recovery_entries(grub, True)
        self.assertIn('findiso=${iso_path} kestrel.recovery', result)
        self.assertEqual(result.count('initrd /live/initrd'), 3)
        console = result.split('safe graphics console')[1]
        self.assertNotIn('persistence', console)
        self.assertIn('nomodeset systemd.unit=multi-user.target', console)
        self.assertEqual(brand.recovery_entries(result, True), result)
        bios = 'label live\n menu label Kestrel\n menu default\n linux /live/kernel\n initrd /live/initrd\n append '+arguments+'\n'
        result = brand.recovery_entries(bios, False)
        self.assertEqual(result.count('menu default'), 1)
        self.assertNotIn('persistence', result.split('label kestrel-console')[1])

    def test_waybar_storage_module(self):
        config = json.loads((ROOT/'linux/niri/waybar.json').read_text())
        self.assertIn('custom/saving', config['modules-right'])
        self.assertEqual(config['custom/saving']['return-type'], 'json')

    def test_waybar_sections_preserve_all_controls(self):
        config = json.loads((ROOT/'linux/niri/waybar.json').read_text())
        self.assertEqual(config['group/navigation']['modules'],
                         ['custom/kestrel', 'niri/workspaces'])
        self.assertEqual(config['group/system']['modules'],
                         ['network', 'pulseaudio', 'battery'])
        self.assertIn('group/navigation', config['modules-left'])
        self.assertIn('group/system', config['modules-right'])
        self.assertIn('niri/window', config['modules-left'])
        self.assertEqual(config['modules-center'], ['clock'])
        for module in ('custom/saving', 'tray', 'custom/settings'):
            self.assertIn(module, config['modules-right'])
        self.assertEqual(config['custom/settings']['on-click'], 'rova-tools quick')
        self.assertEqual(config['custom/settings']['on-click-right'], 'rova-settings')

    def test_waybar_shadow_has_space_inside_layer_surface(self):
        style = (ROOT/'linux/niri/waybar.css').read_text()
        self.assertIn('window#waybar > box', style)
        self.assertIn('margin-bottom: 10px', style)
        self.assertIn('box-shadow:', style)
        self.assertIn('#custom-saving.low-space', style)

    def test_autotile_events_do_not_loop_or_steal_focus(self):
        first, second = self.window(1), self.window(2, column=2)
        events = [
            {'WindowsChanged': {'windows': [first]}},
            {'WindowOpenedOrChanged': {'window': second}},
            {'WindowLayoutsChanged': {'changes': [[1, {**first['layout'], 'tile_size': [400, 600]}]]}},
            {'WindowClosed': {'id': 2}},
        ]
        process = mock.Mock(stdout=[json.dumps(event) for event in events])
        with mock.patch.object(desktop.subprocess, 'Popen', return_value=process), mock.patch.object(desktop.subprocess, 'run') as run:
            desktop.autotile()
        commands = [call.args[0] for call in run.call_args_list]
        self.assertEqual([command[-1] for command in commands], ['100.000000%', '50.000000%', '50.000000%', '100.000000%'])
        self.assertTrue(all(command[3] == 'set-window-width' for command in commands))
        process.terminate.assert_called_once()

    def test_negative_monitor_coordinates_are_not_cli_flags(self):
        source = (ROOT/'linux/includes.chroot/usr/local/bin/kestrel-display-settings').read_text()
        self.assertIn("('position', 'set', '--', str(x), str(y))", source)

    def test_branding_hook_uses_actual_binary_working_directory(self):
        with tempfile.TemporaryDirectory() as root:
            binary = pathlib.Path(root)/'binary'
            config = pathlib.Path(root)/'config/includes.chroot/etc/kestrel'
            config.mkdir(parents=True);(config/'desktop').write_text('niri\n')
            grub = binary/'boot/grub/grub.cfg';grub.parent.mkdir(parents=True)
            grub.write_text('menuentry "Live system (amd64)" {\n linux /live/kernel boot=live persistence\n initrd /live/initrd\n}\n')
            brand.brand(binary)
            self.assertIn('RovaOS', grub.read_text())
            self.assertIn('kestrel.recovery', grub.read_text())
            self.assertTrue((binary/'boot/grub/splash.png').exists())

    def test_root_helpers_are_hardened_against_windows_source_modes(self):
        source = (ROOT/'linux/customize.hook.chroot').read_text()
        self.assertIn('chown -R root:root /usr/local', source)
        self.assertIn("find /usr/local -type d -exec chmod 755 '{}' +", source)
        self.assertIn("find /usr/local -type f -exec chmod go-w '{}' +", source)

    def test_view_alignment_restores_original_focus(self):
        first, second = self.window(1), self.window(2, column=2)
        second['is_focused'] = True
        self.assertEqual(desktop.view_alignment([first, second]), [1, 2])
        second['is_floating'] = True
        self.assertEqual(desktop.view_alignment([first, second]), [])
