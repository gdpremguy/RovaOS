import hashlib
from html.parser import HTMLParser
import importlib.util
import json
import pathlib
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('rova_website', ROOT/'website/build.py')
website = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(website)


class Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = []
        self.links = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if 'id' in attrs:
            self.ids.append(attrs['id'])
        if tag == 'a' and 'href' in attrs:
            self.links.append(attrs['href'])


class WebsiteTests(unittest.TestCase):
    def fixture(self, directory):
        image = directory/'rovaos.iso'
        content = bytearray(34816)
        content[32768:32775] = b'\x01CD001\x01'
        content[32808:32840] = b'ROVA_LINUX'.ljust(32, b' ')
        image.write_bytes(content)
        digest = hashlib.sha256(content).hexdigest()
        pathlib.Path(str(image)+'.sha256').write_text(f'{digest}  rovaos.iso\n')
        return image, digest

    def test_package_downloads_match_real_image(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = pathlib.Path(temporary)
            image, digest = self.fixture(directory)
            output = directory/'site'
            manifest = website.package(image, output)
            self.assertEqual((output/'downloads/rovaos.iso').read_bytes(), image.read_bytes())
            self.assertEqual(manifest['iso_sha256'], digest)
            page = (output/'index.html').read_text(encoding='utf-8')
            self.assertNotIn('{{', page)
            self.assertIn(digest, page)
            self.assertIn('downloads/rovaos.iso', page)
            self.assertEqual(json.loads((output/'release.json').read_text())['iso_bytes'], image.stat().st_size)
            parser = Page()
            parser.feed(page)
            self.assertEqual(len(parser.ids), len(set(parser.ids)))
            for link in parser.links:
                if link.startswith('#') and len(link) > 1:
                    self.assertIn(link[1:], parser.ids)
                elif not link.startswith(('https:', '#')):
                    self.assertTrue((output/link).is_file(), link)

    def test_external_iso_host_does_not_copy_large_image(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = pathlib.Path(temporary)
            image, _ = self.fixture(directory)
            output = directory/'site'
            url = 'https://downloads.example.org/rovaos.iso?download=1&edition=niri'
            website.package(image, output, url)
            self.assertFalse((output/'downloads/rovaos.iso').exists())
            self.assertIn('download=1&amp;edition=niri', (output/'index.html').read_text(encoding='utf-8'))
            self.assertTrue((output/'downloads/rovaos.iso.sha256').is_file())

    def test_invalid_digest_is_rejected_before_publication(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = pathlib.Path(temporary)
            image, _ = self.fixture(directory)
            pathlib.Path(str(image)+'.sha256').write_text('0'*64+'  rovaos.iso\n')
            with self.assertRaisesRegex(ValueError, 'checksum'):
                website.package(image, directory/'site')
            self.assertFalse((directory/'site').exists())

    def test_unrelated_iso_and_unsafe_urls_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = pathlib.Path(temporary)
            image, _ = self.fixture(directory)
            for url in ('javascript:alert(1)', 'http://example.org/file.iso',
                        'https://user:secret@example.org/file.iso', 'https://example.org/#fragment'):
                with self.subTest(url=url), self.assertRaises(ValueError):
                    website.package(image, directory/'site', url)
            image.write_bytes(b'not an ISO')
            with self.assertRaisesRegex(ValueError, 'RovaOS Linux ISO'):
                website.package(image, directory/'site')

    def test_unrelated_output_and_sources_are_protected(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = pathlib.Path(temporary)
            image, _ = self.fixture(directory)
            output = directory/'site'
            output.mkdir()
            (output/'my-file').write_text('keep')
            for destination in (output, ROOT, ROOT/'website', image.parent):
                with self.subTest(output=destination), self.assertRaises(ValueError):
                    website.package(image, destination)
            self.assertEqual((output/'my-file').read_text(), 'keep')

    def test_portability_claims_include_limits_and_saving_requirements(self):
        page = (ROOT/'website/index.html').read_text(encoding='utf-8')
        for text in ('Wherever you go.', 'compatible PCs', 'temporary session',
                     'Persistent USB', 'unencrypted', 'Flashing erases',
                     'No internal-drive installer', 'Apple Silicon', 'Community preview'):
            self.assertIn(text, page)
        self.assertNotIn('runs on any computer', page)
        self.assertNotIn('without leaving a trace', page)
        self.assertIn('prefers-reduced-motion', (ROOT/'website/styles.css').read_text())
        self.assertIn('Skip to content', page)


if __name__ == '__main__':
    unittest.main()
