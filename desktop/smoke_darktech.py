"""Native darktech desktop/portrait captures, theme persistence and usability."""
import os
from pathlib import Path
import subprocess
import sys
import time
import traceback

if os.environ.get('POCKET_TEST_INSTALL'):
    sys.path.insert(0, os.environ['POCKET_TEST_INSTALL'])
from main import Pocket, Gtk, Adw, GLib
from backend import Store

app = Pocket(demo=True, state='/scratch/darktech-state')
phase = 0; errors = []; deadline = time.monotonic()+25; ready_at = None


def shot(name):
    subprocess.run(['import', '-window', 'root', '/scratch/'+name+'.png'], check=True, timeout=10)


def exception(*args):
    errors.append(''.join(traceback.format_exception(*args))); print(errors[-1], file=sys.stderr); app.quit()


sys.excepthook = exception


def check():
    global phase, ready_at
    if time.monotonic() > deadline:
        raise AssertionError(f'Darktech timeout {phase}')
    if phase == 0 and app.session and app.messages:
        assert Adw.StyleManager.get_default().get_dark() and app.window.has_css_class('darktech')
        app.draft.get_buffer().set_text('Revisar implementação')
        phase = 1; ready_at = time.monotonic()
    elif phase == 1 and time.monotonic()-ready_at > .4:
        assert app.send_button.get_sensitive() and app.send_button.get_width() >= 44
        shot('darktech-desktop')
        app.portrait.set_active(True); phase = 2; ready_at = time.monotonic()
    elif phase == 2 and app.window.get_width() <= 430 and time.monotonic()-ready_at > .4:
        assert not app.sidebar.get_visible()
        for widget in (app.voice_button, app.send_button):
            ok, bounds = widget.compute_bounds(app.window)
            assert ok and bounds.get_x() >= 0 and bounds.get_x()+bounds.get_width() <= app.window.get_width()
        shot('darktech-portrait')
        app.options(); assert app.dialogs[-1].has_css_class('darktech')
        app.apply_theme('light')
        assert not app.window.has_css_class('darktech') and not app.dialogs[-1].has_css_class('darktech')
        app.apply_theme('dark')
        assert app.window.has_css_class('darktech') and app.dialogs[-1].has_css_class('darktech')
        for dialog in list(app.dialogs):
            dialog.close()
        assert app.current_draft()['text'] == 'Revisar implementação' and app.sent == 0
        assert Store('/scratch/darktech-state').data['darktech_v1'] is True
        print('PASS: native darktech default, desktop/414px captures, 44px actions, synchronized dialog/light/dark themes and preserved unsent draft; no provider/media started.', flush=True)
        app.window.close(); app.quit(); return GLib.SOURCE_REMOVE
    return GLib.SOURCE_CONTINUE


GLib.timeout_add(150, check); app.run([])
assert not errors, errors
assert phase == 2
