"""Paid-call UI cancellation and delayed-result fencing; no microphone or API."""
import os
from pathlib import Path
import sys
import subprocess
import threading
import time
import traceback

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'preview'))
from test_server import start_fixture
if os.environ.get('POCKET_TEST_INSTALL'):
    sys.path.insert(0, os.environ['POCKET_TEST_INSTALL'])
from main import Pocket, Gtk, GLib
from backend import Gateway


class ControlledVoice(Gateway):
    def __init__(self, root, port):
        super().__init__(root, port=port)
        self.ready = threading.Event(); self.reads = 0; self.paid_calls = 0

    def voice_models(self):
        self.reads += 1
        self.ready.wait(timeout=5)
        return {'data': {'models': [{'model': 'gpt-realtime-2.1', 'available': True, 'transports': ['webrtc']}]}}

    def voice_session(self, *args, **kwargs):
        self.paid_calls += 1
        raise AssertionError('Cancelled call must never reach a paid session or microphone.')


gateway = start_fixture(); app = Pocket(demo=False, state='/scratch/voice-ui-state')
app.client = ControlledVoice('/scratch/voice-ui-state', gateway.server_port); app.client.pair('123456')
phase = 0; errors = []; deadline = time.monotonic() + 30; released_at = None


def walk(widget):
    yield widget
    child = widget.get_first_child()
    while child:
        yield from walk(child); child = child.get_next_sibling()


def find_button(text):
    return next(w for dialog in app.dialogs for w in walk(dialog) if isinstance(w, Gtk.Button) and w.get_label() == text)


def exception(*args):
    text = ''.join(traceback.format_exception(*args)); print(text, file=sys.stderr, flush=True); errors.append(text); app.quit()


sys.excepthook = exception


def check():
    global phase, released_at
    if time.monotonic() > deadline:
        raise AssertionError(f'Voice UI timed out at {phase}; {app.errors}')
    if phase == 0 and app.session:
        app.voice_button.emit('clicked'); phase = .1
    elif phase == .1 and app.voice_window and app.voice_window.get_mapped():
        subprocess.run(['import', '-window', 'root', '/scratch/native-voice.png'], check=True, timeout=10)
        find_button('Ligar · API paga').emit('clicked')
        assert app.client.reads == 0 and app.client.paid_calls == 0 and app.voice_media is None
        consent = app.dialogs[-1]
        assert 'chamada paga' in consent.get_title()
        consent.close()
        assert app.client.paid_calls == 0
        print('PASS: native voice billing dialog can be cancelled; no broker or microphone opened.', flush=True)
        find_button('Ligar · API paga').emit('clicked'); find_button('Confirmar').emit('clicked'); phase = 1
    elif phase == 1 and app.client.reads == 1:
        find_button('Encerrar áudio').emit('clicked')
        app.client.ready.set(); released_at = time.monotonic(); phase = 2
    elif phase == 2 and time.monotonic() - released_at > .5:
        assert app.client.paid_calls == 0 and app.voice_media is None
        assert find_button('Ligar · API paga').get_sensitive()
        print('PASS: ending during delayed availability check fences the result; no late media or paid session starts.', flush=True)
        app.voice_window.close(); assert app.voice_window is None
        app.window.close(); app.quit(); return GLib.SOURCE_REMOVE
    return GLib.SOURCE_CONTINUE


try:
    GLib.timeout_add(100, check); app.run([])
    assert not errors, errors
    assert phase == 2
finally:
    app.client.ready.set(); gateway.shutdown(); gateway.server_close()
