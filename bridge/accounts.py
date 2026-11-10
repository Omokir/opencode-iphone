"""OpenCode-owned OpenAI authentication; no keys/tokens in gateway state/logs.

Never proxies credential reads or raw authentication errors. Operation receipts
contain only public IDs and state. Writes are reserved durably and never retried.
"""
import json
from contextlib import contextmanager
import os
from pathlib import Path
import re
import secrets
import sqlite3
import stat
import threading
import urllib.parse

LOCK = threading.Lock()


class AccountError(Exception):
    def __init__(self, status, message):
        self.status = status
        self.body = {'error': message}


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,160}', value):
        raise AccountError(400, 'Identificador inválido.')
    return value


class OpenAIAccounts:
    def __init__(self, root, request):
        self.root = Path(root)
        self.request = request

    @contextmanager
    def _db(self):
        self.root.mkdir(parents=True, mode=0o700, exist_ok=True)
        info = self.root.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise AccountError(503, 'Registro de autenticação indisponível.')
        path = self.root / 'operations.sqlite'
        if path.exists() or path.is_symlink():
            info = path.lstat()
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_nlink != 1 or info.st_mode & 0o077:
                raise AccountError(503, 'Registro de autenticação indisponível.')
        else:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
            os.close(fd)
        db = sqlite3.connect(path)
        try:
            db.row_factory = sqlite3.Row
            db.execute('CREATE TABLE IF NOT EXISTS operations (id TEXT PRIMARY KEY, owner TEXT, kind TEXT, directory TEXT, integration TEXT, reference TEXT, state TEXT)')
            if 'complete_sent' not in {row[1] for row in db.execute('PRAGMA table_info(operations)')}:
                db.execute('ALTER TABLE operations ADD COLUMN complete_sent INTEGER NOT NULL DEFAULT 0')
            with db:
                yield db
        finally:
            db.close()

    def _json(self, method, path, payload=None):
        try:
            code, raw = self.request(method, path, json.dumps(payload).encode() if payload is not None else None)
            if code not in (200, 204):
                raise ValueError('Upstream rejected request')
            return json.loads(raw)['data'] if raw else None
        except Exception:
            raise AccountError(503, 'OpenCode não confirmou operação. Não repita automaticamente.') from None

    def _integration(self, directory):
        if not isinstance(directory, str) or not directory.startswith('/') or len(directory) > 4096 or '\x00' in directory:
            raise AccountError(400, 'Projeto inválido.')
        query = '?' + urllib.parse.urlencode({'location[directory]': directory})
        provider = self._json('GET', '/api/provider/openai' + query)
        integration = identifier(provider.get('integrationID'))
        value = self._json('GET', '/api/integration/' + urllib.parse.quote(integration, safe='') + query)
        if value.get('id') != integration:
            raise AccountError(503, 'Integração OpenAI não confirmada.')
        return integration, query, value

    def inventory(self, directory):
        integration, _, value = self._integration(directory)
        methods = []
        for method in value.get('methods', [])[:40]:
            if method.get('type') not in ('oauth', 'key'):
                continue
            row = {'type': method['type'], 'label': str(method.get('label', method['type']))[:160],
                   'requiresFields': bool(method.get('form'))}
            if method['type'] == 'oauth':
                row['id'] = identifier(method.get('id'))
            methods.append(row)
        connections = [{'method': row.get('method', row.get('type')), 'needsAuth': bool(row.get('status'))}
                       for row in value.get('connections', [])[:100]]
        return {'integrationID': integration, 'directory': directory, 'methods': methods, 'connections': connections,
                'billingNote': 'API é cobrada por uso; ChatGPT usa limites da assinatura compatível. Nenhuma chamada de modelo é iniciada ao conectar.'}

    def _reserve(self, request_id, owner, kind, directory, integration, reference):
        identifier(request_id)
        with LOCK, self._db() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT 1 FROM operations WHERE id=? OR (owner=? AND state IN (\'attempted\',\'pending\'))', (request_id, owner)).fetchone():
                raise AccountError(409, 'Há tentativa registrada ou incerta. Consulte seu estado; nada foi reenviado.')
            if db.execute('SELECT count(*) FROM operations').fetchone()[0] >= 1000:
                raise AccountError(409, 'Limite do histórico de autenticação atingido.')
            db.execute('INSERT INTO operations (id,owner,kind,directory,integration,reference,state) VALUES (?,?,?,?,?,?,?)',
                       (request_id, owner, kind, directory, integration, reference, 'attempted'))

    def _update(self, request_id, state, reference=None):
        with LOCK, self._db() as db:
            db.execute('UPDATE operations SET state=?, reference=coalesce(?,reference) WHERE id=?', (state, reference, request_id))

    def add_key(self, payload, owner):
        if not isinstance(payload, dict) or set(payload) != {'requestID', 'directory', 'key'}:
            raise AccountError(400, 'Campos de autenticação inválidos.')
        key = payload['key']
        if not isinstance(key, str) or not 8 <= len(key) <= 4096 or any(c.isspace() or not c.isprintable() for c in key):
            raise AccountError(400, 'Chave inválida.')
        integration, _, value = self._integration(payload['directory'])
        if not any(m.get('type') == 'key' and not m.get('form') for m in value.get('methods', [])):
            raise AccountError(400, 'Conexão por chave simples não disponível nesta integração.')
        reference = 'kzl_api_' + secrets.token_hex(16)
        self._reserve(payload['requestID'], owner, 'key', payload['directory'], integration, reference)
        result = self._json('POST', '/api/credential', {'id': reference, 'integrationID': integration,
            'label': 'KzL Center API', 'value': {'type': 'key', 'key': key}, 'activate': False})
        # Raw Credential.Entry contains secrets: discard it after projection.
        if result.get('id') != reference or type(result.get('active')) is not bool:
            raise AccountError(503, 'Credencial não confirmada. Consulte estado antes de outra tentativa.')
        self._update(payload['requestID'], 'complete')
        return {'requestID': payload['requestID'], 'status': 'stored', 'active': result['active'], 'credentialID': reference}

    def start_oauth(self, payload, owner):
        if not isinstance(payload, dict) or set(payload) != {'requestID', 'directory', 'methodID'}:
            raise AccountError(400, 'Campos de autenticação inválidos.')
        integration, query, value = self._integration(payload['directory'])
        method = identifier(payload['methodID'])
        if not any(m.get('type') == 'oauth' and m.get('id') == method and not m.get('form') for m in value.get('methods', [])):
            raise AccountError(400, 'Método oficial sem campos adicionais não disponível.')
        self._reserve(payload['requestID'], owner, 'oauth', payload['directory'], integration, None)
        result = self._json('POST', '/api/integration/' + urllib.parse.quote(integration, safe='') + '/connect/oauth' + query,
                            {'methodID': method, 'label': 'KzL Center ChatGPT'})
        attempt = identifier(result.get('attemptID'))
        self._update(payload['requestID'], 'pending', attempt)
        url = result.get('url', '')
        parts = urllib.parse.urlsplit(url)
        if parts.scheme != 'https' or parts.hostname not in ('auth.openai.com', 'auth0.openai.com', 'chatgpt.com') or parts.username or parts.password or parts.port not in (None, 443):
            raise AccountError(503, 'URL de autorização não reconhecida; abra /connect no OpenCode.')
        if result.get('mode') not in ('auto', 'code') or len(url) > 8192:
            raise AccountError(503, 'Modo de autenticação não suportado.')
        return {'requestID': payload['requestID'], 'status': 'pending', 'url': url, 'mode': result['mode'],
                'paste': bool(result.get('paste')), 'instructions': str(result.get('instructions', ''))[:2000]}

    def status(self, request_id, owner):
        identifier(request_id)
        with LOCK, self._db() as db:
            row = db.execute('SELECT * FROM operations WHERE id=? AND owner=?', (request_id, owner)).fetchone()
        if row is None:
            raise AccountError(404, 'Tentativa não encontrada para este aparelho.')
        state = row['state']
        if state in ('attempted', 'pending'):
            query = '?' + urllib.parse.urlencode({'location[directory]': row['directory']})
            if row['kind'] == 'key':
                value = self._json('GET', '/api/integration/' + urllib.parse.quote(row['integration'], safe='') + query)
                if any(item.get('id') == row['reference'] for item in value.get('connections', [])):
                    state = 'complete'
            elif row['reference']:
                value = self._json('GET', '/api/integration/' + urllib.parse.quote(row['integration'], safe='') +
                                   '/connect/oauth/' + urllib.parse.quote(row['reference'], safe='') + query)
                if value.get('status') in ('pending', 'complete', 'failed', 'expired'):
                    state = value['status']
            self._update(request_id, state)
        return {'requestID': request_id, 'status': 'uncertain' if state == 'attempted' else state}

    def complete_oauth(self, payload, owner):
        if not isinstance(payload, dict) or set(payload) != {'requestID', 'code'} or not isinstance(payload['code'], str) or not 1 <= len(payload['code']) <= 8192 or '\x00' in payload['code']:
            raise AccountError(400, 'Código ou URL de conclusão inválido.')
        identifier(payload['requestID'])
        with LOCK, self._db() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM operations WHERE id=? AND owner=?', (payload['requestID'], owner)).fetchone()
            if not row or row['kind'] != 'oauth' or not row['reference']:
                raise AccountError(404, 'Tentativa OAuth não encontrada.')
            if row['complete_sent'] or row['state'] != 'pending':
                raise AccountError(409, 'Conclusão já enviada ou tentativa encerrada. Consulte estado; não repita.')
            db.execute('UPDATE operations SET complete_sent=1 WHERE id=?', (row['id'],))
        query = '?' + urllib.parse.urlencode({'location[directory]': row['directory']})
        self._json('POST', '/api/integration/' + urllib.parse.quote(row['integration'], safe='') +
                   '/connect/oauth/' + urllib.parse.quote(row['reference'], safe='') + '/complete' + query, {'code': payload['code']})
        return self.status(row['id'], owner)
