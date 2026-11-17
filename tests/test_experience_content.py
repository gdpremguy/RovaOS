import copy
import importlib.util
import json
import pathlib
import re
import tempfile
import unittest
from html.parser import HTMLParser

ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA = ROOT/'linux/includes.chroot/usr/share/rova'
SPEC = importlib.util.spec_from_file_location('render_welcome', ROOT/'linux/render_welcome.py')
site = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(site)
experience = site.experience


class Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = []
        self.links = []
        self.scripts = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if 'id' in attrs:
            self.ids.append(attrs['id'])
        if tag == 'a' and 'href' in attrs:
            self.links.append(attrs['href'])
        if tag == 'script':
            self.scripts.append(attrs)


class ExperienceContentTests(unittest.TestCase):
    def test_current_guide_is_generated_and_offline(self):
        html = site.render('niri')
        self.assertEqual(html, (DATA/'welcome.html').read_text(encoding='utf-8'))
        self.assertNotRegex(html, r'\{\{[a-z_]+\}\}')
        self.assertNotIn('<script', html)
        self.assertNotIn('https://', html)
        self.assertIn('restart', html.lower())
        self.assertIn('not encrypted', html)
        self.assertIn('not migrated', html)
        for stale in ('old custom kernel', 'not Arch', 'have not been ported', 'persistent USB image', 'ThinkPad', 'v26.'):
            self.assertNotIn(stale, html)

    def test_both_profiles_have_accurate_help_and_actions(self):
        brand, center, shortcuts = experience.load_content(DATA)
        niri = experience.for_profile(center['actions'], 'niri')
        xfce = experience.for_profile(center['actions'], 'xfce')
        self.assertIn('rova-tools', [a['command'][0] for a in niri])
        self.assertNotIn('rova-tools', [a['command'][0] for a in xfce])
        self.assertIn('xfce4-display-settings', [a['command'][0] for a in xfce])
        self.assertNotIn('xfce4-display-settings', [a['command'][0] for a in niri])
        self.assertIn('Super+S', site.render('niri'))
        self.assertNotIn('Super+S</kbd>', site.render('xfce'))
        self.assertNotIn('Niri settings', site.render('xfce'))
        self.assertTrue(brand['control_center_title'])

    def test_shortcut_reference_matches_niri_bindings(self):
        _, _, shortcuts = experience.load_content(DATA)
        config = (ROOT/'linux/niri/config.kdl').read_text()
        for item in experience.for_profile(shortcuts, 'niri'):
            self.assertRegex(config, re.escape(item['binding'])+r'(?:\s|\{)')

    def test_navigation_targets_and_accessibility(self):
        page = Page();page.feed(site.render())
        self.assertEqual(len(page.ids), len(set(page.ids)))
        for link in page.links:
            if link.startswith('#'):
                self.assertIn(link[1:], page.ids)
        self.assertFalse(page.scripts)
        self.assertIn('scope="col"', site.render())
        css = (DATA/'welcome.css').read_text()
        self.assertIn(':focus-visible', css)
        self.assertIn('@media (max-width: 520px)', css)

    def edited_content(self, edit):
        temporary = tempfile.TemporaryDirectory()
        folder = pathlib.Path(temporary.name)
        for path in DATA.glob('*.json'):
            content = json.loads(path.read_text(encoding='utf-8'))
            if path.name == 'control-center.json':
                edit(content)
            (folder/path.name).write_text(json.dumps(content), encoding='utf-8')
        self.addCleanup(temporary.cleanup)
        return folder

    def test_actions_can_be_reordered_renamed_or_disabled_without_python(self):
        def edit(center):
            center['columns'] = 2
            center['actions'].reverse()
            center['actions'][0]['label'] = 'Keep my work'
            center['actions'][1]['enabled'] = False
        directory = self.edited_content(edit)
        _, center, _ = experience.load_content(directory)
        actions = experience.for_profile(center['actions'], 'niri')
        self.assertEqual(center['columns'], 2)
        self.assertEqual(actions[0]['label'], 'Keep my work')
        self.assertNotIn('help', [item['id'] for item in actions])

    def test_commands_are_argument_arrays_not_shell_strings(self):
        directory = self.edited_content(lambda center: center['actions'][0].update(command='echo unsafe; whoami'))
        with self.assertRaisesRegex(ValueError, 'argument arrays'):
            experience.load_content(directory)

    def test_duplicate_action_ids_are_rejected(self):
        directory = self.edited_content(lambda center: center['actions'].append(copy.deepcopy(center['actions'][0])))
        with self.assertRaisesRegex(ValueError, 'duplicate action'):
            experience.load_content(directory)

    def test_invalid_profiles_and_layout_are_rejected(self):
        for edit in (lambda center: center.update(columns=0),
                     lambda center: center['actions'][0].update(profiles=['missing']),
                     lambda center: center['actions'][0].update(enabled='false')):
            with self.subTest(edit=edit):
                directory = self.edited_content(edit)
                with self.assertRaises(ValueError):
                    experience.load_content(directory)

    def test_shared_text_is_escaped_in_html(self):
        with tempfile.TemporaryDirectory() as root:
            directory = pathlib.Path(root)
            for path in DATA.iterdir():
                if path.is_file() and path.suffix in ('.json', '.html'):
                    (directory/path.name).write_text(path.read_text(encoding='utf-8'), encoding='utf-8')
            brand = json.loads((directory/'branding.json').read_text())
            brand['headline'] = '<script>alert("test")</script>'
            (directory/'branding.json').write_text(json.dumps(brand))
            result = site.render(directory=directory)
            self.assertIn('&lt;script&gt;', result)
            self.assertNotIn('<script>', result)

    def test_unknown_template_tokens_fail_instead_of_shipping_placeholders(self):
        with tempfile.TemporaryDirectory() as root:
            directory = pathlib.Path(root)
            for path in DATA.glob('*.json'):
                (directory/path.name).write_text(path.read_text(encoding='utf-8'), encoding='utf-8')
            (directory/'welcome.template.html').write_text('{{missing_token}}')
            with self.assertRaisesRegex(ValueError, 'Unknown welcome template token'):
                site.render(directory=directory)
