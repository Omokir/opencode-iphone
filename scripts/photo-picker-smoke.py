"""Simulator-only regression: attachments menu -> real system photo picker.

Only synthetic simulator media is used. Never connects to the user's iPhone.
"""
import json
import subprocess
import sys
import time

cli, device = sys.argv[1:]


def command(*args):
    result = subprocess.run([cli, *args, '--device', device], check=True, capture_output=True, text=True, timeout=45)
    return result.stdout


def tree():
    data = json.loads(command('dump', 'ui', '--format', 'json'))
    roots = data.get('data', {}).get('elements', [])
    def flatten(elements):
        for element in elements:
            yield element
            yield from flatten(element.get('children', []))
    return list(flatten(roots))


def labels(element):
    return [str(element.get(key) or '').casefold() for key in ('label', 'name', 'text')]


def wait_for(predicate, seconds=15):
    deadline = time.monotonic() + seconds
    latest = []
    while time.monotonic() < deadline:
        latest = tree()
        found = next((element for element in latest if predicate(element)), None)
        if found:
            return found, latest
        time.sleep(0.4)
    print('Synthetic simulator UI labels:', [labels(element) for element in latest])
    raise AssertionError('Expected simulator UI did not appear')


button, _ = wait_for(lambda e: 'anexar fotos ou arquivos' in labels(e))
command('io', 'tap', button['ref'])
photo, _ = wait_for(lambda e: 'fotos' in labels(e) and e.get('type') == 'Button')
command('io', 'tap', photo['ref'])
cancel, elements = wait_for(lambda e: any(label in ('cancel', 'cancelar') for label in labels(e)))
assert any(any(label in ('photos', 'fotos', 'photo library', 'fototeca', 'biblioteca de fotos', 'collections') for label in labels(e)) for e in elements), 'Cancel appeared but photo picker was not identified'
subprocess.run(['xcrun', 'simctl', 'io', device, 'screenshot', 'build/iphone-photos.png'], check=True)
command('io', 'tap', cancel['ref'])
wait_for(lambda e: 'anexar fotos ou arquivos' in labels(e))
print('PASS: native Photos menu opens real system picker; Cancel returns to chat.')
