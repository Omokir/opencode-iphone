"""Long native history: bounded reads, retry, viewport and stale response fence."""
import copy
import os
import sys
import threading
import time
import traceback
import urllib.parse

if os.environ.get('POCKET_TEST_INSTALL'):
    sys.path.insert(0, os.environ['POCKET_TEST_INSTALL'])
from main import Pocket, GLib
from backend import PocketError

app = Pocket(demo=True, state='/scratch/pagination-state')
phase = 0; errors = []; reads = []; started = threading.Event(); release = threading.Event()
fault = True; deadline = time.monotonic()+30; original_session = None; old_y = None; changed_at = None
latest = [{'id': f'msg_page_{i:03}', 'type': 'user' if i % 2 else 'assistant', 'text': f'Message {i}\n' + ('Literal history content. '*20), 'time': {'created': i, 'completed': i+1}} for i in range(20, 50)]


def exception(*args):
    errors.append(''.join(traceback.format_exception(*args))); print(errors[-1], file=sys.stderr)
    release.set(); app.quit()


sys.excepthook = exception


def check():
    global phase, fault, original_session, old_y, changed_at
    if time.monotonic() > deadline:
        raise AssertionError(f'Pagination timeout {phase}; reads={reads}')
    if phase == 0 and app.session and app.messages:
        original_session = copy.deepcopy(app.session); original = app.client.request
        route = app.request_path('/message')
        def request(path, method='GET', body=None):
            parsed = urllib.parse.urlsplit(path); query = urllib.parse.parse_qs(parsed.query)
            if parsed.path == route:
                cursor = query.get('cursor', [None])[0]
                if cursor:
                    reads.append(cursor); started.set(); release.wait(timeout=5)
                    if fault:
                        raise PocketError('fixture older page unavailable')
                    if cursor == 'c1':
                        older = [dict(latest[0], id=f'msg_page_{i:03}', text=f'Older {i}\n' + 'Earlier history. '*20, time={'created': i, 'completed': i+1}) for i in range(10, 20)]
                        return {'data': older + [dict(latest[0], text='stale overlapping page')], 'cursor': {'next': 'c2'}}
                    return {'data': [], 'cursor': {'next': cursor}}
                return {'data': copy.deepcopy(latest), 'cursor': {'next': 'c1'}}
            return original(path, method, body)
        app.client.request = request; app.client.messages[app.session['id']] = copy.deepcopy(latest)
        app.messages = copy.deepcopy(latest); app.older = 'c1'; app.render_messages(app.messages); phase = 1
    elif phase == 1 and app.scroll.get_vadjustment().get_upper() > 3000:
        app.scroll.get_vadjustment().set_value(100)
        app.load_older(); app.load_older(); phase = 2
    elif phase == 2 and started.is_set():
        assert reads == ['c1']
        release.set(); phase = 3
    elif phase == 3 and not app.older_loading:
        assert app.older == 'c1' and len(app.messages) == 30
        assert any('older page unavailable' in e for e in app.errors)
        fault = False; started.clear(); release.clear()
        app.scroll.get_vadjustment().set_value(100)
        phase = 31
    elif phase == 31:
        ok, rect = app.message_widgets['msg_page_020'][1].compute_bounds(app.scroll); assert ok
        old_y = rect.get_y()
        app.load_older(); app.load_older(); phase = 4
    elif phase == 4 and started.is_set():
        assert reads == ['c1', 'c1']; release.set(); changed_at = time.monotonic(); phase = 5
    elif phase == 5 and not app.older_loading and time.monotonic()-changed_at > .4:
        assert len(app.messages) == 40 and app.older == 'c2'
        assert next(m for m in app.messages if m['id'] == 'msg_page_020')['text'] == latest[0]['text']
        ok, rect = app.message_widgets['msg_page_020'][1].compute_bounds(app.scroll); assert ok
        assert abs(rect.get_y()-old_y) < 8, (rect.get_y(), old_y)
        print('PASS: older-page failure preserved cursor/history; duplicate clicks issued one GET; retry merged overlapping IDs without replacing newer text and preserved viewport anchor.', flush=True)
        app.load_older(); phase = 6
    elif phase == 6 and not app.older_loading and app.older is None:
        assert len(app.messages) == 40 and any('repetiu o cursor' in e for e in app.errors)
        started.clear(); release.clear(); app.older = 'late'; app.load_older(); phase = 7
    elif phase == 7 and started.is_set():
        other = dict(original_session, id='ses_other', title='Other history')
        app.store.data['drafts']['ses_other'] = {'text': 'Other draft', 'files': []}
        app.open_chat(other); release.set(); changed_at = time.monotonic(); phase = 8
    elif phase == 8 and time.monotonic()-changed_at > .4 and not app.refreshing:
        assert app.session['id'] == 'ses_other' and not app.older_loading
        assert not any(m['id'].startswith('msg_page_') for m in app.messages)
        assert app.current_draft()['text'] == 'Other draft'
        print('PASS: repeated cursor stopped pagination without discarding messages; late page after navigation did not enter another chat or lose its draft. Read-only fixture, no provider.', flush=True)
        app.window.close(); app.quit(); return GLib.SOURCE_REMOVE
    return GLib.SOURCE_CONTINUE


GLib.timeout_add(120, check); app.run([]); release.set()
assert not errors, errors
assert phase == 8
