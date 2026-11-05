"""Delayed/failing rename and interrupt, native UI with synthetic transport."""
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

app = Pocket(demo=True, state='/scratch/mutation-state')
phase = 0; errors = []; writes = []; state = {}; other = {}; dialog = None
started = threading.Event(); release = threading.Event(); fault = False; read_fault = False
deadline = time.monotonic()+30


def walk(widget):
    yield widget
    child = widget.get_first_child()
    while child:
        yield from walk(child); child = child.get_next_sibling()


def find(text, window=None):
    return next(w for w in walk(window or dialog) if isinstance(w, Gtk.Button) and w.get_label() == text)


def records(kind):
    return [r for r in app.store.action_records(state['id']) if r['kind'] == kind]


def exception(*args):
    errors.append(''.join(traceback.format_exception(*args))); print(errors[-1], file=sys.stderr)
    release.set(); app.quit()


sys.excepthook = exception


def check():
    global phase, dialog, fault, read_fault
    if time.monotonic() > deadline:
        raise AssertionError(f'Mutation timeout {phase}; writes={writes}')
    if phase == 0 and app.session and app.messages:
        state.update(copy.deepcopy(app.session)); other.update(dict(state, id='ses_other', title='Other project'))
        original = app.client.request; route = app.request_path()
        def request(path, method='GET', body=None):
            if method in ('PATCH', 'POST') and path in (route, route+'/interrupt'):
                writes.append((method, path, copy.deepcopy(body)))
                if method == 'PATCH':
                    state['title'] = body['title']
                started.set(); release.wait(timeout=5)
                if fault:
                    raise PocketError('fixture acknowledgement lost')
                return {}
            if path == route and method == 'GET':
                if read_fault:
                    raise PocketError('fixture read unavailable')
                return {'data': copy.deepcopy(state)}
            return original(path, method, body)
        app.client.request = request
        app.rename(); dialog = app.dialogs[-1]
        next(w for w in walk(dialog) if isinstance(w, Gtk.Entry)).set_text('Confirmed original title')
        fault = True
        find('Salvar nome').emit('clicked'); find('Salvar nome').emit('clicked'); phase = 1
    elif phase == 1 and started.is_set():
        app.open_chat(copy.deepcopy(other)); release.set(); phase = 2
    elif phase == 2 and records('rename')[0]['state'] == 'acknowledged':
        assert len(writes) == 1 and app.session['id'] == other['id'] and app.title.get_text() == other['title']
        assert dialog not in app.dialogs
        print('PASS: rename with lost PATCH reply confirmed by original-session GET; delayed response did not rename current chat; duplicate click caused one write.', flush=True)
        app.open_chat(copy.deepcopy(state)); app.rename(); dialog = app.dialogs[-1]
        app.open_chat(copy.deepcopy(other)); find('Salvar nome').emit('clicked'); assert len(writes) == 1
        dialog.close(); app.open_chat(copy.deepcopy(state)); app.rename(); dialog = app.dialogs[-1]
        next(w for w in walk(dialog) if isinstance(w, Gtk.Entry)).set_text('Unconfirmed title')
        read_fault = True; find('Salvar nome').emit('clicked'); phase = 3
    elif phase == 3 and records('rename')[0]['state'] == 'uncertain':
        assert dialog in app.dialogs and not find('Salvar nome').get_sensitive()
        assert app.title.get_text() == 'Confirmed original title'
        assert Store('/scratch/mutation-state').action_records(state['id'])[0]['state'] == 'uncertain'
        dialog.close(); read_fault = False; fault = False
        app.interrupt(); dialog = app.dialogs[-1]
        app.open_chat(copy.deepcopy(other)); find('Confirmar').emit('clicked'); assert len(writes) == 2
        app.open_chat(copy.deepcopy(state)); started.clear(); release.clear()
        app.interrupt(); dialog = app.dialogs[-1]; confirm = find('Confirmar')
        confirm.emit('clicked'); confirm.emit('clicked'); phase = 4
        print('PASS: failed rename read-back stayed uncertain/persisted, never displayed requested title as saved; stale rename and interrupt dialogs made no writes.', flush=True)
    elif phase == 4 and started.is_set():
        app.open_chat(copy.deepcopy(other)); release.set(); phase = 5
    elif phase == 5 and records('interrupt')[0]['state'] == 'acknowledged':
        assert len(writes) == 3 and app.session['id'] == other['id']
        assert all('/ses_other' not in path for _, path, _ in writes)
        app.open_chat(copy.deepcopy(state)); fault = True
        app.interrupt(); dialog = app.dialogs[-1]; find('Confirmar').emit('clicked'); phase = 6
    elif phase == 6 and records('interrupt')[0]['state'] == 'uncertain':
        assert len(writes) == 4
        app.interrupt(); dialog = app.dialogs[-1]; find('Confirmar').emit('clicked'); phase = 7
    elif phase == 7:
        assert len(writes) == 4 and records('interrupt')[0]['state'] == 'uncertain'
        print('PASS: delayed interruption acknowledgement persisted on original chat, not treated as stopped execution; uncertain interruption blocks replay across reopened confirmations.', flush=True)
        app.window.close(); app.quit(); return GLib.SOURCE_REMOVE
    return GLib.SOURCE_CONTINUE


GLib.timeout_add(120, check); app.run([]); release.set()
assert not errors, errors
assert phase == 7
