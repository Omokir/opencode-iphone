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
        self.http.phone_control = server.PhoneControl(self.state, lambda *args: server.upstream(*args))
        self.http.codex_usage = server.CodexUsage(reader=lambda: {'account': None})
        self.thread = threading.Thread(target=self.http.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.http.shutdown()
        self.http.server_close()
        self.patch.stop()
        self.temp.cleanup()

    def request(self, path, token=None, body=None, origin=None, method=None):
        headers = {'Content-Type': 'application/json'}
        if token:
            headers['Authorization'] = 'Bearer ' + token
        if origin:
            headers['Origin'] = origin
        req = urllib.request.Request(f'http://127.0.0.1:{self.http.server_port}' + path,
            data=json.dumps(body).encode() if body is not None else None, headers=headers, method=method)
        try:
            r = urllib.request.urlopen(req)
        except urllib.error.HTTPError as error:
            r = error
        with r:
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

    def test_mobile_session_uses_configured_model(self):
        model = {'providerID': 'example', 'id': 'working-model'}
        (self.state / 'defaults.json').write_text(json.dumps({'model': model, 'agent': 'build'}))
        payload = json.loads(server.session_defaults(b'{"location":{"directory":"/workspace"}}'))
        self.assertEqual(payload['model'], model)
        self.assertEqual(payload['agent'], 'build')
        self.assertEqual(payload['location']['directory'], '/workspace')

    def test_explicit_model_is_not_overwritten(self):
        (self.state / 'defaults.json').write_text(json.dumps({'model': {'id': 'fallback', 'providerID': 'example'}}))
        payload = json.loads(server.session_defaults(b'{"model":{"id":"chosen","providerID":"example"}}'))
        self.assertEqual(payload['model']['id'], 'chosen')

    def test_chat_controls_allowlisted_without_global_config(self):
        for action in ['agent', 'model']:
            self.assertTrue(server.allowed('POST', '/api/session/ses_123/' + action))
        self.assertTrue(server.allowed('PATCH', '/api/session/ses_123'))
        self.assertFalse(server.allowed('PATCH', '/api/config'))

    def test_rename_cannot_change_permissions_or_archive(self):
        for payload in [{'title': ''}, {'title': 'x' * 201}, {'title': 'OK', 'permissions': []}, {'archived': True}]:
            self.assertEqual(self.request('/api/session/ses_123', 'test-token', payload, method='PATCH')[0], 400)
        with patch.object(server, 'upstream', return_value=(204, b'')) as upstream:
            # The 204 body is empty, so inspect the wire directly rather than JSON helper.
            request = urllib.request.Request(f'http://127.0.0.1:{self.http.server_port}/api/session/ses_123',
                data=b'{"title":" Renamed "}', method='PATCH', headers={'Authorization': 'Bearer test-token'})
            with urllib.request.urlopen(request) as response:
                self.assertEqual(response.status, 204)
            self.assertEqual(json.loads(upstream.call_args.args[2]), {'title': 'Renamed'})

    def test_catalog_strips_provider_secrets_and_agent_prompts(self):
        models = {'data': [{'id': 'm', 'providerID': 'p', 'name': 'Model', 'enabled': True, 'status': 'active',
            'headers': {'Authorization': 'private'}, 'settings': {'apiKey': 'private'},
            'capabilities': {'input': ['image', 'text'], 'tools': True},
            'variants': [{'id': 'high', 'settings': {'private': True}}]}]}
        agents = {'data': [{'id': 'build', 'name': 'Build', 'mode': 'primary', 'hidden': False, 'system': 'private'},
                           {'id': 'secret', 'name': 'Secret', 'mode': 'primary', 'hidden': True}]}
        with patch.object(server, 'upstream', side_effect=[(200, json.dumps(models).encode()), (200, json.dumps(agents).encode())]):
            status, catalog = server.catalog('/workspace')
        self.assertEqual(status, 200)
        self.assertNotIn('private', json.dumps(catalog))
        self.assertEqual(catalog['agents'], [{'id': 'build', 'name': 'Build'}])
        self.assertEqual(catalog['models'][0]['variants'], [{'id': 'high'}])

    def test_attachments_pass_through_without_logging_or_rewriting(self):
        payload = {'text': 'Read attached text', 'files': [{'uri': 'data:text/plain;base64,aGk=', 'name': 'example.txt'}]}
        with patch.object(server, 'upstream', return_value=(200, b'{"data":{"id":"input"}}')) as upstream:
            self.assertEqual(self.request('/api/session/ses_123/prompt', 'test-token', payload)[0], 200)
            self.assertEqual(json.loads(upstream.call_args.args[2]), payload)

    def test_control_session_disallows_permanent_approvals_and_other_agents(self):
        self.http.phone_control.save({'sessionID': 'ses_123', 'enabled': True, 'expiresAt': server.time.time() + 60})
        self.assertEqual(self.request('/api/session/ses_123/permission/per_1/reply', 'test-token', {'decision': 'always'})[0], 403)
        self.assertEqual(self.request('/api/session/ses_123/agent', 'test-token', {'agent': 'general'})[0], 403)

    def test_paused_control_session_rejects_prompt_without_upstream_write(self):
        self.http.phone_control.save({'sessionID': 'ses_123', 'enabled': False, 'expiresAt': 0})
        with patch.object(server, 'upstream') as upstream:
            self.assertEqual(self.request('/api/session/ses_123/prompt', 'test-token', {'text': 'Hello'})[0], 409)
            upstream.assert_not_called()

    def test_control_routes_require_authentication(self):
        self.assertEqual(self.request('/phone/control/status')[0], 401)
        self.assertEqual(self.request('/phone/control/start', body={})[0], 401)
        self.assertEqual(self.request('/phone/control/stop', body={})[0], 401)
        self.assertEqual(self.request('/phone/codex/usage')[0], 401)

    def test_codex_quota_endpoint_is_readonly_and_sanitized(self):
        status, body = self.request('/phone/codex/usage', 'test-token')
        self.assertEqual(status, 200)
        self.assertFalse(body['available'])
        self.assertIsNone(body['weekly'])
        self.assertFalse(server.allowed('POST', '/phone/codex/usage'))

    def test_question_routes_forward_answers_but_not_form_creation(self):
        self.assertTrue(server.allowed('GET', '/api/session/ses_123/form'))
        self.assertTrue(server.allowed('POST', '/api/session/ses_123/form/form_1/reply'))
        self.assertFalse(server.allowed('POST', '/api/session/ses_123/form'))
        payload = {'answer': {'direction': 'plan'}}
        with patch.object(server, 'upstream', return_value=(200, b'{}')) as upstream:
            self.assertEqual(self.request('/api/session/ses_123/form/form_1/reply', 'test-token', payload)[0], 200)
            self.assertEqual(json.loads(upstream.call_args.args[2]), payload)

    def test_paused_control_cannot_resume_by_answering_form(self):
        self.http.phone_control.save({'sessionID': 'ses_123', 'enabled': False, 'expiresAt': 0})
        with patch.object(server, 'upstream') as upstream:
            self.assertEqual(self.request('/api/session/ses_123/form/form_1/reply', 'test-token', {'answer': {'direction': 'plan'}})[0], 409)
            upstream.assert_not_called()


if __name__ == '__main__':
    unittest.main()
