"""Expired fixture credentials, failed/delayed pairing and navigation recovery."""
import json
import os
from pathlib import Path
import sys
import threading
import time
import traceback
from http.server import ThreadingHTTPServer

sys.path.insert(0, str(Path(__file__).resolve().parent.parent/'preview'))
from transport_fixture import FixtureGateway
if os.environ.get('POCKET_TEST_INSTALL'):
    sys.path.insert(0, os.environ['POCKET_TEST_INSTALL'])
from main import Pocket, Gtk, GLib
from backend import Gateway, Store, atomic_json

SESSIONS = [{'id': 'ses_pair_a', 'title': 'Pair A', 'agent': 'build', 'metadata': {}, 'location': {'directory': '/fixture/a'}},
            {'id': 'ses_pair_b', 'title': 'Pair B', 'agent': 'plan', 'metadata': {}, 'location': {'directory': '/fixture/b'}}]


class Handler(FixtureGateway):
    def reply(self, status, value):
        raw = json.dumps(value).encode(); self.send_response(status)
        self.send_header('Content-Type', 'application/json'); self.send_header('Content-Length', str(len(raw))); self.end_headers(); self.wfile.write(raw)

    def route(self):
        path = self.path.split('?')[0]
        if path == '/pair' and self.command == 'POST':
            body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            self.server.pairs += 1
            if body['code'] == '111111':
                return self.reply(503, {'error': 'fixture pairing response unavailable'})
            assert body['code'] == '222222'
            self.server.started.set(); self.server.release.wait(timeout=8)
            return self.reply(200, {'token': 'fixture-secret-only'})
        if self.command != 'GET':
            self.server.unexpected.append(path)
            return self.reply(403, {'error': 'unexpected mutation'})
        if self.headers.get('Authorization') != 'Bearer fixture-secret-only':
            return self.reply(401, {'error': 'fixture credential expired'})
        if path == '/api/session':
            return self.reply(200, {'data': SESSIONS})
        for session in SESSIONS:
            if path == '/api/session/'+session['id']:
                return self.reply(200, {'data': session})
        return super().route()

    do_GET = route
    do_POST = route


server = ThreadingHTTPServer(('127.0.0.1', 0), Handler); server.daemon_threads = True
server.pairs = 0; server.unexpected = []; server.started = threading.Event(); server.release = threading.Event()
threading.Thread(target=server.serve_forever, daemon=True).start()
root = Path('/scratch/pairing-state'); store = Store(root)
store.data['last'] = SESSIONS[0]['id']; store.data['drafts'] = {s['id']: {'text': s['title']+' draft', 'files': []} for s in SESSIONS}; store.save()
atomic_json(root/'connection.json', {'token': 'fixture-expired-token'})
app = Pocket(demo=False, state=root); app.client = Gateway(root, port=server.server_port)
phase = 0; errors = []; dialog = None; code = None; submit = None; deadline = time.monotonic()+30


def walk(widget):
    yield widget
    child = widget.get_first_child()
    while child:
        yield from walk(child); child = child.get_next_sibling()


def exception(*args):
    errors.append(''.join(traceback.format_exception(*args))); print(errors[-1], file=sys.stderr)
    server.release.set(); app.quit()


sys.excepthook = exception


def check():
    global phase, dialog, code, submit
    if time.monotonic() > deadline:
        raise AssertionError(f'Pairing timeout {phase}; attempts={server.pairs}')
    if phase == 0 and hasattr(app, 'window') and app.errors:
        assert app.session is None
        app.settings(); dialog = app.dialogs[-1]
        code = next(w for w in walk(dialog) if isinstance(w, Gtk.Entry))
        submit = next(w for w in walk(dialog) if isinstance(w, Gtk.Button) and w.get_label() == 'Parear computador')
        code.set_text('111111'); submit.emit('clicked'); submit.emit('clicked'); phase = 1
    elif phase == 1 and server.pairs == 1 and not app.pairing_in_flight:
        assert not submit.get_sensitive()
        assert any(isinstance(w, Gtk.Label) and 'Gere outro código' in w.get_text() for w in walk(dialog))
        assert Gateway(root, port=server.server_port).token == 'fixture-expired-token'
        submit.emit('clicked'); assert server.pairs == 1
        code.set_text('222222'); assert submit.get_sensitive(); submit.emit('clicked'); phase = 2
    elif phase == 2 and server.started.is_set():
        assert server.pairs == 2
        app.open_chat(SESSIONS[1]); app.draft.get_buffer().set_text('B edited during delayed pairing')
        app.persist(); server.release.set(); phase = 3
    elif phase == 3 and dialog not in app.dialogs and not app.pairing_in_flight and app.read_gates['catalog'].ready and not app.refreshing:
        assert server.pairs == 2 and not server.unexpected
        assert app.session['id'] == 'ses_pair_b' and app.current_draft()['text'] == 'B edited during delayed pairing'
        restored = Store(root)
        assert restored.data['drafts']['ses_pair_a']['text'] == 'Pair A draft'
        assert restored.data['drafts']['ses_pair_b']['text'] == 'B edited during delayed pairing'
        client = Gateway(root, port=server.server_port)
        assert client.token == 'fixture-secret-only' and client.request('/api/session')['data'][0]['id'] == 'ses_pair_a'
        assert (root/'connection.json').stat().st_mode & 0o777 == 0o600
        print('PASS: expired credentials preserved drafts; failed pairing kept old private connection, blocked same-code/double-click replay; fresh code persisted new credentials with mode 0600.', flush=True)
        print('PASS: delayed success after navigation retained B selection/edits and A draft, resumed authenticated reads, made exactly two explicit pairing attempts and no provider/session mutation.', flush=True)
        app.window.close(); app.quit(); return GLib.SOURCE_REMOVE
    return GLib.SOURCE_CONTINUE


try:
    GLib.timeout_add(120, check); app.run([])
    assert not errors, errors
    assert phase == 3
finally:
    server.release.set(); server.shutdown(); server.server_close()
