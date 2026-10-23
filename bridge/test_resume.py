import hashlib
import tempfile
import unittest
import uuid
from pathlib import Path
from files import FileError
from inbox import PhoneInbox
from resume import ResumableInbox


class ResumeTests(unittest.TestCase):
    def test_restart_resume_replay_and_no_clobber(self):
        with tempfile.TemporaryDirectory() as folder:
            home = Path(folder); inbox = PhoneInbox(home / 'state', home=home); inbox.prepare()
            identifier = str(uuid.uuid4()); path = inbox.prefix + identifier + '-notes.txt'
            data = b'firstsecond'; digest = hashlib.sha256(data).hexdigest()
            resume = ResumableInbox(inbox)
            self.assertEqual(resume.progress(path, identifier, len(data), digest)['offset'], 0)
            self.assertEqual(resume.append(path, identifier, len(data), digest, 0, b'first', hashlib.sha256(b'first').hexdigest())['offset'], 5)
            resume = ResumableInbox(inbox)
            self.assertEqual(resume.progress(path, identifier, len(data), digest)['offset'], 5)
            self.assertEqual(resume.append(path, identifier, len(data), digest, 0, b'first', hashlib.sha256(b'first').hexdigest())['offset'], 5)
            with self.assertRaises(FileError): resume.commit(path, identifier, len(data), digest)
            with self.assertRaises(FileError): resume.append(path, identifier, len(data), digest, 0, b'other', hashlib.sha256(b'other').hexdigest())
            resume.append(path, identifier, len(data), digest, 5, b'second', hashlib.sha256(b'second').hexdigest())
            resume.commit(path, identifier, len(data), digest)
            self.assertEqual((home / path).read_bytes(), data)
            self.assertEqual(resume.commit(path, identifier, len(data), digest)['sha256'], digest)
            (home / path).write_bytes(b'desktop change')
            with self.assertRaises(FileError): resume.commit(path, identifier, len(data), digest)

    def test_checksum_and_metadata_fail_closed(self):
        with tempfile.TemporaryDirectory() as folder:
            home = Path(folder); inbox = PhoneInbox(home / 'state', home=home); inbox.prepare(); resume = ResumableInbox(inbox)
            identifier = str(uuid.uuid4()); path = inbox.prefix + identifier + '-test.txt'
            digest = hashlib.sha256(b'a').hexdigest()
            with self.assertRaises(FileError): resume.append(path, identifier, 1, digest, 0, b'a', '0' * 64)
            resume.append(path, identifier, 1, digest, 0, b'a', digest)
            with self.assertRaises(FileError): resume.progress(path, identifier, 2, digest)
            with self.assertRaises(FileError): resume.progress('../escape', identifier, 1, digest)

    def test_empty_and_incorrect_full_checksum_preserve_destination(self):
        with tempfile.TemporaryDirectory() as folder:
            home = Path(folder); inbox = PhoneInbox(home / 'state', home=home); inbox.prepare(); resume = ResumableInbox(inbox)
            identifier = str(uuid.uuid4()); path = inbox.prefix + identifier + '-empty.txt'
            digest = hashlib.sha256(b'').hexdigest()
            resume.append(path, identifier, 0, digest, 0, b'', digest)
            self.assertEqual(resume.commit(path, identifier, 0, digest)['size'], 0)
            identifier = str(uuid.uuid4()); path = inbox.prefix + identifier + '-wrong.txt'
            resume.append(path, identifier, 1, '0' * 64, 0, b'a', hashlib.sha256(b'a').hexdigest())
            with self.assertRaises(FileError): resume.commit(path, identifier, 1, '0' * 64)
            self.assertFalse((home / path).exists())
