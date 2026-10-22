"""Simulator-only pin/unpin interaction test using synthetic conversations."""
import json
import subprocess
import sys
import time

cli, device = sys.argv[1:]


def command(*args):
    result = subprocess.run([cli, *args, '--device', device], check=True, capture_output=True, text=True, timeout=45)
    return result.stdout


def tree():
    roots = json.loads(command('dump', 'ui', '--format', 'json')).get('data', {}).get('elements', [])
    def flatten(elements):
        for element in elements:
            yield element
            yield from flatten(element.get('children', []))
    return list(flatten(roots))


def text(element):
    return str(element.get('label') or element.get('name') or element.get('text') or '')


def wait_for(predicate):
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        elements = tree()
        found = next((element for element in elements if predicate(element)), None)
        if found:
            return found
        time.sleep(0.4)
    raise AssertionError('Expected pin UI did not appear: ' + repr([text(e) for e in elements]))


def conversation():
    return wait_for(lambda e: e.get('type') == 'Button' and 'Controle do meu iPhone' in text(e))


row = conversation()
subprocess.run(['xcrun', 'simctl', 'io', device, 'screenshot', 'build/iphone-pins.png'], check=True)
command('io', 'longpress', row['ref'], '--duration', '1000')
unpin = wait_for(lambda e: text(e) == 'Desafixar conversa')
command('io', 'tap', unpin['ref'])
row = conversation()
command('io', 'longpress', row['ref'], '--duration', '1000')
pin = wait_for(lambda e: text(e) == 'Fixar conversa')
command('io', 'tap', pin['ref'])
row = conversation()
command('io', 'longpress', row['ref'], '--duration', '1000')
wait_for(lambda e: text(e) == 'Desafixar conversa')
print('PASS: native context menu unpins, then pins conversation again.')
