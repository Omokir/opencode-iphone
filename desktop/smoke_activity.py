"""Native read-only activity, independent failures and original-session binding."""
import os
from pathlib import Path
import sys
import threading
import time
import traceback

if os.environ.get('POCKET_TEST_INSTALL'):
    sys.path.insert(0, os.environ['POCKET_TEST_INSTALL'])
from main import Pocket, Gtk, GLib
from backend import PocketError

app = Pocket(demo=True, state='/scratch/activity-state')
phase = 0; errors = []; calls = []; release = threading.Event(); deadline = time.monotonic()+25
original_request = app.client.request


def walk(widget):
    yield widget
    child = widget.get_first_child()
    while child:
        yield from walk(child); child = child.get_next_sibling()


def exception(*args):
    errors.append(''.join(traceback.format_exception(*args))); print(errors[-1], file=sys.stderr)
    release.set(); app.quit()


sys.excepthook = exception


def check():
    global phase
    if time.monotonic() > deadline:
        raise AssertionError(f'Activity timeout at {phase}')
    if phase == 0 and app.session and app.messages:
        sid = app.session['id']
        def request(path, method='GET', body=None):
            calls.append((method, path))
            if '/diff?' in path:
                release.wait(timeout=5)
                return {'data': [{'file': 'literal <b>file.py</b>', 'patch': '-old\n+new\tvalue', 'status': 'modified', 'additions': 1, 'deletions': 1}]}
            if '/terminal/read?' in path:
                raise PocketError('fixture terminal offline')
            if path == '/phone/kzl/tasks':
                return {'tasks': [{'parent': sid, 'text': 'Review fixture', 'state': 'running', 'confirmed': False}]}
            return original_request(path, method, body)
        app.client.request = request; app.activity()
        app.open_chat(dict(app.session, id='ses_other', title='Other conversation'))
        release.set(); phase = 1
    elif phase == 1:
        sections = app.activity_sections
        labels = {kind: [w.get_text() for w in walk(target) if isinstance(w, Gtk.Label)] for kind, target in sections.items()}
        if not any('literal <b>' in text for text in labels['diff']) or not any('fixture terminal offline' in text for text in labels['terminal']):
            return GLib.SOURCE_CONTINUE
        assert 'Review fixture' in labels['tasks']
        assert any('Sem confirmação' in text for text in labels['tasks'])
        view = next(w for w in walk(sections['diff']) if isinstance(w, Gtk.TextView))
        assert not view.get_editable()
        assert view.get_buffer().get_text(view.get_buffer().get_start_iter(), view.get_buffer().get_end_iter(), True) == '-old\n+new\tvalue'
        assert all(method == 'GET' for method, path in calls)
        assert not any('/ses_other/diff' in path or '/ses_other/terminal' in path for _, path in calls)
        print('PASS: native activity displays literal diff and unconfirmed task despite terminal failure; navigation retains original session; GET-only, no execution.', flush=True)
        app.window.close(); app.quit(); return GLib.SOURCE_REMOVE
    return GLib.SOURCE_CONTINUE


GLib.timeout_add(120, check); app.run([])
release.set()
assert not errors, errors
assert phase == 1
