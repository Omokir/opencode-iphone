"""Two native peers; run in an isolated network namespace with no default route.

libnice ignores lo by default. The harness supplies one private dummy interface
inside that namespace, then drops network capabilities before executing tests.
"""
import json
import sys
import time
import traceback
from pathlib import Path
from ipaddress import IPv6Address

from voice import WebRTCAudio, VoiceSession, LocalTone, GLib

assert not any(line.split()[1] == '00000000' for line in Path('/proc/net/route').read_text().splitlines()[1:]), 'Private test namespace must have no default route.'
assert next(line.split()[1] for line in Path('/proc/self/status').read_text().splitlines() if line.startswith('CapEff:')) == '0000000000000000', 'Drop all capabilities before running target code.'
allowed_addresses = {'192.0.2.1', '127.0.0.1', '::1'}
ipv6 = Path('/proc/net/if_inet6')
if ipv6.exists():
    for line in ipv6.read_text().splitlines():
        fields = line.split()
        if fields[-1] in ('pocket-test', 'lo'):
            allowed_addresses.add(str(IPv6Address(int(fields[0], 16))))

loop = GLib.MainLoop()
left = WebRTCAudio(synthetic=True, capture=True)
right = WebRTCAudio(synthetic=True, capture=True)
session = VoiceSession(left, 'Historical fixture context; never execute it.', maximum_seconds=60)
errors = []; proposals = []; deadline = time.monotonic() + 12
opened = {'left': False, 'right': False, 'context': False}
muted_at = None
tone = LocalTone(test_sink=True)
tone_done = []
tone.on_done = lambda text: tone_done.append(text)


def fail(text):
    errors.append(text); loop.quit()


def exception(*args):
    text = ''.join(traceback.format_exception(*args))
    print(text, file=sys.stderr, flush=True)
    fail(text)


sys.excepthook = exception
session.on_error = fail; right.on_error = fail
session.on_proposal = lambda *args: proposals.append(args)
def description(target, sdp, answer):
    candidates = [line.split()[4] for line in sdp.splitlines() if line.startswith('a=candidate:')]
    assert candidates and set(candidates) <= allowed_addresses, 'Unexpected private-test candidate addresses: ' + repr(candidates)
    target.remote(sdp, answer=answer)


left.on_description = lambda sdp, kind: description(right, sdp, False)
right.on_description = lambda sdp, kind: description(left, sdp, True)
left.on_open = lambda: opened.update(left=True)


def right_open():
    opened['right'] = True
    right.mute(False)
    right.send({'type': 'session.created'})


right.on_open = right_open


def event(raw):
    item = json.loads(raw)
    if item['type'] == 'session.update':
        raise AssertionError('Broker already configured the session; a second update is forbidden.')
    elif item['type'] == 'conversation.item.create' and item['item']['type'] == 'message':
        opened['context'] = True
        right.send({'type': 'response.output_audio_transcript.delta', 'delta': 'fixture caption'})
        proposal = {'type': 'function_call', 'status': 'completed', 'name': 'opencode_submit', 'call_id': 'call_loopback', 'arguments': json.dumps({'task': 'Isolated proposal; not executed'})}
        right.send({'type': 'response.output_item.done', 'item': proposal})
        right.send({'type': 'response.done', 'response': {'status': 'completed', 'output': [proposal]}})


right.on_event = event


def check():
    global muted_at
    if time.monotonic() > deadline:
        def diagnostics(media):
            local = media.peer.get_property('local-description')
            return {'description_sent': media.description_sent, 'candidates': local.sdp.as_text().count('a=candidate:') if local else 0, 'ice': media.peer.get_property('ice-connection-state').value_nick, 'gather': media.peer.get_property('ice-gathering-state').value_nick}
        fail(f'WebRTC timed out; channel={opened}, frames={left.frames}/{right.frames}, proposals={len(proposals)}; peers={diagnostics(left)}/{diagnostics(right)}')
        return GLib.SOURCE_REMOVE
    if all(opened.values()) and left.nonzero > 8 and right.nonzero > 8 and proposals and session.caption == 'fixture caption' and tone_done:
        if muted_at is None:
            assert len(proposals) == 1
            assert tone.frames == 35 and tone.pipeline is None
            left.mute(True)
            assert left.pipeline.get_by_name('microphone').get_property('mute') is True
            muted_at = time.monotonic()
            print('PASS: native WebRTC SDP/ICE/DTLS/SRTP/Opus exchanged nonzero synthetic audio in both directions.', flush=True)
            print('PASS: local output check generated 35 synthetic buffers and released its pipeline; physical speakers not tested.', flush=True)
            print('PASS: SCTP events established session/context, caption and one deduplicated proposal; no tool executed.', flush=True)
        elif time.monotonic() - muted_at > .3:
            session.stop(); right.stop()
            assert left.closed and right.closed and left.pipeline is None and right.pipeline is None
            print('PASS: mute control applied; end released both media pipelines. No microphone, provider, STUN or external network used.', flush=True)
            loop.quit(); return GLib.SOURCE_REMOVE
    return GLib.SOURCE_CONTINUE


try:
    tone.start(); right.start(initiator=False); left.start()
    GLib.timeout_add(100, check)
    loop.run()
    assert not errors, errors
    assert muted_at is not None
finally:
    session.stop(); right.stop(); tone.stop()
