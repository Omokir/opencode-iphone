"""Actual X11 keyboard input on private Xvfb, never the user's desktop."""
import os
import subprocess
import sys
import time
import traceback

if os.environ.get('POCKET_TEST_INSTALL'):
    sys.path.insert(0, os.environ['POCKET_TEST_INSTALL'])
from main import Pocket, Gtk, GLib

app = Pocket(demo=True, state='/scratch/shortcut-state')
phase = 0; errors = []; writes = []; original_id = None; xid = None; dialog = None
deadline = time.monotonic()+25; original = app.client.request; created_at = None


def request(path, method='GET', body=None):
    if method != 'GET':
        writes.append(path)
    return original(path, method, body)


app.client.request = request


def walk(widget):
    yield widget
    child = widget.get_first_child()
    while child:
        yield from walk(child); child = child.get_next_sibling()


def key(value):
    subprocess.run(['xdotool', 'key', '--clearmodifiers', value], check=True, timeout=5)


def exception(*args):
    errors.append(''.join(traceback.format_exception(*args))); print(errors[-1], file=sys.stderr); app.quit()


sys.excepthook = exception


def check():
    global phase, original_id, xid, dialog, created_at
    if time.monotonic() > deadline:
        raise AssertionError(f'Shortcut timeout {phase}; writes={writes}')
    if phase == 0 and app.session and app.messages:
        original_id = app.session['id']
        message = {'id': 'msg_key_fixture', 'type': 'assistant', 'text': 'Literal needle in loaded conversation', 'time': {'created': 1, 'completed': 2}}
        app.client.messages[original_id] = [message]; app.messages = [message]; app.render_messages(app.messages)
        app.draft.get_buffer().set_text('Unsent original keyboard draft')
        xid = subprocess.run(['xdotool', 'search', '--onlyvisible', '--name', '^KzL Agent$'], check=True, capture_output=True, text=True, timeout=5).stdout.splitlines()[0]
        subprocess.run(['xdotool', 'windowfocus', '--sync', xid], check=True, timeout=5)
        app.draft.grab_focus(); key('ctrl+f'); phase = 1
    elif phase == 1 and app.dialogs:
        dialog = app.dialogs[-1]; assert dialog.get_title() == 'Buscar nesta conversa'
        subprocess.run(['xdotool', 'type', '--clearmodifiers', '--delay', '1', 'needle'], check=True, timeout=5)
        phase = 2
    elif phase == 2 and any(isinstance(w, Gtk.Label) and w.get_text() == '1 resultado(s)' for w in walk(dialog)):
        assert next(w for w in walk(dialog) if isinstance(w, Gtk.SearchEntry)).get_text() == 'needle'
        assert not writes and app.sent == 0
        key('ctrl+n'); created_at = time.monotonic(); phase = 3
    elif phase == 3 and time.monotonic()-created_at > .3:
        assert not writes and app.session['id'] == original_id
        dialog.close()
        subprocess.run(['xdotool', 'windowfocus', '--sync', xid], check=True, timeout=5)
        app.draft.grab_focus(); key('ctrl+n'); phase = 4
    elif phase == 4 and not app.busy and app.session['id'] != original_id:
        assert writes == ['/api/session'] and app.sent == 0
        assert app.store.data['drafts'][original_id]['text'] == 'Unsent original keyboard draft'
        print('PASS: real Ctrl+F opened local search from composer and typed query without sending; Ctrl+N behind dialog made no mutation; main-window Ctrl+N created one demo chat and preserved old draft.', flush=True)
        app.window.close(); app.quit(); return GLib.SOURCE_REMOVE
    return GLib.SOURCE_CONTINUE


GLib.timeout_add(120, check); app.run([])
assert not errors, errors
assert phase == 4
