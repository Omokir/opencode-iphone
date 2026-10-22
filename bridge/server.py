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

STATE = Path.home() / '.local/state/opencode-iphone'
SERVICE_CONFIG = Path.home() / '.config/opencode/service.json'
PAIR_LOCK = threading.Lock()
ATTEMPTS = []
RULES = {
    'GET': [r'/api/info', r'/api/session', r'/api/session/ses[^/]+',
            r'/api/session/ses[^/]+/(message|permission)', r'/phone/status'],
    'POST': [r'/api/session', r'/api/session/ses[^/]+/(prompt|interrupt)',
             r'/api/session/ses[^/]+/permission/[^/]+/reply', r'/phone/mode'],
}


def allowed(method, path):
    return any(re.fullmatch(pattern, path) for pattern in RULES.get(method, []))


def secret():
    return (STATE / 'token.secret').read_text().strip()


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
            if not 0 <= length <= 262144 or self.headers.get('Transfer-Encoding'):
                return self.reply(413, {'error': 'Request too large'})
            self.connection.settimeout(10)
            if path == '/pair' and self.command == 'POST':
                body = self.rfile.read(length)
                return self.reply(*pair(json.loads(body).get('code', '')))
            auth = self.headers.get('Authorization', '')
            if not hmac.compare_digest(auth, 'Bearer ' + secret()):
                return self.reply(401, {'error': 'Pareie novamente no notebook.'})
            if not allowed(self.command, path):
                return self.reply(403, {'error': 'Route not available to mobile client'})
            body = self.rfile.read(length) if length else None
            if path == '/phone/status':
                active = subprocess.run(['systemctl', '--user', 'is-active', '--quiet',
                                         'opencode-phone-mode.service']).returncode == 0
                return self.reply(200, {'awake': active})
            if path == '/phone/mode':
                value = json.loads(body or b'{}').get('awake')
                if not isinstance(value, bool):
                    return self.reply(400, {'error': 'awake must be a boolean'})
                subprocess.run(['systemctl', '--user', 'start' if value else 'stop',
                                'opencode-phone-mode.service'], check=True, timeout=15)
                return self.reply(200, {'awake': value})
            return self.reply(*upstream(self.command, self.path, body))
        except (ValueError, TypeError, json.JSONDecodeError):
            self.reply(400, {'error': 'Invalid request'})
        except Exception:
            self.reply(503, {'error': 'OpenCode indisponível. Verifique serviço no notebook.'})

    do_GET = handle_request
    do_POST = handle_request


if __name__ == '__main__':
    os.umask(0o077)
    server = ThreadingHTTPServer(('127.0.0.1', 49375), Handler)
    server.daemon_threads = True
    server.serve_forever()
