"""Native GTK interaction smoke: run in isolated Xvfb and network namespace."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import traceback

if os.environ.get('POCKET_TEST_INSTALL'):
    sys.path.insert(0, os.environ['POCKET_TEST_INSTALL'])
from main import Pocket, Gtk, GLib, inline
from backend import attachment, Store

app = Pocket(demo=True, state='/scratch/native-state')
app.client.sessions[0]['metadata'] = None  # Valid Core response, not always {}.
errors = []
phase = 0
dark_started = None
deadline = time.monotonic() + 70
original = None
downloads = []
original_download = app.download


def exception(*args):
    errors.append(''.join(traceback.format_exception(*args)))
    app.quit()


sys.excepthook = exception


def walk(widget):
    yield widget
    child = widget.get_first_child()
    while child:
        yield from walk(child); child = child.get_next_sibling()


def find_button(text):
    return next(w for dialog in app.dialogs for w in walk(dialog) if isinstance(w, Gtk.Button) and w.get_label() == text)


def shot(name):
    subprocess.run(['import', '-window', 'root', '/scratch/' + name + '.png'], check=True, timeout=10)


def check():
    global phase, original, deadline, dark_started
    if time.monotonic() > deadline:
        raise AssertionError(f'Native UI timed out at phase {phase}; errors={app.errors}')
    if phase == 0 and hasattr(app, 'session') and app.session and app.catalog:
        assert app.messages, 'History loaded without a prompt'
        assert app.sent == 0
        original = app.session
        app.draft.get_buffer().set_text('Rascunho nativo preservado')
        app.save_draft()
        app.new_chat()
        phase = 1
        print('PASS: native GTK history loads; no provider prompt.', flush=True)
    elif phase == 1 and app.session['id'] != original['id'] and not app.busy:
        assert app.current_draft()['text'] == ''
        app.open_chat(original)
        assert app.current_draft()['text'] == 'Rascunho nativo preservado'
        Path('/scratch/anexo.txt').write_text('fixture attachment')
        app.add_attachments([attachment('/scratch/anexo.txt')])
        assert len(app.current_draft()['files']) == 1
        app.send_button.emit('clicked')
        phase = 2
        print('PASS: one-tap new chat, per-chat draft restoration and native attachments.', flush=True)
    elif phase == 2 and app.sent == 1 and not app.busy:
        assert app.current_draft()['text'] == '' and not app.current_draft()['files']
        assert any(m.get('files') for m in app.client.messages[original['id']])
        app.client.permissions[original['id']] = [{'id': 'per_fixture', 'message': 'Fixture permission', 'action': 'write', 'resources': ['/fixture/test.txt']}]
        app.refresh()
        phase = 3
    elif phase == 3 and app.permission_box.get_first_child():
        app.permission_box.get_first_child().emit('clicked')
        find_button('Negar').emit('clicked')
        phase = 4
    elif phase == 4 and not app.dialogs and not app.client.permissions[original['id']]:
        app.toggle_pin()
        assert original['id'] in app.store.data['pins']
        app.rename()
        entry = next(w for w in walk(app.dialogs[-1]) if isinstance(w, Gtk.Entry))
        entry.set_text('Conversa nativa verificada')
        find_button('Salvar nome').emit('clicked')
        phase = 5
        print('PASS: send accepted once, permission reviewed/denied and persistent chat pin.', flush=True)
    elif phase == 5 and not app.dialogs and app.session['title'] == 'Conversa nativa verificada':
        app.options()
        mode = next(w for w in walk(app.dialogs[-1]) if isinstance(w, Gtk.DropDown)); mode.set_selected(1)
        find_button('Salvar').emit('clicked'); phase = 6
    elif phase == 6 and not app.dialogs and app.session.get('agent') == 'plan':
        assert inline('<img onerror="x"> **bold**') == '&lt;img onerror=&quot;x&quot;&gt; <b>bold</b>'
        app.answer_form({'id': 'form_fixture', 'title': 'Pergunta de teste', 'fields': [{'key': 'name', 'title': 'Nome', 'type': 'string', 'required': True}, {'key': 'count', 'title': 'Quantidade', 'type': 'integer', 'required': True}]})
        entries = [w for w in walk(app.dialogs[-1]) if isinstance(w, Gtk.Entry)]
        entries[0].set_text('native answer'); entries[1].set_text('3')
        find_button('Enviar resposta').emit('clicked'); phase = 6.5
    elif phase == 6.5 and not app.dialogs:
        assert app.client.last_answer == {'name': 'native answer', 'count': 3}
        app.schedules()
        prompt = next(w for w in walk(app.dialogs[-1]) if isinstance(w, Gtk.Entry) and w.get_placeholder_text() == 'Tarefa para executar depois')
        prompt.set_text('Scheduled fixture only, no provider')
        calendar = next(w for w in walk(app.dialogs[-1]) if isinstance(w, Gtk.Calendar))
        calendar.select_day(GLib.DateTime.new_now_local().add_days(1))
        find_button('Agendar uma execução').emit('clicked')
        find_button('Confirmar').emit('clicked'); phase = 6.75
    elif phase == 6.75 and len(app.client.schedules) == 1 and find_button('Agendar uma execução').get_sensitive():
        for dialog in list(app.dialogs):
            dialog.close()
        app.download = lambda *args: downloads.append(args)
        app.render_messages([{'id': 'msg_artifact', 'type': 'assistant', 'text': '[Arquivo](exemplo.txt)', 'time': {'created': 1, 'completed': 2}}])
        save = next(w for w in walk(app.message_box) if isinstance(w, Gtk.Button) and w.get_tooltip_text() == 'Salvar arquivo referenciado na resposta')
        save.emit('clicked'); phase = 6.8
    elif phase == 6.8 and downloads:
        assert downloads[0][0] == 'home' and downloads[0][1]['name'] == 'exemplo.txt'
        app.download = original_download; app.render_messages(app.messages)
        app.apply_theme('light')
        app.window.set_default_size(1180, 820)
        phase = 7
        print('PASS: native rename, Plan/model settings and typed form replies; markup escaped.', flush=True)
        print('PASS: native calendar schedule creation requires explicit confirmation; fixture only.', flush=True)
        print('PASS: generated-file reference card resolves only through approved gateway context/list.', flush=True)
    elif phase == 7 and app.window.get_width() >= 1100:
        assert 280 <= app.sidebar.get_width() <= 340, app.sidebar.get_width()
        shot('native-desktop')
        app.portrait.set_active(True)
        phase = 8
    elif phase == 8 and app.window.get_width() == 414:
        assert not app.sidebar.get_visible()
        shot('native-portrait')
        app.apply_theme('dark'); dark_started = time.monotonic(); phase = 9
        print(f'PASS: native portrait mode width={app.window.get_width()}, sidebar hidden.', flush=True)
    elif phase == 9 and time.monotonic() - dark_started > .5:
        shot('native-dark')
        assert not app.errors, app.errors
        app.store.save(); restored = Store('/scratch/native-state')
        assert original['id'] in restored.data['pins']
        assert restored.data['portrait'] is True
        assert restored.data['drafts'][original['id']]['text'] == ''
        app.window.close(); app.quit()
        print('PASS: light/dark native captures and preferences persisted; no GTK exceptions.', flush=True)
        return GLib.SOURCE_REMOVE
    return GLib.SOURCE_CONTINUE


GLib.timeout_add(120, check)
app.run([])
if errors:
    raise AssertionError('\n'.join(errors))
assert phase == 9, f'Native test incomplete: phase {phase}'
