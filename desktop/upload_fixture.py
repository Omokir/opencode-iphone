"""Isolated HTTP fixture using the REAL gateway inbox/chunk/commit engines.

Never import bridge/server.py or discover any installed service/credentials.
"""
import json
from pathlib import Path
import sys
import threading
from http.server import ThreadingHTTPServer
import urllib.parse

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE / 'preview'))
from test_server import FixtureGateway
sys.path.insert(0, str(BASE / 'bridge'))
from files import FileError
from inbox import PhoneInbox
from resume import ResumableInbox


class UploadHandler(FixtureGateway):
    def reply(self, status, value):
        raw = json.dumps(value).encode()
        self.send_response(status); self.send_header('Content-Type', 'application/json'); self.send_header('Content-Length', str(len(raw)))
        self.end_headers(); self.wfile.write(raw)

    def route(self):
        parsed = urllib.parse.urlsplit(self.path)
        if not parsed.path.startswith('/phone/inbox/'):
            return super().route()
        if self.headers.get('Authorization') != 'Bearer fixture-secret-only':
            return self.reply(401, {'error': 'Fixture token required'})
        query = urllib.parse.parse_qs(parsed.query); action = parsed.path.rsplit('/', 1)[-1]
        length = int(self.headers.get('Content-Length', 0))
        self.server.requests.append({'action': action, 'offset': query.get('offset', [None])[0], 'length': length})
        try:
            if action == 'prepare':
                return self.reply(200, self.server.inbox.prepare())
            path, identifier = query['path'][0], query['id'][0]
            if action == 'verify':
                if self.server.verify_failure:
                    return self.reply(self.server.verify_failure, {'error': 'Fixture verification refused'})
                result = self.server.inbox.verify(path, identifier)
                if self.server.bad_receipt:
                    result['sha256'] = '0'*64
                return self.reply(200, result)
            size, digest = int(query['size'][0]), query['sha256'][0]
            if action == 'progress':
                result = self.server.resumable.progress(path, identifier, size, digest)
                return self.reply(200, self.server.bad_progress if self.server.bad_progress is not None else result)
            if action == 'chunk':
                if length > 4*1024*1024 or self.headers.get('Content-Type') != 'application/octet-stream':
                    return self.reply(400, {'error': 'Fixture invalid chunk'})
                chunk = self.rfile.read(length)
                result = self.server.resumable.append(path, identifier, size, digest, int(query['offset'][0]), chunk, self.headers.get('X-Chunk-SHA256', ''))
                self.server.first_chunk.set()
                if self.server.block_chunk:
                    self.server.continue_chunk.wait(timeout=10)
                if self.server.lose_chunk_once:
                    self.server.lose_chunk_once = False
                    return self.reply(503, {'error': 'Fixture lost acknowledgement AFTER durable chunk'})
                return self.reply(200, result)
            if action == 'commit':
                result = self.server.resumable.commit(path, identifier, size, digest)
                if self.server.lose_commit_once:
                    self.server.lose_commit_once = False
                    return self.reply(503, {'error': 'Fixture lost acknowledgement AFTER actual commit'})
                return self.reply(200, result)
            return self.reply(404, {'error': 'Fixture route missing'})
        except FileError as error:
            return self.reply(error.status, error.body)
        except (ValueError, KeyError):
            return self.reply(400, {'error': 'Invalid fixture request'})

    do_GET = route
    do_POST = route


def start_upload_fixture(root, chunk_bytes=64*1024):
    root = Path(root); home = root / 'gateway-home'; home.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer(('127.0.0.1', 0), UploadHandler); server.daemon_threads = True
    server.inbox = PhoneInbox(root / 'gateway-state', home=home)
    server.resumable = ResumableInbox(server.inbox); server.resumable.chunk_bytes = chunk_bytes
    server.home = home; server.requests = []; server.lose_chunk_once = False; server.lose_commit_once = False
    server.bad_progress = None; server.bad_receipt = False; server.verify_failure = None
    server.block_chunk = False; server.first_chunk = threading.Event(); server.continue_chunk = threading.Event()
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server
