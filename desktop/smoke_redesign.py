"""Native redesign geometry/navigation smoke. Demo data only; no APIs/media.

Run on private Xvfb/D-Bus. Set POCKET_SMOKE_DIR to a private writable directory.
Screenshots are optional: POCKET_SMOKE_CAPTURE=1 requires ImageMagick import.
"""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import traceback

if os.environ.get('POCKET_TEST_INSTALL'):
    sys.path.insert(0, os.environ['POCKET_TEST_INSTALL'])
from main import Pocket, Gtk, Gdk, GLib

scratch = Path(os.environ.get('POCKET_SMOKE_DIR', tempfile.mkdtemp(prefix='kzl-redesign-')))
scratch.mkdir(parents=True, exist_ok=True)
app = Pocket(demo=True, state=scratch / 'state')
phase = 0
errors = []
deadline = time.monotonic() + 30
ready_at = 0


def walk(widget):
    yield widget
    child = widget.get_first_child()
    while child:
        yield from walk(child)
        child = child.get_next_sibling()


def shot(name):
    if os.environ.get('POCKET_SMOKE_CAPTURE') == '1':
        subprocess.run(['import', '-window', 'root', str(scratch / (name + '.png'))], check=True, timeout=10)


def exception(*args):
    errors.append(''.join(traceback.format_exception(*args)))
    print(errors[-1], file=sys.stderr)
    app.quit()


sys.excepthook = exception


def check():
    global phase, ready_at
    assert time.monotonic() < deadline, f'Redesign timeout at phase {phase}'
    if phase == 0 and app.session and app.messages:
        app.draft.get_buffer().set_text('Rascunho preservado pelo redesign')
        assert any(w.has_css_class('message-avatar') for w in walk(app.message_box))
        assert any(w.has_css_class('message-time') for w in walk(app.message_box))
        assert app.subtitle.get_text() == app.options_button.get_label()
        phase = 1; ready_at = time.monotonic()
    elif phase == 1 and time.monotonic() - ready_at > .4:
        shot('redesign-desktop')
        app.chat_menu.popup(); phase = 2
    elif phase == 2:
        assert app.chat_popover.get_visible()
        app.chat_popover.popdown()
        assert app.sent == 0
        app.portrait.set_active(True); phase = 3; ready_at = time.monotonic()
    elif phase == 3 and app.window.get_width() <= 430 and time.monotonic() - ready_at > .4:
        assert not app.sidebar.get_visible() and app.content.get_visible()
        for widget in (app.voice_button, app.send_button, app.chat_menu, app.options_button):
            ok, rect = widget.compute_bounds(app.window)
            assert ok and rect.get_x() >= 0
            assert rect.get_x() + rect.get_width() <= app.window.get_width()
        for widget in (app.voice_button, app.send_button):
            assert widget.get_width() >= 44 and widget.get_height() >= 44
        shot('redesign-portrait')
        app.window_shortcuts(None, Gdk.KEY_k, 0, Gdk.ModifierType.CONTROL_MASK)
        phase = 4
    elif phase == 4:
        assert app.sidebar.get_visible() and not app.content.get_visible()
        app.error('Falha sintética: mensagem visível no histórico')
        assert app.notice.get_parent() is app.root and app.notice.get_mapped()
        app.error('')
        app.window_shortcuts(None, Gdk.KEY_f, 0, Gdk.ModifierType.CONTROL_MASK)
        assert not app.sidebar.get_visible() and app.content.get_visible()
        for dialog in list(app.dialogs):
            dialog.close()
        app.options()
        assert app.dialogs
        assert not app.window_shortcuts(None, Gdk.KEY_k, 0, Gdk.ModifierType.CONTROL_MASK)
        for dialog in list(app.dialogs):
            dialog.close()
        app.apply_theme('light'); app.apply_theme('dark')
        assert app.current_draft()['text'] == 'Rascunho preservado pelo redesign'
        assert app.sent == 0
        app.portrait.set_active(False); phase = 5
    elif phase == 5 and app.window.get_width() > 800:
        assert app.sidebar.get_visible() and app.content.get_visible()
        print('PASS: redesign avatars/times, action menu, 414px geometry, search/sidebar return, modal shortcut guard, theme and draft preservation; no API/media started.', flush=True)
        app.window.close(); app.quit(); return GLib.SOURCE_REMOVE
    return GLib.SOURCE_CONTINUE


GLib.timeout_add(150, check)
app.run([])
assert not errors, errors
assert phase == 5
