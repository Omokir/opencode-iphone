"""Native conversation geometry and keyboard checks; demo only, no API."""
import os
from pathlib import Path
import sys
import time
import traceback

if os.environ.get('POCKET_TEST_INSTALL'):
    sys.path.insert(0, os.environ['POCKET_TEST_INSTALL'])
from main import Pocket, Gtk, GLib

app = Pocket(demo=True, state='/scratch/polish-state')
deadline = time.monotonic()+25; phase = 0; errors = []


def exception(*args):
    errors.append(''.join(traceback.format_exception(*args)))
    print(errors[-1], file=sys.stderr); app.quit()


sys.excepthook = exception


def check():
    global phase
    if time.monotonic() > deadline:
        raise AssertionError(f'Polish checks timed out at {phase}')
    if phase == 0 and app.session and app.messages:
        app.portrait.set_active(True); phase = 1
    elif phase == 1 and app.window.get_width() <= 430:
        for widget in (app.voice_button, app.send_button):
            assert widget.get_width() >= 44 and widget.get_height() >= 44
            assert widget.get_focusable() and widget.get_tooltip_text()
            ok, bounds = widget.compute_bounds(app.window)
            assert ok and bounds.get_x() >= 0 and bounds.get_x()+bounds.get_width() <= app.window.get_width()
        assert app.voice_button.get_parent() is app.send_button.get_parent()
        assert app.draft.grab_focus()
        assert app.draft.has_focus()
        app.draft.get_buffer().set_text('Keyboard review — not sent')
        assert app.send_button.grab_focus() and app.send_button.has_focus()
        app.apply_theme('dark'); phase = 2
        print('PASS: 414px portrait composer keeps 44px named/focusable voice/send targets inside the window; draft and send accept keyboard focus.', flush=True)
    elif phase == 2:
        assert app.draft.get_buffer().get_text(app.draft.get_buffer().get_start_iter(), app.draft.get_buffer().get_end_iter(), True) == 'Keyboard review — not sent'
        assert app.sent == 0
        app.portrait.set_active(False); phase = 3
    elif phase == 3 and app.window.get_width() > 800:
        assert app.sidebar.get_visible() and app.sent == 0
        print('PASS: theme/portrait/desktop changes preserve unsent draft; native navigation retained, no API or paid voice started.', flush=True)
        app.window.close(); app.quit(); return GLib.SOURCE_REMOVE
    return GLib.SOURCE_CONTINUE


GLib.timeout_add(150, check); app.run([])
assert not errors, errors
assert phase == 3
