"""Native command/skill/inbox faults and conversation switches; fixture only."""
import json
import os
from pathlib import Path
import sys
import threading
import time
import traceback
import urllib.parse
from http.server import ThreadingHTTPServer

sys.path.insert(0, str(Path(__file__).resolve().parent.parent/'preview'))
from transport_fixture import FixtureGateway
if os.environ.get('POCKET_TEST_INSTALL'):
    sys.path.insert(0, os.environ['POCKET_TEST_INSTALL'])
from main import Pocket, Gtk, GLib
from backend import Gateway, Store

SESSIONS = [{'id': 'ses_a', 'title': 'Project A', 'agent': 'build', 'metadata': {}, 'location': {'directory': '/fixture/project-a'}},
            {'id': 'ses_b', 'title': 'Project B', 'agent': 'build', 'metadata': {}, 'location': {'directory': '/fixture/project-b'}}]


class Handler(FixtureGateway):
    def reply(self, status, value=None):
        raw = b'' if value is None else json.dumps(value).encode()
        self.send_response(status); self.send_header('Content-Type', 'application/json'); self.send_header('Content-Length', str(len(raw))); self.end_headers()
        try:
            self.wfile.write(raw)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def route(self):
        path = urllib.parse.urlsplit(self.path).path
        if path == '/pair':
            return super().route()
        if self.headers.get('Authorization') != 'Bearer fixture-secret-only':
            return self.reply(401, {'error': 'Fixture auth required'})
        if self.command == 'GET':
            if path == '/api/session':
                return self.reply(200, {'data': SESSIONS})
            if path in ('/api/command', '/api/skill'):
                self.server.catalog_queries.append(urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query))
                return self.reply(200, {'data': [{'name': 'fixture_cmd'}] if path.endswith('command') else [{'id': 'fixture_skill', 'name': 'Fixture Skill'}]})
            if path.endswith('/inbox'):
                self.server.inbox_reads += 1
                rows = list(self.server.queue.values())
                if self.server.wrong_inbox_session:
                    rows = [dict(row, sessionID='ses_b') for row in rows]
                return self.reply(200, {'data': rows})
            if path.endswith(('/message', '/permission', '/form')):
                return self.reply(200, {'data': []})
            for session in SESSIONS:
                if path == '/api/session/'+session['id']:
                    return self.reply(200, {'data': session})
            return super().route()
        length = int(self.headers.get('Content-Length', 0)); assert length <= 65536
        body = json.loads(self.rfile.read(length) or b'{}')
        if path.endswith('/command'):
            self.server.actions.append((path, body)); self.server.failed_at = time.monotonic()
            return self.reply(503, {'error': 'Fixture lost command acknowledgement AFTER acceptance'})
        if path.endswith('/skill'):
            self.server.actions.append((path, body)); self.server.skill_started.set(); self.server.skill_release.wait(timeout=8)
            return self.reply(204)
        if path.endswith('/prompt'):
            self.server.prompt_posts.append((path, body))
            self.server.queue.setdefault(body['id'], {'id': body['id'], 'sessionID': path.split('/')[3], 'type': 'user', 'delivery': 'queue', 'payload': {'text': body['text']}, 'time': {'created': 1}})
            self.server.prompt_started.set(); self.server.prompt_release.wait(timeout=8)
            return self.reply(503, {'error': 'Fixture lost queued-message acknowledgement'})
        return self.reply(403, {'error': 'Unexpected fixture mutation'})

    do_GET = route
    do_POST = route


server = ThreadingHTTPServer(('127.0.0.1', 0), Handler); server.daemon_threads = True
server.actions = []; server.failed_at = None; server.prompt_posts = []; server.queue = {}; server.inbox_reads = 0; server.wrong_inbox_session = True; server.catalog_queries = []
server.skill_started = threading.Event(); server.skill_release = threading.Event(); server.prompt_started = threading.Event(); server.prompt_release = threading.Event()
threading.Thread(target=server.serve_forever, daemon=True).start()
root = Path('/scratch/actions-state'); seed = Store(root); seed.data['last'] = 'ses_a'; seed.data['drafts']['ses_b'] = {'text': 'B draft preserved', 'files': []}; seed.save()
app = Pocket(demo=False, state=root); app.client = Gateway(root, port=server.server_port); app.client.pair('123456')
phase = 0; errors = []; deadline = time.monotonic()+40; first_confirm = None; captured_binding = None; queue_reads = None


def walk(widget):
    yield widget
    child = widget.get_first_child()
    while child:
        yield from walk(child); child = child.get_next_sibling()


def find_button(text):
    return next(w for window in app.dialogs for w in walk(window) if isinstance(w, Gtk.Button) and w.get_label() == text)


def close_dialogs():
    for window in list(app.dialogs):
        window.close()


def exception(*args):
    value = ''.join(traceback.format_exception(*args)); print(value, file=sys.stderr, flush=True); errors.append(value); server.skill_release.set(); server.prompt_release.set()
    if hasattr(app, 'window'):
        app.window.close()
    app.quit()


sys.excepthook = exception


def check():
    global phase, first_confirm, captured_binding, queue_reads
    if time.monotonic() > deadline:
        raise AssertionError(f'Actions fixture timed out at {phase}; posts={len(server.actions)}, inbox={server.inbox_reads}')
    if phase == 0 and app.session and not app.refreshing:
        app.run_command({'name': 'fixture_cmd'}, app.request_path())
        entry = next(w for w in walk(app.dialogs[-1]) if isinstance(w, Gtk.Entry)); entry.set_text('snapshot one')
        find_button('Executar comando').emit('clicked'); first_confirm = find_button('Confirmar'); first_confirm.emit('clicked'); phase = 1
    elif phase == 1 and server.failed_at and time.monotonic()-server.failed_at > .4:
        assert not find_button('Executar comando').get_sensitive(), 'Uncertain command must be locked rather than offered for blind replay.'
        first_confirm.emit('clicked')
        assert len(server.actions) == 1
        records = app.store.action_records('ses_a'); assert records[0]['state'] == 'uncertain'
        close_dialogs(); app.run_command({'name': 'fixture_cmd'}, app.request_path())
        find_button('Executar comando').emit('clicked'); find_button('Confirmar').emit('clicked'); phase = 2
    elif phase == 2:
        assert len(server.actions) == 1
        close_dialogs(); captured_binding = app.action_binding()
        app.run_skill({'id': 'fixture_skill', 'name': 'Fixture Skill'}, captured_binding)
        find_button('Ativar skill').emit('clicked'); first_confirm = find_button('Confirmar')
        app.open_chat(SESSIONS[1]); first_confirm.emit('clicked'); phase = 3
    elif phase == 3:
        assert len(server.actions) == 1 and app.current_draft()['text'] == 'B draft preserved'
        close_dialogs(); app.open_chat(SESSIONS[0]); captured_binding = app.action_binding()
        app.run_skill({'id': 'fixture_skill', 'name': 'Fixture Skill'}, captured_binding)
        find_button('Ativar skill').emit('clicked'); find_button('Confirmar').emit('clicked'); phase = 4
        print('PASS: lost command acknowledgement locks replay across reopened dialogs; stale pre-confirm skill context causes no mutation.', flush=True)
    elif phase == 4 and server.skill_started.is_set():
        app.open_chat(SESSIONS[1]); server.skill_release.set(); phase = 5
    elif phase == 5 and any(r['kind'] == 'skill' and r['state'] == 'acknowledged' for r in app.store.action_records('ses_a')):
        assert app.session['id'] == 'ses_b' and app.current_draft()['text'] == 'B draft preserved'
        assert [p for p, _ in server.actions] == ['/api/session/ses_a/command', '/api/experimental/session/ses_a/skill']
        persisted = Store(root).action_records('ses_a'); assert len(persisted) == 2
        close_dialogs(); app.open_chat(SESSIONS[0]); app.draft.get_buffer().set_text('queued snapshot')
        app.send_button.emit('clicked'); phase = 6
        print('PASS: confirmed skill retained its original project and persisted acknowledgement after conversation switch.', flush=True)
    elif phase == 6 and server.prompt_started.is_set():
        app.open_chat(SESSIONS[1]); server.prompt_release.set(); phase = 7
    elif phase == 7 and not app.busy:
        assert app.current_draft()['text'] == 'B draft preserved' and len(server.prompt_posts) == 1
        app.open_chat(SESSIONS[0]); queue_reads = server.inbox_reads; app.resources(); phase = 8
    elif phase == 8 and server.inbox_reads > queue_reads:
        assert app.store.pending_prompts('ses_a'), 'Foreign-session inbox entry must not confirm or clear this request.'
        assert app.current_draft()['text'] == 'queued snapshot'
        server.wrong_inbox_session = False; queue_reads = server.inbox_reads
        find_button('Atualizar recursos').emit('clicked'); phase = 9
    elif phase == 9 and server.inbox_reads > queue_reads and not app.store.pending_prompts('ses_a'):
        assert app.current_draft()['text'] == '' and len(server.prompt_posts) == 1 and len(server.queue) == 1
        assert len(server.actions) == 2 and app.store.action_records('ses_a')[0]['sessionID'] == 'ses_a'
        assert all('location[directory]' in query and query['location[directory]'] == ['/fixture/project-a'] for query in server.catalog_queries)
        print('PASS: queued request survives lost acknowledgement/switch; only matching session/type inbox proof reconciles it, without retransmission or B-draft loss.', flush=True)
        print('PASS: all action paths and catalog reads remained bound to project A; fixture only, no real provider or tools.', flush=True)
        close_dialogs(); app.window.close(); app.quit(); return GLib.SOURCE_REMOVE
    return GLib.SOURCE_CONTINUE


try:
    GLib.timeout_add(120, check); app.run([])
    assert not errors, errors
    assert phase == 9
finally:
    server.skill_release.set(); server.prompt_release.set(); server.shutdown(); server.server_close()
