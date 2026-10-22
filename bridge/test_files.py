import hashlib
import io
import os
from pathlib import Path
import tempfile
import unittest
import uuid

from files import FileBrowser, FileError, version


class BrowserTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.root = Path(self.folder.name)
        self.home = self.root / 'home'
        self.home.mkdir()
        self.browser = FileBrowser(self.root / 'state', roots={'home': {'name': 'Fixture', 'path': str(self.home)}}, max_bytes=1024)

    def tearDown(self):
        self.folder.cleanup()

    def upload(self, name, data, expected='*', identifier=None, digest=None):
        return self.browser.upload('home', name, io.BytesIO(data), len(data), identifier or str(uuid.uuid4()), digest or hashlib.sha256(data).hexdigest(), expected)

    def test_upload_download_and_receipt(self):
        result = self.upload('a.txt', b'hello')
        self.assertEqual((self.home / 'a.txt').read_bytes(), b'hello')
        self.assertEqual(self.browser.receipt(result['uploadID']), result)
        with self.browser.download('home', 'a.txt', result['version']) as data:
            self.assertEqual(data['stream'].read(), b'hello')
            self.assertEqual(data['sha256'], hashlib.sha256(b'hello').hexdigest())

    def test_requires_explicit_version_to_replace(self):
        first = self.upload('a.txt', b'original')
        with self.assertRaises(FileError) as error:
            self.upload('a.txt', b'replacement')
        self.assertEqual(error.exception.status, 409)
        self.assertEqual(error.exception.body['existing']['version'], first['version'])
        self.assertEqual((self.home / 'a.txt').read_bytes(), b'original')
        self.upload('a.txt', b'replacement', first['version'])
        self.assertEqual((self.home / 'a.txt').read_bytes(), b'replacement')

    def test_stale_version_never_replaces(self):
        first = self.upload('a.txt', b'original')
        (self.home / 'a.txt').write_bytes(b'changed outside app')
        with self.assertRaises(FileError):
            self.upload('a.txt', b'new', first['version'])
        self.assertEqual((self.home / 'a.txt').read_bytes(), b'changed outside app')

    def test_parent_and_final_symlinks_blocked(self):
        outside = self.root / 'outside'
        outside.mkdir()
        (outside / 'private.txt').write_bytes(b'private')
        (self.home / 'link').symlink_to(outside, target_is_directory=True)
        (self.home / 'file-link').symlink_to(outside / 'private.txt')
        with self.assertRaises(FileError):
            self.browser.listing('home', 'link')
        with self.assertRaises(FileError):
            with self.browser.download('home', 'file-link'):
                self.fail('Must not yield symlink content')
        with self.assertRaises(FileError):
            self.upload('link/new.txt', b'bad')
        with self.assertRaises(FileError):
            self.upload('file-link', b'bad')
        self.assertEqual((outside / 'private.txt').read_bytes(), b'private')

    def test_traversal_hidden_and_credentials_blocked(self):
        for name in ['../outside.txt', '/etc/passwd', '.ssh/id_rsa', 'x/../a.txt', 'auth.json', 'private.key', 'operator-credentials.json', 'a\\b', 'bad\x00name']:
            with self.subTest(name=name), self.assertRaises(FileError):
                self.upload(name, b'bad')
        with self.assertRaises(FileError):
            self.browser.listing('unknown-root', '')

    def test_incomplete_and_bad_checksum_do_not_commit(self):
        with self.assertRaises(FileError):
            self.browser.upload('home', 'new.txt', io.BytesIO(b'x'), 2, str(uuid.uuid4()), hashlib.sha256(b'xx').hexdigest(), '*')
        with self.assertRaises(FileError):
            self.upload('new.txt', b'hello', digest='0' * 64)
        self.assertFalse((self.home / 'new.txt').exists())
        self.assertFalse(list(self.home.glob('.pocket-upload-*')))

    def test_download_limits_and_special_files(self):
        (self.home / 'large').write_bytes(b'x' * 1025)
        os.mkfifo(self.home / 'pipe')
        for name in ['large', 'pipe']:
            with self.assertRaises(FileError):
                with self.browser.download('home', name):
                    self.fail('Must not download special/oversized file')

    def test_replay_does_not_write_twice(self):
        identifier = str(uuid.uuid4())
        first = self.upload('a.txt', b'one', identifier=identifier)
        self.assertEqual(self.upload('a.txt', b'one', identifier=identifier), first)
        with self.assertRaises(FileError):
            self.upload('b.txt', b'one', identifier=identifier)
        with self.assertRaises(FileError):
            self.upload('a.txt', b'two', identifier=identifier)

    def test_listing_and_context_stay_in_root(self):
        (self.home / 'Documents').mkdir()
        (self.home / '.env').write_text('secret')
        self.upload('a.txt', b'hello')
        result = self.browser.listing('home', '')
        self.assertEqual([entry['name'] for entry in result['entries']], ['Documents', 'a.txt'])
        self.assertIsNone(result['parent'])
        self.assertEqual(self.browser.context(str(self.home / 'Documents')), {'root': 'home', 'path': 'Documents'})
        with self.assertRaises(FileError):
            self.browser.context('/etc')

    def test_empty_file_and_plain_permissions(self):
        self.upload('empty.txt', b'')
        self.assertEqual((self.home / 'empty.txt').stat().st_mode & 0o777, 0o600)

    def test_existing_concurrent_temporary_is_not_removed(self):
        identifier = str(uuid.uuid4())
        temporary = self.home / ('.pocket-upload-' + identifier)
        temporary.write_bytes(b'other transfer')
        with self.assertRaises(FileError):
            self.upload('target.txt', b'new', identifier=identifier)
        self.assertEqual(temporary.read_bytes(), b'other transfer')

    def test_destination_change_during_upload_is_preserved(self):
        first = self.upload('target.txt', b'original')
        target = self.home / 'target.txt'
        class Changed(io.BytesIO):
            def read(inner, size=-1):
                target.write_bytes(b'desktop update')
                return super().read(size)
        with self.assertRaises(FileError):
            self.browser.upload('home', 'target.txt', Changed(b'new'), 3, str(uuid.uuid4()), hashlib.sha256(b'new').hexdigest(), first['version'])
        self.assertEqual(target.read_bytes(), b'desktop update')
