#!/usr/bin/env python3
"""KzL Agent local terminal helper — separate GTK3/VTE process, no gateway API.

Only explicit human activation starts an interactive shell. Markdown/provider
output is never fed here. Terminal output cannot set our window title or open
links. Clipboard paste is bounded and multiline content needs review.
"""
import argparse
import os
import signal
import select
from pathlib import Path

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
gi.require_version('Vte', '2.91')
from gi.repository import Gdk, Gio, GLib, Gtk, Pango, Vte
from terminal_policy import SHELLS, directory_path, shell_path, paste_text


class TerminalWindow:
    def __init__(self, directory, shell=None):
        self.directory = directory_path(directory); self.shell = shell_path(shell)
        if self.directory != directory:
            raise ValueError('Confirme o caminho canônico do projeto antes de abrir o shell.')
        self.pid = None; self.exited = False; self.closed = False; self.review = None
        self.closing = False; self.spawn_pending = False; self.spawn_cancel = Gio.Cancellable(); self.pidfd = None; self.close_timer = 0
        self.on_closed = lambda: Gtk.main_quit() if Gtk.main_level() else None
        self.window = Gtk.Window(title='KzL Agent · Terminal local')
        self.window.set_wmclass('kzl-agent-terminal', 'com.omokir.PocketDesktop')
        self.window.set_icon_from_file(str(Path(__file__).with_name('KzL.png')))
        self.window.set_default_size(980, 660)
        header = Gtk.HeaderBar(title='KzL Agent · Terminal local', subtitle=self.directory, show_close_button=True)
        self.window.set_titlebar(header)
        copy = Gtk.Button.new_from_icon_name('edit-copy-symbolic', Gtk.IconSize.BUTTON); copy.set_tooltip_text('Copiar seleção · Ctrl+Shift+C')
        copy.connect('clicked', lambda *_: self.terminal.copy_clipboard_format(Vte.Format.TEXT)); header.pack_end(copy)
        paste = Gtk.Button.new_from_icon_name('edit-paste-symbolic', Gtk.IconSize.BUTTON); paste.set_tooltip_text('Colar · texto multilinha exige revisão')
        paste.connect('clicked', lambda *_: self.request_paste()); header.pack_end(paste)
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.terminal = Vte.Terminal()
        self.terminal.set_allow_hyperlink(False); self.terminal.set_enable_sixel(False)
        self.terminal.set_scrollback_lines(10000); self.terminal.set_scroll_on_keystroke(True); self.terminal.set_scroll_on_output(False)
        self.terminal.set_font(Pango.FontDescription('Monospace 11'))
        foreground = Gdk.RGBA(); foreground.parse('#eeeeef')
        background = Gdk.RGBA(); background.parse('#151518')
        self.terminal.set_colors(foreground, background, [])
        self.terminal.set_margin_start(12); self.terminal.set_margin_end(12); self.terminal.set_margin_top(10); self.terminal.set_margin_bottom(10)
        self.terminal.drag_dest_unset()  # No unreviewed text/URI drops into the PTY.
        self.terminal.connect('paste-clipboard', self.intercept_paste)
        self.terminal.connect('button-press-event', self.mouse)
        self.terminal.connect('key-press-event', self.key)
        self.terminal.connect('child-exited', self.child_exited)
        scroll = Gtk.ScrolledWindow(); scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC); scroll.add(self.terminal); root.pack_start(scroll, True, True, 0)
        self.status = Gtk.Label(label='Shell local: comandos têm seus direitos de usuário. Não há conexão de shell pelo gateway.', xalign=0)
        self.status.set_margin_start(12); self.status.set_margin_end(12); self.status.set_margin_top(8); self.status.set_margin_bottom(8); self.status.set_line_wrap(True)
        root.pack_start(self.status, False, False, 0); self.window.add(root)
        self.window.connect('delete-event', self.delete)
        self.window.connect('destroy', lambda *_: self.on_closed())

    def start(self):
        self.window.show_all()
        self.spawn_pending = True
        env = dict(os.environ); env['TERM'] = 'xterm-256color'; env['COLORTERM'] = 'truecolor'
        # argv is fixed; the project directory is a cwd argument, never `cd ...`
        # interpolated into a command. Interactive shell startup files remain the user's.
        self.terminal.spawn_async(pty_flags=Vte.PtyFlags.DEFAULT, working_directory=self.directory,
                                  argv=[self.shell, '-i'], envv=[key + '=' + value for key, value in env.items()],
                                  spawn_flags=GLib.SpawnFlags.DEFAULT, child_setup=None,
                                  timeout=10000, cancellable=self.spawn_cancel, callback=self.spawned, user_data=None)

    def spawned(self, terminal, pid, error, *_):
        self.spawn_pending = False
        if error:
            self.status.set_text('Não foi possível iniciar o shell local. Confira a pasta e o shell instalado.')
            if self.closing:
                GLib.idle_add(self.finish_close)
            return
        self.pid = pid
        try:
            self.pidfd = os.pidfd_open(pid)
        except OSError:
            self.pidfd = None
        if self.closing:
            self.request_child_close(); return
        self.terminal.grab_focus()
        self.status.set_text('Terminal local · Ctrl+Shift+C copia · Ctrl+Shift+V cola · colagens multilinha exigem revisão')

    def child_exited(self, terminal, status):
        self.exited = True
        self.release_pidfd()
        self.status.set_text('Shell encerrado. A saída permanece disponível para consulta e cópia.')
        if self.closing:
            GLib.idle_add(self.finish_close)

    def release_pidfd(self):
        if self.pidfd is not None:
            os.close(self.pidfd); self.pidfd = None
        if self.close_timer:
            GLib.source_remove(self.close_timer); self.close_timer = 0

    def intercept_paste(self, terminal):
        terminal.stop_emission_by_name('paste-clipboard'); self.request_paste()

    def key(self, terminal, event):
        control = event.state & Gdk.ModifierType.CONTROL_MASK
        shift = event.state & Gdk.ModifierType.SHIFT_MASK
        if control and shift and event.keyval in (Gdk.KEY_v, Gdk.KEY_V):
            self.request_paste(); return True
        if control and shift and event.keyval in (Gdk.KEY_c, Gdk.KEY_C):
            terminal.copy_clipboard_format(Vte.Format.TEXT); return True
        if shift and event.keyval == Gdk.KEY_Insert:
            self.request_paste(primary=True); return True
        return False

    def mouse(self, terminal, event):
        if event.button == 2:
            self.request_paste(primary=True); return True
        if event.button == 3:
            menu = Gtk.Menu()
            for name, callback in [('Copiar seleção', lambda: terminal.copy_clipboard_format(Vte.Format.TEXT)), ('Colar texto', self.request_paste)]:
                item = Gtk.MenuItem(label=name); item.connect('activate', lambda _, action=callback: action()); menu.append(item)
            menu.show_all(); menu.popup_at_pointer(event); return True
        return False

    def request_paste(self, primary=False):
        if not self.pid or self.exited or self.closed or self.closing or self.review:
            return
        clipboard = Gtk.Clipboard.get(Gdk.SELECTION_PRIMARY if primary else Gdk.SELECTION_CLIPBOARD)
        def received(clipboard, text, *_):
            if self.closed or self.closing or self.exited or self.review:
                return
            try:
                value = paste_text(text)
            except (ValueError, UnicodeError) as error:
                self.status.set_text(str(error)); return
            if '\n' not in value and '\r' not in value:
                self.terminal.paste_text(value); return
            dialog = Gtk.Dialog(title='Revisar colagem no terminal', transient_for=self.window, modal=True)
            dialog.add_buttons('Cancelar', Gtk.ResponseType.CANCEL, 'Colar texto revisado', Gtk.ResponseType.ACCEPT)
            dialog.set_default_size(640, 400)
            content = dialog.get_content_area(); content.set_spacing(12); content.set_border_width(16)
            warning = Gtk.Label(label='Este texto contém quebras de linha e pode executar comandos no shell. Confira antes de colar.', xalign=0); warning.set_line_wrap(True); content.pack_start(warning, False, False, 0)
            view = Gtk.TextView(editable=False, monospace=True, wrap_mode=Gtk.WrapMode.WORD_CHAR); view.get_buffer().set_text(value)
            scroll = Gtk.ScrolledWindow(); scroll.add(view); content.pack_start(scroll, True, True, 0)
            self.review = dialog
            def response(dialog, response):
                if response == Gtk.ResponseType.ACCEPT and not self.closed and not self.closing and not self.exited:
                    self.terminal.paste_text(value)  # The exact reviewed snapshot; never reread the clipboard.
                self.review = None; dialog.destroy()
            dialog.connect('response', response); dialog.show_all()
        clipboard.request_text(received, None)

    def delete(self, *_):
        if self.closing:
            return True
        if self.pid and not self.exited:
            dialog = Gtk.MessageDialog(transient_for=self.window, modal=True, message_type=Gtk.MessageType.WARNING,
                                       buttons=Gtk.ButtonsType.OK_CANCEL, text='Fechar terminal local?')
            dialog.format_secondary_text('Comandos deste terminal podem ser interrompidos ao fechar a conexão PTY. Tarefas já enviadas ao OpenCode não são canceladas por isso.')
            def response(dialog, result):
                dialog.destroy()
                if result == Gtk.ResponseType.OK:
                    self.close()
            dialog.connect('response', response); dialog.show_all(); return True
        self.close(); return True

    def close(self):
        if self.closed or self.closing:
            return
        self.closing = True
        if self.review:
            self.review.destroy(); self.review = None
        self.terminal.set_sensitive(False)
        if self.spawn_pending:
            self.status.set_text('Cancelando inicialização do shell…')
            self.spawn_cancel.cancel(); return
        if self.pid and not self.exited:
            self.request_child_close(); return
        self.finish_close()

    def request_child_close(self):
        # Do not detach a live PTY: current VTE can crash in set_pty(None).
        # A pidfd targets precisely our spawned shell, never a recycled PID or
        # process group supplied by chat output. No automatic SIGKILL escalation.
        if self.pidfd is None:
            self.closing = False; self.terminal.set_sensitive(True)
            self.status.set_text('Identificador seguro indisponível. Digite exit no shell antes de fechar.'); return
        self.status.set_text('Encerrando o shell local; aguardando saída antes de fechar…')
        try:
            signal.pidfd_send_signal(self.pidfd, signal.SIGHUP)
        except ProcessLookupError:
            pass  # Reaper callback is about to confirm exit.
        except OSError:
            self.closing = False; self.terminal.set_sensitive(True)
            self.status.set_text('Não foi possível encerrar o shell. Use Ctrl-C/exit antes de fechar.'); return
        self.close_timer = GLib.timeout_add(3000, self.close_timeout)

    def close_timeout(self):
        self.close_timer = 0
        if self.exited or (self.pidfd is not None and select.select([self.pidfd], [], [], 0)[0]):
            self.exited = True; self.release_pidfd(); self.finish_close()
        else:
            self.closing = False; self.terminal.set_sensitive(True)
            self.status.set_text('O shell continua ativo. A janela foi mantida; use Ctrl-C/exit e feche novamente.')
        return GLib.SOURCE_REMOVE

    def finish_close(self):
        if self.closed or self.spawn_pending or (self.pid and not self.exited):
            return GLib.SOURCE_REMOVE
        self.closed = True; self.closing = False; self.release_pidfd()
        self.window.destroy()
        return GLib.SOURCE_REMOVE


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', required=True)
    parser.add_argument('--shell', choices=SHELLS)
    args = parser.parse_args()
    try:
        terminal = TerminalWindow(args.directory, args.shell); terminal.start(); Gtk.main()
    except (ValueError, OSError):
        dialog = Gtk.MessageDialog(message_type=Gtk.MessageType.ERROR, buttons=Gtk.ButtonsType.CLOSE,
                                   text='Não foi possível abrir o terminal do KzL Agent.')
        dialog.format_secondary_text('Confira se a pasta local existe e GTK3/VTE estão instalados. Nenhum comando foi enviado ao gateway.')
        dialog.run(); dialog.destroy()
