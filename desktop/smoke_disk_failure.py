"""Fail private draft persistence, attempt native close, recover and reopen state."""
import os
from pathlib import Path
import sys
import time
import traceback

if os.environ.get('POCKET_TEST_INSTALL'):
    sys.path.insert(0, os.environ['POCKET_TEST_INSTALL'])
from main import Pocket, GLib
from backend import Store

root = Path('/scratch/disk-failure-state')
app = Pocket(demo=True, state=root)
phase = 0; errors = []; deadline = time.monotonic()+20; original_save = None; before = None; sid = None


def exception(*args):
    errors.append(''.join(traceback.format_exception(*args))); print(errors[-1], file=sys.stderr); app.quit()


sys.excepthook = exception


def check():
    global phase, original_save, before, sid
    if time.monotonic() > deadline:
        raise AssertionError(f'Disk failure timeout {phase}')
    if phase == 0 and app.session and app.messages and not app.refreshing:
        sid = app.session['id']; app.persist(); before = (root/'preferences.json').read_bytes()
        original_save = app.store.save
        def fail_save():
            raise OSError('fixture disk full')
        app.store.save = fail_save
        app.draft.get_buffer().set_text('Texto não salvo — preserve áudio e código\nprint("fixture")')
        app.save_draft()
        assert 'fixture disk full' in app.notice.get_text()
        assert (root/'preferences.json').read_bytes() == before
        assert app.close() is True, 'Failed persistence must block window close before shutting down the client.'
        assert not app.closing and app.window.get_visible()
        assert app.pool.submit(lambda: 'still usable').result(timeout=2) == 'still usable'
        assert app.close() is True
        assert len([w for w in app.dialogs if w.get_title() == 'Rascunho não salvo']) == 1
        assert app.current_draft()['text'].startswith('Texto não salvo')
        print('PASS: simulated disk-full preserved previous preferences and current UTF-8 draft; close was blocked before cleanup, worker remained usable and repeated close made one warning.', flush=True)
        app.store.save = original_save
        app.draft.get_buffer().set_text(app.current_draft()['text'] + '\nmore edits after failure')
        phase = 1
    elif phase == 1:
        app.window.close()
        restored = Store(root)
        assert restored.data['drafts'][sid]['text'].endswith('more edits after failure')
        assert app.closing
        print('PASS: after storage recovered, normal close saved all subsequent edits; fresh Store restored exact draft. No provider, upload or host state used.', flush=True)
        app.quit(); return GLib.SOURCE_REMOVE
    return GLib.SOURCE_CONTINUE


GLib.timeout_add(120, check); app.run([])
assert not errors, errors
assert phase == 1
