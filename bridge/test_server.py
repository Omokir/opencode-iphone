import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request
import server


class GatewayTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.state = Path(self.temp.name)
        (self.state / 'token.secret').write_text('test-token')
        self.patch = patch.object(server, 'STATE', self.state)
        self.patch.start()
        server.ATTEMPTS.clear()
        self.http = server.ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
        self.thread = threading.Thread(target=self.http.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.http.shutdown()
        self.http.server_close()
        self.patch.stop()
        self.temp.cleanup()

    def request(self, path, token=None, body=None, origin=None):
        headers = {'Content-Type': 'application/json'}
        if token:
            headers['Authorization'] = 'Bearer ' + token
        if origin:
            headers['Origin'] = origin
        req = urllib.request.Request(f'http://127.0.0.1:{self.http.server_port}' + path,
            data=json.dumps(body).encode() if body is not None else None, headers=headers)
        try:
            r = urllib.request.urlopen(req)
        except urllib.error.HTTPError as error:
            r = error
        return r.status, json.loads(r.read())

    def test_authentication_required(self):
        self.assertEqual(self.request('/api/info')[0], 401)
        self.assertEqual(self.request('/api/info', 'wrong')[0], 401)

    def test_no_config_or_shell_or_credentials(self):
        for path in ['/api/config', '/api/credential', '/api/shell', '/api/fs/read/private']:
            self.assertEqual(self.request(path, 'test-token')[0], 403)

    def test_pairing_expires_is_single_use_and_rate_limited(self):
        file = self.state / 'pairing.json'
        file.write_text(json.dumps({'code': '012345', 'expires': server.time.time() + 60}))
        self.assertEqual(self.request('/pair', body={'code': '012345'}), (200, {'token': 'test-token'}))
        self.assertEqual(self.request('/pair', body={'code': '012345'})[0], 401)
        file.write_text(json.dumps({'code': '012345', 'expires': 0}))
        self.assertEqual(self.request('/pair', body={'code': '012345'})[0], 401)
        for _ in range(2):
            self.request('/pair', body={'code': 'wrong'})
        self.assertEqual(self.request('/pair', body={'code': '012345'})[0], 429)

    def test_no_browser_origins(self):
        self.assertEqual(self.request('/pair', body={'code': '123456'}, origin='https://evil.test')[0], 403)

    def test_proxy_preserves_response_and_has_no_automatic_write_retry(self):
        with patch.object(server, 'upstream', return_value=(200, b'{"data":[]}')) as upstream:
            self.assertEqual(self.request('/api/session?limit=30', 'test-token'), (200, {'data': []}))
            upstream.assert_called_once_with('GET', '/api/session?limit=30', None)

    def test_mode_requires_boolean(self):
        self.assertEqual(self.request('/phone/mode', 'test-token', {'awake': 'yes'})[0], 400)

    def test_allowlist(self):
        self.assertTrue(server.allowed('POST', '/api/session/ses_123/prompt'))
        self.assertFalse(server.allowed('DELETE', '/api/session/ses_123'))
        self.assertFalse(server.allowed('POST', '/api/session/ses_123/shell'))


if __name__ == '__main__':
    unittest.main()
