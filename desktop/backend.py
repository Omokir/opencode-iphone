"""Pocket desktop transport and private local preferences. No GTK dependency."""
import base64
import copy
from datetime import datetime, timezone
import hashlib
import json
import mimetypes
import math
import os
from pathlib import Path, PurePosixPath
import re
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

MAX_ATTACHMENTS = 8 * 1024 * 1024
MAX_RESPONSE = 70 * 1024 * 1024


class PocketError(Exception):
    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status


def activity_rows(kind, value, session_id):
    """Bounded, literal review data. No paths, terminal text or patches execute."""
    def text(value, limit=12000):
        return str(value)[:limit]
    rows = []
    if kind == 'diff':
        for item in value.get('data', [])[:100]:
            rows.append({'title': text(item.get('file', 'Arquivo'), 4096),
                         'detail': f"{item.get('status', '')} · +{item.get('additions', 0)} / −{item.get('deletions', 0)}",
                         'body': text(item.get('patch', '')) + ('\n[Prévia limitada; consulte o arquivo completo.]' if item.get('more') or len(str(item.get('patch', ''))) > 12000 else '')})
    elif kind == 'terminal':
        item = value.get('data')
        if item:
            rows.append({'title': text(item.get('title', 'Terminal'), 200), 'detail': text(item.get('cwd', ''), 4096) + ' · somente leitura',
                         'body': text(item.get('screen', {}).get('text', ''), 100000)})
    elif kind == 'tasks':
        for item in value.get('tasks', [])[:100]:
            if session_id not in (item.get('parent'), item.get('child')):
                continue
            state = item.get('state', 'uncertain')
            if not item.get('confirmed') and state not in ('queued', 'completed', 'failed', 'cancelled', 'uncertain'):
                state = 'Sem confirmação recente · conferir notebook'
            rows.append({'title': text(item.get('text', 'Tarefa'), 300), 'detail': text(state, 200), 'body': text(item.get('result', ''))})
    return rows


class ReadRetry:
    """Main-context single-flight/backoff for GET-only UI refreshes."""
    def __init__(self):
        self.in_flight = False; self.ready = False; self.failures = 0; self.next_at = 0

    def begin(self, manual=False, repeat=False, now=None):
        now = time.monotonic() if now is None else now
        if self.in_flight or (not manual and ((self.ready and not repeat) or now < self.next_at)):
            return False
        self.in_flight = True; return True

    def success(self):
        self.in_flight = False; self.ready = True; self.failures = 0; self.next_at = 0

    def failure(self, now=None):
        self.in_flight = False; self.ready = False; self.failures += 1
        self.next_at = (time.monotonic() if now is None else now) + min(30, 2 ** min(self.failures, 5))

    def invalidate(self):
        self.ready = False; self.failures = 0; self.next_at = 0

    def abandon(self):
        self.in_flight = False; self.invalidate()


def atomic_json(path, data):
    path = Path(path)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.' + secrets.token_hex(8))
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, 'w') as file:
            json.dump(data, file, ensure_ascii=False)
            file.flush(); os.fsync(file.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


class Store:
    def __init__(self, root):
        self.root = Path(root)
        self.data = {'drafts': {}, 'pins': [], 'projects': [], 'last': None, 'theme': 'system', 'portrait': False, 'outgoing': {}, 'actions': {}}
        path = self.root / 'preferences.json'
        if path.exists():
            if path.stat().st_size > 64 * 1024 * 1024:
                raise PocketError('Preferências excedem limite de 64 MB. Preserve arquivo e revise antes de abrir.')
            loaded = json.loads(path.read_text())
            if not isinstance(loaded, dict):
                raise PocketError('Preferências inválidas. Arquivo preservado.')
            self.data.update(loaded)

    def save(self):
        raw = json.dumps(self.data)
        if len(raw.encode()) > 64 * 1024 * 1024:
            raise PocketError('Limite local de rascunhos atingido. Remova anexos não usados.')
        atomic_json(self.root / 'preferences.json', self.data)

    def begin_prompt(self, session_id, draft):
        payload = prompt_payload(draft)
        requests = self.data.setdefault('outgoing', {})
        if payload['id'] not in requests:
            for identifier in list(requests):
                if len(requests) < 200:
                    break
                if requests[identifier].get('state') == 'admitted':
                    del requests[identifier]
            if len(requests) >= 200:
                raise PocketError('Há muitos envios sem confirmação. Revise o histórico antes de enviar novamente.')
        previous = requests.get(payload['id'])
        requests[payload['id']] = {'sessionID': session_id, 'state': 'admitted' if previous and previous.get('state') == 'admitted' else 'attempted', 'fingerprint': draft['fingerprint']}
        try:
            self.save()  # Admission intent is durable before any HTTP POST.
        except Exception:
            if previous is None:
                requests.pop(payload['id'], None)
            else:
                requests[payload['id']] = previous
            raise
        return payload

    def mark_prompt(self, identifier, state):
        if state not in ('admitted', 'uncertain'):
            raise PocketError('Estado de envio inválido.')
        record = self.data.setdefault('outgoing', {}).get(identifier)
        if record and not (record.get('state') == 'admitted' and state != 'admitted'):
            record['state'] = state
        return bool(record and record.get('state') == 'admitted')

    def pending_prompts(self, session_id):
        return [identifier for identifier, record in self.data.get('outgoing', {}).items()
                if record.get('sessionID') == session_id and record.get('state') in ('attempted', 'uncertain')]

    def reconcile_prompts(self, session_id, messages):
        admitted = {message['id'] for message in messages if message.get('type') == 'user'}
        found = []; cleared = False
        for identifier in self.pending_prompts(session_id):
            if identifier not in admitted:
                continue
            record = self.data['outgoing'][identifier]; record['state'] = 'admitted'; found.append(identifier)
            draft = self.data['drafts'].get(session_id, {})
            if draft.get('requestID') == identifier:
                try:
                    fingerprint = hashlib.sha256(json.dumps(prompt_content(draft), sort_keys=True).encode()).hexdigest()
                except (PocketError, KeyError, TypeError, AttributeError):
                    continue
                if fingerprint == record.get('fingerprint'):
                    self.data['drafts'][session_id] = {'text': '', 'files': []}; cleared = True
        return {'admitted': found, 'draft_cleared': cleared, 'pending': self.pending_prompts(session_id)}

    def reconcile_inbox(self, session_id, entries):
        evidence = [{'id': entry['id'], 'type': 'user'} for entry in entries
                    if isinstance(entry, dict) and isinstance(entry.get('id'), str) and entry.get('sessionID') == session_id
                    and entry.get('type') == 'user' and entry.get('delivery') in ('queue', 'steer')]
        return self.reconcile_prompts(session_id, evidence)

    def action_records(self, session_id):
        records = [copy.deepcopy(record) for record in self.data.get('actions', {}).values() if record.get('sessionID') == session_id]
        return sorted(records, key=lambda record: record.get('created', 0), reverse=True)

    def pending_creations(self, directory=None):
        return [copy.deepcopy(record) for record in self.data.get('creations', {}).values()
                if record.get('directory') == directory and record.get('state') in ('attempted', 'uncertain')]

    def begin_creation(self, directory=None):
        if directory is not None and (not isinstance(directory, str) or not 1 <= len(directory) <= 4096 or any(ord(c) < 32 for c in directory)):
            raise PocketError('Pasta de projeto inválida.')
        if self.pending_creations(directory):
            raise PocketError('Criação anterior sem confirmação. Confira o histórico antes de iniciar outra.')
        records = self.data.setdefault('creations', {})
        for key in list(records):
            if len(records) < 100:
                break
            if records[key].get('state') in ('acknowledged', 'reviewed'):
                del records[key]
        if len(records) >= 100:
            raise PocketError('Há muitas criações sem confirmação. Confira o histórico; nenhum registro foi descartado.')
        identifier = 'create_' + secrets.token_hex(16)
        records[identifier] = {'id': identifier, 'directory': directory, 'state': 'attempted', 'created': time.time()}
        try:
            self.save()
        except Exception:
            records.pop(identifier, None); raise
        return identifier

    def mark_creation(self, identifier, state, session_id=None):
        if state not in ('acknowledged', 'uncertain', 'reviewed'):
            raise PocketError('Estado de criação inválido.')
        record = self.data['creations'][identifier]
        if record['state'] == 'acknowledged' and state == 'uncertain':
            return
        record['state'] = state
        if session_id:
            record['sessionID'] = session_id

    def begin_action(self, binding, kind, payload):
        if not isinstance(binding, dict) or not re.fullmatch(r'ses[A-Za-z0-9_-]+', binding.get('id', '')):
            raise PocketError('Conversa da ação inválida.')
        if kind == 'command' and set(payload) == {'name', 'text'}:
            target = payload['name']
            if not isinstance(payload['text'], str) or len(payload['text']) > 32000:
                raise PocketError('Argumentos excedem limite de 32.000 caracteres.')
        elif kind == 'skill' and set(payload) == {'id', 'resume'} and payload['resume'] is True:
            target = payload['id']
        elif kind == 'rename' and set(payload) == {'title'} and isinstance(payload['title'], str) and 1 <= len(payload['title']) <= 200:
            target = 'title'
        elif kind == 'interrupt' and payload == {}:
            target = 'execution'
        elif kind == 'permission' and set(payload) == {'id', 'decision'} and payload['decision'] in ('once', 'reject'):
            target = payload['id']
        elif kind == 'form' and set(payload) == {'id', 'answer'} and isinstance(payload['answer'], dict):
            target = payload['id']
        else:
            raise PocketError('Tipo ou corpo de ação inválido.')
        if not isinstance(target, str) or not 1 <= len(target) <= 4096 or any(ord(c) < 32 for c in target):
            raise PocketError('Identificador da ação inválido.')
        records = self.data.setdefault('actions', {})
        if kind in ('permission', 'form') and any(record.get('sessionID') == binding['id'] and record.get('kind') == kind
                and record.get('target') == target and record.get('state') == 'acknowledged' for record in records.values()):
            raise PocketError('Esta permissão/pergunta já recebeu uma resposta confirmada. Atualize os recursos; nenhuma nova resposta foi enviada.')
        if any(record.get('sessionID') == binding['id'] and record.get('kind') == kind and record.get('target') == target
               and record.get('state') in ('attempted', 'uncertain') for record in records.values()):
            raise PocketError('Ação anterior sem confirmação. Confira execução/fila e marque o registro como conferido antes de iniciar outra. A API não oferece reenvio idempotente.')
        for identifier in list(records):
            if len(records) < 200:
                break
            if records[identifier].get('state') in ('acknowledged', 'reviewed'):
                del records[identifier]
        if len(records) >= 200:
            raise PocketError('Há muitas ações sem confirmação. Revise os registros; nenhuma foi descartada.')
        identifier = 'act_' + secrets.token_hex(16)
        records[identifier] = {'id': identifier, 'sessionID': binding['id'], 'title': binding.get('title') or 'Conversa', 'directory': binding.get('directory', ''),
                               'kind': kind, 'target': target, 'payload': copy.deepcopy(payload), 'state': 'attempted', 'created': time.time()}
        try:
            self.save()
        except Exception:
            records.pop(identifier, None); raise
        return identifier

    def mark_action(self, identifier, state, detail=''):
        if state not in ('acknowledged', 'uncertain', 'reviewed'):
            raise PocketError('Estado de ação inválido.')
        record = self.data.get('actions', {}).get(identifier)
        if not record:
            raise PocketError('Registro de ação não encontrado.')
        if record['state'] == 'acknowledged' and state == 'uncertain':
            return
        record.update(state=state, detail=str(detail)[:2000])


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class Gateway:
    demo = False

    def __init__(self, state, port=49375, legacy=None):
        self.state = Path(state)
        self.url = f'http://127.0.0.1:{int(port)}'
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        self.lock = threading.RLock()
        token_file = self.state / 'connection.json'
        self.token = None
        if token_file.exists():
            if token_file.stat().st_size > 4096:
                raise PocketError('Conexão local inválida.')
            self.token = json.loads(token_file.read_text()).get('token')
        if not self.token and legacy and Path(legacy).exists():
            if Path(legacy).stat().st_size <= 512:
                self.token = Path(legacy).read_text().strip()

    def request(self, path, method='GET', body=None, binary=False, version=None):
        parsed = urllib.parse.urlsplit(path)
        if not path.startswith(('/api/', '/phone/')) or parsed.scheme or parsed.netloc or '%' in parsed.path or '..' in parsed.path or '\\' in path:
            raise PocketError('Rota local inválida.')
        # Native desktop is not an unrestricted Core proxy. Existing gateway
        # performs its own authentication and mobile route authorization too.
        if parsed.path.startswith(('/phone/power/', '/phone/control/')) or '/voice/' in parsed.path:
            raise PocketError('Recurso físico/voz não disponível nesta versão desktop.')
        return self._request(path, method, body, binary, version)

    def _request(self, path, method, body=None, binary=False, version=None, raw_body=None, timeout=30, response_max=MAX_RESPONSE):
        with self.lock:
            token = self.token
        headers = {'Content-Type': 'application/json', 'Accept': 'application/json'}
        if token:
            headers['Authorization'] = 'Bearer ' + token
        if version is not None:
            if not isinstance(version, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', version):
                raise PocketError('Versão de arquivo inválida.')
            headers['If-Match'] = version
        data = json.dumps(body).encode() if body is not None else None
        if raw_body is not None:
            if body is not None or not isinstance(raw_body, bytes) or len(raw_body) > 4 * 1024 * 1024:
                raise PocketError('Bloco binário inválido.')
            data = raw_body; headers['Content-Type'] = 'application/octet-stream'
            headers['X-Chunk-SHA256'] = hashlib.sha256(data).hexdigest()
        if data and len(data) > 12 * 1024 * 1024:
            raise PocketError('Solicitação excede 12 MB.')
        req = urllib.request.Request(self.url + path, data=data, method=method, headers=headers)
        try:
            response = self.opener.open(req, timeout=timeout)
        except urllib.error.HTTPError as error:
            with error:
                raw = error.read(65536)
            try:
                payload = json.loads(raw)
                value = payload.get('error') or payload.get('message', '')
                text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
            except (ValueError, AttributeError):
                text = ''
            if error.code == 401:
                raise PocketError('Conexão não autorizada. Abra Ajustes → Parear computador.', status=401) from None
            if 'Scheduled tasks are disabled' in text:
                raise PocketError('Agendamentos estão desativados no OpenCode. Habilitar esse recurso experimental exige sua autorização; nenhuma configuração foi alterada pelo app.', status=error.code) from None
            raise PocketError(text[:2000] or f'Gateway recusou solicitação ({error.code}).', status=error.code) from None
        except (OSError, urllib.error.URLError):
            raise PocketError('Gateway indisponível em 127.0.0.1:49375. Verifique serviço KzL Agent no Linux.') from None
        with response:
            expected_hash = response.headers.get('X-Content-SHA256')
            expected_size = response.headers.get('Content-Length')
            raw = response.read(response_max + 1)
            if len(raw) > response_max:
                raise PocketError('Resposta excede limite local.')
        if binary:
            if not expected_hash or not re.fullmatch(r'[a-f0-9]{64}', expected_hash) or hashlib.sha256(raw).hexdigest() != expected_hash:
                raise PocketError('Integridade do download não confirmada. Nenhum arquivo foi salvo.')
            if expected_size is None or not expected_size.isdigit() or len(raw) != int(expected_size):
                raise PocketError('Download incompleto. Nenhum arquivo foi salvo.')
            return raw
        if not raw:
            return {}
        try:
            return json.loads(raw)
        except ValueError:
            raise PocketError('Gateway retornou resposta não JSON.') from None

    def upload_request(self, action, record=None, offset=None, chunk=None):
        # Only the inbox's documented resumable routes; never arbitrary upload URLs.
        if action not in ('prepare', 'progress', 'chunk', 'commit', 'verify'):
            raise PocketError('Ação de transferência inválida.')
        query = ''
        if action != 'prepare':
            from uploads import wire_parameters
            params = wire_parameters(record)
            if action == 'chunk':
                if not isinstance(offset, int) or isinstance(offset, bool) or not isinstance(chunk, bytes) or not 0 <= offset <= record['size'] or len(chunk) > 4*1024*1024 or offset + len(chunk) > record['size']:
                    raise PocketError('Bloco fora do tamanho declarado.')
                params['offset'] = offset
            query = '?' + urllib.parse.urlencode(params)
        return self._request('/phone/inbox/' + action + query, 'GET' if action in ('progress', 'verify') else 'POST',
                             raw_body=chunk if action == 'chunk' else None, timeout=120 if action in ('chunk', 'commit') else 30, response_max=16384)

    def pair(self, code):
        if not re.fullmatch(r'\d{6}', code):
            raise PocketError('Informe código de seis dígitos.')
        result = self._request('/pair', 'POST', {'code': code, 'name': 'KzL Agent · Linux'})
        token = result.get('token') if isinstance(result, dict) else None
        if not isinstance(token, str) or not 10 < len(token) < 512:
            raise PocketError('Pareamento não confirmado.')
        atomic_json(self.state / 'connection.json', {'token': token})
        with self.lock:
            self.token = token

    def voice_models(self):
        return self._request('/api/experimental/voice/models', 'GET')

    def voice_session(self, sdp, configuration, approved=False, cancelled=None):
        if approved is not True:
            raise PocketError('Chamada paga exige confirmação explícita nesta janela.')
        if cancelled is not None and cancelled.is_set():
            raise PocketError('Chamada cancelada antes do envio ao provedor.')
        if not isinstance(sdp, str) or not sdp.startswith('v=0') or len(sdp.encode()) > 128 * 1024:
            raise PocketError('Oferta de áudio inválida.')
        if not isinstance(configuration, dict) or configuration.get('model') != 'gpt-realtime-2.1' or configuration.get('type') != 'realtime':
            raise PocketError('Configuração de voz inválida.')
        body = {'model': 'gpt-realtime-2.1', 'session': configuration, 'transport': {'type': 'webrtc', 'sdp': sdp}}
        if len(json.dumps(body).encode()) > 256 * 1024:
            raise PocketError('Configuração de voz excede limite.')
        if cancelled is not None and cancelled.is_set():
            raise PocketError('Chamada cancelada antes do envio ao provedor.')
        result = self._request('/api/experimental/voice/session', 'POST', body)
        transport = (result.get('data') or {}).get('transport') or {}
        answer = transport.get('sdp')
        if transport.get('type') != 'webrtc' or not isinstance(answer, str) or not answer.startswith('v=0') or len(answer.encode()) > 128 * 1024:
            raise PocketError('Resposta de áudio não confirmada; não será repetida automaticamente.')
        return answer


def attachment(path):
    path = Path(path)
    size = path.stat().st_size
    if not path.is_file() or not 0 < size <= 4 * 1024 * 1024:
        raise PocketError('Use arquivo de até 4 MB.')
    data = path.read_bytes()
    if len(data) != size:
        raise PocketError('Arquivo mudou durante leitura. Selecione novamente.')
    mime = mimetypes.guess_type(path.name)[0] or 'text/plain'
    if mime not in ('image/png', 'image/jpeg', 'image/webp', 'image/gif', 'application/pdf'):
        try:
            data.decode('utf-8')
        except UnicodeDecodeError:
            raise PocketError('Formato não suportado. Use imagem, PDF ou texto UTF-8.') from None
        mime = 'text/plain'
    return {'name': path.name, 'size': size, 'uri': f'data:{mime};base64,' + base64.b64encode(data).decode()}


def prompt_content(draft):
    text = draft.get('text', '').strip()
    files = draft.get('files', [])
    if not text and not files:
        raise PocketError('Escreva uma mensagem ou anexe arquivo.')
    if len(files) > 5 or sum(f['size'] for f in files) > MAX_ATTACHMENTS:
        raise PocketError('Limite de cinco anexos e 8 MB no total.')
    return {'text': text, 'files': [{k: f[k] for k in ('name', 'uri')} for f in files]}


def prompt_payload(draft):
    content = prompt_content(draft)
    fingerprint = hashlib.sha256(json.dumps(content, sort_keys=True).encode()).hexdigest()
    if draft.get('fingerprint') != fingerprint or not draft.get('requestID'):
        draft['requestID'] = 'msg_' + secrets.token_hex(16)
        draft['fingerprint'] = fingerprint
    return {'id': draft['requestID'], **content}


def field_visible(field, answers):
    if field.get('hidden'):
        return False
    for condition in field.get('when') or []:
        same = answers.get(condition['key']) == condition.get('value')
        if condition['op'] not in ('eq', 'neq') or (same if condition['op'] == 'neq' else not same):
            return False
    return True


def form_answers(form, answers):
    result = {}
    for field in form['fields']:
        if not field_visible(field, answers):
            continue
        key = field['key']; kind = field['type']; value = answers.get(key)
        if value is None or value == '' or value == []:
            if field.get('required'):
                raise PocketError('Responda: ' + field.get('title', key))
            continue
        if kind == 'boolean':
            if not isinstance(value, bool):
                raise PocketError('Resposta precisa ser sim ou não.')
        elif kind in ('number', 'integer'):
            try:
                value = float(str(value).replace(',', '.'))
            except ValueError:
                raise PocketError('Informe número válido: ' + key) from None
            if not math.isfinite(value) or (kind == 'integer' and value != int(value)):
                raise PocketError('Informe número válido: ' + key)
            if kind == 'integer':
                value = int(value)
        elif kind == 'multiselect':
            if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
                raise PocketError('Selecione opções válidas: ' + key)
        elif kind == 'string':
            if not isinstance(value, str):
                raise PocketError('Informe texto: ' + key)
        else:
            raise PocketError('Tipo de pergunta não suportado: ' + kind)
        options = {o['value'] for o in field.get('options') or []}
        if options and not field.get('custom') and kind in ('string', 'multiselect'):
            if any(v not in options for v in (value if kind == 'multiselect' else [value])):
                raise PocketError('Selecione uma das opções: ' + key)
        result[key] = value
    return result


def experimental_session_path(sid, suffix):
    if not re.fullmatch(r'ses[A-Za-z0-9_-]+', sid) or suffix not in ('skill', 'terminal/read'):
        raise PocketError('Recurso de conversa inválido.')
    return '/api/experimental/session/' + sid + '/' + suffix


def artifacts(message, directory, links=None):
    """Only local Markdown references. Never fetch or execute generated links."""
    text = message.get('text') or '\n'.join(p.get('text') or '' for p in message.get('content') or [] if p.get('type') == 'text')
    found = {}
    if not isinstance(directory, str) or not directory.startswith('/'):
        return []
    references = links if links is not None else (match.groups() for match in re.finditer(r'\[([^\]\n]{1,200})\]\(([^\s)]+)\)', text[:500000]))
    for name, target in references:
        try:
            url = urllib.parse.urlsplit(target)
        except ValueError:
            continue
        if url.scheme not in ('', 'file') or url.netloc or url.query or url.fragment:
            continue
        path = urllib.parse.unquote(url.path)
        try:
            path.encode('utf-8', 'strict')
        except UnicodeEncodeError:
            continue
        if not path or '\\' in path or any(ord(c) < 32 or ord(c) == 127 for c in path) or '..' in path.split('/'):
            continue
        absolute = PurePosixPath(path) if path.startswith('/') else PurePosixPath(directory) / path
        if str(absolute) == '/' or len(str(absolute)) > 4096:
            continue
        found[str(absolute)] = {'name': absolute.name, 'label': name, 'path': str(absolute)}
        if len(found) >= 20:
            break
    return list(found.values())


def search_loaded_messages(messages, query):
    if not isinstance(query, str) or len(query) > 256:
        raise PocketError('Busca limitada a 256 caracteres.')
    query = query.strip()
    if not query:
        return []
    pattern = re.compile(re.escape(query), re.IGNORECASE)
    found = []; seen = set()
    for message in messages:
        if message.get('type') not in ('user', 'assistant') or message.get('id') in seen:
            continue
        seen.add(message.get('id'))
        text = message.get('text')
        if not isinstance(text, str):
            text = '\n'.join(p['text'] for p in message.get('content', []) if isinstance(p, dict) and p.get('type') == 'text' and isinstance(p.get('text'), str))
        match = pattern.search(text)
        if match:
            start = max(0, match.start()-60); end = min(len(text), match.end()+120)
            found.append({'id': message['id'], 'role': message['type'], 'preview': ('…' if start else '') + text[start:end] + ('…' if end < len(text) else '')})
        if len(found) >= 100:
            break
    return found


def tool_state_label(tool):
    state = tool.get('state')
    status = state.get('status') if isinstance(state, dict) else None
    return {'running': 'Em execução', 'streaming': 'Preparando entrada', 'completed': 'Concluída', 'error': 'Falhou'}.get(status, 'Estado não confirmado')


def tool_progress(tools):
    counts = {}
    for tool in tools:
        state = tool_state_label(tool); counts[state] = counts.get(state, 0)+1
    return 'Ferramentas · ' + ' · '.join(f'{state}: {counts[state]}' for state in
        ('Em execução', 'Preparando entrada', 'Falhou', 'Estado não confirmado', 'Concluída') if counts.get(state))


def conversation_export(session, messages):
    """Literal UTF-8 transcript of loaded text only; never serialize credentials/files."""
    lines = ['KzL Agent · conversa carregada', str(session.get('title') or 'Conversa'),
             'Conversa: ' + str(session.get('id', '')), '',
             'Cópia parcial: somente mensagens carregadas no momento da exportação.',
             'Rascunho, conteúdo de anexos e detalhes de ferramentas não incluídos.', '']
    seen = set(); total = sum(len(line.encode('utf-8'))+1 for line in lines)
    if total > 8*1024*1024:
        raise PocketError('Exportação excede limite de 8 MB.')
    for message in messages:
        role = message.get('type')
        if role not in ('user', 'assistant') or message.get('id') in seen:
            continue
        seen.add(message.get('id'))
        text = message.get('text')
        if not isinstance(text, str):
            text = '\n'.join(part['text'] for part in message.get('content', []) if isinstance(part, dict) and part.get('type') == 'text' and isinstance(part.get('text'), str))
        entry = ['── ' + ('Você' if role == 'user' else 'Assistente') + ' ──', text, '']
        total += sum(len(line.encode('utf-8'))+1 for line in entry)
        if total > 8*1024*1024:
            raise PocketError('Exportação excede limite de 8 MB. Nenhum texto foi truncado; escolha menos mensagens.')
        lines.extend(entry)
    return ('\n'.join(lines)+'\n').encode('utf-8')


def save_download(destination, data, overwrite=False):
    """Atomic publication; failed saves never truncate a previous file."""
    destination = Path(destination)
    if destination.is_symlink():
        raise PocketError('Destino é um link simbólico. Escolha outro arquivo.')
    if destination.exists() and not overwrite:
        raise PocketError('Arquivo já existe. Confirme substituição antes de salvar.')
    temporary = destination.with_name('.pocket-download-' + secrets.token_hex(12))
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, 'wb') as output:
            output.write(data); output.flush(); os.fsync(output.fileno())
        if overwrite:
            os.replace(temporary, destination)
        else:
            os.link(temporary, destination, follow_symlinks=False)
    finally:
        temporary.unlink(missing_ok=True)


def schedule_payload(sid, prompt, when, now=None):
    if not re.fullmatch(r'ses[A-Za-z0-9_-]+', sid):
        raise PocketError('Conversa inválida.')
    if not isinstance(prompt, str) or not 1 <= len(prompt.strip()) <= 32000:
        raise PocketError('Informe tarefa com até 32.000 caracteres.')
    try:
        value = datetime.fromisoformat(when.replace('Z', '+00:00'))
    except (ValueError, AttributeError):
        raise PocketError('Data inválida.') from None
    if value.tzinfo is None or value.timestamp() <= (time.time() if now is None else now):
        raise PocketError('Escolha data futura com fuso horário explícito.')
    return {'sessionID': sid, 'prompt': prompt.strip(), 'when': {'at': value.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')}}


class DemoGateway:
    """No network, credentials, microphone or provider calls."""
    demo = True

    def __init__(self):
        model = {'providerID': 'openai', 'id': 'gpt-6.1-terra-fast'}
        self.sessions = [{'id': 'ses_demo', 'title': 'Uma ideia, do começo ao fim', 'agent': 'build', 'model': model, 'location': {'directory': '/projetos/meu-app'}, 'metadata': {}, 'time': {'created': 1, 'updated': 2}}, {'id': 'ses_kzl', 'title': 'Agente KzL', 'agent': 'build', 'location': {'directory': '/projetos/meu-app'}, 'metadata': {'kzlAgent': True}}]
        self.messages = {'ses_demo': [{'id': 'msg_user', 'type': 'user', 'text': 'Vamos criar uma página para meu projeto? Quero algo simples, sem cara de template.', 'time': {'created': 1}}, {'id': 'msg_assistant', 'type': 'assistant', 'text': 'Sim. Começaria com uma ideia clara, bastante espaço e uma tipografia que tenha a cara do projeto.\n\n**Minha proposta**\n\n• Uma abertura direta, sem slogans genéricos.\n• Conteúdo organizado em poucas seções.\n• Uma ação principal, fácil de encontrar.\n\nPodemos explorar o visual antes de mexer nos arquivos.', 'time': {'created': 2, 'completed': 3}}], 'ses_kzl': []}
        self.permissions = {}
        self.progress = {}
        self.accepted = set()
        self.schedules = []
        self.lock = threading.RLock()

    def request(self, path, method='GET', body=None, binary=False, version=None):
        with self.lock:
            result = self._request(path, method, body or {}, binary)
            return result if binary else json.loads(json.dumps(result))

    def voice_models(self):
        return {'data': {'models': []}}

    def voice_session(self, sdp, configuration, approved=False, cancelled=None):
        raise PocketError('Demonstração nunca cria chamada paga ou envia microfone à rede.')

    def _request(self, path, method, body, binary):
        url = urllib.parse.urlsplit(path)
        route, query = url.path, urllib.parse.parse_qs(url.query)
        if route == '/phone/catalog':
            return {'models': [{'providerID': 'openai', 'id': 'gpt-6.1-terra-fast', 'name': 'Terra Fast', 'variants': [{'id': 'high'}]}]}
        if route == '/api/info':
            return {'demo': True}
        if route == '/phone/status':
            return {'demo': True, 'battery': {'available': True, 'percentage': 82}, 'computer': 'Demonstração local'}
        if route == '/phone/kzl/ensure':
            return {'data': self.sessions[-1]}
        if route == '/phone/kzl/tasks':
            return {'tasks': []}
        if route == '/phone/files/roots':
            return {'roots': [{'id': 'home', 'name': 'Arquivos de demonstração'}]}
        if route == '/phone/files/list':
            return {'path': '', 'parent': None, 'entries': [{'name': 'exemplo.txt', 'path': 'exemplo.txt', 'kind': 'file', 'readable': True}]}
        if route == '/phone/files/context':
            return {'root': 'home', 'path': ''}
        if route == '/phone/files/download':
            return b'Arquivo ficticio: nenhum arquivo real foi acessado.\n'
        if route == '/api/experimental/schedule':
            if method == 'POST':
                item = {'id': 'schedule_' + secrets.token_hex(8), 'name': body['prompt'], 'status': 'active', 'runCount': 0, 'nextDueAt': datetime.fromisoformat(body['when']['at'].replace('Z', '+00:00')).timestamp() * 1000}
                self.schedules.append(item); return {'data': item}
            return {'data': self.schedules}
        if route.startswith('/api/experimental/schedule/'):
            sid = route.split('/')[4]
            item = next(s for s in self.schedules if s['id'] == sid)
            if method == 'DELETE':
                self.schedules.remove(item)
            else:
                item['status'] = 'paused' if route.endswith('/pause') else 'active'
            return {}
        if route in ('/api/command', '/api/skill'):
            return {'data': []}
        if route == '/api/session':
            if method == 'POST':
                session = {'id': 'ses_' + secrets.token_hex(8), 'title': 'Nova conversa', 'agent': 'build', 'location': {'directory': body.get('location', {}).get('directory', '/projetos/meu-app')}, 'metadata': {}, 'time': {'created': time.time(), 'updated': time.time()}}
                self.sessions.insert(0, session); self.messages[session['id']] = []
                return {'data': session}
            term = query.get('search', [''])[0].casefold()
            return {'data': [s for s in self.sessions if not (s.get('metadata') or {}).get('kzlAgent') and term in s['title'].casefold()]}
        parts = route.split('/')
        sid = parts[3] if len(parts) > 3 else ''
        session = next((s for s in self.sessions if s['id'] == sid), None)
        if not session:
            return {'data': []}
        action = parts[4] if len(parts) > 4 else ''
        if not action:
            if method == 'PATCH':
                session['title'] = body['title']
            return {'data': session}
        if action == 'message':
            if sid in self.progress:
                item, started = self.progress[sid]
                text = 'Demonstração funcional. Esta resposta aparece progressivamente, sem acessar nenhum provedor.\n\nConecte o computador em Ajustes para trabalhar com conversas e ferramentas reais.'
                item['text'] = text[:int((time.monotonic() - started) * 120)]
                if len(item['text']) == len(text):
                    item['time']['completed'] = time.time(); del self.progress[sid]
            return {'data': self.messages[sid]}
        if action == 'permission':
            if method == 'POST':
                self.permissions[sid] = []
                return {}
            return {'data': self.permissions.get(sid, [])}
        if action == 'form' and method == 'POST':
            self.last_answer = body['answer']; return {}
        if action in ('form', 'diff', 'inbox'):
            return {'data': []}
        if action == 'prompt':
            if body['id'] in self.accepted:
                return {'accepted': True}
            self.accepted.add(body['id'])
            self.messages[sid].append({'id': body['id'], 'type': 'user', 'text': body['text'], 'files': body['files'], 'time': {'created': time.time()}})
            item = {'id': 'msg_' + secrets.token_hex(8), 'type': 'assistant', 'text': '', 'time': {'created': time.time() + 0.001}}
            self.messages[sid].append(item); self.progress[sid] = (item, time.monotonic())
            return {'accepted': True}
        if action == 'interrupt':
            item = self.progress.pop(sid, None)
            if item:
                item[0]['time']['completed'] = time.time()
            return {}
        if action in ('model', 'agent'):
            session[action] = body[action]
        return {}
