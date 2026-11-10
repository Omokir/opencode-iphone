"""Kill an owned test client after fixture admission, then restart real GTK clients.

No provider/tools run. The fixture models request-ID admission and delayed/lost
HTTP acknowledgement; the installed live service is never discovered or used.
"""
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
from transport_fixture import FixtureGateway


class RecoveryHandler(FixtureGateway):
    def reply(self, status, value):
        raw = json.dumps(value).encode()
        self.send_response(status); self.send_header('Content-Type', 'application/json'); self.send_header('Content-Length', str(len(raw))); self.end_headers()
        try:
            self.wfile.write(raw)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def route(self):
        if self.path.startswith('/api/session/ses_connected/message'):
            if self.headers.get('Authorization') != 'Bearer fixture-secret-only':
                return self.reply(401, {'error': 'fixture auth required'})
            return self.reply(200, {'data': list(self.server.admitted.values()) if self.server.show_messages else []})
        if self.path == '/api/session/ses_connected/prompt' and self.command == 'POST':
            if self.headers.get('Authorization') != 'Bearer fixture-secret-only':
                return self.reply(401, {'error': 'fixture auth required'})
            size = int(self.headers.get('Content-Length', 0)); assert 0 < size <= 16384
            value = json.loads(self.rfile.read(size)); self.server.posts.append(value['id'])
            self.server.admitted.setdefault(value['id'], {'id': value['id'], 'type': 'user', 'text': value['text'], 'files': value.get('files', []), 'time': {'created': 1}})
            if self.server.hold_first:
                self.server.hold_first = False; self.server.accepted.set(); self.server.release.wait(timeout=20)
                return self.reply(503, {'error': 'Fixture lost acknowledgement after admission'})
            return self.reply(200, {'accepted': True})
        return super().route()

    do_GET = route
    do_POST = route


def child(phase, state, port):
    if os.environ.get('POCKET_TEST_INSTALL'):
        sys.path.insert(0, os.environ['POCKET_TEST_INSTALL'])
    from main import Pocket, GLib
    from backend import Gateway
    app = Pocket(demo=False, state=state); app.client = Gateway(state, port=port); app.client.pair('123456')
    progress = {'value': 0}; errors = []; deadline = time.monotonic()+20
    expected = app.store.data.get('drafts', {}).get('ses_connected', {}).get('requestID')
    def exception(*args):
        value = ''.join(traceback.format_exception(*args)); print(value, file=sys.stderr, flush=True); errors.append(value)
        if hasattr(app, 'window'):
            app.window.close()
        app.quit()
    sys.excepthook = exception
    def check():
        if time.monotonic() > deadline:
            raise AssertionError('Recovery child timed out: ' + phase)
        if progress['value'] == 0 and app.session and not app.refreshing:
            assert app.sent == 0
            if phase == 'send':
                app.draft.get_buffer().set_text('fixture recovery request')
                app.send_button.emit('clicked'); progress['value'] = 1
            elif phase == 'resume':
                assert app.current_draft()['requestID'] == expected
                assert app.current_draft()['text'] == 'fixture recovery request'
                assert app.notice.get_visible() and 'sem confirmação' in app.notice.get_text(), 'Uncertain admission warning must survive process restart.'
                app.send_button.emit('clicked'); progress['value'] = 1
            else:
                if phase == 'history':
                    assert app.current_draft()['text'] == '', 'History admission must reconcile the identical old draft without another POST.'
                elif phase == 'edited':
                    assert app.current_draft()['text'].endswith('edited after crash'), 'Recovery must not erase an edited draft.'
                assert app.store.data['outgoing'][expected]['state'] == 'admitted'
                progress['value'] = 2; app.window.close(); app.quit(); return GLib.SOURCE_REMOVE
        elif progress['value'] == 1 and phase == 'resume' and app.sent == 1 and not app.busy:
            assert app.current_draft()['text'] == ''
            progress['value'] = 2; app.window.close(); app.quit(); return GLib.SOURCE_REMOVE
        return GLib.SOURCE_CONTINUE
    GLib.timeout_add(100, check); app.run([])
    assert not errors, errors
    assert progress['value'] == 2, phase


def parent():
    root = Path('/scratch/recovery'); root.mkdir()
    server = ThreadingHTTPServer(('127.0.0.1', 0), RecoveryHandler); server.daemon_threads = True
    server.admitted = {}; server.posts = []; server.show_messages = False; server.hold_first = True
    server.accepted = threading.Event(); server.release = threading.Event()
    threading.Thread(target=server.serve_forever, daemon=True).start()
    processes = []
    def command(phase, state):
        return [sys.executable, str(Path(__file__).resolve()), '--phase', phase, '--state', str(state), '--port', str(server.server_port)]
    def run(phase, state):
        result = subprocess.run(command(phase, state), capture_output=True, text=True, timeout=25)
        if result.returncode:
            raise AssertionError(phase + ': ' + result.stdout[-2000:] + result.stderr[-8000:])
    try:
        state = root/'state'
        with open(root/'crash-client.log', 'wb') as log:
            process = subprocess.Popen(command('send', state), stdout=log, stderr=log); processes.append(process)
            assert server.accepted.wait(timeout=20), 'Fixture never admitted the synthetic request.'
            assert process.poll() is None
            process.kill(); process.wait(timeout=5)  # Only the Popen-owned sandbox test client.
        initial = json.loads((state/'preferences.json').read_text())
        expected = initial['drafts']['ses_connected']['requestID']
        assert server.posts == [expected] and len(server.admitted) == 1
        server.release.set()
        run('resume', state)
        assert server.posts == [expected, expected] and len(server.admitted) == 1
        print('PASS: killed client after fixture admission; restart preserved uncertainty and request ID; explicit retry did not create a second admission.', flush=True)
        server.show_messages = True
        for phase in ('history', 'edited'):
            location = root/phase; location.mkdir(mode=0o700)
            prefs = copy.deepcopy(initial)
            if phase == 'edited':
                prefs['drafts']['ses_connected']['text'] += ' edited after crash'
            (location/'preferences.json').write_text(json.dumps(prefs))
            run(phase, location)
        assert len(server.posts) == 2
        print('PASS: history reconciled admitted request without retransmission; identical old draft cleared, edited draft preserved.', flush=True)
        print('PASS: recovery used separate client processes and isolated HTTP fixture only; no provider, tools or live account writes.', flush=True)
    finally:
        server.release.set()
        for process in processes:
            if process.poll() is None:
                process.kill(); process.wait(timeout=5)
        server.shutdown(); server.server_close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--phase'); parser.add_argument('--state'); parser.add_argument('--port', type=int)
    args = parser.parse_args()
    child(args.phase, args.state, args.port) if args.phase else parent()
