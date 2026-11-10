"""Secret-free authentication receipts; HTTP writes are never replayed."""
import secrets
import json
import os
import stat
import urllib.parse
import re
from backend import PocketError, atomic_json


class AccountClient:
    def __init__(self, gateway, store, directory):
        self.gateway = gateway
        self.store = store
        self.directory = directory
        self.file = store.root / 'openai-auth.json'

    @property
    def pending(self):
        try:
            fd = os.open(self.file, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        except FileNotFoundError:
            return None
        with os.fdopen(fd, 'rb') as file:
            info = os.fstat(file.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_mode & 0o077 or info.st_size > 8192:
                raise PocketError('Registro local de autenticação inseguro; preservado.')
            try:
                value = json.load(file)
            except ValueError:
                raise PocketError('Registro local inválido; escritas bloqueadas.') from None
        if not isinstance(value, dict) or set(value) != {'requestID', 'kind', 'directory'} or not all(isinstance(v, str) for v in value.values()):
            raise PocketError('Registro local inválido; escritas bloqueadas.')
        return value

    def inventory(self):
        return self.gateway.request('/phone/openai?' + urllib.parse.urlencode({'directory': self.directory}))

    def _write_intent(self, record):
        self.file.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        fd = os.open(self.file, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'w') as file:
            json.dump(record, file); file.flush(); os.fsync(file.fileno())

    def _begin(self, kind):
        if self.pending:
            raise PocketError('Há autenticação pendente. Consulte resultado; não inicie outra tentativa.')
        record = {'requestID': 'auth_' + secrets.token_hex(16), 'kind': kind, 'directory': self.directory}
        try:
            self._write_intent(record)
        except Exception:
            raise PocketError('Não foi possível salvar intenção local; nada enviado.') from None
        return record

    def _finish(self, request_id):
        if not self.pending or self.pending['requestID'] != request_id:
            raise PocketError('Registro local mudou; nenhuma tentativa liberada.')
        try:
            self.file.unlink()
        except Exception:
            raise PocketError('Resultado recebido, mas registro local não foi salvo. Consulte novamente.') from None

    def _write(self, kind, fields):
        record = self._begin(kind)
        payload = {'requestID': record['requestID'], 'directory': self.directory, **fields}
        try:
            result = self.gateway.request('/phone/openai/' + kind, 'POST', payload)
        except PocketError as error:
            if error.status == 400:
                self._finish(record['requestID'])  # Gateway validation rejected before admission.
            raise PocketError('Solicitação recusada ou não confirmada. Consulte estado antes de outra tentativa.') from None
        except Exception:
            raise PocketError('Autenticação não confirmada. Consulte resultado; nada será reenviado.') from None
        if result.get('requestID') != record['requestID']:
            raise PocketError('Resposta de outra tentativa recusada.')
        if result.get('status') == 'stored':
            self._finish(record['requestID'])
        if kind == 'oauth':
            parts = urllib.parse.urlsplit(result.get('url', ''))
            if parts.scheme != 'https' or parts.hostname not in ('auth.openai.com', 'auth0.openai.com', 'chatgpt.com') or parts.username or parts.password or parts.port not in (None, 443):
                raise PocketError('URL de autorização recusada. Consulte tentativa no OpenCode.')
        return result

    def add_key(self, key):
        if not isinstance(key, str) or not 8 <= len(key) <= 4096 or any(c.isspace() or not c.isprintable() for c in key):
            raise PocketError('Formato de chave inválido. Nada enviado.')
        return self._write('key', {'key': key})

    def start_oauth(self, method_id):
        if not isinstance(method_id, str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,160}', method_id):
            raise PocketError('Método OAuth inválido.')
        return self._write('oauth', {'methodID': method_id})

    def complete_oauth(self, code):
        if not isinstance(code, str) or not 1 <= len(code) <= 8192 or '\x00' in code:
            raise PocketError('Código OAuth inválido. Nada enviado.')
        record = self.pending
        if not record or record['kind'] != 'oauth':
            raise PocketError('Conclusão ausente ou já enviada. Consulte estado.')
        # Never persist the code/redirect URL; only fence its one explicit send.
        atomic_json(self.file, dict(record, kind='oauth-completing'))
        try:
            result = self.gateway.request('/phone/openai/complete', 'POST', {'requestID': record['requestID'], 'code': code})
        except Exception:
            raise PocketError('Conclusão não confirmada. Consulte estado; não repita código.') from None
        if result.get('requestID') != record['requestID']:
            raise PocketError('Resposta de outra tentativa recusada.')
        if result.get('status') in ('complete', 'failed', 'expired'):
            self._finish(record['requestID'])
        return result

    def status(self):
        if not self.pending:
            return {'status': 'none'}
        record = self.pending
        result = self.gateway.request('/phone/openai/operation?' + urllib.parse.urlencode({'id': record['requestID']}))
        if result.get('requestID') != record['requestID']:
            raise PocketError('Resposta de outra tentativa recusada.')
        if result.get('status') in ('complete', 'failed', 'expired'):
            self._finish(record['requestID'])
        return result
