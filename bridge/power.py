"""Explicit, one-shot power-off admission. No root policy changes or wake claims."""
import json
import secrets
import subprocess
import threading
import time


class NotebookPower:
    def __init__(self, run=subprocess.run, clock=time.monotonic):
        self.run = run; self.clock = clock; self.lock = threading.Lock(); self.tickets = {}

    def status(self):
        try:
            result = self.run(['/usr/bin/busctl', '--system', '--json=short', 'call', 'org.freedesktop.login1',
                '/org/freedesktop/login1', 'org.freedesktop.login1.Manager', 'CanPowerOff'], capture_output=True, text=True, timeout=5, check=False)
            value = json.loads(result.stdout).get('data', [None])[0] if result.returncode == 0 else None
            capability = value if value in ('yes', 'no', 'challenge') else 'unavailable'
        except (OSError, ValueError, subprocess.SubprocessError): capability = 'unavailable'
        return {'powerOff': capability, 'wakeConfigured': False}

    def prepare(self, device):
        if self.status()['powerOff'] != 'yes':
            return 403, {'error': 'Desligamento sem interação administrativa não autorizado pelo Linux. Nenhuma política será alterada pelo app.'}
        with self.lock:
            self.tickets = {key: value for key, value in self.tickets.items() if value[1] > self.clock()}
            if len(self.tickets) >= 20:
                return 429, {'error': 'Confirmações demais; aguarde expiração.'}
            token = secrets.token_urlsafe(32)
            self.tickets[token] = (device, self.clock() + 45)
            return 200, {'ticket': token, 'expiresIn': 45}

    def power_off(self, device, ticket):
        if not isinstance(ticket, str) or len(ticket) > 128:
            return 400, {'error': 'Confirmação inválida.'}
        with self.lock:
            saved = self.tickets.pop(ticket, None)
        if not saved or saved[0] != device or saved[1] <= self.clock():
            return 409, {'error': 'Confirmação ausente, expirada ou já consumida. Não houve repetição automática.'}
        # Noninteractive: never grant privileges, bypass inhibitors or alter Polkit.
        try:
            result = self.run(['/usr/bin/systemctl', '--no-ask-password', '--no-block', 'poweroff'],
                              capture_output=True, text=True, timeout=8, check=False)
            if result.returncode != 0:
                return 403, {'error': 'Linux recusou desligamento. Confira políticas e tarefas no notebook.'}
        except (OSError, subprocess.SubprocessError):
            return 503, {'error': 'Resultado do desligamento incerto. Confira notebook antes de qualquer nova tentativa.'}
        return 202, {'admitted': True}
