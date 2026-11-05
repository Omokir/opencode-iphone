"""Actual native GTK3/VTE PTY and guarded paste, private Xvfb/home/network."""
import os
from pathlib import Path
import subprocess
import sys
import time
import traceback

if os.environ.get('POCKET_TEST_INSTALL'):
    sys.path.insert(0, os.environ['POCKET_TEST_INSTALL'])
from terminal import TerminalWindow, Gtk, Gdk, GLib, Vte

project = Path('/scratch/project ; $(touch marker)'); project.mkdir()
window = TerminalWindow(str(project), shell='/bin/sh')
phase = 0; errors = []; deadline = time.monotonic() + 40
clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)


def text():
    return window.terminal.get_text_format(Vte.Format.TEXT) or ''


def command(value):
    window.terminal.feed_child((value+'\n').encode())


def exception(*args):
    value = ''.join(traceback.format_exception(*args)); print(value, file=sys.stderr, flush=True); errors.append(value); window.close()


sys.excepthook = exception


def check():
    global phase
    if time.monotonic() > deadline:
        raise AssertionError(f'Native VTE timed out at phase {phase}; pid={window.pid}, exited={window.exited}; status={window.status.get_text()}')
    if phase == 0 and window.pid:
        command(r"printf '\033[31m'; printf 'ANSI_'; printf 'OK\033[0m\n'; printf 'UTF_'; printf '\303\241udio\n'; printf '__HERE__'; pwd")
        phase = 1
    elif phase == 1 and 'ANSI_OK' in text() and 'UTF_áudio' in text() and '__HERE__'+str(project) in text():
        assert '\x1b' not in text()
        command("printf 'RUN_'; printf 'START\\n'; sleep 20")
        phase = 2
        print('PASS: native VTE executed interactive input, decoded ANSI/UTF-8 and kept a metacharacter project path literal.', flush=True)
    elif phase == 2 and 'RUN_START' in text() and os.tcgetpgrp(window.terminal.get_pty().get_fd()) != window.pid:
        window.terminal.feed_child(b'\x03'); phase = 3
    elif phase == 3 and os.tcgetpgrp(window.terminal.get_pty().get_fd()) == window.pid:
        command("printf 'INT_'; printf 'OK\\n'"); phase = 4
    elif phase == 4 and 'INT_OK' in text():
        clipboard.set_text('CLIPBOARD_SENTINEL', -1)
        command(r"printf '\033]52;c;UE9JU09O\007'; printf '\033]0;untrusted-title\007'; printf 'OSC_'; printf 'DONE\n'")
        phase = 5
        print('PASS: Ctrl-C interrupted a foreground job and left the shell interactive.', flush=True)
    elif phase == 5 and 'OSC_DONE' in text():
        assert clipboard.wait_for_text() == 'CLIPBOARD_SENTINEL'
        assert window.window.get_title() == 'KzL Agent · Terminal local'
        clipboard.set_text("printf 'PASTE_'; printf 'OK\\n'\n", -1)
        window.terminal.emit('paste-clipboard'); phase = 6
    elif phase == 6 and window.review:
        assert 'PASTE_OK' not in text()
        window.review.response(Gtk.ResponseType.CANCEL); phase = 7
    elif phase == 7 and window.review is None:
        assert 'PASTE_OK' not in text()
        window.terminal.emit('paste-clipboard'); phase = 8
    elif phase == 8 and window.review:
        clipboard.set_text("printf 'BAD_'; printf 'CLIP\\n'\n", -1)
        window.review.response(Gtk.ResponseType.ACCEPT)
        window.terminal.feed_child(b'\n'); phase = 9
    elif phase == 9 and 'PASTE_OK' in text():
        assert 'BAD_CLIP' not in text()
        assert not (project/'marker').exists() and not Path('/scratch/marker').exists()
        assert window.terminal.get_allow_hyperlink() is False and window.terminal.get_enable_sixel() is False
        subprocess.run(['import', '-window', 'root', '/scratch/native-terminal.png'], check=True, timeout=10)
        command('exit'); phase = 10
        print('PASS: OSC clipboard/title requests did not affect host UI; cancelled multiline paste did not run, accepted paste used the reviewed snapshot.', flush=True)
    elif phase == 10 and window.exited:
        window.close()
        print('PASS: child-exit lifecycle completed; no gateway, provider, user startup files or external network used.', flush=True)
        return GLib.SOURCE_REMOVE
    return GLib.SOURCE_CONTINUE


window.start(); GLib.timeout_add(100, check)
Gtk.main()
assert not errors, errors
assert phase == 10
