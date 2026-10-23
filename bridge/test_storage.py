from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from storage import storage_status


class StorageTests(unittest.TestCase):
    def test_capacity_and_available_user_bytes(self):
        value = SimpleNamespace(f_blocks=1000, f_frsize=4096, f_bavail=250)
        with patch('storage.os.statvfs', return_value=value):
            self.assertEqual(storage_status('/'), {'totalBytes': 4096000, 'freeBytes': 1024000})

    def test_missing_destination_uses_existing_ancestor(self):
        with tempfile.TemporaryDirectory() as temp:
            result = storage_status(Path(temp) / 'not-created' / 'inbox')
            self.assertGreater(result['totalBytes'], 0)
            self.assertGreaterEqual(result['freeBytes'], 0)

    def test_failure_is_unavailable_not_zero(self):
        with patch('storage.os.statvfs', side_effect=OSError):
            self.assertIsNone(storage_status('/'))
