import subprocess
import unittest
from power import NotebookPower


class PowerTests(unittest.TestCase):
    def test_device_binding_single_use_and_expiry_without_actual_shutdown(self):
        calls = []
        now = [100]
        def fake(args, **kwargs):
            calls.append(args)
            return subprocess.CompletedProcess(args, 0, '{"data":["yes"]}', '')
        power = NotebookPower(run=fake, clock=lambda: now[0])
        _, result = power.prepare('device-a')
        self.assertEqual(power.power_off('device-b', result['ticket'])[0], 409)
        self.assertFalse(any('poweroff' in call for call in calls))
        _, result = power.prepare('device-a')
        self.assertEqual(power.power_off('device-a', result['ticket']), (202, {'admitted': True}))
        self.assertEqual(power.power_off('device-a', result['ticket'])[0], 409)
        self.assertEqual(len([call for call in calls if 'poweroff' in call]), 1)
        _, result = power.prepare('device-a'); now[0] += 46
        self.assertEqual(power.power_off('device-a', result['ticket'])[0], 409)

    def test_challenge_cannot_prepare_or_escalate(self):
        def fake(args, **kwargs): return subprocess.CompletedProcess(args, 0, '{"data":["challenge"]}', '')
        power = NotebookPower(run=fake)
        self.assertEqual(power.prepare('device')[0], 403)
        self.assertFalse(power.status()['wakeConfigured'])
