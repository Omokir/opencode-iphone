"""Read only Linux power-supply sensors, with explicit unavailable values."""
from pathlib import Path


def battery_status(root=Path('/sys/class/power_supply')):
    def text(path):
        try:
            return path.read_text().strip()
        except OSError:
            return None

    def number(path):
        try:
            return int(text(path))
        except (TypeError, ValueError):
            return None

    try:
        nodes = list(Path(root).iterdir())
    except OSError:
        nodes = []
    batteries = [node for node in nodes if text(node / 'type') == 'Battery' and text(node / 'present') != '0']
    online = [number(node / 'online') for node in nodes if text(node / 'type') in ('Mains', 'USB', 'USB_C', 'USB_PD')]
    online = [value for value in online if value in (0, 1)]
    result = {'available': bool(batteries), 'percentage': None, 'charging': None,
              'onAC': any(online) if online else None, 'state': None}
    if not batteries:
        return result
    capacities = [number(node / 'capacity') for node in batteries]
    capacities = [value for value in capacities if value is not None and 0 <= value <= 100]
    energies = [(number(node / 'energy_now'), number(node / 'energy_full')) for node in batteries]
    if all(now is not None and full is not None and 0 <= now <= full and full > 0 for now, full in energies):
        result['percentage'] = round(100 * sum(now for now, _ in energies) / sum(full for _, full in energies))
    elif len(capacities) == len(batteries):
        result['percentage'] = round(sum(capacities) / len(capacities))
    states = {text(node / 'status') for node in batteries}
    state = next(iter(states)) if len(states) == 1 else 'Mixed'
    result['state'] = state if state in ('Charging', 'Discharging', 'Full', 'Not charging', 'Mixed') else None
    if state == 'Charging':
        result['charging'] = True
    elif state in ('Discharging', 'Full', 'Not charging'):
        result['charging'] = False
    return result
