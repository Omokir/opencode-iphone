"""Read-only Codex app-server quota adapter. Never starts a thread or logs auth."""
import json
import math
import os
import queue
import shutil
import signal
import subprocess
import threading
import time


def read_codex():
    executable = shutil.which('codex')
    if not executable:
        raise RuntimeError('Codex CLI não encontrado no notebook.')
    process = subprocess.Popen([executable, 'app-server', '--listen', 'stdio://', '-c', 'analytics.enabled=false'],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        text=True, start_new_session=True)
    messages = queue.Queue()
    deadline = time.monotonic() + 20

    def receive():
        try:
            for line in process.stdout:
                if len(line) > 1024 * 1024:
                    continue
                try:
                    messages.put(json.loads(line))
                except ValueError:
                    pass
        finally:
            messages.put(None)
    receiver = threading.Thread(target=receive, daemon=True)
    receiver.start()

    def send(value):
        process.stdin.write(json.dumps(value) + '\n')
        process.stdin.flush()

    def call(identifier, method, params=None):
        # Fixed read-only methods only; never supplied by a mobile request.
        assert method in ('initialize', 'account/read', 'account/rateLimits/read')
        value = {'id': identifier, 'method': method}
        if params is not None:
            value['params'] = params
        send(value)
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise RuntimeError('Consulta de cota não respondeu a tempo.')
            try:
                response = messages.get(timeout=remaining)
            except queue.Empty:
                raise RuntimeError('Consulta de cota não respondeu a tempo.') from None
            if response is None:
                raise RuntimeError('Codex encerrou consulta de cota.')
            if response.get('id') == identifier:
                if 'error' in response:
                    raise RuntimeError('Conta ou versão do Codex não disponibilizou esta consulta.')
                return response['result']

    try:
        call(0, 'initialize', {'clientInfo': {'name': 'opencode_pocket_status', 'title': 'OpenCode Pocket status', 'version': '0.3'}})
        send({'method': 'initialized', 'params': {}})
        account = call(1, 'account/read', {'refreshToken': False}).get('account')
        if not account or account.get('type') != 'chatgpt':
            return {'account': account, 'limits': None}
        limits = call(2, 'account/rateLimits/read')
        return {'account': account, 'limits': limits}
    finally:
        # Only terminate this newly created process group, including its own
        # helper children. Never touches an existing Codex session/server.
        try:
            os.killpg(process.pid, signal.SIGTERM)
            process.wait(timeout=3)
        except ProcessLookupError:
            pass
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=2)
        receiver.join(timeout=1)
        if process.stdout and not receiver.is_alive():
            process.stdout.close()
        if process.stdin:
            try:
                process.stdin.close()
            except BrokenPipeError:
                pass


def normalize_usage(raw, now):
    result = {'available': False, 'source': 'Codex CLI no notebook', 'checkedAt': now,
              'accountLabel': None, 'plan': None, 'weekly': None, 'shortWindow': None,
              'reason': None}
    account = raw.get('account')
    if not account:
        result['reason'] = 'Codex não está autenticado no notebook.'
        return result
    if account.get('type') != 'chatgpt':
        result['reason'] = 'Cota semanal é da conta ChatGPT no Codex, não do saldo de uma chave API.'
        return result
    email = account.get('email')
    if isinstance(email, str) and '@' in email:
        name, domain = email.split('@', 1)
        result['accountLabel'] = (name[:1] or '*') + '***@' + domain
    result['plan'] = account.get('planType') if isinstance(account.get('planType'), str) else None
    limits = raw.get('limits') or {}
    bucket = (limits.get('rateLimitsByLimitId') or {}).get('codex')
    if bucket is None:
        legacy = limits.get('rateLimits')
        if isinstance(legacy, dict) and legacy.get('limitId') in (None, 'codex'):
            bucket = legacy
    if not isinstance(bucket, dict):
        result['reason'] = 'Conta não informou cota geral do Codex.'
        return result
    for key in ('primary', 'secondary'):
        window = bucket.get(key)
        if not isinstance(window, dict):
            continue
        used = window.get('usedPercent')
        minutes = window.get('windowDurationMins')
        reset = window.get('resetsAt')
        if isinstance(used, bool) or not isinstance(used, (int, float)) or not math.isfinite(used) or not 0 <= used <= 100:
            continue
        if isinstance(minutes, bool) or not isinstance(minutes, (int, float)) or minutes <= 0:
            continue
        reset = reset if isinstance(reset, (int, float)) and not isinstance(reset, bool) and math.isfinite(reset) and reset > 0 else None
        value = {'usedPercent': used, 'windowMinutes': minutes, 'resetsAt': reset}
        if minutes == 7 * 24 * 60:
            result['weekly'] = value
        elif minutes < 7 * 24 * 60:
            result['shortWindow'] = value
    result['available'] = result['weekly'] is not None or result['shortWindow'] is not None
    if result['weekly'] is None:
        result['reason'] = 'Janela semanal não informada pela conta.'
    return result


class CodexUsage:
    def __init__(self, reader=read_codex, clock=time.time):
        self.reader = reader
        self.clock = clock
        self.lock = threading.Lock()
        self.cached = None

    def get(self, refresh=False):
        with self.lock:
            if self.cached and self.clock() - self.cached['checkedAt'] < (10 if refresh else 60):
                return self.cached
            try:
                result = normalize_usage(self.reader(), self.clock())
            except Exception:
                result = {'available': False, 'source': 'Codex CLI no notebook', 'checkedAt': self.clock(),
                          'accountLabel': None, 'plan': None, 'weekly': None, 'shortWindow': None,
                          'reason': 'Consulta indisponível. Verifique login do Codex no notebook; nenhum valor foi estimado.'}
            self.cached = result
            return result
