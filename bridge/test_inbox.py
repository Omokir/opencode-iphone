import hashlib
import io
from pathlib import Path
import tempfile
import unittest
import uuid
from unittest.mock import patch
from files import FileError
from inbox import PhoneInbox


class InboxTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.home = Path(self.temp.name) / 'home'
        self.home.mkdir()
        self.inbox = PhoneInbox(Path(self.temp.name) / 'state', self.home)

    def tearDown(self):
        self.temp.cleanup()

    def send(self, data=b'fixture', name='image.png', identifier=None):
        identifier = identifier or str(uuid.uuid4())
        path = self.inbox.prefix + identifier + '-' + name
        result = self.inbox.upload(path, io.BytesIO(data), len(data), identifier, hashlib.sha256(data).hexdigest())
        return path, identifier, result

    def test_prepare_is_idempotent_and_preserves_existing(self):
        self.assertEqual(self.inbox.prepare()['path'], 'Downloads/Iphone 11 Omoki')
        folder = self.home / self.inbox.prefix
        (folder / 'existing.txt').write_text('keep')
        self.inbox.prepare()
        self.assertEqual((folder / 'existing.txt').read_text(), 'keep')

    def test_same_names_preserved_and_actual_bytes_verified(self):
        self.inbox.prepare()
        first, one, receipt = self.send(b'one')
        second, two, _ = self.send(b'two')
        self.assertNotEqual(first, second)
        self.assertEqual((self.home / first).read_bytes(), b'one')
        self.assertEqual((self.home / second).read_bytes(), b'two')
        self.assertEqual(self.inbox.verify(first, one)['sha256'], receipt['sha256'])
        (self.home / first).write_bytes(b'desktop change')
        self.assertNotEqual(self.inbox.verify(first, one)['sha256'], receipt['sha256'])

    def test_verify_does_not_trust_stale_receipt(self):
        self.inbox.prepare()
        path, identifier, _ = self.send()
        (self.home / path).unlink()
        with self.assertRaises(FileError) as error:
            self.inbox.verify(path, identifier)
        self.assertEqual(error.exception.status, 404)

    def test_no_overwrite_on_replay_after_destination_changed(self):
        self.inbox.prepare()
        path, identifier, _ = self.send()
        (self.home / path).write_bytes(b'changed')
        with self.assertRaises(FileError):
            self.send(identifier=identifier)
        self.assertEqual((self.home / path).read_bytes(), b'changed')

    def test_escape_and_symlink_rejected(self):
        identifier = str(uuid.uuid4())
        for path in ['elsewhere.txt', self.inbox.prefix + identifier + '-a/other', self.inbox.prefix + identifier + '-../other']:
            with self.assertRaises(FileError):
                self.inbox.verify(path, identifier)
        outside = Path(self.temp.name) / 'outside'
        outside.mkdir()
        (self.home / 'Downloads').symlink_to(outside)
        with self.assertRaises(FileError):
            self.inbox.prepare()
        self.assertEqual(list(outside.iterdir()), [])

    def test_incomplete_upload_never_creates_destination(self):
        self.inbox.prepare()
        identifier = str(uuid.uuid4())
        path = self.inbox.prefix + identifier + '-a.txt'
        with self.assertRaises(FileError):
            self.inbox.upload(path, io.BytesIO(b'x'), 2, identifier, hashlib.sha256(b'xx').hexdigest())
        self.assertFalse((self.home / path).exists())

    def test_inbox_has_no_64_mib_ceiling(self):
        self.inbox.prepare()
        identifier = str(uuid.uuid4())
        path = self.inbox.prefix + identifier + '-large.bin'
        size = 65 * 1024 * 1024
        with tempfile.TemporaryFile() as source:
            source.truncate(size)
            digest = hashlib.sha256()
            while chunk := source.read(1024 * 1024):
                digest.update(chunk)
            source.seek(0)
            self.inbox.upload(path, source, size, identifier, digest.hexdigest())
        verified = self.inbox.verify(path, identifier)
        self.assertEqual(verified['size'], size)
        self.assertEqual(verified['sha256'], digest.hexdigest())

    def test_destination_replacement_during_verify_is_rejected(self):
        self.inbox.prepare()
        path, identifier, _ = self.send()
        from inbox import os
        read = os.read
        replaced = False
        def swap(fd, length):
            nonlocal replaced
            data = read(fd, length)
            if not replaced:
                replaced = True
                replacement = self.home / 'replacement'
                replacement.write_bytes(b'other')
                replacement.replace(self.home / path)
            return data
        with patch('inbox.os.read', side_effect=swap), self.assertRaises(FileError):
            self.inbox.verify(path, identifier)
