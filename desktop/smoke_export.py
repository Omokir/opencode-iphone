"""Local transcript snapshot through actual GTK chooser; no gateway writes."""
import os
from pathlib import Path
import sys
import time
import traceback

if os.environ.get('POCKET_TEST_INSTALL'):
    sys.path.insert(0, os.environ['POCKET_TEST_INSTALL'])
from main import Pocket, Gtk, Gio, GLib
from backend import conversation_export

app = Pocket(demo=True, state='/scratch/export-state')
destination = Path('/scratch/transcript.txt')
phase = 0; errors = []; writes = []; expected = None; deadline = time.monotonic()+35
original = app.client.request


def request(path, method='GET', body=None):
    if method != 'GET':
        writes.append(path)
    return original(path, method, body)


app.client.request = request


def chooser(**kwargs):
    control = Gtk.FileChooserDialog(title=kwargs['title'], transient_for=kwargs['transient_for'], action=kwargs['action'])
    control.add_buttons('Cancelar', Gtk.ResponseType.CANCEL, 'Salvar', Gtk.ResponseType.ACCEPT)
    control.set_current_folder(Gio.File.new_for_path('/scratch')); return control


app.save_chooser_factory = chooser


def walk(widget):
    yield widget
    child = widget.get_first_child()
    while child:
        yield from walk(child); child = child.get_next_sibling()


def find(text, window):
    return next(w for w in walk(window) if isinstance(w, Gtk.Button) and w.get_label() == text)


def exception(*args):
    errors.append(''.join(traceback.format_exception(*args))); print(errors[-1], file=sys.stderr); app.quit()


sys.excepthook = exception


def check():
    global phase, expected
    if time.monotonic() > deadline:
        raise AssertionError(f'Export timeout {phase}')
    if phase == 0 and app.session and app.messages:
        app.export_conversation(); find('Escolher destino', app.dialogs[-1]).emit('clicked')
        app.save_choosers[-1].response(Gtk.ResponseType.CANCEL)
        assert not destination.exists()
        app.draft.get_buffer().set_text('PRIVATE_UNSENT_DRAFT')
        expected = conversation_export(app.session, app.messages)
        app.export_conversation(); find('Escolher destino', app.dialogs[-1]).emit('clicked')
        app.save_choosers[-1].set_current_name(destination.name)
        other = dict(app.session, id='ses_other', title='Unrelated conversation')
        app.open_chat(other); phase = 1
    elif phase == 1 and app.save_choosers[-1].get_file() and app.save_choosers[-1].get_file().get_path() == str(destination):
        app.save_choosers[-1].response(Gtk.ResponseType.ACCEPT); phase = 2
    elif phase == 2 and destination.exists():
        assert destination.read_bytes() == expected and b'PRIVATE_UNSENT_DRAFT' not in expected
        assert app.session['id'] == 'ses_other' and not writes and app.sent == 0
        assert destination.stat().st_mode & 0o777 == 0o600
        print('PASS: native chooser cancel wrote nothing; UTF-8 transcript used reviewed original snapshot after navigation, excluded unsent draft and saved privately/atomically without gateway writes.', flush=True)
        app.export_conversation(); find('Escolher destino', app.dialogs[-1]).emit('clicked')
        app.save_choosers[-1].set_current_name(destination.name); phase = 3
    elif phase == 3 and app.save_choosers[-1].get_file() and app.save_choosers[-1].get_file().get_path() == str(destination):
        app.save_choosers[-1].response(Gtk.ResponseType.ACCEPT); phase = 4
    elif phase == 4:
        if app.dialogs and app.dialogs[-1].get_title() == 'Substituir arquivo?':
            assert destination.read_bytes() == expected
            app.dialogs[-1].close(); phase = 5
        else:
            windows = Gtk.Window.get_toplevels()
            for index in range(windows.get_n_items()):
                window = windows.get_item(index)
                if window.get_visible():
                    for control in walk(window):
                        if isinstance(control, Gtk.Button) and (control.get_label() or '').replace('_', '').casefold() in ('replace', 'substituir'):
                            control.emit('clicked'); return GLib.SOURCE_CONTINUE
    elif phase == 5:
        assert destination.read_bytes() == expected and not writes
        assert not list(Path('/scratch').glob('.pocket-download-*'))
        print('PASS: existing transcript remained unchanged after replacement consent was cancelled; no partial export or provider request.', flush=True)
        app.window.close(); app.quit(); return GLib.SOURCE_REMOVE
    return GLib.SOURCE_CONTINUE


GLib.timeout_add(120, check); app.run([])
assert not errors, errors
assert phase == 5
