import unittest
from server import allowed


class SessionActionsPolicyTests(unittest.TestCase):
    def test_only_explicit_actions_are_forwarded(self):
        for method, path in [
            ('GET', '/api/command'), ('GET', '/api/skill'),
            ('GET', '/api/session/ses_test/inbox'),
            ('POST', '/api/session/ses_test/command'),
            ('POST', '/api/experimental/session/ses_test/skill'),
            ('POST', '/api/experimental/schedule'),
            ('POST', '/api/experimental/schedule/job_1/pause'),
            ('DELETE', '/api/session/ses_test/inbox/msg_1'),
        ]:
            self.assertTrue(allowed(method, path), (method, path))
        for method, path in [
            ('GET', '/api/credential'), ('DELETE', '/api/session/ses_test'),
            ('POST', '/api/session/ses_test/shell'),
            ('POST', '/api/experimental/config'),
            ('DELETE', '/api/experimental/schedule/job_1/extra'),
        ]:
            self.assertFalse(allowed(method, path), (method, path))
