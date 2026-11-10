"""Private Xvfb/D-Bus only. Synthetic accounts; no network/provider/browser."""
import time
import os
import sys
import traceback
from pathlib import Path
if os.environ.get('POCKET_TEST_INSTALL'):
    assert os.environ['POCKET_TEST_INSTALL'] == '/installed'
    sys.path.insert(0, '/installed')
from main import Pocket, Gtk, GLib
from backend import PocketError

app = Pocket(demo=True, state=Path('/scratch/state'))
phase = 0
posts = []
errors = []
deadline = time.monotonic() + 30
original = app.client.request
request_id = None


def request(path, method='GET', body=None, **kwargs):
    global request_id
    if path.startswith('/phone/openai?'):
        return {'methods': [{'type': 'oauth', 'id': 'chatgpt', 'label': 'Entrar com ChatGPT', 'requiresFields': False}], 'connections': [{'method': 'oauth'}]}
    if path == '/phone/openai/key':
        posts.append('key'); request_id = body['requestID']
        assert body['key'] == 'synthetic-secret'
        return {'requestID': request_id, 'status': 'stored', 'active': False}
    if path == '/phone/openai/oauth':
        posts.append('oauth'); request_id = body['requestID']
        return {'requestID': request_id, 'status': 'pending', 'mode': 'code',
                'url': 'https://auth.openai.com/oauth/authorize?state=synthetic', 'instructions': 'Fixture only'}
    if path == '/phone/openai/complete':
        posts.append('complete')
        assert body['code'] == 'synthetic-code'
        raise PocketError('Resposta sintética perdida.', 503)
    if path.startswith('/phone/openai/operation?'):
        return {'requestID': request_id, 'status': 'complete'}
    return original(path, method, body, **kwargs)


app.client.request = request


def walk(widget):
    yield widget
    child = widget.get_first_child()
    while child:
        yield from walk(child)
        child = child.get_next_sibling()


def click(text, window=None):
    target = next(w for w in walk(window or app.dialogs[-1]) if isinstance(w, Gtk.Button) and w.get_label() == text)
    assert target.get_sensitive(), text
    target.emit('clicked')


def text(window):
    return ' '.join(w.get_text() for w in walk(window) if isinstance(w, Gtk.Label))


def exception(*args):
    errors.append(''.join(traceback.format_exception(*args))); print(errors[-1], file=sys.stderr); app.quit()


sys.excepthook = exception


def check():
    global phase, account_window
    assert time.monotonic() < deadline, ('Timeout', phase)
    if phase == 0 and app.session:
        app.draft.get_buffer().set_text('Draft must survive account operations')
        app.openai_accounts('/fixture'); account_window = app.dialogs[-1]; phase = 1
    elif phase == 1 and 'Métodos oficiais consultados' in text(account_window):
        key = next(w for w in walk(account_window) if isinstance(w, Gtk.Entry) and (w.get_placeholder_text() or '').startswith('Chave OpenAI'))
        assert not key.get_visibility()
        key.set_text('synthetic-secret')
        click('Revisar cadastro de chave API', account_window)
        app.dialogs[-1].close()
        assert posts == []
        click('Revisar cadastro de chave API', account_window); click('Confirmar'); phase = 2
    elif phase == 2 and 'Login ativo existente preservado' in text(account_window):
        assert posts == ['key']
        key = next(w for w in walk(account_window) if isinstance(w, Gtk.Entry) and (w.get_placeholder_text() or '').startswith('Chave OpenAI'))
        assert key.get_text() == ''
        assert not (app.store.root / 'openai-auth.json').exists()
        click('Entrar com ChatGPT', account_window); click('Confirmar'); phase = 3
    elif phase == 3 and any(isinstance(w, Gtk.LinkButton) for w in walk(account_window)):
        # Never click the browser link. Only explicit user gesture can open it.
        code = next(w for w in walk(account_window) if isinstance(w, Gtk.Entry) and (w.get_placeholder_text() or '').startswith('Código OAuth'))
        assert not code.get_visibility(); code.set_text('synthetic-code')
        click('Revisar conclusão OAuth', account_window); click('Confirmar'); phase = 4
    elif phase == 4 and 'não confirmada' in text(account_window):
        assert posts == ['key', 'oauth', 'complete']
        assert (app.store.root / 'openai-auth.json').exists()
        account_window.close(); app.openai_accounts('/fixture'); account_window = app.dialogs[-1]; phase = 5
    elif phase == 5 and 'Métodos oficiais consultados' in text(account_window):
        save = next(w for w in walk(account_window) if isinstance(w, Gtk.Button) and w.get_label() == 'Revisar cadastro de chave API')
        assert not save.get_sensitive()
        click('Consultar resultado da tentativa anterior', account_window); phase = 6
    elif phase == 6 and 'Estado da tentativa: complete' in text(account_window):
        assert posts == ['key', 'oauth', 'complete']
        assert not (app.store.root / 'openai-auth.json').exists()
        for file in app.store.root.iterdir():
            if file.is_file():
                assert b'synthetic-secret' not in file.read_bytes() and b'synthetic-code' not in file.read_bytes()
        assert app.current_draft()['text'] == 'Draft must survive account operations'
        print('PASS: native API/OAuth confirmations, masked fields, preserved active-login notice, no browser launch, lost-ack fence/reopen/read-only recovery; zero real calls', flush=True)
        account_window.close(); app.window.close(); app.quit(); return GLib.SOURCE_REMOVE
    return GLib.SOURCE_CONTINUE


GLib.timeout_add(100, check)
app.run([])
assert not errors and phase == 6, (errors, phase)
