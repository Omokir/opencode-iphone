"""Start with a refused socket, return a private gateway, then interrupt reads.

Seeded drafts/uncertainty stay private. No POST/PATCH/DELETE is allowed by this
fixture, and no provider, scheduler, microphone or installed service is used.
"""
import copy
import argparse
import json
import os
from pathlib import Path
import socket
import sys
import threading
import time
import traceback
from http.server import ThreadingHTTPServer

sys.path.insert(0, str(Path(__file__).resolve().parent.parent/'preview'))
from transport_fixture import FixtureGateway
if os.environ.get('POCKET_TEST_INSTALL'):
    sys.path.insert(0, os.environ['POCKET_TEST_INSTALL'])
from main import Pocket, GLib
from backend import Gateway, Store

parser = argparse.ArgumentParser(); parser.add_argument('--empty', action='store_true'); args = parser.parse_args()


class ReconnectHandler(FixtureGateway):
    def reply(self, status, value):
        raw = json.dumps(value).encode(); self.send_response(status)
        self.send_header('Content-Type', 'application/json'); self.send_header('Content-Length', str(len(raw))); self.end_headers()
        try:
            self.wfile.write(raw)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def route(self):
        if self.command != 'GET':
            self.server.writes.append(self.path)
            return self.reply(403, {'error': 'Reconnect fixture permits reads only'})
        if self.headers.get('Authorization') != 'Bearer fixture-secret-only':
            return self.reply(401, {'error': 'Fixture auth required'})
        self.server.reads.append(self.path)
        if self.path.startswith('/api/session?'):
            self.server.list_reads += 1; self.server.active_lists += 1
            self.server.max_active_lists = max(self.server.max_active_lists, self.server.active_lists)
            self.server.list_started.set()
            try:
                self.server.release.wait(timeout=8)
                return self.reply(200, {'data': [] if args.empty else [{'id': 'ses_other', 'title': 'Other fixture chat', 'location': {'directory': '/fixture'}, 'metadata': {}}]})
            finally:
                self.server.active_lists -= 1
        if self.path == '/api/session/ses_connected':
            self.server.last_reads += 1
            if self.server.last_reads == 1:
                return self.reply(503, {'error': 'Fixture temporary last-chat outage'})
            return super().route()
        if '/message?' in self.path:
            if self.server.history_down:
                return self.reply(503, {'error': 'Fixture temporary history outage'})
            self.server.history_success += 1
            if self.server.user_admission:
                return self.reply(200, {'data': [self.server.user_admission]})
        if self.path == '/phone/catalog':
            return self.reply(200, {'models': [] if args.empty else [{'providerID': 'fixture', 'id': 'fixture-model', 'name': 'Recovered model'}]})
        return super().route()

    do_GET = route
    do_POST = route
    do_PATCH = route
    do_DELETE = route


reservation = socket.socket(); reservation.bind(('127.0.0.1', 0)); port = reservation.getsockname()[1]
root = Path('/scratch/reconnect-empty-state' if args.empty else '/scratch/reconnect-state')
seed = Store(root)
draft = {'text': 'unsent after outage', 'files': [{'name': 'note.txt', 'size': 4, 'uri': 'data:text/plain;base64,dGVzdA=='}]}
payload = None
if not args.empty:
    seed.data['drafts']['ses_connected'] = draft; seed.data['last'] = 'ses_connected'
    payload = seed.begin_prompt('ses_connected', draft); seed.mark_prompt(payload['id'], 'uncertain')
seed.save()
original = copy.deepcopy(draft)
app = Pocket(demo=False, state=root); app.client = Gateway(root, port=port); app.client.token = 'fixture-secret-only'
server = None; phase = 0; errors = []; deadline = time.monotonic()+50; held_at = None; success_before = None


def exception(*args):
    value = ''.join(traceback.format_exception(*args)); print(value, file=sys.stderr, flush=True); errors.append(value)
    if hasattr(app, 'window'):
        app.window.close()
    app.quit()


sys.excepthook = exception


def check():
    global server, phase, held_at, success_before
    if time.monotonic() > deadline:
        raise AssertionError(f'Reconnect timed out at {phase}; list reads={server.list_reads if server else None}; session={bool(app.session)}')
    if phase == 0 and hasattr(app, 'window') and len(app.errors) >= 2:
        assert app.session is None
        if not args.empty:
            assert app.store.data['drafts']['ses_connected'] == original
            assert app.store.pending_prompts('ses_connected') == [payload['id']]
        reservation.close()
        server = ThreadingHTTPServer(('127.0.0.1', port), ReconnectHandler); server.daemon_threads = True
        server.reads = []; server.writes = []; server.list_reads = 0; server.active_lists = 0; server.max_active_lists = 0
        server.history_down = False; server.history_success = 0; server.list_started = threading.Event(); server.release = threading.Event()
        server.last_reads = 0; server.user_admission = None
        threading.Thread(target=server.serve_forever, daemon=True).start(); phase = 1
        print('PASS: refused-socket startup does not create a conversation or discard local state.', flush=True)
    elif phase == 1 and server.list_started.is_set():
        held_at = time.monotonic(); phase = 2
    elif phase == 2 and time.monotonic()-held_at > 3.6:
        assert server.list_reads == 1 and server.max_active_lists == 1, 'Read retries must not overlap or flood the worker queue.'
        assert not server.writes
        server.release.set(); phase = 3
    elif phase == 3 and args.empty and app.read_gates['sessions'].ready and app.read_gates['catalog'].ready:
        assert app.session is None and not app.sessions and not server.writes
        assert 'Conectado' in app.status.get_text() and not app.notice.get_visible()
        assert not app.store.data['drafts'] and not app.store.data['outgoing']
        assert not app.catalog and server.reads.count('/phone/catalog') == 1
        print('PASS: a healthy empty gateway stays connected/empty; no automatic conversation, draft, pairing or prompt write.', flush=True)
        phase = 10; app.window.close(); app.quit(); return GLib.SOURCE_REMOVE
    elif phase == 3 and app.session and not app.refreshing and app.catalog:
        assert app.session['id'] == 'ses_connected'
        assert server.last_reads >= 2, 'Last-chat metadata must recover after its own outage; never substitute the first recent chat.'
        assert app.current_draft() == original
        assert app.store.pending_prompts('ses_connected') == [payload['id']]
        assert app.notice.get_visible() and 'sem confirmação' in app.notice.get_text()
        assert app.catalog[0]['id'] == 'fixture-model' and not server.writes and app.sent == 0
        server.history_down = True; success_before = server.history_success; phase = 4
        print('PASS: gateway return restores last chat and catalog via bounded single-flight reads; nothing is created or retransmitted.', flush=True)
    elif phase == 4 and any('temporary history outage' in error for error in app.errors):
        app.draft.get_buffer().set_text(original['text'] + ' — edited while offline')
        app.save_draft(); server.history_down = False; phase = 5
    elif phase == 5 and server.history_success > success_before and not app.refreshing and 'Conectado' in app.status.get_text():
        assert app.current_draft()['text'].endswith('edited while offline')
        assert app.current_draft()['files'] == original['files']
        assert app.current_draft()['requestID'] == payload['id']
        assert app.store.pending_prompts('ses_connected') == [payload['id']]
        assert 'sem confirmação' in app.notice.get_text() and not server.writes and app.sent == 0
        assert Store(root).data['drafts']['ses_connected']['text'].endswith('edited while offline')
        print('PASS: a second read outage recovers without losing local edits/attachments or uncertain state; zero write requests.', flush=True)
        server.user_admission = {'id': payload['id'], 'type': 'user', 'text': original['text'], 'time': {'created': 2}}
        phase = 6
    elif phase == 6 and not app.store.pending_prompts('ses_connected') and not app.refreshing:
        assert app.current_draft()['text'].endswith('edited while offline')
        assert not app.notice.get_visible()
        server.history_down = True; phase = 7
    elif phase == 7 and app.notice_owner == 'read:history':
        server.history_down = False; success_before = server.history_success; phase = 8
    elif phase == 8 and server.history_success > success_before and not app.refreshing:
        assert not app.notice.get_visible(), 'Recovered read failure must not leave a stale disconnected banner.'
        app.error('Fixture manual action warning'); success_before = server.history_success; phase = 9
    elif phase == 9 and server.history_success > success_before and not app.refreshing:
        assert app.notice.get_text() == 'Fixture manual action warning', 'A healthy background GET must not erase an unrelated action warning.'
        assert app.current_draft()['files'] == original['files'] and not server.writes and app.sent == 0
        print('PASS: admission read-back preserves edited draft; transient read banners clear on recovery but unrelated action warnings remain.', flush=True)
        app.window.close(); app.quit(); return GLib.SOURCE_REMOVE
    return GLib.SOURCE_CONTINUE


try:
    GLib.timeout_add(100, check); app.run([])
    assert not errors, errors
    assert phase == (10 if args.empty else 9)
finally:
    reservation.close()
    if server:
        server.release.set(); server.shutdown(); server.server_close()
