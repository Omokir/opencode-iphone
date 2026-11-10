import json
import unittest
from connections import inventory


class ConnectionsTests(unittest.TestCase):
    def test_location_and_projection(self):
        calls = []
        def request(method, path, body):
            calls.append((method, path, body))
            rows = [{'name': 'docs', 'status': {'status': 'failed', 'error': 'SECRET'},
                     'config': {'headers': {'Authorization': 'SECRET'}}}] if '/mcp?' in path else [
                {'id': 'openai', 'name': 'OpenAI', 'metadata': {'token': 'SECRET'},
                 'methods': [{'type': 'oauth', 'label': 'SECRET'}, {'type': 'key', 'form': 'SECRET'}],
                 'connections': [{'token': 'SECRET'}]}]
            return 200, json.dumps({'data': rows}).encode()
        value = inventory(request, '/clients/a & b')
        self.assertNotIn('SECRET', json.dumps(value))
        self.assertEqual(value['mcp'], [{'name': 'docs', 'status': 'failed'}])
        self.assertEqual(value['integrations'][0]['methods'], ['key', 'oauth'])
        self.assertEqual(value['integrations'][0]['connectionCount'], 1)
        self.assertEqual(value['unavailable'], [])
        self.assertTrue(value['readOnly'])
        self.assertTrue(all(m == 'GET' and b is None and 'location%5Bdirectory%5D=%2Fclients%2Fa+%26+b' in p for m, p, b in calls))

    def test_errors_are_unavailable_and_redacted(self):
        for response in [(503, b'SECRET'), (200, b'SECRET'), (200, b'{"data": {}}'),
                         (200, b'{"data": [{"name": "x", "status": "SECRET"}]}')]:
            value = inventory(lambda *args: response, '/work')
            self.assertNotIn('SECRET', json.dumps(value))
            self.assertEqual(value['unavailable'], ['mcp', 'integration'])

    def test_independent_categories(self):
        def request(method, path, body):
            if '/mcp?' in path:
                raise TimeoutError('SECRET')
            return 200, b'{"data": []}'
        self.assertEqual(inventory(request, '/work')['unavailable'], ['mcp'])

    def test_invalid_directory_never_calls_upstream(self):
        def unexpected(*args):
            self.fail('Upstream called')
        for value in ['', 'relative', None, '/\x00', '/' + 'x' * 4096]:
            with self.assertRaises(ValueError):
                inventory(unexpected, value)

    def test_unknown_status_not_connected(self):
        def request(*args):
            return 200, b'{"data": [{"name":"x", "status":{"status":"future"}}]}'
        self.assertEqual(inventory(request, '/work')['mcp'][0]['status'], 'unknown')


if __name__ == '__main__':
    unittest.main()
