import json
import unittest

from codex_usage import CodexUsage, normalize_usage


class QuotaTests(unittest.TestCase):
    def sample(self):
        return {'account': {'type': 'chatgpt', 'email': 'person@example.invalid', 'planType': 'plus', 'token': 'never-return-this'},
                'limits': {'rateLimitsByLimitId': {'codex': {'primary': {'usedPercent': 40, 'windowDurationMins': 300, 'resetsAt': 2000},
                    'secondary': {'usedPercent': 65, 'windowDurationMins': 10080, 'resetsAt': 3000}}}}}

    def test_week_is_classified_by_duration_not_position(self):
        data = self.sample()
        bucket = data['limits']['rateLimitsByLimitId']['codex']
        bucket['primary'], bucket['secondary'] = bucket['secondary'], bucket['primary']
        result = normalize_usage(data, 1000)
        self.assertEqual(result['weekly']['usedPercent'], 65)
        self.assertEqual(result['shortWindow']['windowMinutes'], 300)
        self.assertEqual(result['accountLabel'], 'p***@example.invalid')
        self.assertNotIn('never-return-this', json.dumps(result))

    def test_api_key_is_not_presented_as_subscription_quota(self):
        result = normalize_usage({'account': {'type': 'apiKey'}}, 1000)
        self.assertFalse(result['available'])
        self.assertIsNone(result['weekly'])

    def test_no_weekly_value_is_not_zero(self):
        data = self.sample()
        data['limits']['rateLimitsByLimitId']['codex']['secondary'] = None
        result = normalize_usage(data, 1000)
        self.assertIsNone(result['weekly'])
        self.assertIsNotNone(result['reason'])

    def test_other_bucket_is_not_confused_with_codex(self):
        data = self.sample()
        data['limits']['rateLimitsByLimitId']['other'] = data['limits']['rateLimitsByLimitId'].pop('codex')
        self.assertFalse(normalize_usage(data, 1000)['available'])

    def test_cache_and_explicit_refresh_throttle(self):
        count = []
        now = [1000]
        usage = CodexUsage(reader=lambda: count.append(1) or self.sample(), clock=lambda: now[0])
        usage.get(); usage.get(refresh=True)
        self.assertEqual(len(count), 1)
        now[0] += 11
        usage.get(refresh=True)
        self.assertEqual(len(count), 2)

    def test_errors_are_sanitized_and_not_stale_success(self):
        def fail():
            raise RuntimeError('secret-error-token')
        result = CodexUsage(reader=fail).get()
        self.assertFalse(result['available'])
        self.assertIsNone(result['weekly'])
        self.assertNotIn('secret-error-token', json.dumps(result))
