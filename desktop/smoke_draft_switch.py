"""Private disk fault across two chats, followed by a fresh GTK process."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import traceback

ROOT = Path('/scratch/draft-switch-state')


def child(phase):
    if os.environ.get('POCKET_TEST_INSTALL'):
        sys.path.insert(0, os.environ['POCKET_TEST_INSTALL'])
    from main import Pocket, GLib
    from backend import Store
    app = Pocket(demo=True, state=ROOT)
    errors = []; step = 0; sessions = None; saved = None; before = None; writes = []
    deadline = time.monotonic()+20
    original_request = app.client.request
    def request(path, method='GET', body=None):
        if method != 'GET':
            writes.append((method, path))
        return original_request(path, method, body)
    app.client.request = request
    def exception(*args):
        errors.append(''.join(traceback.format_exception(*args))); print(errors[-1], file=sys.stderr); app.quit()
    sys.excepthook = exception
    def check():
        nonlocal step, sessions, saved, before
        if time.monotonic() > deadline:
            raise AssertionError(f'Draft-switch timeout {phase}/{step}')
        if step == 0 and app.session and not app.refreshing:
            if phase == 'prepare':
                second = dict(app.session, id='ses_draft_b', title='Draft B fixture')
                app.client.sessions.append(second)
                sessions = [dict(app.session), second]
                app.persist(); before = (ROOT/'preferences.json').read_bytes(); saved = app.store.save
                def fail():
                    raise OSError('fixture storage unavailable during navigation')
                app.store.save = fail
                app.draft.get_buffer().set_text('Draft A — unsaved edits')
                app.add_attachments([{'name': 'a.txt', 'size': 1, 'uri': 'data:text/plain;base64,YQ=='}])
                app.open_chat(sessions[1]); step = 1
            else:
                expected = json.loads((ROOT/'expected.json').read_text()); sessions = expected['sessions']
                app.client.sessions.append(sessions[1])
                for session, title in zip(sessions, ('A', 'B')):
                    app.open_chat(session)
                    assert app.current_draft()['text'] == 'Draft '+title+' — unsaved edits'
                    assert app.current_draft()['files'][0]['name'] == title.lower()+'.txt'
                assert not writes and app.sent == 0
                print('PASS: fresh GTK process restored both exact UTF-8 drafts and attachments after storage recovery; zero writes/prompts.', flush=True)
                step = 3; app.window.close(); app.quit(); return GLib.SOURCE_REMOVE
        elif step == 1 and not app.refreshing:
            assert app.notice.get_visible() and 'storage unavailable' in app.notice.get_text(), 'Navigation/background GET must not erase unsaved-storage warning.'
            app.draft.get_buffer().set_text('Draft B — unsaved edits')
            app.add_attachments([{'name': 'b.txt', 'size': 1, 'uri': 'data:text/plain;base64,Yg=='}])
            app.open_chat(sessions[0]); step = 2
        elif step == 2 and not app.refreshing:
            assert app.current_draft()['text'] == 'Draft A — unsaved edits'
            assert app.current_draft()['files'][0]['name'] == 'a.txt'
            assert app.notice.get_visible() and 'storage unavailable' in app.notice.get_text()
            assert (ROOT/'preferences.json').read_bytes() == before
            app.store.save = saved; app.persist()
            assert not app.notice.get_visible(), 'Successful durable save should clear its own storage warning.'
            restored = Store(ROOT)
            assert restored.data['drafts'][sessions[1]['id']]['text'] == 'Draft B — unsaved edits'
            (ROOT/'expected.json').write_text(json.dumps({'sessions': sessions}))
            assert not writes and app.sent == 0
            print('PASS: storage fault retained both chats in memory and previous on-disk snapshot; warning survived navigation/GET; recovered save persisted all drafts without sending.', flush=True)
            step = 3; app.window.close(); app.quit(); return GLib.SOURCE_REMOVE
        return GLib.SOURCE_CONTINUE
    GLib.timeout_add(120, check); app.run([])
    assert not errors, errors
    assert step == 3


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--phase'); args = parser.parse_args()
    if args.phase:
        child(args.phase)
    else:
        for phase in ('prepare', 'restore'):
            result = subprocess.run([sys.executable, str(Path(__file__).resolve()), '--phase', phase], capture_output=True, text=True, timeout=25)
            assert result.returncode == 0, result.stdout + result.stderr[-5000:]
            print(result.stdout, end='', flush=True)
