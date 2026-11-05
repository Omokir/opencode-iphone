"""Real AT-SPI names/roles from a separate reader on private D-Bus/Xvfb."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import traceback

EXPECTED = {'Detalhe da tarefa · obrigatório', 'Número de tentativas · obrigatório',
            'Modo de trabalho', 'Modelo da conversa', 'Variante do modelo · opcional', 'Mensagem'}


def probe():
    import gi
    gi.require_version('Atspi', '2.0')
    from gi.repository import Atspi
    deadline = time.monotonic()+15; latest = []
    while time.monotonic() < deadline:
        pending = [Atspi.get_desktop(0)]; entries = []; visited = 0
        while pending and visited < 1000:
            node = pending.pop(); visited += 1
            if node is None:
                continue
            try:
                name = node.get_name(); role = node.get_role_name(); description = node.get_description()
                if name in EXPECTED or description in EXPECTED:
                    entries.append({'name': name[:200], 'description': description[:200], 'role': role})
                pending.extend(node.get_child_at_index(i) for i in range(min(node.get_child_count(), 100)))
            except Exception:
                continue
        latest = entries
        named_controls = {value for row in entries if row['role'] not in ('label', 'static', 'unknown') for value in (row['name'], row['description'])}
        if EXPECTED <= named_controls:
            print(json.dumps(entries, ensure_ascii=False), flush=True); return
        time.sleep(.2)
    raise AssertionError('AT-SPI missing named controls: ' + json.dumps(latest, ensure_ascii=False))


def main():
    if os.environ.get('POCKET_TEST_INSTALL'):
        sys.path.insert(0, os.environ['POCKET_TEST_INSTALL'])
    from main import Pocket, GLib
    app = Pocket(demo=True, state='/scratch/a11y-state')
    phase = 0; errors = []; process = None; output = None; diagnostics = None; deadline = time.monotonic()+30
    def exception(*args):
        errors.append(''.join(traceback.format_exception(*args))); print(errors[-1], file=sys.stderr); app.quit()
    sys.excepthook = exception
    def check():
        nonlocal phase, process, output, diagnostics
        if time.monotonic() > deadline:
            raise AssertionError(f'AT-SPI test timeout {phase}')
        if phase == 0 and app.session and app.messages:
            app.answer_form({'id': 'form_a11y', 'title': 'Acessibilidade da pergunta', 'fields': [
                {'key': 'detail', 'title': 'Detalhe da tarefa', 'type': 'string', 'required': True},
                {'key': 'tries', 'title': 'Número de tentativas', 'type': 'integer', 'required': True}]})
            app.options()
            output = open('/scratch/a11y-probe.json', 'w'); diagnostics = open('/scratch/a11y-probe.log', 'w')
            process = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), '--probe'], stdout=output, stderr=diagnostics)
            phase = 1
        elif phase == 1 and process.poll() is not None:
            output.close(); diagnostics.close()
            assert process.returncode == 0, Path('/scratch/a11y-probe.log').read_text()[-4000:]
            rows = json.loads(Path('/scratch/a11y-probe.json').read_text())
            assert EXPECTED <= {value for row in rows for value in (row['name'], row['description'])}
            print('PASS: separate AT-SPI reader observed all six native control names/descriptions/roles, not merely visual labels: ' + json.dumps(rows, ensure_ascii=False), flush=True)
            assert app.sent == 0
            phase = 2; app.window.close(); app.quit(); return GLib.SOURCE_REMOVE
        return GLib.SOURCE_CONTINUE
    try:
        GLib.timeout_add(150, check); app.run([])
        assert not errors, errors
        assert phase == 2
    finally:
        if process and process.poll() is None:
            process.kill(); process.wait(timeout=5)
        for file in (output, diagnostics):
            if file and not file.closed:
                file.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--probe', action='store_true'); args = parser.parse_args()
    probe() if args.probe else main()
