import json
import unittest
from read_markers import read_markers


class MarkerTests(unittest.TestCase):
    def test_projects_only_server_read_timestamp_and_deduplicates(self):
        calls = []
        def fetch(method, path, body):
            calls.append((method, path, body))
            return 200, json.dumps({'data': {'id': 'ses_old', 'title': 'never-forward', 'time': {'viewed': 500}, 'model': {'private': 'never-forward'}}}).encode()
        result = read_markers(['ses_old', 'ses_old'], fetch)
        self.assertEqual(result, {'viewed': {'ses_old': 500}, 'unavailable': []})
        self.assertEqual(calls, [('GET', '/api/session/ses_old', None)])

    def test_invalid_paths_and_large_batches_never_reach_core(self):
        for ids in [['ses_1/../../config'], ['not-session'], ['ses_1'] * 121, 'ses_1']:
            with self.subTest(ids=str(ids)[:40]), self.assertRaises(ValueError):
                read_markers(ids, lambda *args: self.fail('Must not query Core'))

    def test_missing_or_invalid_markers_cannot_mark_read(self):
        for stamp in [None, True, -1, '500', float('nan')]:
            result = read_markers(['ses_old'], lambda *args: (200, json.dumps({'data': {'id': 'ses_old', 'time': {'viewed': stamp}}}).encode()))
            self.assertEqual(result['viewed'], {})
        result = read_markers(['ses_old'], lambda *args: (404, b'{}'))
        self.assertEqual(result['unavailable'], ['ses_old'])
