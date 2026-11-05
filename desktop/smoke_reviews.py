"""Native permission/form replies: delayed acknowledgement, fault and navigation."""
import copy
import os
import sys
import threading
import time
import traceback

if os.environ.get('POCKET_TEST_INSTALL'):
    sys.path.insert(0, os.environ['POCKET_TEST_INSTALL'])
from main import Pocket, Gtk, GLib
from backend import PocketError, Store

app = Pocket(demo=True, state='/scratch/review-state')
phase = 0; errors = []; writes = []; original_session = None; other = None; dialog = None
started = threading.Event(); release = threading.Event(); fault = False
deadline = time.monotonic()+30
permission = {'id': 'per_fixture', 'message': 'Fixture permission', 'source': {}}
form = {'id': 'form_fixture', 'title': 'Fixture question', 'fields': [{'key': 'reply', 'type': 'string', 'required': True, 'default': 'snapshot answer'}]}


def walk(widget):
    yield widget
    child = widget.get_first_child()
    while child:
        yield from walk(child); child = child.get_next_sibling()


def find(text, window=None):
    return next(w for w in walk(window or dialog) if isinstance(w, Gtk.Button) and w.get_label() == text)


def records(kind):
    return [r for r in app.store.action_records(original_session['id']) if r['kind'] == kind]


def exception(*args):
    errors.append(''.join(traceback.format_exception(*args))); print(errors[-1], file=sys.stderr)
    release.set(); app.quit()


sys.excepthook = exception


def check():
    global phase, dialog, original_session, other, fault
    if time.monotonic() > deadline:
        raise AssertionError(f'Review timeout {phase}; writes={writes}')
    if phase == 0 and app.session and app.messages:
        original_session = copy.deepcopy(app.session); other = dict(original_session, id='ses_other', title='Other')
        app.store.data['drafts']['ses_other'] = {'text': 'B untouched', 'files': []}
        original = app.client.request
        def request(path, method='GET', body=None):
            if method == 'POST' and path.endswith('/reply'):
                writes.append((path, copy.deepcopy(body))); started.set(); release.wait(timeout=5)
                if fault:
                    raise PocketError('fixture reply acknowledgement lost')
                return {}
            return original(path, method, body)
        app.client.request = request
        app.review_permission(permission); dialog = app.dialogs[-1]
        find('Permitir uma vez').emit('clicked'); confirmation = app.dialogs[-1]
        app.open_chat(copy.deepcopy(other)); find('Confirmar', confirmation).emit('clicked')
        assert not writes
        app.open_chat(copy.deepcopy(original_session)); app.review_permission(permission); dialog = app.dialogs[-1]
        find('Permitir uma vez').emit('clicked'); confirmation = app.dialogs[-1]
        confirm = find('Confirmar', confirmation); confirm.emit('clicked'); confirm.emit('clicked'); phase = 1
    elif phase == 1 and started.is_set():
        app.open_chat(copy.deepcopy(other)); release.set(); phase = 2
    elif phase == 2 and records('permission')[0]['state'] == 'acknowledged':
        assert len(writes) == 1 and writes[0][1] == {'decision': 'once'}
        assert app.session['id'] == 'ses_other' and app.current_draft()['text'] == 'B untouched'
        print('PASS: stale permission confirmation made no write; double confirmation produced one original-session reply, acknowledged after navigation without changing B.', flush=True)
        app.open_chat(copy.deepcopy(original_session)); app.answer_form(form); dialog = app.dialogs[-1]
        app.open_chat(copy.deepcopy(other)); find('Enviar resposta').emit('clicked'); assert len(writes) == 1
        dialog.close(); app.open_chat(copy.deepcopy(original_session)); app.answer_form(form); dialog = app.dialogs[-1]
        fault = True; started.clear(); release.clear()
        find('Enviar resposta').emit('clicked'); find('Enviar resposta').emit('clicked'); phase = 3
    elif phase == 3 and started.is_set():
        app.open_chat(copy.deepcopy(other)); release.set(); phase = 4
    elif phase == 4 and records('form')[0]['state'] == 'uncertain':
        assert len(writes) == 2 and writes[1][1] == {'answer': {'reply': 'snapshot answer'}}
        assert app.current_draft()['text'] == 'B untouched'
        assert not find('Enviar resposta').get_sensitive()
        assert any(r['kind'] == 'form' and r['state'] == 'uncertain' for r in Store('/scratch/review-state').action_records(original_session['id']))
        dialog.close(); app.open_chat(copy.deepcopy(original_session)); app.answer_form(form); dialog = app.dialogs[-1]
        find('Enviar resposta').emit('clicked'); phase = 5
    elif phase == 5:
        assert len(writes) == 2
        dialog.close(); app.review_permission(dict(permission, id='per_failed')); dialog = app.dialogs[-1]
        find('Negar').emit('clicked'); phase = 6
    elif phase == 6 and records('permission')[0]['state'] == 'uncertain':
        assert len(writes) == 3 and not find('Negar').get_sensitive() and not find('Permitir uma vez').get_sensitive()
        dialog.close(); app.review_permission(dict(permission, id='per_failed')); dialog = app.dialogs[-1]
        find('Permitir uma vez').emit('clicked'); find('Confirmar', app.dialogs[-1]).emit('clicked'); phase = 7
    elif phase == 7:
        assert len(writes) == 3
        assert all('/ses_other/' not in path for path, _ in writes)
        print('PASS: stale form refused; lost form/permission replies persisted uncertainty and blocked reopened replay, including opposite permission decision; B draft retained.', flush=True)
        app.window.close(); app.quit(); return GLib.SOURCE_REMOVE
    return GLib.SOURCE_CONTINUE


GLib.timeout_add(120, check); app.run([]); release.set()
assert not errors, errors
assert phase == 7
