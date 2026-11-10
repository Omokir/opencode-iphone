"""GTK4 launcher consent/directory binding; actual PTY is tested separately."""
import os
from pathlib import Path
import sys
import time
import traceback

sys.path.insert(0, str(Path(__file__).resolve().parent.parent/'preview'))
from transport_fixture import start_fixture, FixtureGateway
if os.environ.get('POCKET_TEST_INSTALL'):
    sys.path.insert(0, os.environ['POCKET_TEST_INSTALL'])
from main import Pocket, Gtk, GLib
from backend import Gateway

server = start_fixture(); app = Pocket(demo=False, state='/scratch/terminal-launch-state')
app.client = Gateway('/scratch/terminal-launch-state', port=server.server_port); app.client.pair('123456')
project = Path('/scratch/terminal-project'); project.mkdir()
launches = []; app.spawn_terminal = lambda path: launches.append(path)
phase = 0; errors = []; deadline = time.monotonic()+30


def walk(widget):
    yield widget
    child = widget.get_first_child()
    while child:
        yield from walk(child); child = child.get_next_sibling()


def confirm():
    return next(w for w in walk(app.dialogs[-1]) if isinstance(w, Gtk.Button) and w.get_label() == 'Confirmar')


def exception(*args):
    value = ''.join(traceback.format_exception(*args)); print(value, file=sys.stderr, flush=True); errors.append(value); app.quit()


sys.excepthook = exception


def check():
    global phase
    if time.monotonic() > deadline:
        raise AssertionError(f'Terminal launcher timed out at {phase}; {app.errors}')
    if phase == 0 and app.session:
        assert app.window.get_title() == 'KzL Agent'
        assert app.header.get_title_widget().get_text() == 'KzL Agent'
        app.session['location']['directory'] = str(project)
        app.terminal_button.emit('clicked'); phase = 1
    elif phase == 1 and app.dialogs:
        assert not launches
        assert any(str(project) in w.get_text() for w in walk(app.dialogs[-1]) if isinstance(w, Gtk.Label))
        app.dialogs[-1].close(); app.terminal_button.emit('clicked'); phase = 2
    elif phase == 2 and app.dialogs:
        confirm().emit('clicked'); assert launches == [str(project)]
        app.terminal_button.emit('clicked'); phase = 3
    elif phase == 3 and app.dialogs:
        app.scope += 1; confirm().emit('clicked')
        assert launches == [str(project)]
        assert any('Conversa mudou' in error for error in app.errors)
        assert not any(call[1].endswith('/prompt') for call in FixtureGateway.calls)
        print('PASS: KzL Agent title/header, reviewed directory and cancel/stale-context guards verified; no shell or provider launched by UI test.', flush=True)
        app.window.close(); app.quit(); return GLib.SOURCE_REMOVE
    return GLib.SOURCE_CONTINUE


try:
    GLib.timeout_add(120, check); app.run([])
    assert not errors, errors
    assert phase == 3
finally:
    server.shutdown(); server.server_close()
