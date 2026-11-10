"""Actual GTK save chooser -> authenticated fixture -> checksum -> atomic file."""
import hashlib
import os
from pathlib import Path
import sys
import time
import traceback

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'preview'))
from transport_fixture import start_fixture, FixtureGateway
if os.environ.get('POCKET_TEST_INSTALL'):
    sys.path.insert(0, os.environ['POCKET_TEST_INSTALL'])
from main import Pocket, Gtk, Gio, GLib
from backend import Gateway

gateway = start_fixture(); app = Pocket(demo=False, state='/scratch/download-state')
app.client = Gateway('/scratch/download-state', port=gateway.server_port); app.client.pair('123456')
phase = 0; errors = []; deadline = time.monotonic() + 45
destination = Path('/scratch/download-output.txt')
original_request = app.client.request


def chooser(**kwargs):
    # Private GTK file chooser, not a mocked file or bypassed response handler.
    window = Gtk.FileChooserDialog(title=kwargs['title'], transient_for=kwargs['transient_for'], action=kwargs['action'])
    window.add_buttons('Cancelar', Gtk.ResponseType.CANCEL, 'Salvar', Gtk.ResponseType.ACCEPT)
    window.set_current_folder(Gio.File.new_for_path('/scratch'))
    return window


app.save_chooser_factory = chooser


def walk(widget):
    yield widget
    child = widget.get_first_child()
    while child:
        yield from walk(child); child = child.get_next_sibling()


def exception(*args):
    text = ''.join(traceback.format_exception(*args)); print(text, file=sys.stderr, flush=True); errors.append(text); app.quit()


sys.excepthook = exception


def check():
    global phase
    if time.monotonic() > deadline:
        raise AssertionError(f'Download UI timed out at phase {phase}; {app.errors}')
    if phase == 0 and app.session and app.messages:
        app.download_artifact({'name': 'result.txt', 'path': '/fixture/result.txt'})
        phase = 1
    elif phase == 1 and app.save_choosers:
        control = app.save_choosers[-1]; control.set_current_name(destination.name); phase = 2
    elif phase == 2 and app.save_choosers[-1].get_file() and app.save_choosers[-1].get_file().get_path() == str(destination):
        app.save_choosers[-1].response(Gtk.ResponseType.ACCEPT); phase = 3
    elif phase == 3 and destination.exists():
        assert destination.read_bytes() == b'fixture file\n'
        assert hashlib.sha256(destination.read_bytes()).hexdigest() == hashlib.sha256(b'fixture file\n').hexdigest()
        assert any('/phone/files/context' in c[1] for c in FixtureGateway.calls)
        assert any('/phone/files/list' in c[1] for c in FixtureGateway.calls)
        assert any('/phone/files/download' in c[1] for c in FixtureGateway.calls)
        print('PASS: native artifact action -> approved root/list -> GTK save chooser -> authenticated bytes/SHA-256 -> atomic saved file.', flush=True)
        def corrupt(path, *args, **kwargs):
            if path.startswith('/phone/files/download'):
                path += '&corrupt=true'
            return original_request(path, *args, **kwargs)
        app.client.request = corrupt
        app.download('home', {'name': destination.name, 'path': 'fixture/result.txt', 'version': 'fixture-v1'})
        phase = 4
    elif phase == 4 and app.save_choosers:
        app.save_choosers[-1].set_current_name(destination.name); phase = 5
    elif phase == 5 and app.save_choosers[-1].get_file() and app.save_choosers[-1].get_file().get_path() == str(destination):
        app.save_choosers[-1].response(Gtk.ResponseType.ACCEPT); phase = 6
    elif phase == 6 and app.dialogs:
        accept = next(w for w in walk(app.dialogs[-1]) if isinstance(w, Gtk.Button) and w.get_label() == 'Confirmar')
        accept.emit('clicked'); phase = 7
    elif phase == 6:
        windows = Gtk.Window.get_toplevels()
        for index in range(windows.get_n_items()):
            window = windows.get_item(index)
            if not window.get_visible():
                continue
            for control in walk(window):
                if isinstance(control, Gtk.Button) and (control.get_label() or '').replace('_', '').casefold() in ('replace', 'substituir'):
                    control.emit('clicked')
                    print('PASS: native file chooser replacement confirmation explicitly accepted in fixture.', flush=True)
                    return GLib.SOURCE_CONTINUE
    elif phase == 7 and any('Integridade' in error for error in app.errors):
        assert destination.read_bytes() == b'fixture file\n'
        assert not list(destination.parent.glob('.pocket-download-*'))
        print('PASS: corrupted download rejected end-to-end; previously saved file preserved even after replacement consent.', flush=True)
        app.window.close(); app.quit(); return GLib.SOURCE_REMOVE
    return GLib.SOURCE_CONTINUE


try:
    GLib.timeout_add(120, check); app.run([])
    assert not errors, errors
    assert phase == 7
finally:
    gateway.shutdown(); gateway.server_close()
