import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest

from backend import DemoGateway, Gateway, PocketError
from voice import VoiceSession, WebRTCAudio, configuration, context_text


class FakeMedia:
    def __init__(self):
        self.sent = []; self.muted = True; self.closed = False

    def send(self, event):
        self.sent.append(event)

    def mute(self, value):
        self.muted = value

    def stop(self):
        self.closed = True


class VoiceTests(unittest.TestCase):
    def setUp(self):
        self.media = FakeMedia(); self.voice = VoiceSession(self.media, 'historical fixture data')

    def tearDown(self):
        self.voice.stop()

    def event(self, kind, **values):
        self.voice.receive(json.dumps({'type': kind, **values}))

    def test_handshake_idempotent_and_microphone_starts_muted(self):
        self.assertTrue(self.media.muted)
        self.event('session.created'); self.event('session.created')
        self.assertEqual(len(self.media.sent), 1)
        self.event('session.updated'); self.event('session.updated')
        self.assertEqual(len(self.media.sent), 1)
        self.assertFalse(any(event['type'] == 'session.update' for event in self.media.sent))
        self.assertFalse(self.media.muted)
        self.assertTrue(self.voice.active)

    def test_mute_chosen_during_connection_is_preserved(self):
        self.voice.set_muted(True)
        self.event('session.created'); self.event('session.updated')
        self.assertTrue(self.media.muted)
        self.voice.set_muted(False)
        self.assertFalse(self.media.muted)

    def test_completed_proposal_deduplicated_and_never_executes(self):
        proposals = []; self.voice.on_proposal = lambda *args: proposals.append(args)
        item = {'type': 'function_call', 'status': 'completed', 'call_id': 'call_fixture', 'name': 'opencode_submit', 'arguments': json.dumps({'task': 'fixture task'})}
        self.event('response.output_item.done', item=item)
        self.event('response.done', response={'status': 'completed', 'output': [item]})
        self.assertEqual(proposals, [('call_fixture', 'fixture task')])
        output = json.loads(self.media.sent[-1]['item']['output'])
        self.assertEqual(output['status'], 'pending_review')
        self.assertEqual(len(self.media.sent), 1)

    def test_unfinished_or_malformed_tools_do_not_execute(self):
        proposals = []; self.voice.on_proposal = lambda *args: proposals.append(args)
        self.event('response.output_item.done', item={'type': 'function_call', 'status': 'running'})
        self.assertFalse(proposals)
        self.event('response.output_item.done', item={'type': 'function_call', 'status': 'completed', 'name': 'opencode_submit', 'call_id': 'call_bad', 'arguments': '{"task":"x","extra":"injection"}'})
        self.assertFalse(proposals); self.assertTrue(self.voice.closed); self.assertTrue(self.media.closed)

    def test_error_and_deadline_release_media_without_retry(self):
        self.voice.started -= 400
        self.voice.tick()
        self.assertTrue(self.voice.closed); self.assertTrue(self.media.closed)
        self.assertFalse(self.media.sent)
        self.event('session.created')
        self.assertFalse(self.media.sent)

    def test_context_bounded_and_config_explicit(self):
        text = context_text({'agent': None, 'location': {'directory': '/fixture'}}, [{'type': 'assistant', 'text': 'x'*20000}]*30)
        self.assertLess(len(text), 16000)
        self.assertIn('NÃO pedidos novos', text)
        self.assertEqual(configuration()['model'], 'gpt-realtime-2.1')
        with self.assertRaises(PocketError):
            configuration('invalid')

    def test_paid_session_guard_and_demo_no_network(self):
        gateway = Gateway('/scratch/no-voice-credentials')
        with self.assertRaisesRegex(PocketError, 'confirmação explícita'):
            gateway.voice_session('v=0', configuration())
        with self.assertRaises(PocketError):
            DemoGateway().voice_session('v=0', configuration(), approved=True)

    def test_approved_broker_contract_against_isolated_fixture(self):
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'preview'))
        from transport_fixture import start_fixture, FixtureGateway
        server = start_fixture()
        try:
            with tempfile.TemporaryDirectory() as directory:
                gateway = Gateway(directory, port=server.server_port); gateway.pair('123456')
                self.assertTrue(gateway.voice_models()['data']['models'][0]['available'])
                answer = gateway.voice_session('v=0\r\ns=synthetic-offer\r\n', configuration(), approved=True)
                self.assertTrue(answer.startswith('v=0'))
                method, path, _, body = FixtureGateway.calls[-1]
                self.assertEqual((method, path), ('POST', '/api/experimental/voice/session'))
                request = json.loads(body)
                self.assertEqual(request['model'], 'gpt-realtime-2.1')
                self.assertEqual(request['transport']['type'], 'webrtc')
                self.assertEqual(request['session']['max_output_tokens'], 512)
                with self.assertRaises(PocketError):
                    gateway.request(path, 'POST', request)
                before = len(FixtureGateway.calls)
                cancelled = threading.Event(); cancelled.set()
                with self.assertRaisesRegex(PocketError, 'cancelada antes'):
                    gateway.voice_session('v=0\r\n', configuration(), approved=True, cancelled=cancelled)
                self.assertEqual(before, len(FixtureGateway.calls))
        finally:
            server.shutdown(); server.server_close()

    def test_oversized_and_nonobject_events_fail_closed(self):
        self.voice.receive('[]')
        self.assertTrue(self.voice.closed); self.assertTrue(self.media.closed)

    def test_media_event_queue_is_bounded(self):
        media = WebRTCAudio(synthetic=True, capture=True)
        for _ in range(1000):
            media.dispatch(lambda: None)
        self.assertEqual(media.pending, 128)
        self.assertTrue(media.overflow)
        media.stop()


if __name__ == '__main__':
    unittest.main()
