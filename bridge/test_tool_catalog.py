import hashlib
import json
from pathlib import Path
import tempfile
import time
import unittest
from tool_catalog import catalog


class CatalogTests(unittest.TestCase):
    def test_real_snapshot_search_scope_expiry_and_projection(self):
        with tempfile.TemporaryDirectory() as temporary:
            state = Path(temporary); root = state / 'tool-catalog'; root.mkdir()
            directory = '/fixture'
            file = root / (hashlib.sha256(directory.encode()).hexdigest() + '.json')
            self.assertFalse(catalog(state, directory)['available'])
            payload = {'version': 1, 'directory': directory, 'checkedAt': time.time()*1000,
                       'tools': [{'id': 'linux_computer_observe', 'description': 'Read a window', 'parameters': ['window'], 'secret': 'must-not-leak'},
                                 {'id': 'other', 'description': 'Another tool', 'parameters': []}]}
            file.write_text(json.dumps(payload))
            value = catalog(state, directory, 'linux_computer')
            self.assertTrue(value['available']); self.assertEqual(value['matching'], 1)
            self.assertEqual(value['tools'][0]['id'], 'linux_computer_observe')
            self.assertNotIn('must-not-leak', str(value))
            self.assertFalse(catalog(state, '/other')['available'])
            payload['checkedAt'] -= 61000; file.write_text(json.dumps(payload))
            self.assertFalse(catalog(state, directory)['available'])

    def test_truncated_catalog_never_claims_complete(self):
        with tempfile.TemporaryDirectory() as temporary:
            state = Path(temporary); root = state / 'tool-catalog'; root.mkdir()
            file = root / (hashlib.sha256(b'/fixture').hexdigest() + '.json')
            file.write_text(json.dumps({'version': 1, 'directory': '/fixture', 'checkedAt': time.time()*1000,
                'tools': [{'id': 'tool_'+str(i)} for i in range(50)]}))
            value = catalog(state, '/fixture')
            self.assertEqual(len(value['tools']), 30); self.assertFalse(value['complete'])
            with self.assertRaises(ValueError): catalog(state, '/fixture', 'x'*201)
