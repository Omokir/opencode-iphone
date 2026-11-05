"""Native tool status transitions, literal failure details and unknown states."""
import os
import sys
import time
import traceback

if os.environ.get('POCKET_TEST_INSTALL'):
    sys.path.insert(0, os.environ['POCKET_TEST_INSTALL'])
from main import Pocket, Gtk, GLib

app = Pocket(demo=True, state='/scratch/tools-state')
phase = 0; errors = []; deadline = time.monotonic()+20; writes = []
original = app.client.request


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


def show(status):
    message = {'id': 'msg_tool_fixture', 'type': 'assistant', 'text': 'Execution review', 'time': {'created': 3, 'completed': 4}, 'content': [
        {'id': 'tool_fixture', 'type': 'tool', 'name': '<b>literal-tool</b>', 'state': {'status': status, 'error': {'message': '<script>literal failure</script>'}, 'input': {'command': 'NEVER_EXECUTE'}}, 'time': {'created': 3}}]}
    app.client.messages[app.session['id']] = [message]; app.messages = [message]; app.render_messages(app.messages)
    for widget in walk(app.message_box):
        if isinstance(widget, Gtk.Expander) and widget.get_label().startswith('Ferramentas'):
            widget.set_expanded(True)


def exception(*args):
    errors.append(''.join(traceback.format_exception(*args))); print(errors[-1], file=sys.stderr); app.quit()


sys.excepthook = exception


def check():
    global phase
    if time.monotonic() > deadline:
        raise AssertionError(f'Tool UI timeout {phase}')
    if phase == 0 and app.session and app.messages:
        show('running'); phase = 1
    elif phase == 1:
        expander = next(w for w in walk(app.message_box) if isinstance(w, Gtk.Expander) and w.get_label().startswith('Ferramentas'))
        assert 'Em execução: 1' in expander.get_label() and 'Concluída' not in expander.get_label()
        show('error'); phase = 2
    elif phase == 2:
        labels = [w.get_text() for w in walk(app.message_box) if isinstance(w, Gtk.Label)]
        assert any('Falhou: 1' in text for text in labels)
        assert any('<script>literal failure</script>' in text for text in labels)
        assert any('Falhou · <b>literal-tool</b>' == text for text in labels)
        assert not any('Concluída' in text for text in labels)
        show('future_status'); phase = 3
    elif phase == 3:
        labels = [w.get_text() for w in walk(app.message_box) if isinstance(w, Gtk.Label)]
        assert any('Estado não confirmado: 1' in text for text in labels)
        assert not any('Concluída' in text for text in labels)
        show('completed'); phase = 4
    elif phase == 4:
        labels = [w.get_text() for w in walk(app.message_box) if isinstance(w, Gtk.Label)]
        assert any('Concluída: 1' in text for text in labels)
        assert not writes and app.sent == 0
        print('PASS: running → error → unknown → completed rendered explicit native statuses; only completed counted as success. Tool names/errors stayed literal, no command or provider invoked.', flush=True)
        app.window.close(); app.quit(); return GLib.SOURCE_REMOVE
    return GLib.SOURCE_CONTINUE


GLib.timeout_add(120, check); app.run([])
assert not errors, errors
assert phase == 4
