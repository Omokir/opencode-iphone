import fcntl
import hashlib
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest

from backend import Gateway, DemoGateway, PocketError
from uploads import UploadManager, UploadPaused, remote_name, wire_parameters
from upload_fixture import start_upload_fixture


class UploadTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name)
        self.server = start_upload_fixture(self.root)
        self.gateway = Gateway(self.root / 'client', port=self.server.server_port); self.gateway.pair('123456')
        self.manager = UploadManager(self.root / 'client', self.gateway)
        self.source = self.root / 'source.bin'; self.data = b'fixture-binary\0\xff'*18000; self.source.write_bytes(self.data)

    def tearDown(self):
        self.manager.close(); self.server.continue_chunk.set(); self.server.shutdown(); self.server.server_close(); self.temp.cleanup()

    def counts(self, action):
        return sum(item['action'] == action for item in self.server.requests)

    def test_complete_upload_actual_bytes_and_separate_verified_receipt(self):
        identifier = self.manager.add(self.source)
        receipt = self.manager.run(identifier)
        record = self.manager.get(identifier)
        self.assertEqual(record['state'], 'completed')
        self.assertEqual(receipt['sha256'], hashlib.sha256(self.data).hexdigest())
        self.assertEqual((self.server.home / record['destination']).read_bytes(), self.data)
        self.assertEqual(self.source.read_bytes(), self.data)
        self.assertGreater(self.counts('chunk'), 1)
        self.assertLessEqual(max(r['length'] for r in self.server.requests), 64*1024)
        self.assertEqual(self.server.requests[-1]['action'], 'verify')
        self.assertEqual((self.manager.root/'uploads.json').stat().st_mode & 0o777, 0o600)

    def test_lost_chunk_ack_resume_reads_durable_offset_after_restart(self):
        identifier = self.manager.add(self.source); self.server.lose_chunk_once = True
        with self.assertRaises(PocketError):
            self.manager.run(identifier)
        self.assertEqual(self.manager.get(identifier)['offset'], 0)
        self.assertEqual(self.counts('chunk'), 1)
        again = UploadManager(self.root / 'client', self.gateway); again.run(identifier)
        offsets = [int(r['offset']) for r in self.server.requests if r['action'] == 'chunk']
        self.assertEqual(offsets[:2], [0, 64*1024])
        self.assertEqual(offsets.count(0), 1)
        self.assertEqual(again.get(identifier)['state'], 'completed')
        self.assertEqual(self.source.read_bytes(), self.data)

    def test_lost_commit_ack_resume_only_verifies_without_reupload(self):
        identifier = self.manager.add(self.source); self.server.lose_commit_once = True
        with self.assertRaises(PocketError):
            self.manager.run(identifier)
        chunks, commits = self.counts('chunk'), self.counts('commit')
        moved = self.root / 'source-moved-by-user.bin'; self.source.rename(moved)
        again = UploadManager(self.root / 'client', self.gateway); again.run(identifier)
        self.assertEqual((self.counts('chunk'), self.counts('commit')), (chunks, commits))
        self.assertEqual(self.server.requests[-1]['action'], 'verify')
        self.assertEqual(again.get(identifier)['state'], 'completed')
        self.assertEqual(moved.read_bytes(), self.data)

    def test_pause_and_resume_and_empty_file(self):
        identifier = self.manager.add(self.source)
        def pause(offset, _):
            if offset:
                self.manager.pause(identifier)
        with self.assertRaises(UploadPaused):
            self.manager.run(identifier, notify=pause)
        self.assertEqual(self.manager.get(identifier)['state'], 'paused')
        self.assertEqual(self.counts('commit'), 0)
        self.manager.run(identifier)
        empty = self.root / 'empty.txt'; empty.write_bytes(b'')
        empty_id = self.manager.add(empty); result = self.manager.run(empty_id)
        self.assertEqual(result['size'], 0); self.assertTrue(empty.exists())

    def test_source_changed_blocks_same_id_and_preserves_partial(self):
        identifier = self.manager.add(self.source)
        with self.assertRaises(UploadPaused):
            self.manager.run(identifier, notify=lambda offset, _: self.manager.pause(identifier) if offset else None)
        before = self.counts('chunk'); self.source.write_bytes(b'z'*len(self.data))
        with self.assertRaisesRegex(PocketError, 'origem mudou'):
            self.manager.run(identifier)
        self.assertEqual(self.counts('chunk'), before); self.assertEqual(self.counts('commit'), 0)
        self.assertEqual(self.source.read_bytes(), b'z'*len(self.data))

    def test_auth_failure_during_verify_is_not_treated_as_missing(self):
        identifier = self.manager.add(self.source)
        with self.assertRaises(UploadPaused):
            self.manager.run(identifier, notify=lambda offset, _: self.manager.pause(identifier) if offset else None)
        before = self.counts('chunk'); self.server.verify_failure = 401
        with self.assertRaises(PocketError):
            self.manager.run(identifier)
        self.assertEqual(self.counts('chunk'), before)

    def test_bad_progress_and_bad_receipt_never_mark_complete(self):
        identifier = self.manager.add(self.source); self.server.bad_progress = {'offset': True, 'chunkBytes': 65536}
        with self.assertRaises(PocketError):
            self.manager.run(identifier)
        self.assertEqual(self.counts('chunk'), 0)
        self.server.bad_progress = None; self.server.bad_receipt = True
        with self.assertRaisesRegex(PocketError, 'Recibo'):
            self.manager.run(identifier)
        self.assertNotEqual(self.manager.get(identifier)['state'], 'completed')
        self.assertEqual(self.source.read_bytes(), self.data)

    def test_lease_blocks_concurrent_writer_without_mutating_record(self):
        identifier = self.manager.add(self.source)
        with open(self.manager.root/(identifier+'.lock'), 'wb') as lease:
            fcntl.flock(lease.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaisesRegex(PocketError, 'outro processo'):
                self.manager.run(identifier)
        self.assertEqual(self.manager.get(identifier)['state'], 'ready')
        self.assertFalse(self.server.requests)

    def test_pre_cancel_symlink_protected_names_and_demo_have_no_writes(self):
        cancelled = threading.Event(); cancelled.set()
        with self.assertRaises(UploadPaused):
            self.manager.add(self.source, cancelled)
        link = self.root / 'link.bin'; link.symlink_to(self.source)
        with self.assertRaises(PocketError):
            self.manager.add(link)
        secret = self.root / 'auth.json'; secret.write_text('{}')
        with self.assertRaises(PocketError):
            self.manager.add(secret)
        with self.assertRaises(PocketError):
            UploadManager(self.root/'demo', DemoGateway()).add(self.source)
        self.assertFalse(self.server.requests)

    def test_long_names_and_wire_validation(self):
        shortened = remote_name('é'*120 + '.zip')
        self.assertLessEqual(len(shortened.encode()), 200)
        self.assertTrue(shortened.endswith('.zip'))
        identifier = self.manager.add(self.source); record = self.manager.get(identifier)
        record['destination'] = '../escape'
        with self.assertRaises(PocketError):
            wire_parameters(record)

    def test_file_larger_than_chat_limit_uses_bounded_four_megabyte_chunks(self):
        self.server.resumable.chunk_bytes = 4*1024*1024
        data = b'large-fixture\0'*((9*1024*1024)//14 + 1)
        self.source.write_bytes(data)
        identifier = self.manager.add(self.source); receipt = self.manager.run(identifier)
        lengths = [r['length'] for r in self.server.requests if r['action'] == 'chunk']
        self.assertGreater(len(data), 8*1024*1024)
        self.assertEqual(lengths[:2], [4*1024*1024]*2)
        self.assertLessEqual(max(lengths), 4*1024*1024)
        self.assertEqual(receipt['sha256'], hashlib.sha256(data).hexdigest())
        self.assertEqual(self.source.read_bytes(), data)

    def test_regular_file_short_reads_are_supported_without_corrupting_chunks(self):
        self.manager.read = lambda fd, count: os.read(fd, min(count, 257))
        identifier = self.manager.add(self.source); result = self.manager.run(identifier)
        self.assertEqual(result['sha256'], hashlib.sha256(self.data).hexdigest())
        self.assertEqual((self.server.home/result['path']).read_bytes(), self.data)


if __name__ == '__main__':
    unittest.main()
