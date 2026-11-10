"""Run only inside the documented offline OS sandbox, never against user service."""
import json
import base64
import os
from pathlib import Path
import socket
import re
import subprocess
import sys
import time
import threading
import urllib.parse
import urllib.request

release = Path(os.environ.get('KZL_TEST_RELEASE', '/app'))
assert str(release) in ('/app', '/release'), 'Only sandbox source/release paths permitted'
sys.path.insert(0, str(release / 'bridge'))
import server as bridge
sys.path.insert(0, str(release / 'desktop'))
from backend import Gateway
from llm_fixture import model_server

assert os.environ['HOME'] == '/scratch', 'Sandbox HOME required'
root = Path('/scratch')
a = root / 'client-a'; a.mkdir()
b = root / 'client-b'; b.mkdir()
config = root / '.config/opencode'; config.mkdir(parents=True)
plugin = config / 'plugins/kzl-center-connections'; plugin.mkdir(parents=True)
(plugin / 'package.json').write_text(json.dumps({'name': 'kzl-center-connections', 'type': 'module', 'exports': {'.': './index.js'}}))
(plugin / 'index.js').write_text("export { default } from " + json.dumps((release / 'plugins/kzl-connections.mjs').as_uri()) + '\n')
model = model_server()
threading.Thread(target=model.serve_forever, daemon=True).start()
os.environ['KZL_FIXTURE_KEY'] = 'offline-dummy-key'
(config / 'opencode.json').write_text(json.dumps({
    '$schema': 'https://opencode.ai/config.json',
    'providers': {'fixture': {'name': 'Offline fixture', 'env': ['KZL_FIXTURE_KEY'],
        'package': '@opencode/ai/providers/openai-compatible',
        'settings': {'baseURL': f'http://127.0.0.1:{model.server_port}/v1'},
        'models': {'fixture-model': {'capabilities': {'tools': True, 'input': ['text'], 'output': ['text']},
                                     'limit': {'context': 32768, 'output': 1024}}}}},
}))
with socket.socket() as sock:
    sock.bind(('127.0.0.1', 0)); port = sock.getsockname()[1]
base = 'http://127.0.0.1:' + str(port)
log = (root / 'opencode.log').open('w+')
process = subprocess.Popen(['/opencode', 'serve', '--hostname', '127.0.0.1', '--port', str(port)],
                           cwd=a, stdout=log, stderr=subprocess.STDOUT)


def core_http(method, path, body=None):
    # Read only this disposable server's generated credential, never user auth.
    output = (root / 'opencode.log').read_text()
    match = re.search(r'^server password (\S+)', output, re.MULTILINE)
    headers = {}
    if match:
        headers['Authorization'] = 'Basic ' + base64.b64encode(('opencode:' + match[1]).encode()).decode()
    headers['Content-Type'] = 'application/json'
    req = urllib.request.Request(base + path, headers=headers, method=method, data=body)
    return urllib.request.urlopen(req, timeout=10)


def request(path, directory=None, body=None):
    if directory:
        path += '?' + urllib.parse.urlencode({'location[directory]': str(directory)})
    with core_http('POST' if body is not None else 'GET', path, json.dumps(body).encode() if body is not None else None) as response:
        data = response.read()
        return json.loads(data) if data else None


def wait(check, label, seconds=30):
    end = time.monotonic() + seconds
    last = None
    while time.monotonic() < end:
        if process.poll() is not None:
            raise RuntimeError('OpenCode exited before ' + label)
        try:
            last = check()
            if last:
                print('PASS:', label, flush=True)
                return last
        except (OSError, ValueError) as error:
            last = type(error).__name__
        time.sleep(.25)
    raise AssertionError(label + ': ' + str(last))


try:
    wait(lambda: request('/api/info'), 'isolated OpenCode HTTP API ready')
    def upstream(method, path, body):
        try:
            with core_http(method, path, body) as response:
                return response.status, response.read()
        except urllib.error.HTTPError as error:
            return error.code, error.read()
    state = root / '.local/state/opencode-iphone'; state.mkdir(parents=True)
    bridge.STATE = state
    bridge.upstream = upstream
    http = bridge.ThreadingHTTPServer(('127.0.0.1', 0), bridge.Handler)
    http.phone_control = bridge.PhoneControl(state, upstream)
    http.daemon_threads = True
    threading.Thread(target=http.serve_forever, daemon=True).start()
    try:
        urllib.request.urlopen(f'http://127.0.0.1:{http.server_port}/phone/connections/registry', timeout=5)
        raise AssertionError('Gateway allowed unpaired client')
    except urllib.error.HTTPError as error:
        assert error.code == 401
    (state / 'pairing.json').write_text(json.dumps({'code': '123456', 'expires': time.time() + 60}))
    client = Gateway(root / 'desktop-client', port=http.server_port)
    client.pair('123456')
    assert not (state / 'pairing.json').exists()
    print('PASS: release gateway rejects unpaired access; desktop client pairs using one-time code', flush=True)
    route = '/phone/connections/registry'
    registry = client.request(route)['registry']
    assert registry['revision'] == 0
    saved = client.request(route, 'POST', {'revision': 0, 'operation': 'add', 'name': 'fixture', 'config': {'type': 'local', 'command': [
        '/usr/bin/python3', '/app/tests/mcp_fixture.py', '/scratch/mcp-events.jsonl']}})
    assert not saved['runtimeConfirmed'] and saved['registry']['servers']['fixture']['projects'] == []
    client.request(route, 'POST', {'revision': 1, 'operation': 'grant', 'name': 'fixture', 'directory': str(a)})
    print('PASS: paired desktop client persists MCP registration and explicit project grant through release gateway', flush=True)
    def connected():
        global last_mcp
        rows = request('/api/mcp', a)['data']
        last_mcp = rows
        return any(row['name'] == 'kzl_center_fixture' and row['status']['status'] == 'connected' for row in rows)
    wait(connected, 'granted project connects actual local MCP fixture')
    other = request('/api/mcp', b)['data']
    assert all(row['name'] != 'kzl_center_fixture' for row in other), other
    print('PASS: ungranted project has no managed fixture MCP', flush=True)
    events = (root / 'mcp-events.jsonl').read_text()
    assert 'initialize' in events and 'tools/list' in events
    assert 'tools/call' not in events
    print('PASS: real MCP handshake/catalog; registration executes no tools', flush=True)

    def call_count():
        return sum(json.loads(line)['method'] == 'tools/call' for line in (root / 'mcp-events.jsonl').read_text().splitlines())

    def new_turn(directory):
        session = client.request('/api/session', 'POST', {'location': {'directory': str(directory)},
            'model': {'providerID': 'fixture', 'id': 'fixture-model'},
            'permissions': [{'action': '*', 'resource': '*', 'effect': 'ask'}]})['data']
        sid = session['id']
        client.request('/api/session/' + sid + '/prompt', 'POST', {'text': 'Run only the synthetic fixture ping.'})
        return sid

    def permissions(sid):
        return client.request('/api/session/' + sid + '/permission')['data']

    denied = new_turn(a)
    pending = wait(lambda: permissions(denied), 'model-generated MCP call waits for explicit permission')
    assert call_count() == 0, 'Tool ran before approval'
    client.request('/api/session/' + denied + '/permission/' + pending[0]['id'] + '/reply', 'POST', {'decision': 'reject'})
    wait(lambda: not permissions(denied), 'explicit rejection settles permission request')
    assert call_count() == 0, 'Rejected tool executed'
    print('PASS: explicit rejection executes zero MCP tools', flush=True)

    allowed = new_turn(a)
    approved = 0
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline and call_count() == 0:
        for item in permissions(allowed):
            client.request('/api/session/' + allowed + '/permission/' + item['id'] + '/reply', 'POST', {'decision': 'once'})
            approved += 1
        time.sleep(.1)
    assert approved > 0 and call_count() == 1, (approved, call_count())
    print('PASS: allow-once executes exactly one real MCP tools/call', flush=True)

    client.request(route, 'POST', {'revision': 2, 'operation': 'revoke', 'name': 'fixture', 'directory': str(a)})
    wait(lambda: all(row['name'] != 'kzl_center_fixture' for row in request('/api/mcp', a)['data']),
         'persisted revoke removes managed MCP from actual OpenCode')
    before = call_count()
    revoked = new_turn(a)
    # Any outer Code Mode request can still need approval; permit that so the
    # test proves the removed MCP cannot execute even after the outer approval.
    until = time.monotonic() + 3
    while time.monotonic() < until:
        for item in permissions(revoked):
            client.request('/api/session/' + revoked + '/permission/' + item['id'] + '/reply', 'POST', {'decision': 'once'})
        time.sleep(.1)
    assert call_count() == before, 'Revoked MCP executed'
    print('PASS: model request after revocation produces zero additional MCP calls', flush=True)

    # Exercise the installed engine's actual credential contract with dummy
    # values only. This HOME has never contained a user account or real key.
    metadata = client.request('/phone/openai?' + urllib.parse.urlencode({'directory': str(a)}))
    print('PASS: actual OpenCode OpenAI methods discovered:', [m['type'] for m in metadata['methods']], flush=True)
    integration = metadata['integrationID']
    original = request('/api/credential', body={'id': 'fixture_existing', 'integrationID': integration,
        'label': 'Synthetic existing account', 'value': {'type': 'key', 'key': 'synthetic-existing-not-a-key'}})['data']
    assert original['active'] is True
    created = client.request('/phone/openai/key', 'POST', {'requestID': 'fixture_auth', 'directory': str(a), 'key': 'synthetic-new-not-a-key'})
    assert created['status'] == 'stored' and created['active'] is False
    # Credential reads are test-only against this empty disposable engine;
    # gateway production code never exposes or calls this endpoint.
    credentials = request('/api/credential')['data']
    assert next(c for c in credentials if c['id'] == 'fixture_existing')['active'] is True
    assert next(c for c in credentials if c['id'] == created['credentialID'])['active'] is False
    for file in (state / 'accounts').iterdir():
        assert b'synthetic-new-not-a-key' not in file.read_bytes()
    print('PASS: actual OpenCode stores dummy API credential inactive; existing active account preserved; gateway receipt contains no key', flush=True)
finally:
    if 'http' in globals():
        http.shutdown(); http.server_close()
    process.terminate()
    try: process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill(); process.wait(timeout=5)
    if sys.exc_info()[0]:
        # Read only synthetic metadata from this disposable engine.
        # The process has stopped, so use the last captured runtime response.
        print('Fixture MCP state:', globals().get('last_mcp'), file=sys.stderr)
        fixture_log = root / 'model-events.jsonl'
        if fixture_log.exists():
            print('Fixture model metadata:', fixture_log.read_text()[-6000:], file=sys.stderr)
        engine_log = root / '.local/share/opencode/log/opencode.log'
        if engine_log.exists():
            print('Fixture engine diagnostics:\n' + engine_log.read_text()[-12000:], file=sys.stderr)
        log.flush(); log.seek(0)
        output = re.sub(r'server password \S+', 'server password [redacted]', log.read())
        print('Fixture-only OpenCode log tail:\n' + output[-8000:], file=sys.stderr)
    log.close()
    model.shutdown(); model.server_close()
