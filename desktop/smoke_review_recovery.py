"""Kill owned GTK clients after synthetic review/creation admission, then restart.

The authenticated loopback fixture holds its HTTP reply. No real permissions,
tools, providers or installed service are used. Only Popen-owned children die.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import traceback
from http.server import ThreadingHTTPServer

sys.path.insert(0, str(Path(__file__).resolve().parent.parent/'preview'))
from test_server import FixtureGateway

SESSIONS = [{'id': 'ses_review_a', 'title': 'Review project A', 'agent': 'build', 'metadata': {}, 'location': {'directory': '/fixture/a'}},
            {'id': 'ses_review_b', 'title': 'Other project B', 'agent': 'plan', 'metadata': {}, 'location': {'directory': '/fixture/b'}}]
PERMISSION = {'id': 'per_recovery', 'message': 'Synthetic permission', 'source': {}}
FORM = {'id': 'form_recovery', 'title': 'Synthetic question', 'fields': [{'key': 'text', 'type': 'string', 'required': True, 'default': 'original answer'}]}


class Handler(FixtureGateway):
    def reply(self, status, value):
        raw = json.dumps(value).encode(); self.send_response(status)
        self.send_header('Content-Type', 'application/json'); self.send_header('Content-Length', str(len(raw))); self.end_headers()
        try:
            self.wfile.write(raw)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def route(self):
        path = self.path.split('?')[0]
        if path == '/pair':
            return super().route()
        if self.headers.get('Authorization') != 'Bearer fixture-secret-only':
            return self.reply(401, {'error': 'fixture authentication required'})
        if self.command == 'GET':
            if path == '/api/session':
                return self.reply(200, {'data': self.server.sessions})
            for session in self.server.sessions:
                if path == '/api/session/'+session['id']:
                    return self.reply(200, {'data': session})
            if path.endswith(('/message', '/permission', '/form')):
                return self.reply(200, {'data': []})
            return super().route()
        if self.command == 'POST' and (path.endswith('/reply') or path == '/api/session'):
            body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            result = {}
            if path == '/api/session':
                created = dict(SESSIONS[0], id='ses_created_recovery', title='Created before crash', location=body['location'])
                self.server.sessions.insert(0, created); result = {'data': created}
            self.server.posts.append((path, body)); self.server.accepted.set()
            self.server.release.wait(timeout=20)
            return self.reply(200, result)
        self.server.unexpected.append((self.command, path))
        return self.reply(403, {'error': 'unexpected fixture mutation'})

    do_GET = route
    do_POST = route
    do_PATCH = route


def child(kind, phase, root, port):
    if os.environ.get('POCKET_TEST_INSTALL'):
        sys.path.insert(0, os.environ['POCKET_TEST_INSTALL'])
    from main import Pocket, Gtk, GLib
    from backend import Gateway, Store
    root = Path(root)
    if phase == 'send':
        seed = Store(root); seed.data['last'] = 'ses_review_a'
        seed.data['drafts']['ses_review_b'] = {'text': 'B private draft preserved', 'files': []}; seed.save()
    app = Pocket(demo=False, state=root); app.client = Gateway(root, port=port)
    if phase == 'send':
        app.client.pair('123456')
    errors = []; step = 0; dialog = None; deadline = time.monotonic()+20
    def walk(widget):
        yield widget
        c = widget.get_first_child()
        while c:
            yield from walk(c); c = c.get_next_sibling()
    def find(text, window):
        return next(w for w in walk(window) if isinstance(w, Gtk.Button) and w.get_label() == text)
    def exception(*args):
        errors.append(''.join(traceback.format_exception(*args))); print(errors[-1], file=sys.stderr); app.quit()
    sys.excepthook = exception
    def check():
        nonlocal step, dialog
        if time.monotonic() > deadline:
            raise AssertionError(f'Review restart timeout {kind}/{phase}/{step}')
        if step == 0 and app.session and not app.refreshing:
            if phase == 'restore':
                assert app.session['id'] == 'ses_review_b'
                assert app.current_draft()['text'] == 'B private draft preserved'
                if kind == 'creation':
                    record = app.store.pending_creations('/fixture/new')[0]
                    assert record['state'] == 'attempted'
                else:
                    record = app.store.action_records('ses_review_a')[0]
                    assert record['kind'] == kind and record['state'] in ('attempted', 'uncertain')
                    assert record['directory'] == '/fixture/a'
                    app.open_chat(SESSIONS[0])
            if kind == 'creation':
                app.new_chat('/fixture/new')
                if phase == 'restore':
                    dialog = app.dialogs[-1]
                    assert dialog.get_title() == 'Criação anterior sem confirmação'
            elif kind == 'permission':
                app.review_permission(PERMISSION); dialog = app.dialogs[-1]
                find('Permitir uma vez', dialog).emit('clicked')
                find('Confirmar', app.dialogs[-1]).emit('clicked')
            else:
                app.answer_form(FORM); dialog = app.dialogs[-1]
                if phase == 'restore':
                    next(w for w in walk(dialog) if isinstance(w, Gtk.Entry)).set_text('different after restart')
                find('Enviar resposta', dialog).emit('clicked')
            step = 1
        elif step == 1:
            if phase == 'send':
                record = app.store.pending_creations('/fixture/new')[0] if kind == 'creation' else app.store.action_records('ses_review_a')[0]
                assert record['state'] == 'attempted'
                app.open_chat(SESSIONS[1]); app.persist()
                (root/'ready-to-kill').write_text('owned fixture client, B saved')
                step = 2
            else:
                if kind == 'creation':
                    find('Atualizar histórico', dialog).emit('clicked'); step = 4
                    return GLib.SOURCE_CONTINUE
                assert any(isinstance(w, Gtk.Label) and 'Ação anterior sem confirmação' in w.get_text() for w in walk(dialog))
                assert app.session['id'] == 'ses_review_a'
                assert app.store.data['drafts']['ses_review_b']['text'] == 'B private draft preserved'
                assert len(app.store.action_records('ses_review_a')) == 1
                step = 3; app.window.close(); app.quit(); return GLib.SOURCE_REMOVE
        elif step == 4 and not app.read_gates['sessions'].in_flight:
            created = next((s for s in app.sessions if s['id'] == 'ses_created_recovery'), None)
            if not created:
                return GLib.SOURCE_CONTINUE
            assert app.session['id'] == 'ses_review_b' and app.current_draft()['text'] == 'B private draft preserved'
            assert app.store.pending_creations('/fixture/new')
            assert created['location']['directory'] == '/fixture/new'
            dialog.close(); app.open_chat(created)
            assert app.session['id'] == 'ses_created_recovery'
            assert app.store.data['drafts']['ses_review_b']['text'] == 'B private draft preserved'
            step = 3; app.window.close(); app.quit(); return GLib.SOURCE_REMOVE
        return GLib.SOURCE_CONTINUE
    GLib.timeout_add(120, check); app.run([])
    assert not errors, errors
    assert phase == 'restore' and step == 3


def parent(only=None):
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler); server.daemon_threads = True
    server.posts = []; server.unexpected = []; server.accepted = threading.Event(); server.release = threading.Event()
    server.sessions = list(SESSIONS)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    processes = []
    def command(kind, phase, root):
        return [sys.executable, str(Path(__file__).resolve()), '--kind', kind, '--phase', phase, '--root', str(root), '--port', str(server.server_port)]
    try:
        kinds = (only,) if only else ('permission', 'form')
        for kind in kinds:
            root = Path('/scratch/review-recovery-'+kind); root.mkdir()
            server.accepted = threading.Event(); server.release = threading.Event()
            with (root/'client.log').open('wb') as log:
                process = subprocess.Popen(command(kind, 'send', root), stdout=log, stderr=log); processes.append(process)
                assert server.accepted.wait(timeout=15), (root/'client.log').read_text()[-4000:]
                end = time.monotonic()+5
                while not (root/'ready-to-kill').exists() and time.monotonic() < end:
                    assert process.poll() is None, (root/'client.log').read_text()[-4000:]
                    time.sleep(.05)
                assert (root/'ready-to-kill').exists()
                process.kill(); process.wait(timeout=5)
            server.release.set()
            before = len(server.posts)
            result = subprocess.run(command(kind, 'restore', root), capture_output=True, text=True, timeout=25)
            assert result.returncode == 0, result.stdout + result.stderr[-6000:]
            assert len(server.posts) == before
            print(f'PASS: {kind} client killed after fixture receipt/before acknowledgement; restart preserved unresolved original-project record, blocked replay and retained B draft.', flush=True)
        assert len(server.posts) == len(kinds) and not server.unexpected
        for kind, (path, body) in zip(kinds, server.posts):
            expected = {'creation': {'location': {'directory': '/fixture/new'}}, 'permission': {'decision': 'once'}, 'form': {'answer': {'text': 'original answer'}}}[kind]
            assert body == expected
            assert (path == '/api/session') if kind == 'creation' else ('/ses_review_a/' in path)
        if only == 'creation':
            assert len(server.sessions) == 3
            print('PASS: created conversation recovered through GET-only history and explicit selection; exactly one original creation POST, zero restart retransmissions or B writes.', flush=True)
        else:
            print('PASS: original replies only, zero restart retransmissions or B writes; only owned sandbox clients terminated, no real permission/tool/provider used.', flush=True)
    finally:
        server.release.set()
        for process in processes:
            if process.poll() is None:
                process.kill(); process.wait(timeout=5)
        server.shutdown(); server.server_close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--phase'); parser.add_argument('--kind', choices=['permission', 'form', 'creation']); parser.add_argument('--root'); parser.add_argument('--port', type=int)
    args = parser.parse_args()
    child(args.kind, args.phase, args.root, args.port) if args.phase else parent(args.kind)
