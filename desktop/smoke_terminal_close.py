"""Cancel/confirm close with a live foreground job, then reopen a native PTY."""
import os
from pathlib import Path
import sys
import time
import traceback

if os.environ.get('POCKET_TEST_INSTALL'):
    sys.path.insert(0, os.environ['POCKET_TEST_INSTALL'])
from terminal import TerminalWindow, Gtk, GLib, Vte

project = Path('/scratch/active-close-project'); project.mkdir()
first = TerminalWindow(str(project), shell='/bin/sh'); first.on_closed = lambda: None
second = None; third = None; phase = 0; errors = []; deadline = time.monotonic()+30; foreground = None; closed_at = None


def running(pid):
    try:
        value = Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()[0]
        return value not in ('Z', 'X')
    except FileNotFoundError:
        return False


def confirmation():
    return next(window for window in Gtk.Window.list_toplevels() if isinstance(window, Gtk.MessageDialog) and window.get_visible() and window.get_transient_for() is first.window)


def exception(*args):
    value = ''.join(traceback.format_exception(*args)); print(value, file=sys.stderr, flush=True); errors.append(value)
    first.close()
    if second:
        second.close()
    if third:
        third.close()
    if Gtk.main_level():
        Gtk.main_quit()


sys.excepthook = exception


def check():
    global phase, second, third, foreground, closed_at
    if time.monotonic() > deadline:
        raise AssertionError(f'Active close timed out at {phase}, shell={first.pid}, job={foreground}, exited={first.exited}')
    if phase == 0 and first.pid:
        first.terminal.feed_child(b"printf 'ACTIVE_'; printf 'JOB\\n'; sleep 30\n"); phase = 1
    elif phase == 1 and 'ACTIVE_JOB' in (first.terminal.get_text_format(Vte.Format.TEXT) or '') and os.tcgetpgrp(first.terminal.get_pty().get_fd()) not in (0, first.pid):
        foreground = os.tcgetpgrp(first.terminal.get_pty().get_fd())
        assert running(foreground)
        first.delete(); confirmation().response(Gtk.ResponseType.CANCEL)
        assert not first.closed and running(first.pid) and running(foreground)
        print('PASS: cancelling native terminal close preserves the live shell and foreground job.', flush=True)
        first.delete(); confirmation().response(Gtk.ResponseType.OK)
        assert first.closing; closed_at = time.monotonic(); phase = 2
    elif phase == 2:
        if running(first.pid) or running(foreground):
            if time.monotonic()-closed_at > 3:
                raise AssertionError(f'Closing the PTY left an active fixture process: shell={running(first.pid)}, job={running(foreground)}')
            return GLib.SOURCE_CONTINUE
        if not first.closed:
            return GLib.SOURCE_CONTINUE
        second = TerminalWindow(str(project), shell='/bin/sh'); second.on_closed = lambda: None; second.start(); phase = 3
        print('PASS: confirming close released the PTY; neither fixture shell nor foreground job remained running.', flush=True)
    elif phase == 3 and second.pid:
        second.terminal.feed_child(b"printf 'RECOVERY_'; printf 'OK\\n'\n"); phase = 4
    elif phase == 4 and 'RECOVERY_OK' in (second.terminal.get_text_format(Vte.Format.TEXT) or ''):
        second.terminal.feed_child(b'exit\n'); phase = 5
    elif phase == 5 and second.exited:
        second.close()
        print('PASS: reopening a terminal after active closure produced a new usable interactive shell.', flush=True)
        third = TerminalWindow(str(project), shell='/bin/sh'); third.on_closed = lambda: None
        third.start(); third.close(); phase = 6
    elif phase == 6 and third.closed:
        assert not third.pid or not running(third.pid)
        print('PASS: closing during asynchronous shell startup left no late-running child.', flush=True)
        Gtk.main_quit()
        return GLib.SOURCE_REMOVE
    return GLib.SOURCE_CONTINUE


first.start(); GLib.timeout_add(100, check); Gtk.main()
assert not errors, errors
assert phase == 6
