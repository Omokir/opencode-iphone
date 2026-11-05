"""Separate GTK processes: accepted settings, failed GET, restart without POST."""
import argparse
import copy
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


class Handler(FixtureGateway):
    def reply(self, status, value):
        raw = json.dumps(value).encode(); self.send_response(status)
        self.send_header('Content-Type', 'application/json'); self.send_header('Content-Length', str(len(raw))); self.end_headers(); self.wfile.write(raw)

    def route(self):
        path = self.path.split('?')[0]
        if path == '/pair':
            return super().route()
        if self.headers.get('Authorization') != 'Bearer fixture-secret-only':
            return self.reply(401, {'error': 'fixture authentication required'})
        if path == '/phone/catalog':
            return self.reply(200, {'models': [{'id': 'fixture-model', 'providerID': 'fixture', 'name': 'Fixture model'}]})
        if path == '/api/session':
            return self.reply(200, {'data': [copy.deepcopy(self.server.session)]})
        if path == '/api/session/ses_connected':
            self.server.gets += 1
            if self.server.fail_read:
                return self.reply(503, {'error': 'fixture confirmation read unavailable'})
            return self.reply(200, {'data': copy.deepcopy(self.server.session)})
        if self.command == 'POST' and path in ('/api/session/ses_connected/agent', '/api/session/ses_connected/model'):
            payload = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            self.server.posts.append((path, payload))
            if path.endswith('/agent'):
                self.server.session['agent'] = payload['agent']
            else:
                self.server.session['model'] = payload['model']; self.server.fail_read = True
            return self.reply(200, {})
        if self.command != 'GET':
            return self.reply(403, {'error': 'unexpected write'})
        return super().route()

    do_GET = route
    do_POST = route


def child(phase, port):
    if os.environ.get('POCKET_TEST_INSTALL'):
        sys.path.insert(0, os.environ['POCKET_TEST_INSTALL'])
    from main import Pocket, Gtk, GLib
    from backend import Gateway
    app = Pocket(demo=False, state='/scratch/options-recovery-state')
    app.client = Gateway('/scratch/options-recovery-state', port=port)
    if phase == 'write':
        app.client.pair('123456')
    errors = []; step = 0; dialog = None; deadline = time.monotonic()+20
    def walk(widget):
        yield widget
        c = widget.get_first_child()
        while c:
            yield from walk(c); c = c.get_next_sibling()
    def exception(*args):
        errors.append(''.join(traceback.format_exception(*args))); print(errors[-1], file=sys.stderr); app.quit()
    sys.excepthook = exception
    def check():
        nonlocal step, dialog
        if time.monotonic() > deadline:
            raise AssertionError(f'Options recovery timeout {phase}/{step}')
        if step == 0 and app.session and app.catalog and not app.refreshing:
            app.options(); dialog = app.dialogs[-1]
            drops = [w for w in walk(dialog) if isinstance(w, Gtk.DropDown)]
            variant = next(w for w in walk(dialog) if isinstance(w, Gtk.Entry))
            if phase == 'write':
                drops[0].set_selected(1); drops[1].set_selected(1); variant.set_text('high')
                next(w for w in walk(dialog) if isinstance(w, Gtk.Button) and w.get_label() == 'Salvar').emit('clicked'); step = 1
            else:
                assert app.session['agent'] == 'plan'
                assert app.session['model'] == {'id': 'fixture-model', 'providerID': 'fixture', 'variant': 'high'}
                assert drops[0].get_selected() == 1 and variant.get_text() == 'high'
                assert drops[1].get_selected_item().get_string() == 'Fixture model'
                assert app.sent == 0
                step = 2; app.window.close(); app.quit(); return GLib.SOURCE_REMOVE
        elif step == 1 and any(isinstance(w, Gtk.Label) and 'Configuração sem confirmação' in w.get_text() for w in walk(dialog)):
            assert dialog in app.dialogs
            assert not next(w for w in walk(dialog) if isinstance(w, Gtk.Button) and w.get_label() == 'Salvar').get_sensitive()
            step = 2; app.window.close(); app.quit(); return GLib.SOURCE_REMOVE
        return GLib.SOURCE_CONTINUE
    GLib.timeout_add(120, check); app.run([])
    assert not errors, errors
    assert step == 2


def parent():
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler); server.daemon_threads = True
    server.session = {'id': 'ses_connected', 'title': 'Recovery fixture', 'agent': 'build', 'metadata': {}, 'location': {'directory': '/fixture'}}
    server.posts = []; server.gets = 0; server.fail_read = False
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        for phase in ('write', 'restore'):
            result = subprocess.run([sys.executable, str(Path(__file__).resolve()), '--phase', phase, '--port', str(server.server_port)], capture_output=True, text=True, timeout=25)
            assert result.returncode == 0, result.stdout + result.stderr[-6000:]
            assert len(server.posts) == 2
            server.fail_read = False
        assert server.posts[1][1]['model']['variant'] == 'high' and server.gets >= 1
        print('PASS: accepted mode/model/variant followed by failed confirmation GET remained unconfirmed; separate restarted GTK process restored actual settings with exactly two original POSTs, no retransmission.', flush=True)
    finally:
        server.shutdown(); server.server_close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--phase'); parser.add_argument('--port', type=int); args = parser.parse_args()
    child(args.phase, args.port) if args.phase else parent()
