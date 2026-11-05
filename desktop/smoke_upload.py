"""GTK source chooser, consent, pause, journal reload and real chunk engine."""
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import time
import traceback

from upload_fixture import start_upload_fixture, FixtureGateway
if os.environ.get('POCKET_TEST_INSTALL'):
    sys.path.insert(0, os.environ['POCKET_TEST_INSTALL'])
from main import Pocket, Gtk, Gio, GLib
from backend import Gateway
from uploads import UploadManager

server = start_upload_fixture('/scratch/upload-fixture'); server.block_chunk = True
app = Pocket(demo=False, state='/scratch/upload-ui-state')
app.client = Gateway('/scratch/upload-ui-state', port=server.server_port); app.client.pair('123456')
source = Path('/scratch/upload-source.bin'); data = b'gtk-upload-fixture\0'*24000; source.write_bytes(data)
phase = 0; errors = []; deadline = time.monotonic() + 45; identifier = None


def chooser(**kwargs):
    window = Gtk.FileChooserDialog(title=kwargs['title'], transient_for=kwargs['transient_for'], action=kwargs['action'])
    window.add_buttons('Cancelar', Gtk.ResponseType.CANCEL, 'Selecionar', Gtk.ResponseType.ACCEPT)
    window.set_current_folder(Gio.File.new_for_path('/scratch'))
    return window


app.upload_chooser_factory = chooser


def walk(widget):
    yield widget
    child = widget.get_first_child()
    while child:
        yield from walk(child); child = child.get_next_sibling()


def find_button(text):
    return next(w for dialog in app.dialogs for w in walk(dialog) if isinstance(w, Gtk.Button) and w.get_label() == text)


def exception(*args):
    text = ''.join(traceback.format_exception(*args)); print(text, file=sys.stderr, flush=True); errors.append(text); app.quit()


sys.excepthook = exception


def check():
    global phase, identifier
    if time.monotonic() > deadline:
        raise AssertionError(f'Upload UI timed out at phase {phase}; {app.errors}')
    if phase == 0 and app.session and app.messages:
        app.transfers(); find_button('Selecionar e enviar arquivo').emit('clicked'); phase = 1
    elif phase == 1 and app.upload_choosers and app.upload_choosers[-1].get_mapped() and app.upload_choosers[-1].get_current_folder() and app.upload_choosers[-1].get_current_folder().get_path() == '/scratch':
        app.upload_choosers[-1].set_file(Gio.File.new_for_path(str(source))); phase = 1.1
    elif phase == 1.1 and app.upload_choosers and app.upload_choosers[-1].get_file():
        assert app.upload_choosers[-1].get_file().get_path() == str(source)
        app.upload_choosers[-1].response(Gtk.ResponseType.ACCEPT)
        assert not server.requests, 'Choosing a file is not permission to send before confirmation.'
        find_button('Confirmar').emit('clicked'); phase = 2
    elif phase == 2 and server.first_chunk.is_set():
        find_button('Pausar envio atual').emit('clicked'); server.continue_chunk.set(); phase = 3
    elif phase == 3 and app.upload_running_id is None and app.uploads.list():
        record = app.uploads.list()[0]; identifier = record['id']
        assert record['state'] == 'paused' and record['offset'] == 64*1024
        assert not any(request['action'] == 'commit' for request in server.requests)
        assert source.read_bytes() == data
        app.transfer_window.close()
        app.uploads = UploadManager(app.store.root, app.client)  # A fresh instance reads the durable journal.
        app.transfers(); server.block_chunk = False; phase = 4
        print('PASS: native source chooser + explicit consent; pause preserves original and 64 KiB durable partial.', flush=True)
    elif phase == 4 and find_button('Retomar / conferir').get_sensitive():
        find_button('Retomar / conferir').emit('clicked'); phase = 5
    elif phase == 5 and app.upload_running_id is None and app.uploads.get(identifier)['state'] == 'completed':
        record = app.uploads.get(identifier)
        assert record['receipt']['sha256'] == hashlib.sha256(data).hexdigest()
        assert (server.home / record['destination']).read_bytes() == data
        assert source.read_bytes() == data
        offsets = [int(request['offset']) for request in server.requests if request['action'] == 'chunk']
        assert offsets.count(0) == 1
        assert server.requests[-1]['action'] == 'verify'
        phase = 6
    elif phase == 6 and find_button('Inserir no chat').get_sensitive():
        find_button('Inserir no chat').emit('clicked')
        assert identifier in app.current_draft()['text']
        assert not any(call[1].endswith('/prompt') for call in FixtureGateway.calls)
        phase = 7
    elif phase == 7:
        subprocess.run(['import', '-window', 'root', '/scratch/native-transfers.png'], check=True, timeout=10)
        print('PASS: persisted upload resumes from durable offset, verifies actual SHA-256 and bytes; origin never deleted.', flush=True)
        print('PASS: inserting confirmed remote path changes only draft; no provider prompt sent.', flush=True)
        assert not app.errors, app.errors
        app.window.close(); app.quit(); return GLib.SOURCE_REMOVE
    return GLib.SOURCE_CONTINUE


try:
    GLib.timeout_add(120, check); app.run([])
    assert not errors, errors
    assert phase == 7
finally:
    server.continue_chunk.set(); server.shutdown(); server.server_close()
