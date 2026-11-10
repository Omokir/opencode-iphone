import json
from pathlib import Path
import tempfile
import unittest
from accounts import AccountError, OpenAIAccounts


SECRET = 'synthetic-key-never-real'


class Core:
    def __init__(self):
        self.calls = []
        self.existing = {'id': 'existing-chatgpt', 'type': 'credential', 'method': 'oauth', 'label': 'Existing'}
        self.connections = [self.existing.copy()]
        self.active = 'existing-chatgpt'
        self.lose_reply = False
        self.oauth_state = 'pending'
        self.oauth_url = 'https://auth.openai.com/oauth/authorize?state=synthetic'

    def __call__(self, method, path, raw):
        self.calls.append((method, path))  # Deliberately never retain credential bodies.
        if method == 'GET' and path.startswith('/api/provider/openai?'):
            result = {'integrationID': 'openai', 'headers': {'secret': SECRET}}
        elif method == 'POST' and '/connect/oauth/attempt_fixture/complete?' in path:
            self.oauth_state = 'complete'
            if self.lose_reply: raise TimeoutError(SECRET)
            return 204, b''
        elif '/connect/oauth/attempt_fixture' in path:
            result = {'status': self.oauth_state, 'message': SECRET, 'access': SECRET}
        elif method == 'GET' and path.startswith('/api/integration/openai?'):
            result = {'id': 'openai', 'methods': [{'type': 'key'}, {'type': 'oauth', 'id': 'chatgpt', 'label': 'Sign in with ChatGPT'}],
                      'connections': self.connections, 'metadata': {'secret': SECRET}}
        elif method == 'POST' and path == '/api/credential':
            value = json.loads(raw)
            assert value['activate'] is False
            assert value['value']['key'] == SECRET
            self.connections.append({'id': value['id'], 'type': 'credential', 'method': 'key'})
            result = dict(value, active=False)
            if self.lose_reply:
                raise TimeoutError(SECRET)
        elif method == 'POST' and '/connect/oauth?' in path:
            result = {'attemptID': 'attempt_fixture', 'mode': 'auto', 'url': self.oauth_url,
                      'instructions': 'Synthetic browser login', 'refresh': SECRET}
        else:
            raise AssertionError((method, path))
        return 200, json.dumps({'data': result}).encode()


class AccountsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.core = Core()
        self.root = Path(self.tmp.name) / 'accounts'
        self.accounts = OpenAIAccounts(self.root, self.core)

    def key_payload(self, request='req_key'):
        return {'requestID': request, 'directory': '/client/a', 'key': SECRET}

    def test_projection_and_billing_separation(self):
        result = self.accounts.inventory('/client/a')
        self.assertNotIn(SECRET, json.dumps(result))
        self.assertEqual([m['type'] for m in result['methods']], ['key', 'oauth'])
        self.assertEqual(result['connections'][0]['method'], 'oauth')
        self.assertTrue(all(m == 'GET' for m, _ in self.core.calls))

    def test_key_preserves_existing_login_and_never_persists_secret(self):
        result = self.accounts.add_key(self.key_payload(), 'device-a')
        self.assertEqual(result['status'], 'stored')
        self.assertFalse(result['active'])
        self.assertEqual(self.core.active, 'existing-chatgpt')
        self.assertEqual(self.core.connections[0], self.core.existing)
        self.assertNotIn(SECRET, json.dumps(result))
        for file in self.root.iterdir():
            self.assertNotIn(SECRET.encode(), file.read_bytes())
        self.assertEqual((self.root / 'operations.sqlite').stat().st_mode & 0o777, 0o600)

    def test_duplicate_attempt_never_writes_twice(self):
        self.accounts.add_key(self.key_payload(), 'device-a')
        with self.assertRaises(AccountError) as error:
            self.accounts.add_key(self.key_payload(), 'device-a')
        self.assertEqual(error.exception.status, 409)
        self.assertEqual(sum(m == 'POST' for m, _ in self.core.calls), 1)

    def test_lost_key_ack_reconciles_after_restart_by_read_only_metadata(self):
        self.core.lose_reply = True
        with self.assertRaises(AccountError) as error:
            self.accounts.add_key(self.key_payload(), 'device-a')
        self.assertNotIn(SECRET, str(error.exception.body))
        with self.assertRaises(AccountError):
            self.accounts.add_key(self.key_payload('req_new'), 'device-a')
        result = OpenAIAccounts(self.root, self.core).status('req_key', 'device-a')
        self.assertEqual(result['status'], 'complete')
        self.assertEqual(sum(m == 'POST' for m, _ in self.core.calls), 1)
        self.assertFalse(any(p == '/api/credential' and m == 'GET' for m, p in self.core.calls))

    def test_operation_bound_to_paired_device(self):
        self.accounts.add_key(self.key_payload(), 'device-a')
        with self.assertRaises(AccountError) as error:
            self.accounts.status('req_key', 'device-b')
        self.assertEqual(error.exception.status, 404)

    def test_official_oauth_pending_completed_without_returning_tokens(self):
        payload = {'requestID': 'req_oauth', 'directory': '/client/a', 'methodID': 'chatgpt'}
        result = self.accounts.start_oauth(payload, 'device-a')
        self.assertEqual(result['status'], 'pending')
        self.assertNotIn(SECRET, json.dumps(result))
        self.assertEqual(self.accounts.status('req_oauth', 'device-a')['status'], 'pending')
        self.core.oauth_state = 'complete'
        result = self.accounts.status('req_oauth', 'device-a')
        self.assertEqual(result['status'], 'complete')
        self.assertNotIn(SECRET, json.dumps(result))
        self.assertEqual(self.core.active, 'existing-chatgpt')

    def test_oauth_does_not_open_unrecognized_authorization_host(self):
        self.core.oauth_url = 'https://attacker.example/steal'
        with self.assertRaises(AccountError):
            self.accounts.start_oauth({'requestID': 'req_bad', 'directory': '/client/a', 'methodID': 'chatgpt'}, 'device-a')

    def test_invalid_payload_and_method_cannot_reach_writes(self):
        for payload in [dict(self.key_payload(), activate=True), dict(self.key_payload(), key='bad\nkey')]:
            with self.assertRaises(AccountError): self.accounts.add_key(payload, 'device-a')
        with self.assertRaises(AccountError):
            self.accounts.start_oauth({'requestID': 'req_bad', 'directory': '/client/a', 'methodID': '../../other'}, 'device-a')
        self.assertFalse(any(m == 'POST' for m, _ in self.core.calls))

    def test_code_completion_is_once_and_reconciles_lost_ack(self):
        payload = {'requestID': 'req_oauth', 'directory': '/client/a', 'methodID': 'chatgpt'}
        self.accounts.start_oauth(payload, 'device-a')
        self.core.lose_reply = True
        code = {'requestID': 'req_oauth', 'code': 'synthetic-private-auth-code'}
        with self.assertRaises(AccountError): self.accounts.complete_oauth(code, 'device-a')
        with self.assertRaises(AccountError): self.accounts.complete_oauth(code, 'device-a')
        self.assertEqual(self.accounts.status('req_oauth', 'device-a')['status'], 'complete')
        self.assertEqual(sum(m == 'POST' and '/complete?' in p for m, p in self.core.calls), 1)
        for file in self.root.iterdir():
            self.assertNotIn(b'synthetic-private-auth-code', file.read_bytes())


if __name__ == '__main__':
    unittest.main()
