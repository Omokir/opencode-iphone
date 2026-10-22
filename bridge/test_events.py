import json
import unittest

from events import session_hint


class EventTests(unittest.TestCase):
    def test_only_matching_session_emits_hint(self):
        raw = {'id': 'seq', 'type': 'session.message.delta', 'data': {'sessionID': 'ses_a', 'secretText': 'never-forward'}}
        result = session_hint(json.dumps(raw), 'ses_a')
        self.assertEqual(result, {'type': 'session.message.delta', 'sessionID': 'ses_a'})
        self.assertNotIn('never-forward', json.dumps(result))
        self.assertIsNone(session_hint(json.dumps(raw), 'ses_b'))

    def test_metadata_and_double_encoded_data(self):
        raw = {'type': 'session.updated', 'data': {'info': {'id': 'ses_a', 'title': 'private'}}}
        self.assertIsNotNone(session_hint(json.dumps(json.dumps(raw)), 'ses_a'))
        self.assertIsNone(session_hint('{bad', 'ses_a'))
        self.assertIsNone(session_hint('{"type":"server.connected","data":{}}', 'ses_a'))
