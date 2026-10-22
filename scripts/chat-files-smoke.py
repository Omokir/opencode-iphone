"""Synthetic simulator interactions for modes, draft recovery and file previews."""
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


def label(e):
    return str(e.get('label') or e.get('name') or e.get('text') or '')


def wait_for(predicate, seconds=15):
    deadline = time.monotonic() + seconds
    elements = []
    while time.monotonic() < deadline:
        elements = tree()
        result = next((e for e in elements if predicate(e)), None)
        if result:
            return result
        time.sleep(0.4)
    raise AssertionError('Synthetic UI not found: ' + repr([(e.get('type'), label(e), e.get('value')) for e in elements]))


def tap(predicate):
    e = wait_for(predicate)
    command('io', 'tap', e['ref'])


def launch():
    subprocess.run(['xcrun', 'simctl', 'launch', device, 'com.omokir.opencodepocket', '--snapshot-chat'], check=True)


def terminate():
    subprocess.run(['xcrun', 'simctl', 'terminate', device, 'com.omokir.opencodepocket'], check=True)


launch()
for agent in ['Plan', 'Build']:
    tap(lambda e: e.get('type') == 'Button' and label(e) == agent)
    wait_for(lambda e: e.get('type') == 'Button' and label(e) == agent and (e.get('selected') is True or e.get('value') == 'Selecionado'))
print('PASS: rapid Plan/Build buttons change confirmed selection for same session ID.')
subprocess.run(['xcrun', 'simctl', 'io', device, 'screenshot', 'build/iphone-modes.png'], check=True)
tap(lambda e: e.get('type') in ('TextField', 'TextView') and 'Peça algo ao OpenCode' in label(e))
draft = 'Rascunho de teste, nunca enviar.'
command('io', 'fill', draft)
wait_for(lambda e: label(e) == 'Rascunho salvo')
terminate()
launch()
wait_for(lambda e: e.get('type') in ('TextField', 'TextView') and e.get('value') == draft)
print('PASS: draft text survives app termination/relaunch without sending a prompt.')
tap(lambda e: 'Prévia de requisitos.txt' in label(e))
wait_for(lambda e: 'Salvar/Compartilhar' in label(e))
subprocess.run(['xcrun', 'simctl', 'io', device, 'screenshot', 'build/iphone-attachment-preview.png'], check=True)
print('PASS: pending attachment opens native Quick Look preview.')
terminate()
launch()
tap(lambda e: e.get('type') == 'Button' and label(e) == 'Opções da conversa')
tap(lambda e: label(e) == 'Arquivos do projeto')
wait_for(lambda e: 'Arquivos do notebook' in label(e))
tap(lambda e: e.get('type') == 'Button' and 'README.txt' in label(e))
wait_for(lambda e: 'Salvar/Compartilhar' in label(e))
subprocess.run(['xcrun', 'simctl', 'io', device, 'screenshot', 'build/iphone-download-preview.png'], check=True)
print('PASS: project file browser downloads synthetic text into native preview/share flow.')
terminate()
