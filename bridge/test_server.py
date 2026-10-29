import json
import hashlib
import io
import uuid
import subprocess
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
        self.http.files = server.FileBrowser(self.state, roots={'home': {'name': 'Fixture', 'path': str(self.state)}})
        self.http.inbox = server.PhoneInbox(self.state / 'inbox-state', home=self.state)
        self.http.resumable = server.ResumableInbox(self.http.inbox)
        self.http.power = server.NotebookPower(run=lambda args, **kwargs: subprocess.CompletedProcess(args, 1, '', ''))
        self.http.kzl = server.KzL(self.state, lambda *args: server.upstream(*args), server.session_defaults)
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

    def test_kzl_routes_require_auth_and_reject_arbitrary_execution(self):
        for path in ('/phone/kzl/tasks', '/phone/kzl/context', '/phone/kzl/memory', '/phone/kzl/capabilities', '/phone/kzl/events'):
            self.assertEqual(self.request(path)[0], 401)
        self.assertEqual(self.request('/phone/kzl/ensure', body={})[0], 401)
        self.assertEqual(self.request('/phone/kzl/submit', body={'callID': 'x', 'text': 'x'})[0], 401)
        with patch.object(server, 'upstream') as upstream:
            self.assertEqual(self.request('/phone/kzl/submit', 'test-token', {'callID': 'x', 'text': 'x', 'permissions': 'allow'})[0], 400)
            self.assertEqual(self.request('/phone/kzl/config', 'test-token')[0], 403)
            self.assertEqual(self.request('/phone/kzl/task/job_x/../../shell', 'test-token', {})[0], 400)
            upstream.assert_not_called()

    def test_power_routes_do_not_execute_without_explicit_device_ticket(self):
        self.assertEqual(self.request('/phone/power/status')[0], 401)
        self.assertEqual(self.request('/phone/power/status', 'test-token')[1]['powerOff'], 'unavailable')
        self.assertEqual(self.request('/phone/power/prepare', 'test-token', method='POST')[0], 403)
        self.assertEqual(self.request('/phone/power/off', 'test-token', {'ticket': 'not-issued'})[0], 409)

    def test_active_state_is_authenticated_read_only_proxy(self):
        self.assertEqual(self.request('/api/session/active')[0], 401)
        with patch.object(server, 'upstream', return_value=(200, b'{"data":{"ses_running":{"type":"running"}}}')) as upstream:
            status, result = self.request('/api/session/active', 'test-token')
            self.assertEqual(status, 200)
            self.assertEqual(result['data']['ses_running']['type'], 'running')
            upstream.assert_called_once_with('GET', '/api/session/active', None)

    def test_voice_broker_requires_auth_and_limits_transport(self):
        self.assertEqual(self.request('/api/experimental/voice/models')[0], 401)
        self.assertEqual(self.request('/api/experimental/voice/session', body={})[0], 401)
        with patch.object(server, 'upstream') as upstream:
            for payload in [{}, {'model': 'gpt-live-1', 'transport': {'type': 'webrtc', 'sdp': 'v=0\r\n'}},
                            {'model': 'gpt-realtime-2.1', 'transport': {'type': 'websocket'}}]:
                self.assertEqual(self.request('/api/experimental/voice/session', 'test-token', payload)[0], 400)
            upstream.assert_not_called()
        with patch.object(server, 'upstream', return_value=(200, b'{"data":{"transport":{"type":"webrtc","sdp":"v=0"}}}')) as upstream:
            payload = {'model': 'gpt-realtime-2.1', 'session': {}, 'transport': {'type': 'webrtc', 'sdp': 'v=0\r\n'}}
            self.assertEqual(self.request('/api/experimental/voice/session', 'test-token', payload)[0], 200)
            self.assertEqual(upstream.call_count, 1)

    def test_shared_read_markers_project_only_viewed_and_reject_paths(self):
        self.assertEqual(self.request('/phone/session/read-state', body={'ids': ['ses_old']})[0], 401)
        with patch.object(server, 'upstream', return_value=(200, b'{"data":{"id":"ses_old","title":"private","time":{"viewed":50}}}')) as upstream:
            self.assertEqual(self.request('/phone/session/read-state', 'test-token', {'ids': ['ses_old']}), (200, {'viewed': {'ses_old': 50}, 'unavailable': []}))
            upstream.assert_called_once_with('GET', '/api/session/ses_old', None)
        with patch.object(server, 'upstream') as upstream:
            self.assertEqual(self.request('/phone/session/read-state', 'test-token', {'ids': ['ses_old/../../config']})[0], 400)
            upstream.assert_not_called()

    def test_no_config_or_shell_or_credentials(self):
        for path in ['/api/config', '/api/credential', '/api/shell', '/api/fs/read/private']:
            self.assertEqual(self.request(path, 'test-token')[0], 403)

    def test_pairing_expires_is_single_use_and_rate_limited(self):
        file = self.state / 'pairing.json'
        file.write_text(json.dumps({'code': '012345', 'expires': server.time.time() + 60}))
        status, paired = self.request('/pair', body={'code': '012345'})
        self.assertEqual(status, 200)
        self.assertNotEqual(paired['token'], 'test-token')
        self.assertIsNotNone(server.DeviceTokens(self.state).identify(paired['token']))
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

    def test_file_transfer_wire_roundtrip_and_auth(self):
        base = f'http://127.0.0.1:{self.http.server_port}'
        payload = b'wire fixture'
        identifier = str(uuid.uuid4())
        headers = {'Authorization': 'Bearer test-token', 'Content-Type': 'application/octet-stream',
                   'X-Upload-ID': identifier, 'X-Content-SHA256': hashlib.sha256(payload).hexdigest(), 'If-None-Match': '*'}
        request = urllib.request.Request(base + '/phone/files/upload?root=home&path=fixture.txt', data=payload, headers=headers)
        with urllib.request.urlopen(request) as response:
            receipt = json.load(response)
        self.assertEqual(receipt['sha256'], hashlib.sha256(payload).hexdigest())
        with urllib.request.urlopen(urllib.request.Request(base + '/phone/files/download?root=home&path=fixture.txt', headers={'Authorization': 'Bearer test-token'})) as response:
            self.assertEqual(response.read(), payload)
            self.assertEqual(response.headers['X-Content-SHA256'], receipt['sha256'])
        self.assertEqual(self.request('/phone/files/roots')[0], 401)
        self.assertFalse(server.allowed('DELETE', '/phone/files/download'))

    def test_resumable_inbox_wire(self):
        import urllib.parse
        self.http.inbox.prepare()
        identifier = str(uuid.uuid4())
        payload = b'wire resumable fixture'
        digest = hashlib.sha256(payload).hexdigest()
        path = self.http.inbox.prefix + identifier + '-fixture.txt'
        query = '?' + urllib.parse.urlencode({'path': path, 'id': identifier, 'size': len(payload), 'sha256': digest})
        self.assertEqual(self.request('/phone/inbox/progress' + query, 'test-token')[1]['offset'], 0)
        base = f'http://127.0.0.1:{self.http.server_port}'
        headers = {'Authorization': 'Bearer test-token', 'Content-Type': 'application/octet-stream', 'X-Chunk-SHA256': digest}
        with urllib.request.urlopen(urllib.request.Request(base + '/phone/inbox/chunk' + query + '&offset=0', data=payload, headers=headers)) as response:
            self.assertEqual(json.load(response)['offset'], len(payload))
        self.assertEqual(self.request('/phone/inbox/commit' + query, 'test-token', method='POST')[0], 200)
        self.assertEqual(self.request('/phone/inbox/verify?' + urllib.parse.urlencode({'path': path, 'id': identifier}), 'test-token')[1]['sha256'], digest)

    def test_device_registry_wire_revokes_only_selected_token(self):
        registry = server.DeviceTokens(self.state)
        token = registry.issue('Synthetic phone')
        second = registry.issue('Second synthetic phone')
        status, listing = self.request('/phone/devices', token)
        self.assertEqual(status, 200)
        current = next(d for d in listing['devices'] if d['current'])
        self.assertEqual(self.request('/phone/devices/revoke', token, {'id': current['id']})[0], 200)
        self.assertEqual(self.request('/phone/devices', token)[0], 401)
        self.assertEqual(self.request('/phone/devices', second)[0], 200)

    def test_history_search_wire_preserves_upstream_pagination(self):
        page = {'data': [{'id': 'msg_old', 'type': 'assistant', 'content': [{'type': 'text', 'text': 'An old matching result'}], 'time': {'created': 1}}], 'cursor': {'next': 'next+/='}}
        with patch.object(server, 'upstream', return_value=(200, json.dumps(page).encode())) as upstream:
            status, result = self.request('/phone/session/ses_test/search?q=matching&cursor=opaque%2B%2F%3D', 'test-token')
            self.assertEqual(status, 200)
            self.assertEqual(result['matches'][0]['id'], 'msg_old')
            self.assertEqual(result['cursor'], 'next+/=')
            upstream.assert_called_once_with('GET', '/api/session/ses_test/message?limit=15&cursor=opaque%2B%2F%3D', None)
        self.assertEqual(self.request('/phone/session/ses_test/search?q=', 'test-token')[0], 400)

    def test_message_projection_omits_inline_file_data(self):
        body = b'{"data":[{"id":"msg_1","type":"user","files":[{"name":"photo.png","mime":"image/png","data":"private-base64","source":{"uri":"private"}}]}]}'
        projected = json.loads(server.mobile_messages(body))
        self.assertEqual(projected['data'][0]['files'], [{'name': 'photo.png', 'mime': 'image/png'}])
        self.assertNotIn('private-base64', json.dumps(projected))
        tools = {'data': {'id': 'msg_2', 'type': 'assistant', 'content': [
            {'type': 'tool', 'state': {'status': 'running', 'input': {'code': 'review this'}, 'content': ['large-output']}},
            {'type': 'tool', 'state': {'status': 'completed', 'input': {'code': 'old-input'}, 'content': ['large-output']}}]}}
        result = json.loads(server.mobile_messages(json.dumps(tools).encode()))
        self.assertEqual(result['data']['content'][0]['state']['input'], {'code': 'review this'})
        self.assertNotIn('large-output', json.dumps(result))
        self.assertNotIn('old-input', json.dumps(result))

    def test_initial_history_is_small_without_changing_pagination(self):
        result = server.mobile_history_path('/api/session/ses_1/message?limit=50&order=desc')
        self.assertIn('limit=15', result)
        for path in ['/api/session/ses_1/message?limit=50&cursor=older', '/api/session/ses_1/message?limit=5&order=desc&type=assistant', '/api/session?limit=50&order=desc']:
            self.assertEqual(server.mobile_history_path(path), path)

    def test_inbox_authenticated_wire_and_actual_verification(self):
        base = f'http://127.0.0.1:{self.http.server_port}'
        auth = {'Authorization': 'Bearer test-token'}
        with urllib.request.urlopen(urllib.request.Request(base + '/phone/inbox/prepare', data=b'', headers=auth)) as response:
            self.assertEqual(json.load(response)['path'], 'Downloads/Iphone 11 Omoki')
        identifier = str(uuid.uuid4())
        path = 'Downloads/Iphone 11 Omoki/' + identifier + '-wire.txt'
        payload = b'inbox wire fixture'
        headers = dict(auth, **{'Content-Type': 'application/octet-stream', 'X-Upload-ID': identifier, 'X-Content-SHA256': hashlib.sha256(payload).hexdigest()})
        query = urllib.parse.urlencode({'path': path, 'id': identifier})
        with urllib.request.urlopen(urllib.request.Request(base + '/phone/inbox/upload?' + query, data=payload, headers=headers)) as response:
            self.assertEqual(json.load(response)['size'], len(payload))
        with urllib.request.urlopen(urllib.request.Request(base + '/phone/inbox/verify?' + query, headers=auth)) as response:
            self.assertEqual(json.load(response)['sha256'], hashlib.sha256(payload).hexdigest())
        self.assertEqual(self.request('/phone/inbox/verify?' + query)[0], 401)

    def test_sse_stream_forwards_hints_not_other_sessions_or_content(self):
        own = json.dumps({'type': 'session.message.delta', 'data': {'sessionID': 'ses_own', 'text': 'private-own-text'}})
        other = json.dumps({'type': 'session.message.delta', 'data': {'sessionID': 'ses_other', 'text': 'private-other-text'}})
        wire = ('data: ' + own + '\n\n' + 'data: ' + other + '\n\n').encode()
        base = f'http://127.0.0.1:{self.http.server_port}'
        original_open = urllib.request.urlopen
        def open_core_or_client(request, *args, **kwargs):
            if isinstance(request, urllib.request.Request) and request.full_url == 'http://core.invalid/events':
                return io.BytesIO(wire)
            return original_open(request, *args, **kwargs)
        with patch.object(server, 'core_request', return_value=urllib.request.Request('http://core.invalid/events')), patch.object(urllib.request, 'urlopen', side_effect=open_core_or_client):
            request = urllib.request.Request(base + '/phone/session/ses_own/events', headers={'Authorization': 'Bearer test-token'})
            with original_open(request, timeout=5) as response:
                body = response.read().decode()
                self.assertIn('text/event-stream', response.headers['Content-Type'])
        self.assertIn('ses_own', body)
        self.assertNotIn('ses_other', body)
        self.assertNotIn('private-own-text', body)
        self.assertNotIn('private-other-text', body)


if __name__ == '__main__':
    unittest.main()
