"""Exercise real native transport against an isolated synthetic gateway only."""
import sys
import os
import time
import traceback
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'preview'))
from test_server import start_fixture, FixtureGateway
if os.environ.get('POCKET_TEST_INSTALL'):
    sys.path.insert(0, os.environ['POCKET_TEST_INSTALL'])
from main import Pocket, GLib
from backend import Gateway

gateway = start_fixture()
app = Pocket(demo=False, state='/scratch/connected-state')
app.client = Gateway('/scratch/connected-state', port=gateway.server_port)
app.client.pair('123456')
phase = 0
deadline = time.monotonic() + 40
errors = []


def exception(*args):
    errors.append(''.join(traceback.format_exception(*args))); app.quit()


sys.excepthook = exception


def check():
    global phase
    if time.monotonic() > deadline:
        raise AssertionError(f'Connected native UI timed out at {phase}: {app.errors}')
    if phase == 0 and app.session and app.messages:
        assert not app.client.demo
        assert app.session['id'] == 'ses_connected'
        assert 'Connected transport verified' in app.messages[0]['text']
        assert not any(call[1].endswith('/prompt') for call in FixtureGateway.calls)
        app.draft.get_buffer().set_text('native fixture prompt, not a real provider')
        app.send_button.emit('clicked'); phase = 1
        print('PASS: connected native window loads authenticated gateway history, without sending on open.', flush=True)
    elif phase == 1 and app.sent == 1 and not app.busy:
        prompts = [call for call in FixtureGateway.calls if call[1].endswith('/prompt')]
        assert len(prompts) == 1
        assert prompts[0][2] == 'Bearer fixture-secret-only'
        assert app.current_draft()['text'] == ''
        assert not app.errors, app.errors
        app.window.close(); app.quit()
        print('PASS: connected native send accepted once; draft cleared only after acknowledgement.', flush=True)
        return GLib.SOURCE_REMOVE
    return GLib.SOURCE_CONTINUE


try:
    GLib.timeout_add(120, check)
    app.run([])
    assert not errors, errors
    assert phase == 1 and app.sent == 1
finally:
    gateway.shutdown(); gateway.server_close()
