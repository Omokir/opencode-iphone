"""Partial model/mode writes and navigation, synthetic transport only."""
import copy
import os
import sys
import threading
import time
import traceback

if os.environ.get('POCKET_TEST_INSTALL'):
    sys.path.insert(0, os.environ['POCKET_TEST_INSTALL'])
from main import Pocket, Gtk, GLib
from backend import PocketError

app = Pocket(demo=True, state='/scratch/options-state')
phase = 0; errors = []; posts = []; release = threading.Event(); started = threading.Event()
deadline = time.monotonic()+25; state = {}; fail_model = True; preserve_variant = False; dialog = None


def walk(widget):
    yield widget
    child = widget.get_first_child()
    while child:
        yield from walk(child); child = child.get_next_sibling()


def button(text):
    return next(w for w in walk(dialog) if isinstance(w, Gtk.Button) and w.get_label() == text)


def exception(*args):
    errors.append(''.join(traceback.format_exception(*args))); print(errors[-1], file=sys.stderr)
    release.set(); app.quit()


sys.excepthook = exception


def check():
    global phase, dialog, fail_model, preserve_variant
    if time.monotonic() > deadline:
        raise AssertionError(f'Options timeout phase {phase}')
    if phase == 0 and app.session and app.messages:
        state.update(copy.deepcopy(app.session)); state['model'] = {'providerID': 'fixture', 'id': 'unlisted'}
        app.session = copy.deepcopy(state); app.catalog = [{'providerID': 'fixture', 'id': 'new', 'name': 'New model'}]
        original = app.client.request; path = app.request_path()
        def request(route, method='GET', body=None):
            if route == path and method == 'GET':
                return {'data': copy.deepcopy(state)}
            if route in (path+'/agent', path+'/model') and method == 'POST':
                posts.append((route, copy.deepcopy(body)))
                if route.endswith('/agent'):
                    state['agent'] = body['agent']; return {}
                started.set(); release.wait(timeout=5)
                if fail_model:
                    raise PocketError('fixture model rejected after mode saved')
                state['model'] = dict(body['model'])
                if preserve_variant:
                    state['model']['variant'] = 'high'
                return {}
            return original(route, method, body)
        app.client.request = request; app.options(); dialog = app.dialogs[-1]
        dropdowns = [w for w in walk(dialog) if isinstance(w, Gtk.DropDown)]
        assert dropdowns[1].get_selected_item().get_string() == 'unlisted · atual'
        dropdowns[0].set_selected(1); dropdowns[1].set_selected(1)
        button('Salvar').emit('clicked'); button('Salvar').emit('clicked'); phase = 1
    elif phase == 1 and started.is_set():
        app.open_chat(dict(state, id='ses_other', agent='build', title='Other'))
        release.set(); phase = 2
    elif phase == 2 and any(isinstance(w, Gtk.Label) and 'Gravação parcial' in w.get_text() for w in walk(dialog)):
        assert len(posts) == 2 and app.session['id'] == 'ses_other' and app.session['agent'] == 'build'
        assert not button('Salvar').get_sensitive()
        button('Consultar estado salvo').emit('clicked'); phase = 3
        print('PASS: partial mode/model failure read back original project, blocked double-save and did not overwrite the newly opened conversation.', flush=True)
    elif phase == 3 and button('Consultar estado salvo').get_sensitive():
        assert len(posts) == 2
        dialog.close(); app.open_chat(copy.deepcopy(state)); app.options(); dialog = app.dialogs[-1]
        dropdowns = [w for w in walk(dialog) if isinstance(w, Gtk.DropDown)]
        assert dropdowns[0].get_selected() == 1 and dropdowns[1].get_selected_item().get_string() == 'unlisted · atual'
        app.open_chat(dict(state, id='ses_other', agent='build'))
        button('Salvar').emit('clicked'); assert len(posts) == 2
        dialog.close(); app.open_chat(copy.deepcopy(state)); app.options(); dialog = app.dialogs[-1]
        dropdowns = [w for w in walk(dialog) if isinstance(w, Gtk.DropDown)]; dropdowns[1].set_selected(1)
        fail_model = False; button('Salvar').emit('clicked'); phase = 4
    elif phase == 4 and dialog not in app.dialogs:
        assert len(posts) == 4 and app.session['agent'] == 'plan' and app.session['model']['id'] == 'new'
        print('PASS: explicit GET-only review restored actual partial state; stale dialog caused no writes; successful new save closed only after matching read-back.', flush=True)
        state['model']['variant'] = 'high'; app.session = copy.deepcopy(state)
        app.options(); dialog = app.dialogs[-1]
        next(w for w in walk(dialog) if isinstance(w, Gtk.Entry)).set_text('')
        preserve_variant = True; button('Salvar').emit('clicked'); phase = 5
    elif phase == 5 and any(isinstance(w, Gtk.Label) and 'variante: high' in w.get_text() for w in walk(dialog)):
        assert dialog in app.dialogs and len(posts) == 6
        assert next(w for w in walk(dialog) if isinstance(w, Gtk.Entry)).get_text() == 'high'
        assert app.session['model']['variant'] == 'high'
        print('PASS: server retaining a different variant cannot be mistaken for a matching save; actual variant is displayed/restored without retry.', flush=True)
        app.window.close(); app.quit(); return GLib.SOURCE_REMOVE
    return GLib.SOURCE_CONTINUE


GLib.timeout_add(120, check); app.run([]); release.set()
assert not errors, errors
assert phase == 5
