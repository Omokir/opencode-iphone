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
from codex_usage import CodexUsage
from files import FileBrowser, FileError
from events import session_hint
from devices import DeviceTokens
from chat_search import search_page
from power import NotebookPower
from resume import ResumableInbox
from inbox import PhoneInbox
from storage import storage_status

STATE = Path.home() / '.local/state/opencode-iphone'
SERVICE_CONFIG = Path.home() / '.config/opencode/service.json'
PAIR_LOCK = threading.Lock()
ATTEMPTS = []
MAX_BODY = 16 * 1024 * 1024
ENDPOINT_LOCK = threading.Lock()
CORE_ENDPOINT = None
CORE_CHECKED_AT = 0
STREAM_SLOTS = threading.BoundedSemaphore(8)
SEARCH_SLOTS = threading.BoundedSemaphore(2)
RULES = {
    'GET': [r'/api/info', r'/api/session', r'/api/session/ses[^/]+',
            r'/api/session/ses[^/]+/(message|permission|form)', r'/api/session/ses[^/]+/message/msg[^/]+',
            r'/phone/status', r'/phone/catalog', r'/phone/control/status', r'/phone/codex/usage', r'/phone/devices', r'/phone/power/status',
            r'/phone/files/(roots|list|download|receipt|context)', r'/phone/inbox/(verify|progress)', r'/phone/session/ses[^/]+/(events|search)'],
    'POST': [r'/api/session', r'/api/session/ses[^/]+/(prompt|interrupt|agent|model)',
             r'/api/session/ses[^/]+/permission/[^/]+/reply', r'/api/session/ses[^/]+/form/[^/]+/reply',
             r'/phone/mode', r'/phone/control/(start|stop)', r'/phone/files/upload', r'/phone/inbox/(prepare|upload|chunk|commit)', r'/phone/devices/revoke', r'/phone/power/(prepare|off)'],
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


def pair(code, name='iPhone'):
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
        token = DeviceTokens(STATE).issue(name)
        file.unlink()
        return 200, {'token': token}


def core_request(method, path, data=None):
    global CORE_ENDPOINT, CORE_CHECKED_AT
    with ENDPOINT_LOCK:
        if CORE_ENDPOINT is None or time.monotonic() - CORE_CHECKED_AT > 2:
            CORE_ENDPOINT = subprocess.check_output(['opencode', 'service', 'status'], text=True, timeout=15).strip()
            CORE_CHECKED_AT = time.monotonic()
        url = CORE_ENDPOINT
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != 'http' or parsed.hostname not in ('127.0.0.1', 'localhost', '::1'):
        raise ValueError('Managed service is not loopback')
    password = json.loads(SERVICE_CONFIG.read_text())['password']
    auth = base64.b64encode(('opencode:' + password).encode()).decode()
    return urllib.request.Request(url.rstrip('/') + path, data=data, method=method,
                                    headers={'Authorization': 'Basic ' + auth,
                                             'Content-Type': 'application/json'})
def upstream(method, path, data):
    global CORE_ENDPOINT
    try:
        with urllib.request.urlopen(core_request(method, path, data), timeout=30) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.read()
    except (urllib.error.URLError, TimeoutError, ConnectionError):
        with ENDPOINT_LOCK:
            CORE_ENDPOINT = None
        # Never replay writes with uncertain admission. Caller inspects state.
        raise


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


def mobile_messages(body):
    value = json.loads(body)
    messages = value.get('data')
    if isinstance(messages, dict):
        messages = [messages]
    if not isinstance(messages, list):
        return body
    for message in messages:
        if not isinstance(message, dict):
            continue
        if isinstance(message.get('files'), list):
            # Metadata is enough for history. Do not resend base64 attachment
            # contents on every live refresh; file-browser downloads are separate.
            message['files'] = [{key: item[key] for key in ('name', 'mime') if key in item}
                                for item in message['files'] if isinstance(item, dict)]
        for part in message.get('content', []):
            if isinstance(part, dict) and part.get('type') == 'tool' and isinstance(part.get('state'), dict):
                state = part['state']
                content = state.pop('content', None)
                # Bounded text preview, never inline binary/tool attachment data.
                if isinstance(content, list):
                    text = '\n'.join(item.get('text', '')[:2048] for item in content[:8]
                                     if isinstance(item, dict) and isinstance(item.get('text'), str))
                    if text:
                        state['detail'] = text[:8192] + ('\n[prévia limitada]' if len(text) > 8192 else '')
                if state.get('status') not in ('running', 'streaming'):
                    state.pop('input', None)
    return json.dumps(value).encode()


def mobile_history_path(path):
    parsed = urllib.parse.urlsplit(path)
    if not re.fullmatch(r'/api/session/ses[^/]+/message', parsed.path):
        return path
    query = urllib.parse.parse_qs(parsed.query)
    # First screen/foreground reconciliation stays small. Cursor pagination
    # and the explicit assistant-only live page retain their requested sizes.
    if 'cursor' not in query and 'type' not in query and query.get('order') == ['desc']:
        try:
            if int(query.get('limit', ['50'])[0]) > 15:
                query['limit'] = ['15']
                return parsed.path + '?' + urllib.parse.urlencode(query, doseq=True)
        except ValueError:
            pass
    return path


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

    def stream_events(self, session_id):
        # Stream setup is read-only and authorized exactly like session history.
        request = core_request('GET', '/api/event')
        request.add_header('Accept', 'text/event-stream')
        with urllib.request.urlopen(request, timeout=20) as response:
            self.send_response(200)
            self.send_header('Content-Type', 'text/event-stream; charset=utf-8')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Accel-Buffering', 'no')
            self.send_header('Connection', 'close')
            self.end_headers()
            self.wfile.write(b'event: connected\ndata: {"type":"connected"}\n\n')
            self.wfile.flush()
            started = time.monotonic()
            data = []
            oversized = False
            try:
                while time.monotonic() - started < 50:
                    line = response.readline(262145)
                    if not line:
                        break
                    if len(line) >= 262145:
                        oversized = True
                        continue
                    if line.strip() == b'':
                        if data and not oversized:
                            hint = session_hint('\n'.join(data), session_id)
                            if hint:
                                packet = 'event: changed\ndata: ' + json.dumps(hint) + '\n\n'
                                self.wfile.write(packet.encode())
                                self.wfile.flush()
                        data = []
                        oversized = False
                    elif line.startswith(b'data:') and not oversized:
                        if sum(map(len, data)) + len(line) > 262144:
                            oversized = True
                        else:
                            data.append(line[5:].decode('utf-8', 'replace').strip())
            except (TimeoutError, OSError):
                pass

    def handle_request(self):
        try:
            if self.headers.get('Origin'):
                return self.reply(403, {'error': 'Native clients only'})
            path = urllib.parse.urlsplit(self.path).path
            if not self.path.startswith('/') or '%' in path or '..' in path:
                return self.reply(400, {'error': 'Invalid path'})
            length = int(self.headers.get('Content-Length', '0'))
            maximum = self.server.files.max_bytes if path in ('/phone/files/upload', '/phone/inbox/upload') else MAX_BODY
            if length < 0 or (path != '/phone/inbox/upload' and length > maximum) or self.headers.get('Transfer-Encoding'):
                return self.reply(413, {'error': 'Request too large'})
            self.connection.settimeout(10)
            if path == '/pair' and self.command == 'POST':
                if length > 1024:
                    return self.reply(413, {'error': 'Pairing request too large'})
                body = self.rfile.read(length)
                payload = json.loads(body)
                return self.reply(*pair(payload.get('code', ''), payload.get('name', 'iPhone')))
            auth = self.headers.get('Authorization', '')
            device_tokens = DeviceTokens(STATE)
            current_device = device_tokens.identify(auth[7:] if auth.startswith('Bearer ') else '')
            if current_device is None:
                return self.reply(401, {'error': 'Pareie novamente no notebook.'})
            if not allowed(self.command, path):
                return self.reply(403, {'error': 'Route not available to mobile client'})
            search = re.fullmatch(r'/phone/session/(ses[^/]+)/search', path)
            if search:
                query = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
                text = query.get('q', [''])[0].strip()
                if not 1 <= len(text) <= 200:
                    return self.reply(400, {'error': 'Busca deve ter entre 1 e 200 caracteres.'})
                if not SEARCH_SLOTS.acquire(blocking=False):
                    return self.reply(429, {'error': 'Outra busca está em andamento. Tente novamente.'})
                try:
                    params = {'limit': '15'}
                    cursor = query.get('cursor', [''])[0]
                    if cursor:
                        if len(cursor) > 8192:
                            return self.reply(400, {'error': 'Cursor inválido.'})
                        params['cursor'] = cursor
                    else:
                        params['order'] = 'desc'
                    code, raw = upstream('GET', '/api/session/' + search[1] + '/message?' + urllib.parse.urlencode(params), None)
                    if code != 200:
                        return self.reply(code, raw)
                    return self.reply(200, search_page(json.loads(raw), text))
                finally:
                    SEARCH_SLOTS.release()
            stream = re.fullmatch(r'/phone/session/(ses[^/]+)/events', path)
            if stream:
                if not STREAM_SLOTS.acquire(blocking=False):
                    return self.reply(429, {'error': 'Muitas conexões de atualização. Aguarde e tente novamente.'})
                try:
                    return self.stream_events(stream[1])
                finally:
                    STREAM_SLOTS.release()
            if path.startswith('/phone/inbox/'):
                query = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
                relative = query.get('path', [''])[0]
                if path.endswith('/progress'):
                    return self.reply(200, self.server.resumable.progress(relative, query.get('id', [''])[0],
                        int(query.get('size', ['-1'])[0]), query.get('sha256', [''])[0]))
                if path.endswith('/chunk'):
                    if length > self.server.resumable.chunk_bytes or self.headers.get('Content-Type') != 'application/octet-stream':
                        return self.reply(400, {'error': 'Bloco inválido.'})
                    chunk = self.rfile.read(length)
                    if len(chunk) != length:
                        return self.reply(400, {'error': 'Bloco incompleto.'})
                    return self.reply(200, self.server.resumable.append(relative, query.get('id', [''])[0],
                        int(query.get('size', ['-1'])[0]), query.get('sha256', [''])[0],
                        int(query.get('offset', ['-1'])[0]), chunk, self.headers.get('X-Chunk-SHA256', '')))
                if path.endswith('/commit'):
                    if length:
                        return self.reply(400, {'error': 'Sem corpo nesta operação.'})
                    self.connection.settimeout(3600)
                    return self.reply(200, self.server.resumable.commit(relative, query.get('id', [''])[0],
                        int(query.get('size', ['-1'])[0]), query.get('sha256', [''])[0]))
                if path.endswith('/prepare'):
                    if length:
                        return self.reply(400, {'error': 'Sem corpo nesta operação.'})
                    return self.reply(200, self.server.inbox.prepare())
                if path.endswith('/verify'):
                    return self.reply(200, self.server.inbox.verify(relative, query.get('id', [''])[0]))
                if self.headers.get('Content-Type', '').split(';')[0] != 'application/octet-stream':
                    return self.reply(415, {'error': 'Envio binário obrigatório.'})
                return self.reply(200, self.server.inbox.upload(relative, self.rfile, length,
                    self.headers.get('X-Upload-ID', ''), self.headers.get('X-Content-SHA256', '')))
            if path.startswith('/phone/files/'):
                query = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
                root = query.get('root', ['home'])[0]
                relative = query.get('path', [''])[0]
                if path.endswith('/roots'):
                    return self.reply(200, self.server.files.root_list())
                if path.endswith('/context'):
                    return self.reply(200, self.server.files.context(query.get('directory', [''])[0]))
                if path.endswith('/list'):
                    return self.reply(200, self.server.files.listing(root, relative))
                if path.endswith('/receipt'):
                    return self.reply(200, self.server.files.receipt(query.get('id', [''])[0]))
                if path.endswith('/download'):
                    with self.server.files.download(root, relative, self.headers.get('If-Match')) as result:
                        self.send_response(200)
                        self.send_header('Content-Type', result['mime'])
                        self.send_header('Content-Length', str(result['size']))
                        self.send_header('Cache-Control', 'no-store')
                        self.send_header('X-Content-SHA256', result['sha256'])
                        self.send_header('ETag', result['version'])
                        self.send_header('Content-Disposition', "attachment; filename*=UTF-8''" + urllib.parse.quote(result['name'], safe=''))
                        self.end_headers()
                        while chunk := result['stream'].read(65536):
                            self.wfile.write(chunk)
                    return
                if path.endswith('/upload'):
                    if self.headers.get('Content-Type', '').split(';')[0] != 'application/octet-stream':
                        return self.reply(415, {'error': 'Envio precisa usar application/octet-stream.'})
                    if self.headers.get('If-None-Match') == '*':
                        expected = '*'
                    else:
                        expected = self.headers.get('If-Match')
                    result = self.server.files.upload(root, relative, self.rfile, length,
                        self.headers.get('X-Upload-ID', ''), self.headers.get('X-Content-SHA256', ''), expected)
                    return self.reply(200, result)
            body = self.rfile.read(length) if length else None
            if path == '/phone/power/status':
                return self.reply(200, self.server.power.status())
            if path == '/phone/power/prepare':
                return self.reply(*self.server.power.prepare(current_device))
            if path == '/phone/power/off':
                return self.reply(*self.server.power.power_off(current_device, json.loads(body or b'{}').get('ticket')))
            if path == '/phone/devices':
                return self.reply(200, device_tokens.listing(current_device))
            if path == '/phone/devices/revoke':
                payload = json.loads(body or b'{}')
                identifier = payload.get('id')
                if not isinstance(identifier, str) or len(identifier) > 64:
                    return self.reply(400, {'error': 'Identificador inválido.'})
                return self.reply(200, device_tokens.revoke(identifier))
            control = self.server.phone_control
            if path == '/phone/codex/usage':
                query = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
                return self.reply(200, self.server.codex_usage.get(refresh=query.get('refresh') == ['1']))
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
                return self.reply(200, {'awake': active, 'battery': battery_status(), 'storage': storage_status()})
            if path == '/phone/mode':
                value = json.loads(body or b'{}').get('awake')
                if not isinstance(value, bool):
                    return self.reply(400, {'error': 'awake must be a boolean'})
                subprocess.run(['systemctl', '--user', 'start' if value else 'stop',
                                'opencode-phone-mode.service'], check=True, timeout=15)
                return self.reply(200, {'awake': value})
            if self.command == 'POST' and path == '/api/session':
                body = session_defaults(body)
            proxy_path = mobile_history_path(self.path) if self.command == 'GET' else self.path
            status, result = upstream(self.command, proxy_path, body)
            if status == 200 and self.command == 'GET' and re.fullmatch(r'/api/session/ses[^/]+/message(?:/msg[^/]+)?', path):
                result = mobile_messages(result)
            return self.reply(status, result)
        except FileError as error:
            self.reply(error.status, error.body)
        except (BrokenPipeError, ConnectionResetError):
            pass
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
    server.codex_usage = CodexUsage()
    server.files = FileBrowser(STATE)
    server.inbox = PhoneInbox(STATE)
    server.resumable = ResumableInbox(server.inbox)
    server.power = NotebookPower()
    server.daemon_threads = True
    server.serve_forever()
