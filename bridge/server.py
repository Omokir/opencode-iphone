#!/usr/bin/env python3
"""Private, token-authenticated mobile gateway. Never listens beyond loopback."""
import base64
import hmac
import json
import os
from pathlib import Path
import re
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from phone_control import PhoneControl
from battery import battery_status

STATE = Path.home() / '.local/state/opencode-iphone'
SERVICE_CONFIG = Path.home() / '.config/opencode/service.json'
PAIR_LOCK = threading.Lock()
ATTEMPTS = []
MAX_BODY = 16 * 1024 * 1024
RULES = {
    'GET': [r'/api/info', r'/api/session', r'/api/session/ses[^/]+',
            r'/api/session/ses[^/]+/(message|permission|form)', r'/api/session/ses[^/]+/message/msg[^/]+',
            r'/phone/status', r'/phone/catalog', r'/phone/control/status'],
    'POST': [r'/api/session', r'/api/session/ses[^/]+/(prompt|interrupt|agent|model)',
             r'/api/session/ses[^/]+/permission/[^/]+/reply', r'/api/session/ses[^/]+/form/[^/]+/reply',
             r'/phone/mode', r'/phone/control/(start|stop)'],
    'PATCH': [r'/api/session/ses[^/]+'],
}


def allowed(method, path):
    return any(re.fullmatch(pattern, path) for pattern in RULES.get(method, []))


def secret():
    return (STATE / 'token.secret').read_text().strip()


def session_defaults(body):
    payload = json.loads(body or b'{}')
    file = STATE / 'defaults.json'
    if file.exists():
        defaults = json.loads(file.read_text())
        for key in ('agent', 'model'):
            if key in defaults and not payload.get(key):
                payload[key] = defaults[key]
    return json.dumps(payload).encode()


def pair(code):
    with PAIR_LOCK:
        now = time.time()
        ATTEMPTS[:] = [t for t in ATTEMPTS if now - t < 60]
        if len(ATTEMPTS) >= 5:
            return 429, {'error': 'Muitas tentativas. Aguarde um minuto.'}
        ATTEMPTS.append(now)
        file = STATE / 'pairing.json'
        if not file.exists():
            return 401, {'error': 'Gere um novo código no notebook.'}
        entry = json.loads(file.read_text())
        if entry['expires'] < now or not hmac.compare_digest(str(code), entry['code']):
            return 401, {'error': 'Código inválido ou expirado.'}
        file.unlink()
        return 200, {'token': secret()}


def upstream(method, path, data):
    # Resolve the managed service every time; its port can change on restart.
    url = subprocess.check_output(['opencode', 'service', 'status'], text=True, timeout=15).strip()
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != 'http' or parsed.hostname not in ('127.0.0.1', 'localhost', '::1'):
        raise ValueError('Managed service is not loopback')
    password = json.loads(SERVICE_CONFIG.read_text())['password']
    auth = base64.b64encode(('opencode:' + password).encode()).decode()
    request = urllib.request.Request(url.rstrip('/') + path, data=data, method=method,
                                    headers={'Authorization': 'Basic ' + auth,
                                             'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.read()


def catalog(directory):
    if not directory.startswith('/') or len(directory) > 4096:
        raise ValueError('Invalid directory')
    query = '?' + urllib.parse.urlencode({'location[directory]': directory})
    result = {}
    # Only expose display metadata, never provider headers/settings or agent prompts.
    for kind in ('model', 'agent'):
        status, body = upstream('GET', '/api/' + kind + query, None)
        if status != 200:
            return status, body
        records = json.loads(body)['data']
        if kind == 'model':
            result['models'] = [
                {key: record[key] for key in ('id', 'providerID', 'name', 'capabilities', 'variants', 'status')}
                for record in records if record.get('enabled') and record.get('status') != 'deprecated'
            ]
            for record in result['models']:
                record['capabilities'] = {'input': record['capabilities'].get('input', [])}
                record['variants'] = [{'id': variant['id']} for variant in record['variants']]
        else:
            result['agents'] = [
                {key: record[key] for key in ('id', 'name')}
                for record in records if not record.get('hidden') and record.get('mode') in ('primary', 'all')
            ]
    return 200, result


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass  # No URLs, prompts, tokens or response content in access logs.

    def reply(self, status, value):
        body = value if isinstance(value, bytes) else json.dumps(value).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def handle_request(self):
        try:
            if self.headers.get('Origin'):
                return self.reply(403, {'error': 'Native clients only'})
            path = urllib.parse.urlsplit(self.path).path
            if not self.path.startswith('/') or '%' in path or '..' in path:
                return self.reply(400, {'error': 'Invalid path'})
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 <= length <= MAX_BODY or self.headers.get('Transfer-Encoding'):
                return self.reply(413, {'error': 'Request too large'})
            self.connection.settimeout(10)
            if path == '/pair' and self.command == 'POST':
                if length > 1024:
                    return self.reply(413, {'error': 'Pairing request too large'})
                body = self.rfile.read(length)
                return self.reply(*pair(json.loads(body).get('code', '')))
            auth = self.headers.get('Authorization', '')
            if not hmac.compare_digest(auth, 'Bearer ' + secret()):
                return self.reply(401, {'error': 'Pareie novamente no notebook.'})
            if not allowed(self.command, path):
                return self.reply(403, {'error': 'Route not available to mobile client'})
            body = self.rfile.read(length) if length else None
            control = self.server.phone_control
            if path == '/phone/control/status':
                return self.reply(200, control.status())
            if path == '/phone/control/start':
                return self.reply(*control.start())
            if path == '/phone/control/stop':
                return self.reply(*control.stop())
            session_match = re.match(r'/api/session/(ses[^/]+)', path)
            if session_match and control.is_control_session(session_match[1]):
                payload = json.loads(body or b'{}') if self.command == 'POST' else {}
                if '/permission/' in path and path.endswith('/reply') and payload.get('decision') not in ('once', 'reject'):
                    return self.reply(403, {'error': 'Controle aceita apenas permitir uma vez ou negar.'})
                if path.endswith('/agent') and payload.get('agent') not in ('build', 'plan'):
                    return self.reply(403, {'error': 'Conversa de controle usa apenas Build ou Plan.'})
                if path.endswith('/prompt') or ('/form/' in path and path.endswith('/reply')):
                    state = control.state()
                    if state.get('enabled') is not True or state.get('expiresAt', 0) <= time.time():
                        return self.reply(409, {'error': 'Automação pausada ou expirada. Libere novamente no painel do iPhone.'})
            if path == '/phone/catalog':
                query = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
                return self.reply(*catalog(query.get('directory', [str(Path.home())])[0]))
            if self.command == 'PATCH':
                payload = json.loads(body or b'{}')
                if set(payload) != {'title'} or not isinstance(payload['title'], str) or not 1 <= len(payload['title'].strip()) <= 200:
                    return self.reply(400, {'error': 'Nome deve ter entre 1 e 200 caracteres.'})
                body = json.dumps({'title': payload['title'].strip()}).encode()
            if path == '/phone/status':
                active = subprocess.run(['systemctl', '--user', 'is-active', '--quiet',
                                         'opencode-phone-mode.service']).returncode == 0
                return self.reply(200, {'awake': active, 'battery': battery_status()})
            if path == '/phone/mode':
                value = json.loads(body or b'{}').get('awake')
                if not isinstance(value, bool):
                    return self.reply(400, {'error': 'awake must be a boolean'})
                subprocess.run(['systemctl', '--user', 'start' if value else 'stop',
                                'opencode-phone-mode.service'], check=True, timeout=15)
                return self.reply(200, {'awake': value})
            if self.command == 'POST' and path == '/api/session':
                body = session_defaults(body)
            return self.reply(*upstream(self.command, self.path, body))
        except (ValueError, TypeError, json.JSONDecodeError):
            self.reply(400, {'error': 'Invalid request'})
        except Exception:
            self.reply(503, {'error': 'OpenCode indisponível. Verifique serviço no notebook.'})

    do_GET = handle_request
    do_POST = handle_request
    do_PATCH = handle_request


if __name__ == '__main__':
    os.umask(0o077)
    server = ThreadingHTTPServer(('127.0.0.1', 49375), Handler)
    server.phone_control = PhoneControl(STATE, upstream)
    server.daemon_threads = True
    server.serve_forever()
