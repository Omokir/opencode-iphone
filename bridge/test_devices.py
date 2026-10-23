import json
from pathlib import Path
import tempfile
import unittest
from devices import DeviceTokens


class DeviceTests(unittest.TestCase):
    def test_independent_revocation_and_no_token_disclosure(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); (root / 'token.secret').write_text('old-token')
            store = DeviceTokens(root)
            first = store.issue('Phone 1'); second = store.issue('Phone 2')
            identifier = store.identify(first)
            self.assertNotEqual(identifier, store.identify(second))
            self.assertNotIn(first, store.path.read_text())
            self.assertNotIn('hash', json.dumps(store.listing(identifier)))
            store.revoke(identifier)
            self.assertIsNone(store.identify(first))
            self.assertIsNotNone(store.identify(second))
            self.assertEqual(store.identify('old-token'), 'legacy')
            store.revoke('legacy')
            self.assertIsNone(store.identify('old-token'))
            self.assertIsNone(store.identify(''))
