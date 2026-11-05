"""Independent review read faults must not hide newly received messages."""
import os
import sys
import time
import traceback

if os.environ.get('POCKET_TEST_INSTALL'):
    sys.path.insert(0, os.environ['POCKET_TEST_INSTALL'])
from main import Pocket, Gtk, GLib
from backend import PocketError

app = Pocket(demo=True, state='/scratch/partial-read-state')
phase = 0; errors = []; writes = []; failed = set(); version = 1
permission_dialog = None; form_dialog = None; deadline = time.monotonic()+30
permission = {'id': 'per_partial', 'message': 'Partial fixture permission', 'source': {}}
form = {'id': 'form_partial', 'title': 'Partial fixture question', 'fields': [{'key': 'text', 'type': 'string', 'default': 'not sent'}]}


def walk(widget):
    yield widget
    child = widget.get_first_child()
    while child:
        yield from walk(child); child = child.get_next_sibling()


def find(text, root):
    return next(w for w in walk(root) if isinstance(w, Gtk.Button) and w.get_label() == text)


def text_is_current():
    return any(m['id'] == 'msg_partial' and m['text'] == f'Read version {version}' for m in app.messages)


def exception(*args):
    errors.append(''.join(traceback.format_exception(*args))); print(errors[-1], file=sys.stderr); app.quit()


sys.excepthook = exception


def check():
    global phase, version, permission_dialog, form_dialog
    if time.monotonic() > deadline:
        raise AssertionError(f'Partial-read timeout {phase}; messages={app.messages}')
    if phase == 0 and app.session and app.messages and not app.refreshing:
        route = app.request_path(); original = app.client.request
        def request(path, method='GET', body=None):
            if method != 'GET':
                writes.append(path); return {}
            for kind in ('message', 'permission', 'form'):
                if path.split('?')[0] == route+'/'+kind:
                    if kind in failed:
                        raise PocketError('fixture '+kind+' unavailable')
                    return {'data': [{'id': 'msg_partial', 'type': 'assistant', 'text': f'Read version {version}', 'time': {'created': 1, 'completed': 2}}] if kind == 'message' else ([permission] if kind == 'permission' else [form])}
            return original(path, method, body)
        app.client.request = request; app.refresh(); phase = 1
    elif phase == 1 and not app.refreshing and text_is_current():
        app.review_permission(permission); permission_dialog = app.dialogs[-1]
        app.answer_form(form); form_dialog = app.dialogs[-1]
        failed.add('permission'); version = 2; app.refresh(); phase = 2
    elif phase == 2 and not app.refreshing and text_is_current():
        assert not find('Permissão necessária · Partial fixture permission', app.permission_box).get_sensitive()
        assert find('Responder: Partial fixture question', app.permission_box).get_sensitive()
        find('Negar', permission_dialog).emit('clicked'); assert not writes
        failed.clear(); failed.add('form'); version = 3; app.refresh(); phase = 3
    elif phase == 3 and not app.refreshing and text_is_current():
        assert find('Permissão necessária · Partial fixture permission', app.permission_box).get_sensitive()
        assert not find('Responder: Partial fixture question', app.permission_box).get_sensitive()
        find('Enviar resposta', form_dialog).emit('clicked'); assert not writes
        failed.clear(); version = 4; app.refresh(); phase = 4
    elif phase == 4 and not app.refreshing and text_is_current():
        assert all(w.get_sensitive() for w in walk(app.permission_box) if isinstance(w, Gtk.Button))
        find('Negar', permission_dialog).emit('clicked'); find('Enviar resposta', form_dialog).emit('clicked')
        assert not writes, 'Previously invalidated open reviews must require reopening even after connectivity returns.'
        print('PASS: permission/form read failures did not hide new messages or block the other fresh review; stale buttons/dialogs refused submission, including after recovery.', flush=True)
        failed.add('message'); version = 5; app.refresh(); phase = 5
    elif phase == 5 and not app.refreshing:
        assert any(m['id'] == 'msg_partial' and m['text'] == 'Read version 4' for m in app.messages)
        assert all(not w.get_sensitive() for w in walk(app.permission_box) if isinstance(w, Gtk.Button))
        failed.clear(); version = 6; app.refresh(); phase = 6
    elif phase == 6 and not app.refreshing and text_is_current():
        assert all(w.get_sensitive() for w in walk(app.permission_box) if isinstance(w, Gtk.Button))
        assert not writes and app.sent == 0
        print('PASS: failed message read preserved prior history and fenced review controls; manual read recovery restored all fresh controls without automatic replies/provider calls.', flush=True)
        app.window.close(); app.quit(); return GLib.SOURCE_REMOVE
    return GLib.SOURCE_CONTINUE


GLib.timeout_add(120, check); app.run([])
assert not errors, errors
assert phase == 6
