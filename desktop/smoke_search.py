"""Loaded-message search, literal matching, stale results and native scrolling."""
import copy
import os
import sys
import time
import traceback

if os.environ.get('POCKET_TEST_INSTALL'):
    sys.path.insert(0, os.environ['POCKET_TEST_INSTALL'])
from main import Pocket, Gtk, GLib

app = Pocket(demo=True, state='/scratch/search-state')
phase = 0; errors = []; calls = []; dialog = None; deadline = time.monotonic()+25; original_session = None
original_request = app.client.request


def request(path, method='GET', body=None):
    calls.append((method, path)); return original_request(path, method, body)


app.client.request = request


def walk(widget):
    yield widget
    child = widget.get_first_child()
    while child:
        yield from walk(child); child = child.get_next_sibling()


def result():
    return next((w for w in walk(dialog) if isinstance(w, Gtk.Button) and '[x].*' in (w.get_label() or '')), None)


def begin():
    global dialog
    app.search_conversation(); dialog = app.dialogs[-1]
    next(w for w in walk(dialog) if isinstance(w, Gtk.SearchEntry)).set_text('[x].* áudio')


def exception(*args):
    errors.append(''.join(traceback.format_exception(*args))); print(errors[-1], file=sys.stderr); app.quit()


sys.excepthook = exception


def check():
    global phase, original_session
    if time.monotonic() > deadline:
        raise AssertionError(f'Loaded search timeout {phase}')
    if phase == 0 and app.session and app.messages:
        original_session = copy.deepcopy(app.session)
        messages = [{'id': f'msg_search_{i}', 'type': 'assistant', 'text': ('literal [x].* ÁUDIO\n' if i == 10 else '') + f'Paragraph {i}\n' + ('Text for native reading geometry. '*30), 'time': {'created': i, 'completed': i+1}} for i in range(25)]
        app.client.messages[app.session['id']] = messages; app.messages = messages; app.render_messages(messages)
        begin(); phase = 1
    elif phase == 1 and result():
        other = dict(app.session, id='ses_other', title='Other')
        app.store.data['drafts']['ses_other'] = {'text': 'Other unsent draft', 'files': []}
        app.open_chat(other); result().emit('clicked')
        assert dialog in app.dialogs and any(isinstance(w, Gtk.Label) and 'Conversa mudou' in w.get_text() for w in walk(dialog))
        assert app.current_draft()['text'] == 'Other unsent draft'
        dialog.close(); app.open_chat(original_session); phase = 2
    elif phase == 2 and len(app.messages) == 25 and not app.refreshing:
        begin(); phase = 3
    elif phase == 3 and result():
        assert any(isinstance(w, Gtk.Label) and w.get_text() == '1 resultado(s)' for w in walk(dialog))
        result().emit('clicked'); phase = 4
    elif phase == 4:
        ok, bounds = app.message_widgets['msg_search_10'][1].compute_bounds(app.scroll)
        assert ok and abs(bounds.get_y()) < 8, bounds.get_y()
        assert all(method == 'GET' for method, _ in calls)
        assert not any('/command' in path or '/prompt' in path for _, path in calls)
        assert app.sent == 0
        print('PASS: local literal/case-insensitive query found one loaded message and scrolled its native widget to view; stale result refused after navigation, unrelated draft preserved, zero provider/mutation requests.', flush=True)
        app.window.close(); app.quit(); return GLib.SOURCE_REMOVE
    return GLib.SOURCE_CONTINUE


GLib.timeout_add(120, check); app.run([])
assert not errors, errors
assert phase == 4
