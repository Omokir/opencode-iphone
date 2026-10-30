"""Native UI interactions against simulator-only data, never real services."""
import json
import subprocess
import sys
import time

cli, device = sys.argv[1:]
bundle = 'com.omokir.opencodepocket'

def command(*args):
    return subprocess.check_output([cli, *args, '--device', device], text=True, timeout=45)

def elements():
    roots = json.loads(command('dump', 'ui', '--format', 'json')).get('data', {}).get('elements', [])
    def flatten(group):
        for element in group:
            yield element
            yield from flatten(element.get('children', []))
    return list(flatten(roots))

def label(element):
    return str(element.get('label') or element.get('name') or element.get('text') or '')

def wait(predicate, seconds=20):
    deadline = time.monotonic() + seconds
    last = []
    while time.monotonic() < deadline:
        last = elements()
        found = next((e for e in last if predicate(e)), None)
        if found: return found
        time.sleep(0.4)
    raise AssertionError('Fixture UI missing: ' + repr([(e.get('type'), label(e)) for e in last]))

def tap(predicate):
    target = wait(lambda e: predicate(e) and e.get('enabled', True) is not False)
    command('io', 'tap', target['ref'])

def launch(screen):
    subprocess.run(['xcrun', 'simctl', 'terminate', device, bundle], capture_output=True)
    subprocess.run(['xcrun', 'simctl', 'launch', device, bundle, '--snapshot-' + screen], check=True, timeout=30)

def shot(name):
    subprocess.run(['xcrun', 'simctl', 'io', device, 'screenshot', 'build/iphone-' + name + '.png'], check=True, timeout=20)

launch('conversation')
wait(lambda e: 'Pronto para revisar.' in label(e))
print('PASS: native history renders on open without sending a message.', flush=True)
subprocess.run(['xcrun', 'simctl', 'ui', device, 'appearance', 'dark'], check=True)
shot('conversation-dark')
tap(lambda e: e.get('identifier') == 'chat.composer' or (e.get('type') in ('TextField', 'TextView') and label(e) == 'Mensagem'))
command('io', 'fill', 'Rascunho visual, sem enviar.')
try:
    # Device Kit exposes actual keys, not always a parent Keyboard element.
    wait(lambda e: e.get('type') == 'Key' and label(e) in ('space', 'espaço'))
    wait(lambda e: e.get('type') == 'Key' and label(e) == 'delete')
    wait(lambda e: 'Pronto para revisar.' in label(e))
finally:
    shot('conversation-keyboard')
print('PASS: keyboard and draft input keep fixture history in native hierarchy; no prompt sent.', flush=True)

launch('sidebar')
wait(lambda e: 'Seu agente no computador' in label(e))
wait(lambda e: e.get('type') == 'Button' and label(e) == 'Arquivos')
shot('sidebar-dark')
tap(lambda e: e.get('type') == 'Button' and label(e) == 'Nova conversa')
wait(lambda e: label(e) == 'Nova conversa')
wait(lambda e: 'Como posso ajudar?' in label(e))
assert not any(label(e) == 'Pasta no notebook' for e in elements())
shot('new-chat')
print('PASS: new chat opens from sidebar without a directory prompt.', flush=True)

launch('call')
wait(lambda e: e.get('type') == 'Button' and label(e) == 'Ligar para KzL')
shot('call-dark')
tap(lambda e: e.get('type') == 'Button' and label(e) == 'Ligar para KzL')
wait(lambda e: 'Ligar com OpenAI Realtime?' in label(e))
tap(lambda e: e.get('type') == 'Button' and label(e) == 'Cancelar')
print('PASS: call screen opens billing notice; cancelled before any audio or paid API call.', flush=True)
