"""Synthetic loopback gateway, extracted from the original preview test fixture.

Desktop tests must not depend on the unpublished web-preview package.
"""
import hashlib
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading


class FixtureGateway(BaseHTTPRequestHandler):
    calls = []

    def log_message(self, *args):
        pass

    def route(self):
        body = self.rfile.read(int(self.headers.get('Content-Length', 0)))
        self.calls.append((self.command, self.path, self.headers.get('Authorization'), body))
        if self.path == '/pair':
            code = json.loads(body)['code']
            status, result = (200, {'token': 'fixture-secret-only'}) if code == '123456' else (403, {'error': 'no'})
        elif self.headers.get('Authorization') != 'Bearer fixture-secret-only':
            status, result = 401, {'error': 'no token'}
        elif self.path == '/api/experimental/schedule?disabled=true':
            status, result = 403, {'_tag': 'FixtureError', 'message': 'Scheduled tasks are disabled; set experimental.schedules in config'}
        elif self.path == '/api/experimental/voice/models':
            status, result = 200, {'data': {'models': [{'model': 'gpt-realtime-2.1', 'available': True, 'transports': ['webrtc']}]}}
        elif self.path == '/api/experimental/voice/session':
            status, result = 200, {'data': {'transport': {'type': 'webrtc', 'sdp': 'v=0\r\ns=fixture-only\r\n'}}}
        elif self.path.startswith('/phone/files/download'):
            raw = b'fixture file\n'
            self.send_response(200)
            self.send_header('Content-Length', str(len(raw)))
            self.send_header('X-Content-SHA256', '0'*64 if 'corrupt=true' in self.path else hashlib.sha256(raw).hexdigest())
            self.end_headers(); self.wfile.write(raw); return
        elif self.path.startswith('/phone/files/context'):
            status, result = 200, {'root': 'home', 'path': 'fixture'}
        elif self.path.startswith('/phone/files/list'):
            status, result = 200, {'root': 'home', 'path': 'fixture', 'parent': '', 'entries': [{'name': 'result.txt', 'path': 'fixture/result.txt', 'kind': 'file', 'readable': True, 'version': 'fixture-v1'}]}
        elif self.path.startswith('/phone/files/roots'):
            status, result = 200, {'roots': [{'id': 'home', 'name': 'Fixture root'}]}
        elif self.path.startswith('/api/session') and '/message' not in self.path and '/permission' not in self.path and '/form' not in self.path and '/prompt' not in self.path:
            session = {'id': 'ses_connected', 'title': 'Gateway fixture', 'agent': 'build', 'metadata': {}, 'location': {'directory': '/fixture'}}
            status, result = 200, {'data': [session] if self.command == 'GET' and self.path.startswith('/api/session?') else session}
        elif '/message' in self.path:
            status, result = 200, {'data': [{'id': 'msg_fixture', 'type': 'assistant', 'text': 'Connected transport verified with isolated fixture.', 'time': {'created': 1, 'completed': 2}}]}
        elif '/permission' in self.path or '/form' in self.path:
            status, result = 200, {'data': []}
        elif self.path == '/phone/catalog':
            status, result = 200, {'models': []}
        elif self.path.startswith('/api/session/') and self.path.endswith('/prompt'):
            status, result = 200, {'accepted': True}
        else:
            status, result = 200, {'fixture': True}
        raw = json.dumps(result).encode()
        self.send_response(status); self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(raw))); self.end_headers(); self.wfile.write(raw)

    do_GET = route
    do_POST = route


def start_fixture(port=0):
    gateway = ThreadingHTTPServer(('127.0.0.1', port), FixtureGateway)
    gateway.daemon_threads = True
    threading.Thread(target=gateway.serve_forever, daemon=True).start()
    return gateway
