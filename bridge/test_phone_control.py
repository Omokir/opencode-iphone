import json
from pathlib import Path
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import patch

from phone_control import PhoneControl, CONTROL_PERMISSIONS


class ControlTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        (self.root / 'workspace/.git').mkdir(parents=True)
        self.config = {'cli': '/fake/mobilecli', 'deviceID': 'local-phone',
                       'home': str(self.root / 'daemon'), 'workspace': str(self.root / 'workspace')}
        (self.root / 'automation-config.json').write_text(json.dumps(self.config))
        self.calls = []
        self.session = None
        self.controller = PhoneControl(self.root, self.upstream, run=self.run_command, clock=lambda: 1000)

    def tearDown(self):
        self.temporary.cleanup()

    def run_command(self, args, **kwargs):
        if args[1:] == ['devices']:
            self.assertTrue(kwargs['env']['MOBILECLI_HOME'].endswith('-metadata'))
            body = {'data': {'devices': [{'id': 'local-phone', 'name': 'Test iPhone', 'state': 'online'}]}}
        elif args[1:3] == ['agent', 'status']:
            body = {'status': 'ok'}
        else:
            self.assertEqual(args[1:], ['daemon', 'stop'])
            self.assertEqual(kwargs['env']['MOBILECLI_HOME'], self.config['home'])
            self.assertFalse(self.controller.state()['enabled'])
            body = {'status': 'ok'}
        return subprocess.CompletedProcess(args, 0, json.dumps(body), '')

    def upstream(self, method, path, data):
        self.calls.append((method, path, data))
        if path == '/api/session' and method == 'POST':
            payload = json.loads(data)
            self.session = {'id': 'ses_control', **payload}
            return 200, json.dumps({'data': self.session}).encode()
        if method == 'GET' and path == '/api/session/ses_control':
            return 200, json.dumps({'data': self.session}).encode()
        if path.endswith('/synthetic'):
            self.assertFalse(json.loads(data)['resume'])
            return 200, b'{"data":{"id":"synthetic"}}'
        if method == 'PATCH':
            return 204, b''
        if path == '/api/session/active':
            return 200, b'{"data":{}}'
        if path.endswith('/permission'):
            return 200, b'{"data":[]}'
        if path.endswith('/interrupt'):
            self.assertFalse(self.controller.state()['enabled'])
            return 200, b'{}'
        return 404, b'{"error":"not found"}'

    def test_missing_configuration_disables_start(self):
        (self.root / 'automation-config.json').unlink()
        self.assertEqual(self.controller.start()[0], 409)
        self.assertFalse(self.calls)

    def test_start_uses_isolated_workspace_and_restricted_permissions(self):
        status, body = self.controller.start()
        self.assertEqual(status, 200)
        self.assertEqual(body['data']['metadata'], {'phoneControl': True})
        self.assertEqual(body['data']['location']['directory'], self.config['workspace'])
        self.assertEqual(body['data']['permissions'], CONTROL_PERMISSIONS)
        state = self.controller.state()
        self.assertTrue(state['enabled'])
        self.assertEqual(state['expiresAt'], 1900)
        self.assertEqual(self.controller.state_file.stat().st_mode & 0o777, 0o600)

    def test_repeated_start_reuses_session_without_replaying_prompt(self):
        self.controller.start()
        self.controller.start()
        self.assertEqual(sum(method == 'POST' and path == '/api/session' for method, path, _ in self.calls), 1)
        self.assertEqual(sum(path.endswith('/synthetic') for _, path, _ in self.calls), 1)
        self.assertFalse(any(path.endswith('/prompt') for _, path, _ in self.calls))

    def test_stop_closes_gate_before_upstream_and_process_commands(self):
        self.controller.start()
        status, result = self.controller.stop()
        self.assertEqual(status, 200)
        self.assertFalse(result['enabled'])
        self.assertFalse(self.controller.state()['enabled'])

    def test_expired_gate_reports_disabled(self):
        self.controller.save({'enabled': True, 'expiresAt': 999})
        status = self.controller.status()
        self.assertFalse(status['enabled'])
        self.assertIsNone(status['device']['locked'])

    def test_corrupt_state_fails_closed(self):
        self.controller.state_file.write_text('not json')
        self.assertEqual(self.controller.state(), {})

    def test_no_other_devices_used(self):
        def wrong_device(args, **kwargs):
            return subprocess.CompletedProcess(args, 0, '{"data":{"devices":[{"id":"some-other-phone","state":"online"}]}}', '')
        self.controller.run = wrong_device
        self.assertEqual(self.controller.start()[0], 409)

    def test_stop_keeps_gate_closed_if_transport_fails(self):
        self.controller.save({'enabled': True, 'sessionID': 'ses_control', 'expiresAt': 1900})
        def fail(*_):
            raise OSError('network unavailable')
        self.controller.upstream = fail
        status, result = self.controller.stop()
        self.assertFalse(self.controller.state()['enabled'])
        self.assertEqual(status, 200)
        self.assertTrue(result['warnings'])

    def test_instructions_uncertain_response_does_not_create_again(self):
        original = self.controller.upstream
        def fail_synthetic(method, path, data):
            if path.endswith('/synthetic'):
                return 503, b'{"error":"unavailable"}'
            return original(method, path, data)
        self.controller.upstream = fail_synthetic
        self.assertEqual(self.controller.start()[0], 503)
        self.assertFalse(self.controller.state()['enabled'])
        self.assertEqual(self.controller.state()['sessionID'], 'ses_control')

    def test_stop_wins_over_start_already_in_flight(self):
        entered = threading.Event()
        release = threading.Event()
        original = self.controller.upstream
        result = []
        def slow_create(method, path, data):
            if method == 'POST' and path == '/api/session':
                entered.set()
                release.wait(timeout=5)
            return original(method, path, data)
        self.controller.upstream = slow_create
        thread = threading.Thread(target=lambda: result.append(self.controller.start()))
        thread.start()
        self.assertTrue(entered.wait(timeout=2))
        try:
            self.assertFalse(self.controller.stop()[1]['enabled'])
            self.assertFalse(self.controller.state()['enabled'])
        finally:
            release.set()
            thread.join(timeout=3)
        self.assertEqual(result[0][0], 409)
        self.assertFalse(self.controller.state()['enabled'])


if __name__ == '__main__':
    unittest.main()
