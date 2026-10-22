"""Opt-in local model integration test; may use configured provider credits.

Uses an offline MCP fixture, never the user's physical phone. Not run in CI.
"""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import uuid

project = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project / 'bridge'))
from phone_control import PhoneControl
from server import upstream

with tempfile.TemporaryDirectory(prefix='phone-policy-', dir='/tmp/opencode') as directory:
    root = Path(directory)
    workspace = root / 'workspace'
    workspace.mkdir()
    subprocess.run(['git', 'init', '--quiet', str(workspace)], check=True)
    marker = root / 'launch-executed'
    fixture = project / 'tests/fake-phone-mcp.mjs'
    (workspace / 'opencode.json').write_text(json.dumps({'$schema': 'https://opencode.ai/config.json', 'mcp': {'servers': {'iphone': {'type': 'local', 'command': ['node', str(fixture), str(marker)]}}}}))
    (root / 'automation-config.json').write_text(json.dumps({'cli': '/offline-fixture', 'deviceID': 'fixture-phone', 'home': str(root / 'daemon'), 'workspace': str(workspace)}))
    defaults = json.loads((Path.home() / '.local/state/opencode-iphone/defaults.json').read_text())
    (root / 'defaults.json').write_text(json.dumps({'model': defaults['model']}))
    def no_device_command(args, **kwargs):
        return subprocess.CompletedProcess(args, 0, '{"status":"ok"}', '')
    control = PhoneControl(root, upstream, run=no_device_command)
    control.device = lambda: {'connected': True, 'agentInstalled': True, 'name': 'Offline fixture', 'locked': None}
    status, response = control.start()
    assert status == 200, (status, response)
    session_id = response['data']['id']
    try:
        payload = {'id': 'msg_' + uuid.uuid4().hex, 'text': 'Teste offline das permissões. Liste dispositivos pelo iphone e solicite abrir com.apple.Preferences no fixture-phone usando mobile_launch_app. Aguarde autorização. Use somente iphone e nenhuma ferramenta alternativa. Não há aparelho real neste teste.'}
        status, _ = upstream('POST', f'/api/session/{session_id}/prompt', json.dumps(payload).encode())
        assert status == 200
        deadline = time.monotonic() + 90
        permission = None
        while time.monotonic() < deadline:
            status, data = upstream('GET', f'/api/session/{session_id}/permission', None)
            pending = json.loads(data).get('data', []) if status == 200 else []
            if pending:
                permission = pending[0]
                break
            if marker.exists():
                raise AssertionError('Simulated action executed without pending approval')
            time.sleep(1)
        if permission is None:
            status, data = upstream('GET', f'/api/session/{session_id}/message?limit=10&order=desc', None)
            messages = json.loads(data).get('data', []) if status == 200 else []
            print('Offline test outcomes:', [{'type': m['type'], 'error': m.get('error', {}).get('message')} for m in messages])
            raise AssertionError('No approval request reached')
        assert permission['action'] == 'iphone_mobile_launch_app', permission['action']
        assert not marker.exists()
        source = permission['source']
        status, data = upstream('GET', f'/api/session/{session_id}/message/{source["messageID"]}', None)
        message = json.loads(data)['data']
        part = next(p for p in message['content'] if p.get('id') == source['id'])
        assert part.get('state', {}).get('input') is not None
        status, _ = upstream('POST', f'/api/session/{session_id}/permission/{permission["id"]}/reply', b'{"decision":"reject"}')
        assert status in (200, 204)
        assert not marker.exists()
        print('PASS: real OpenCode requested one-action approval, arguments are reviewable, rejection did not execute offline launch.')
    finally:
        control.stop()
        upstream('DELETE', f'/api/session/{session_id}', None)
        print('Offline integration session removed. No real iPhone action was requested.')
