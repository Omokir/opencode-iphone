"""Lost/delayed new-chat acknowledgement, durable replay guard and navigation."""
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

app = Pocket(demo=True, state='/scratch/creation-state')
phase = 0; errors = []; posts = []; admitted = []; other = None; fault = True
started = threading.Event(); release = threading.Event(); deadline = time.monotonic()+25


def walk(widget):
    yield widget
    child = widget.get_first_child()
    while child:
        yield from walk(child); child = child.get_next_sibling()


def find(text, window):
    return next(w for w in walk(window) if isinstance(w, Gtk.Button) and w.get_label() == text)


def exception(*args):
    errors.append(''.join(traceback.format_exception(*args))); print(errors[-1], file=sys.stderr)
    release.set(); app.quit()


sys.excepthook = exception


def check():
    global phase, other, fault
    if time.monotonic() > deadline:
        raise AssertionError(f'Creation timeout {phase}; posts={posts}')
    if phase == 0 and app.session and app.messages:
        other = copy.deepcopy(app.session)
        original = app.client.request
        def request(path, method='GET', body=None):
            if path == '/api/session' and method == 'POST':
                posts.append(copy.deepcopy(body))
                created = dict(other, id='ses_created_'+str(len(posts)), title='Created fixture', location=body.get('location', other['location']))
                admitted.append(created); app.client.sessions.insert(0, created)
                started.set(); release.wait(timeout=5)
                if fault:
                    raise PocketError('fixture acknowledgement lost after creation')
                return {'data': created}
            return original(path, method, body)
        app.client.request = request
        app.new_chat('/fixture/a'); app.new_chat('/fixture/a'); phase = 1
    elif phase == 1 and started.is_set():
        app.open_chat(copy.deepcopy(other)); app.draft.get_buffer().set_text('Unrelated draft kept')
        release.set(); phase = 2
    elif phase == 2 and not app.busy:
        assert len(posts) == len(admitted) == 1
        assert app.session['id'] == other['id'] and app.current_draft()['text'] == 'Unrelated draft kept'
        app.store = Store('/scratch/creation-state')
        assert app.store.pending_creations('/fixture/a')[0]['state'] == 'uncertain'
        app.new_chat('/fixture/a'); dialog = app.dialogs[-1]
        assert dialog.get_title() == 'Criação anterior sem confirmação'
        find('Atualizar histórico', dialog).emit('clicked'); phase = 3
    elif phase == 3 and any(s['id'] == admitted[0]['id'] for s in app.sessions):
        assert len(posts) == 1
        dialog = app.dialogs[-1]; find('Já conferi o histórico', dialog).emit('clicked')
        # Closing confirmation is cancellation, not permission to retry.
        app.dialogs[-1].close(); dialog.close(); app.new_chat('/fixture/a')
        assert app.dialogs[-1].get_title() == 'Criação anterior sem confirmação'
        find('Já conferi o histórico', app.dialogs[-1]).emit('clicked')
        find('Confirmar', app.dialogs[-1]).emit('clicked')
        assert len(posts) == 1 and not app.store.pending_creations('/fixture/a')
        fault = False; started.clear(); release.clear(); app.new_chat('/fixture/a'); phase = 4
        print('PASS: lost new-chat reply persisted uncertainty, blocked duplicate creation after state reload, and GET-only history exposed admitted chat; cancelled review did not unlock replay.', flush=True)
    elif phase == 4 and started.is_set():
        app.open_chat(copy.deepcopy(other)); release.set(); phase = 5
    elif phase == 5 and not app.busy:
        assert len(posts) == 2 and app.session['id'] == other['id']
        assert app.current_draft()['text'] == 'Unrelated draft kept'
        assert not app.store.pending_creations('/fixture/a')
        assert any(r.get('sessionID') == admitted[1]['id'] and r['state'] == 'acknowledged' for r in Store('/scratch/creation-state').data['creations'].values())
        print('PASS: explicit review alone made no POST; later manual creation retained acknowledgement after navigation and preserved unrelated draft.', flush=True)
        app.window.close(); app.quit(); return GLib.SOURCE_REMOVE
    return GLib.SOURCE_CONTINUE


GLib.timeout_add(120, check); app.run([]); release.set()
assert not errors, errors
assert phase == 5
