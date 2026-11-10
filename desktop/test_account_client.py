import json
from pathlib import Path
import tempfile
import unittest
from backend import Store, PocketError
from account_client import AccountClient


class Gateway:
    def __init__(self):
        self.posts = 0
        self.request_id = None
        self.lose = False

    def request(self, path, method='GET', body=None):
        if method == 'POST':
            self.posts += 1; self.request_id = body['requestID']
            if self.lose: raise TimeoutError('synthetic-secret')
            if path.endswith('/oauth'):
                return {'requestID': self.request_id, 'status': 'pending', 'url': 'https://auth.openai.com/oauth/authorize?state=fixture', 'mode': 'auto'}
            if path.endswith('/complete'):
                return {'requestID': self.request_id, 'status': 'complete'}
            return {'requestID': self.request_id, 'status': 'stored', 'active': False}
        return {'requestID': self.request_id, 'status': 'complete'}


class AccountClientTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.store = Store(Path(self.tmp.name))
        self.store.save()
        self.gateway = Gateway()
        self.client = AccountClient(self.gateway, self.store, '/fixture')

    def test_key_never_written_to_preferences(self):
        result = self.client.add_key('synthetic-secret')
        self.assertFalse(result['active'])
        self.assertNotIn('synthetic-secret', (self.store.root / 'preferences.json').read_text())
        self.assertIsNone(self.client.pending)

    def test_uncertainty_survives_restart_without_retransmission(self):
        self.gateway.lose = True
        with self.assertRaises(PocketError) as error:
            self.client.add_key('synthetic-secret')
        self.assertNotIn('synthetic-secret', str(error.exception))
        restarted = AccountClient(self.gateway, Store(self.store.root), '/other-project')
        self.assertEqual(restarted.pending['directory'], '/fixture')
        with self.assertRaises(PocketError): restarted.add_key('new-secret')
        self.assertEqual(self.gateway.posts, 1)
        self.assertEqual(restarted.status()['status'], 'complete')
        self.assertIsNone(restarted.pending)
        self.assertEqual(self.gateway.posts, 1)

    def test_failed_intent_persistence_sends_nothing(self):
        def fail(record): raise OSError('synthetic disk failure')
        self.client._write_intent = fail
        with self.assertRaises(PocketError): self.client.add_key('synthetic-secret')
        self.assertEqual(self.gateway.posts, 0)

    def test_oauth_code_is_not_saved_and_lost_ack_cannot_replay(self):
        self.client.start_oauth('chatgpt')
        self.gateway.lose = True
        with self.assertRaises(PocketError): self.client.complete_oauth('synthetic-private-code')
        restarted = AccountClient(self.gateway, Store(self.store.root), '/fixture')
        with self.assertRaises(PocketError): restarted.complete_oauth('synthetic-private-code')
        self.assertEqual(self.gateway.posts, 2)
        for file in self.store.root.iterdir():
            self.assertNotIn(b'synthetic-private-code', file.read_bytes())
        self.assertEqual(restarted.status()['status'], 'complete')
        self.assertEqual(self.gateway.posts, 2)

    def test_invalid_key_never_creates_pending_intent(self):
        with self.assertRaises(PocketError): self.client.add_key('bad')
        self.assertIsNone(self.client.pending)
        self.assertEqual(self.gateway.posts, 0)


if __name__ == '__main__': unittest.main()
