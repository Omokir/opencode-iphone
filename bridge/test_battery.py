from pathlib import Path
import tempfile
import unittest

from battery import battery_status


class BatteryTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.root = Path(self.folder.name)

    def tearDown(self):
        self.folder.cleanup()

    def node(self, name, values):
        node = self.root / name
        node.mkdir()
        for key, value in values.items():
            (node / key).write_text(str(value))

    def test_discharge_and_ac(self):
        self.node('BAT0', {'type': 'Battery', 'capacity': 17, 'status': 'Discharging'})
        self.node('AC', {'type': 'Mains', 'online': 0})
        status = battery_status(self.root)
        self.assertEqual(status['percentage'], 17)
        self.assertFalse(status['charging'])
        self.assertFalse(status['onAC'])

    def test_charging(self):
        self.node('BAT0', {'type': 'Battery', 'capacity': 46, 'status': 'Charging'})
        self.node('AC', {'type': 'Mains', 'online': 1})
        status = battery_status(self.root)
        self.assertTrue(status['charging'])
        self.assertTrue(status['onAC'])

    def test_invalid_percentage_is_not_zero(self):
        self.node('BAT0', {'type': 'Battery', 'capacity': 'bad', 'status': 'Unknown'})
        self.assertIsNone(battery_status(self.root)['percentage'])

    def test_missing_battery_is_explicit(self):
        self.assertFalse(battery_status(self.root)['available'])
        self.assertIsNone(battery_status(self.root)['percentage'])

    def test_multiple_batteries_use_energy_weighting(self):
        self.node('BAT0', {'type': 'Battery', 'energy_now': 10, 'energy_full': 20})
        self.node('BAT1', {'type': 'Battery', 'energy_now': 90, 'energy_full': 100})
        self.assertEqual(battery_status(self.root)['percentage'], 83)

    def test_connected_iphone_does_not_hide_notebook_percentage(self):
        self.node('BAT0', {'type': 'Battery', 'capacity': 54, 'status': 'Discharging'})
        self.node('apple_mfi', {'type': 'Battery', 'scope': 'Device'})
        self.node('phone_usb', {'type': 'USB', 'scope': 'Device', 'online': 1})
        self.node('AC', {'type': 'Mains', 'online': 0})
        status = battery_status(self.root)
        self.assertEqual(status['percentage'], 54)
        self.assertFalse(status['onAC'])
        self.assertEqual(status['state'], 'Discharging')
