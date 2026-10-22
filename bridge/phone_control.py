"""Explicit, expiring automation consent and a restricted OpenCode conversation.

This is a control for the normal MCP path, not a sandbox against other processes
running as the notebook user. Never exposes device screenshots or shell access.
"""
import json
import os
from pathlib import Path
import subprocess
import threading
import time
import urllib.request

CONTROL_PERMISSIONS = [
    {'action': '*', 'resource': '*', 'effect': 'deny'},
    {'action': 'execute', 'resource': '*', 'effect': 'allow'},
    {'action': 'iphone_*', 'resource': '*', 'effect': 'ask'},
    *[{'action': 'iphone_' + name, 'resource': '*', 'effect': 'allow'} for name in (
        'mobile_list_available_devices', 'mobile_list_elements_on_screen',
        'mobile_take_screenshot', 'mobile_list_apps')],
    # A mixed batch may otherwise hide a send/delete behind navigation steps.
    {'action': 'iphone_mobile_batch_commands', 'resource': '*', 'effect': 'deny'},
    {'action': 'iphone_*remote*', 'resource': '*', 'effect': 'deny'},
    {'action': 'iphone_mobile_install_app', 'resource': '*', 'effect': 'deny'},
    {'action': 'iphone_mobile_uninstall_app', 'resource': '*', 'effect': 'deny'},
]
INSTRUCTIONS = '''Controle apenas o iPhone autorizado pelo painel. Use ferramentas
iphone; não use shell, subagentes, desktop ou outras integrações como alternativa.
Leia a tela antes de agir. Ações de navegação, toques, digitação e abertura de apps
pedem autorização individual. Explique destino e efeito antes da solicitação.
Nunca envie mensagens, publique, apague, compre ou execute Atalhos sem explicar
efeito e obter confirmação explícita. Não tente contornar uma negativa, pausa,
bloqueio de tela ou autenticação. Não digite senhas/códigos Apple pelo usuário.
Não contrate dispositivos remotos. Ações já executadas não são desfeitas ao parar.
'''


class PhoneControl:
    def __init__(self, root, upstream, run=subprocess.run, clock=time.time):
        self.root = Path(root)
        self.upstream = upstream
        self.run = run
        self.clock = clock
        self.lock = threading.Lock()
        self.device_cache = None
        self.cached_at = 0

    @property
    def state_file(self):
        return self.root / 'automation.json'

    def state(self):
        try:
            value = json.loads(self.state_file.read_text())
            return value if isinstance(value, dict) else {}
        except (OSError, ValueError):
            return {}

    def config(self):
        try:
            value = json.loads((self.root / 'automation-config.json').read_text())
            if not all(isinstance(value.get(k), str) and value[k] for k in ('cli', 'deviceID', 'home')):
                return None
            if not Path(value['cli']).is_absolute():
                return None
            return value
        except (OSError, ValueError):
            return None

    def save(self, state):
        self.root.mkdir(parents=True, exist_ok=True)
        temporary = self.state_file.with_suffix('.tmp')
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w') as stream:
            json.dump(state, stream)
        os.replace(temporary, self.state_file)

    def command(self, args, timeout=12):
        config = self.config()
        if not config:
            raise RuntimeError('Controle ainda não configurado no notebook.')
        env = os.environ.copy()
        # Metadata must never start/reuse the action daemon without its gate.
        env['MOBILECLI_HOME'] = config['home'] if args == ['daemon', 'stop'] else config['home'] + '-metadata'
        # Only fixed metadata/stop commands below use this host-side path.
        # Model-invoked MCP commands keep the state-file gate in their env.
        env.pop('MOBILECLI_CONTROL_STATE', None)
        result = self.run([config['cli'], *args], env=env, capture_output=True,
                          text=True, timeout=timeout, check=False)
        if result.returncode:
            raise RuntimeError('Não foi possível consultar agente. Verifique cabo e desbloqueio.')
        return json.loads(result.stdout)

    def device(self):
        if self.device_cache is not None and self.clock() - self.cached_at < 3:
            return self.device_cache
        result = {'connected': False, 'agentInstalled': False, 'name': 'iPhone', 'locked': None}
        config = self.config()
        if config:
            try:
                devices = self.command(['devices'])['data']['devices']
                match = next((d for d in devices if d.get('id') == config['deviceID']), None)
                if match:
                    result['connected'] = match.get('state') == 'online'
                    result['name'] = match.get('name', 'iPhone')
                if result['connected']:
                    agent = self.command(['agent', 'status', '--device', config['deviceID']])
                    result['agentInstalled'] = agent.get('status') == 'ok'
            except (RuntimeError, ValueError, KeyError, subprocess.SubprocessError):
                pass
        self.device_cache = result
        self.cached_at = self.clock()
        return result

    def is_control_session(self, session_id):
        return self.state().get('sessionID') == session_id

    def status(self):
        state = self.state()
        enabled = state.get('enabled') is True and state.get('expiresAt', 0) > self.clock()
        result = {'configured': self.config() is not None, 'enabled': enabled,
                  'expiresAt': state.get('expiresAt'), 'sessionID': state.get('sessionID'),
                  'device': self.device(), 'running': False, 'pending': 0,
                  'activity': 'Aguardando tarefa', 'ready': False}
        session_id = state.get('sessionID')
        if session_id:
            status, data = self.upstream('GET', '/api/session/active', None)
            if status == 200:
                result['running'] = session_id in json.loads(data).get('data', {})
            status, data = self.upstream('GET', f'/api/session/{session_id}/permission', None)
            if status == 200:
                result['pending'] = len(json.loads(data).get('data', []))
            if result['pending']:
                result['activity'] = 'Aguardando sua confirmação'
            elif result['running']:
                result['activity'] = 'IA executando tarefa'
        if enabled and result['device']['connected']:
            try:
                with urllib.request.urlopen('http://127.0.0.1:8100/health', timeout=0.5) as response:
                    result['ready'] = response.status == 200
            except OSError:
                pass
        return result

    def start(self):
        with self.lock:
            config = self.config()
            if not config:
                return 409, {'error': 'Controle ainda não configurado no notebook.'}
            device = self.device()
            if not device['connected'] or not device['agentInstalled']:
                return 409, {'error': 'Conecte iPhone por cabo e desbloqueie. Agente precisa estar instalado.'}
            state = self.state()
            session_id = state.get('sessionID')
            status, session = (self.upstream('GET', f'/api/session/{session_id}', None)
                               if session_id else (404, b''))
            if status == 404:
                workspace = Path(config.get('workspace', self.root / 'control-workspace'))
                if not (workspace / '.git').is_dir():
                    return 409, {'error': 'Workspace isolado de controle precisa ser preparado no notebook.'}
                defaults_path = self.root / 'defaults.json'
                defaults = json.loads(defaults_path.read_text()) if defaults_path.exists() else {}
                payload = {'title': 'Controle do meu iPhone', 'agent': 'build',
                           'location': {'directory': str(workspace)},
                           'metadata': {'phoneControl': True}, 'permissions': CONTROL_PERMISSIONS}
                if defaults.get('model'):
                    payload['model'] = defaults['model']
                status, session = self.upstream('POST', '/api/session', json.dumps(payload).encode())
                if status != 200:
                    return status, session
                session_id = json.loads(session)['data']['id']
                # Save ID before subsequent writes, so uncertain responses never
                # blindly create duplicate control conversations.
                self.save({'enabled': False, 'sessionID': session_id, 'expiresAt': 0})
                status, data = self.upstream('POST', f'/api/session/{session_id}/synthetic',
                    json.dumps({'text': INSTRUCTIONS, 'description': 'Regras do controle do iPhone', 'resume': False}).encode())
                if status != 200:
                    return status, data
            elif status != 200:
                return status, session
            # Reapply restricted permissions if session was changed elsewhere.
            status, data = self.upstream('PATCH', f'/api/session/{session_id}',
                json.dumps({'permissions': CONTROL_PERMISSIONS}).encode())
            if status not in (200, 204):
                return status, data
            self.save({'enabled': True, 'sessionID': session_id, 'expiresAt': self.clock() + 900})
            return 200, json.loads(session)

    def stop(self):
        with self.lock:
            state = self.state()
            state.update(enabled=False, expiresAt=0)
            self.save(state)  # Gate closes before trying to contact anything else.
            warnings = []
            session_id = state.get('sessionID')
            def interrupt():
                if not session_id:
                    return
                try:
                    status, _ = self.upstream('POST', f'/api/session/{session_id}/interrupt', b'{}')
                    if status not in (200, 204):
                        warnings.append('Interrupção da tarefa não confirmada.')
                    status, data = self.upstream('GET', f'/api/session/{session_id}/permission', None)
                    requests = json.loads(data).get('data', []) if status == 200 else []
                    if requests:
                        self.upstream('POST', f'/api/session/{session_id}/permission/{requests[0]["id"]}/reply', b'{"decision":"reject"}')
                except Exception:
                    warnings.append('Notebook não confirmou interrupção da tarefa.')
            worker = threading.Thread(target=interrupt, daemon=True)
            worker.start()
            try:
                self.command(['daemon', 'stop'], timeout=8)
            except Exception:
                warnings.append('Encerramento do agente não confirmado; novas chamadas MCP seguem bloqueadas.')
            worker.join(timeout=0.5)
            result_warnings = list(warnings)
            if worker.is_alive():
                result_warnings.append('Novas chamadas bloqueadas; interrupção da conversa ainda aguardando confirmação.')
            return 200, {'enabled': False, 'warnings': result_warnings}
