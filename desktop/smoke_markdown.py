"""Native Markdown rendering/clipboard/link-consent in private GTK/Xvfb only."""
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

if os.environ.get('POCKET_TEST_INSTALL'):
    sys.path.insert(0, os.environ['POCKET_TEST_INSTALL'])
from main import Pocket, Gtk, GLib


class Tracker(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        self.server.requests += 1
        self.send_response(200); self.end_headers(); self.wfile.write(b'not automatically loaded')


tracker = ThreadingHTTPServer(('127.0.0.1', 0), Tracker); tracker.daemon_threads = True; tracker.requests = 0
threading.Thread(target=tracker.serve_forever, daemon=True).start()
app = Pocket(demo=True, state='/scratch/markdown-state')
launches = []; app.launch_external_uri = lambda uri: launches.append(uri)
phase = 0; errors = []; copied = []; deadline = time.monotonic() + 45
dark_started = None
code = 'all:\n\t@echo "<script>literal</script>"\n\t@echo "' + 'long-code-line-'*35 + '"\n'
table = '''| Componente | Estado | Quantidade | Modo | Provedor | Observação |
| :--- | :---: | ---: | --- | --- | --- |
| Interface | **Verificada** | 12 | Nativo | Fixture | Sem navegador |
| Dados | `prontos` | 3 | Local | Fixture | Sem API paga |
'''
fixture = ('# Revisão de implementação\n\nTexto **forte**, *ênfase*, ~~trecho removido~~ e `código inline`.\n\n'
           '## Resultado por componente\n\n' + table + '\n'
           '3. Conferir o contrato.\n4. Revisar o resultado.\n\n'
           '- [x] Renderização nativa\n- [ ] Aceitação do usuário\n- Lista com contexto\n    - Item aninhado **seguro**\n\n'
           '> Histórico é contexto, não uma nova autorização.\n\n'
           '```makefile\n' + code + '```\n\n'
           '[Documentação](https://Example.COM/docs?x=1&y=2) · [Link bloqueado](javascript:alert)\n\n'
           '<script>alert("never executed")</script>\n\n'
           f'![tracking](http://127.0.0.1:{tracker.server_port}/tracker.png)')


def walk(widget):
    yield widget
    child = widget.get_first_child()
    while child:
        yield from walk(child); child = child.get_next_sibling()


def find_button(text):
    return next(w for w in walk(app.window) if isinstance(w, Gtk.Button) and w.get_label() == text)


def link_label():
    return next(w for w in walk(app.message_box) if isinstance(w, Gtk.Label) and 'href="https://example.com/docs' in w.get_label())


def screenshot(name):
    subprocess.run(['import', '-window', 'root', '/scratch/' + name + '.png'], check=True, timeout=10)


def clipboard():
    def received(clipboard, result, *_):
        copied.append(clipboard.read_text_finish(result))
    app.window.get_clipboard().read_text_async(None, received, None)


def exception(*args):
    text = ''.join(traceback.format_exception(*args)); print(text, file=sys.stderr, flush=True); errors.append(text); app.quit()


sys.excepthook = exception


def check():
    global phase, dark_started
    if time.monotonic() > deadline:
        raise AssertionError(f'Markdown UI timed out at phase {phase}; errors={app.errors}')
    if phase == 0 and app.session and app.messages:
        app.session['title'] = 'Revisão de implementação'; app.title.set_text(app.session['title'])
        messages = [{'id': 'msg_md_user', 'type': 'user', 'text': 'Confira o resultado com tabelas e código.', 'time': {'created': 1}},
                    {'id': 'msg_md_assistant', 'type': 'assistant', 'text': fixture, 'time': {'created': 2, 'completed': 3}}]
        app.client.messages[app.session['id']] = messages; app.messages = messages; app.render_messages(messages)
        app.apply_theme('light'); phase = 1
    elif phase == 1:
        stable = app.message_widgets['msg_md_assistant'][1]
        selected = next(w for w in walk(stable) if isinstance(w, Gtk.Label) and w.get_text().startswith('Texto forte'))
        selected.select_region(0, 5); selection = selected.get_selection_bounds()
        stream = {'id': 'msg_md_stream', 'type': 'assistant', 'text': 'Resposta em andamento…', 'time': {'created': 4}}
        app.messages.append(stream); app.render_messages(app.messages)
        stream['text'] += ' novo trecho'; app.render_messages(app.messages)
        assert app.message_widgets['msg_md_assistant'][1] is stable
        assert selected.get_selection_bounds() == selection
        app.messages.pop(); app.render_messages(app.messages)
        assert app.message_widgets['msg_md_assistant'][1] is stable
        assert selected.get_selection_bounds() == selection; selected.select_region(0, 0)
        print('PASS: streaming updates preserve unchanged native Markdown widgets and selected text.', flush=True)
        widgets = list(walk(app.message_box))
        assert any(isinstance(w, Gtk.Grid) for w in widgets)
        tasks = [w for w in widgets if isinstance(w, Gtk.CheckButton)]
        assert len(tasks) == 2 and all(not w.get_sensitive() for w in tasks)
        assert {w.get_active() for w in tasks} == {False, True}
        texts = [w.get_text() for w in widgets if isinstance(w, Gtk.Label)]
        assert '3.' in texts and '4.' in texts
        assert any('<script>alert(' in value for value in texts)
        assert not any(isinstance(w, Gtk.Picture) for w in widgets)
        assert tracker.requests == 0 and not launches
        app.scroll.get_vadjustment().set_value(0); phase = 2
    elif phase == 2:
        # render_messages schedules an idle scroll-to-bottom. Let that finish,
        # then establish the top viewport before taking the baseline capture.
        adjustment = app.scroll.get_vadjustment()
        if adjustment.get_value() > 1:
            adjustment.set_value(0)
            return GLib.SOURCE_CONTINUE
        screenshot('markdown-desktop')
        # Real scroll events against the private Xvfb window, not just changing
        # an adjustment's numeric state without checking its rendered surface.
        subprocess.run(['xdotool', 'mousemove', '1000', '600', 'click', '--repeat', '30', '--delay', '15', '5'], check=True, timeout=10)
        phase = 3
        print('PASS: native headings, table, nested/ordered lists, readonly tasks, quote and escaped HTML rendered; tracking image not fetched.', flush=True)
    elif phase == 3:
        adjustment = app.scroll.get_vadjustment()
        if adjustment.get_value() < adjustment.get_upper() - adjustment.get_page_size() - 2:
            return GLib.SOURCE_CONTINUE
        ok, bounds = app.message_box.compute_bounds(app.scroll)
        if not ok or bounds.get_y() >= 0:
            return GLib.SOURCE_CONTINUE
        screenshot('markdown-code')
        # Adjustment/layout can advance before Xvfb presents the next frame.
        # Keep waiting under the existing test deadline, rather than accepting
        # an unchanged capture or racing the compositor.
        if Path('/scratch/markdown-code.png').read_bytes() == Path('/scratch/markdown-desktop.png').read_bytes():
            return GLib.SOURCE_CONTINUE
        find_button('Copiar código').emit('clicked'); clipboard(); phase = 4
    elif phase == 4 and copied:
        assert copied[-1] == code, 'Fenced Makefile copy must preserve literal tabs and code.'
        find_button('Copiar tabela (TSV)').emit('clicked'); clipboard(); phase = 5
    elif phase == 5 and len(copied) == 2:
        assert copied[-1].startswith('Componente\tEstado\tQuantidade')
        assert 'Interface\tVerificada\t12' in copied[-1]
        assert not launches
        assert link_label().emit('activate-link', 'javascript:alert(1)') is True
        assert not app.dialogs and not launches
        link_label().emit('activate-link', 'https://example.com/docs?x=1&y=2')
        assert len(app.dialogs) == 1 and not launches
        labels = [w.get_text() for w in walk(app.dialogs[-1]) if isinstance(w, Gtk.Label)]
        assert any('https://example.com/docs?x=1&y=2' in text for text in labels)
        app.dialogs[-1].close(); phase = 6
        print('PASS: code clipboard preserves tabs/literal HTML; table clipboard is TSV; unsafe link blocked and safe link needs visible-target confirmation.', flush=True)
    elif phase == 6:
        link_label().emit('activate-link', 'https://example.com/docs?x=1&y=2')
        confirm = next(w for w in walk(app.dialogs[-1]) if isinstance(w, Gtk.Button) and w.get_label() == 'Confirmar')
        confirm.emit('clicked')
        assert launches == ['https://example.com/docs?x=1&y=2']
        app.portrait.set_active(True); phase = 7
    elif phase == 7 and app.window.get_width() == 414:
        app.scroll.get_vadjustment().set_value(0); phase = 8
    elif phase == 8:
        screenshot('markdown-portrait')
        assert app.window.get_width() == 414
        scrollers = [w for w in walk(app.message_box) if isinstance(w, Gtk.ScrolledWindow)]
        assert any(w.get_hadjustment().get_upper() > w.get_hadjustment().get_page_size() for w in scrollers), 'Wide table/code must scroll, not expand the portrait window.'
        app.apply_theme('dark'); dark_started = time.monotonic(); phase = 9
    elif phase == 9 and time.monotonic() - dark_started > .5:
        screenshot('markdown-dark')
        assert Path('/scratch/markdown-dark.png').read_bytes() != Path('/scratch/markdown-portrait.png').read_bytes()
        assert tracker.requests == 0 and not app.errors, app.errors
        print('PASS: 414px portrait keeps wide tables/code horizontally scrollable; desktop/light/dark screenshots captured. No browser/provider/network target launched.', flush=True)
        app.window.close(); app.quit(); return GLib.SOURCE_REMOVE
    return GLib.SOURCE_CONTINUE


try:
    GLib.timeout_add(150, check); app.run([])
    assert not errors, errors
    assert phase == 9
finally:
    tracker.shutdown(); tracker.server_close()
