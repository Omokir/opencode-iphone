"""Private resumable-upload journal; originals are never moved or removed.

Explicit start/resume only. Reconciliation reads a committed receipt before
querying durable offset; transport failures never cause automatic write retries.
"""
import copy
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import threading
import time
import uuid

from backend import PocketError, atomic_json

MAX_FILE = 1024 ** 4
MAX_CHUNK = 4 * 1024 * 1024


class UploadPaused(PocketError):
    pass


def identity(info):
    return [info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns]


def safe_name(name):
    try:
        name.encode('utf-8', 'strict')
    except UnicodeEncodeError:
        raise PocketError('Nome de arquivo não é UTF-8 válido.') from None
    lower = name.casefold()
    if (not name or name.startswith('.') or '/' in name or '\\' in name or any(ord(c) < 32 or ord(c) == 127 for c in name)
            or Path(lower).suffix in ('.pem', '.key', '.p12', '.pfx', '.kdbx', '.mobileprovision')
            or lower in ('id_rsa', 'id_ed25519', 'auth.json')
            or lower.endswith('.json') and any(word in lower for word in ('credential', 'secret', 'token'))):
        raise PocketError('Nome protegido ou inválido para a caixa de entrada do KzL Agent.')
    return name


def remote_name(name):
    safe_name(name)
    if len(name.encode()) <= 200:
        return name
    suffix = Path(name).suffix.encode()[:20].decode('utf-8', 'ignore')
    return name.encode()[:160].decode('utf-8', 'ignore') + '-' + hashlib.sha256(name.encode()).hexdigest()[:8] + suffix


def wire_parameters(record):
    if not isinstance(record, dict):
        raise PocketError('Registro de transferência inválido.')
    try:
        identifier = str(uuid.UUID(record['id']))
        path = record['destination']; size = record['size']; digest = record['sha256']
    except (KeyError, ValueError, AttributeError, TypeError):
        raise PocketError('Registro de transferência inválido.') from None
    if identifier != record['id'] or not isinstance(size, int) or isinstance(size, bool) or not 0 <= size <= MAX_FILE or not isinstance(digest, str) or not re.fullmatch(r'[0-9a-f]{64}', digest):
        raise PocketError('Identidade ou checksum de transferência inválido.')
    if not isinstance(path, str) or len(path) > 4096 or path.startswith('/') or '\\' in path or any(p in ('', '.', '..') or p.startswith('.') for p in path.split('/')) or any(ord(c) < 32 for c in path):
        raise PocketError('Destino de transferência inválido.')
    if not Path(path).name.startswith(identifier + '-'):
        raise PocketError('Destino não corresponde à identidade do envio.')
    safe_name(Path(path).name)
    return {'path': path, 'id': identifier, 'size': size, 'sha256': digest}


class UploadManager:
    def __init__(self, root, gateway):
        self.root = Path(root) / 'transfers'; self.gateway = gateway
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.lock = threading.RLock(); self.active = {}; self.shutdown = False
        self.read = os.read
        self.cache = self.journal()

    def journal(self, change=None):
        with self.lock:
            fd = os.open(self.root / 'journal.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX)
                path = self.root / 'uploads.json'
                value = {}
                if path.exists():
                    if path.is_symlink() or path.stat().st_size > 2 * 1024 * 1024:
                        raise PocketError('Registro de transferências inválido; arquivo preservado.')
                    value = json.loads(path.read_text())
                    if not isinstance(value, dict) or len(value) > 200:
                        raise PocketError('Registro de transferências inválido; arquivo preservado.')
                if change:
                    change(value)
                    if len(value) > 200:
                        raise PocketError('Limite de 200 transferências. Remova registros antigos concluídos.')
                    if len(json.dumps(value, ensure_ascii=False).encode()) > 2*1024*1024:
                        raise PocketError('Registro de transferências cheio. Remova registros concluídos.')
                    atomic_json(path, value)
                self.cache = copy.deepcopy(value)
                return copy.deepcopy(value)
            finally:
                os.close(fd)

    def list(self):
        with self.lock:
            values = copy.deepcopy(self.cache)
        result = []
        for identifier, record in values.items():
            item = copy.deepcopy(record)
            item['active'] = identifier in self.active
            if not item['active'] and item.get('state') in ('uploading', 'committing', 'checking'):
                item['state'] = 'uncertain'
                item['message'] = 'Processo anterior interrompido. Retome para consultar o notebook antes de enviar.'
            result.append(item)
        return sorted(result, key=lambda row: row.get('created', 0), reverse=True)

    def get(self, identifier):
        if not isinstance(identifier, str) or str(uuid.UUID(identifier)) != identifier:
            raise PocketError('Identificador de transferência inválido.')
        result = self.journal().get(identifier)
        if not isinstance(result, dict):
            raise PocketError('Transferência não encontrada.')
        return result

    def update(self, identifier, **changes):
        def change(value):
            if identifier not in value:
                raise PocketError('Transferência não encontrada.')
            value[identifier].update(changes, updated=time.time())
        self.journal(change)

    def source(self, record):
        try:
            fd = os.open(record['source'], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        except OSError:
            raise PocketError('Arquivo de origem indisponível ou é um link. Original não foi removido.') from None
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or identity(info) != record['identity']:
            os.close(fd)
            raise PocketError('Arquivo de origem mudou. Inicie outro envio para a nova versão; parcial anterior preservado.')
        return fd

    def add(self, source, cancelled=None):
        if self.gateway.demo:
            raise PocketError('Envio real não é permitido na demonstração.')
        if self.shutdown:
            raise UploadPaused('Aplicativo encerrando. Nenhum envio iniciado.')
        path = Path(source).absolute(); safe_name(path.name)
        try:
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        except OSError:
            raise PocketError('Selecione arquivo regular, não um link.') from None
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or not 0 <= info.st_size <= MAX_FILE:
                raise PocketError('Use arquivo regular de até 1 TiB.')
            digest = hashlib.sha256()
            remaining = info.st_size
            while remaining:
                if self.shutdown or (cancelled and cancelled.is_set()):
                    raise UploadPaused('Preparação pausada. Original preservado.')
                count = min(remaining, 1024*1024); chunk = self.read(fd, count)
                if not chunk:
                    raise PocketError('Arquivo mudou durante preparação. Nenhum envio iniciado.')
                digest.update(chunk); remaining -= len(chunk)
            if identity(info) != identity(os.fstat(fd)):
                raise PocketError('Arquivo mudou durante preparação. Nenhum envio iniciado.')
        finally:
            os.close(fd)
        if self.shutdown or (cancelled and cancelled.is_set()):
            raise UploadPaused('Preparação pausada. Original preservado.')
        identifier = str(uuid.uuid4())
        record = {'id': identifier, 'source': str(path), 'name': path.name, 'identity': identity(info), 'size': info.st_size, 'sha256': digest.hexdigest(),
                  'destination': None, 'offset': 0, 'state': 'ready', 'created': time.time(), 'message': 'Pronto; original será preservado.', 'gateway': self.gateway.url}
        self.journal(lambda value: value.update({identifier: record}))
        return identifier

    def pause(self, identifier):
        with self.lock:
            event = self.active.get(identifier)
            if event:
                event.set()

    def close(self):
        with self.lock:
            self.shutdown = True
            for event in self.active.values():
                event.set()

    def forget(self, identifier):
        if identifier in self.active:
            raise PocketError('Pause o envio antes de remover seu registro.')
        def change(value):
            item = value.get(identifier)
            if not item or item.get('state') != 'completed':
                raise PocketError('Somente registros concluídos podem ser removidos. Arquivos não serão apagados.')
            del value[identifier]
        self.journal(change)

    @staticmethod
    def progress(value, size):
        if not isinstance(value, dict):
            raise PocketError('Posição remota inválida.')
        offset = value.get('offset'); chunk = value.get('chunkBytes')
        if not isinstance(offset, int) or isinstance(offset, bool) or not 0 <= offset <= size or not isinstance(chunk, int) or isinstance(chunk, bool) or not 1 <= chunk <= MAX_CHUNK:
            raise PocketError('Posição ou limite de bloco inválido; envio interrompido.')
        return offset, chunk

    @staticmethod
    def receipt(value, record):
        if (not isinstance(value, dict) or value.get('uploadID') != record['id'] or value.get('root') != 'home' or value.get('path') != record['destination']
                or not isinstance(value.get('size'), int) or isinstance(value['size'], bool) or value['size'] != record['size'] or value.get('sha256') != record['sha256']
                or not isinstance(value.get('version'), str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', value['version'])):
            raise PocketError('Recibo não corresponde a este envio. Original preservado; confira o notebook.')
        return value

    def run(self, identifier, notify=lambda offset, size: None, cancelled=None):
        if self.gateway.demo:
            raise PocketError('Envio real não é permitido na demonstração.')
        with self.lock:
            if identifier in self.active:
                raise PocketError('Este envio já está em andamento.')
            if self.shutdown:
                raise UploadPaused('Aplicativo encerrando; envio não iniciado.')
            event = cancelled if cancelled is not None else threading.Event(); self.active[identifier] = event
        lease = None; source = None; leased = False
        def check():
            if event.is_set() or self.shutdown:
                raise UploadPaused('Pausado. Bloco em andamento pode ter terminado; retomada consultará posição durável.')
        try:
            record = self.get(identifier)
            lease = os.open(self.root / (identifier + '.lock'), os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
            try:
                fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise PocketError('Envio em andamento em outro processo. Aguarde antes de retomar.') from None
            leased = True
            if record.get('gateway') != self.gateway.url:
                raise PocketError('Computador de destino mudou. Não retomado automaticamente.')
            check(); self.update(identifier, state='checking', message='Consultando confirmação no notebook…')
            if record.get('destination'):
                wire_parameters(record)
                try:
                    saved = self.gateway.upload_request('verify', record)
                except PocketError as error:
                    if error.status != 404:
                        raise
                else:
                    self.receipt(saved, record)
                    self.update(identifier, state='completed', offset=record['size'], receipt=saved, message='Arquivo confirmado por releitura e SHA-256. Original preservado.')
                    notify(record['size'], record['size']); return saved
            check(); source = self.source(record)
            if not record.get('destination'):
                prepared = self.gateway.upload_request('prepare')
                prefix = prepared.get('path') if isinstance(prepared, dict) else None
                if not isinstance(prefix, str) or prepared.get('root') != 'home' or prefix.endswith('/'):
                    raise PocketError('Caixa de entrada inválida.')
                record['destination'] = prefix + '/' + identifier + '-' + remote_name(record['name'])
                wire_parameters(record)
                self.update(identifier, destination=record['destination'])
            check()
            offset, chunk_size = self.progress(self.gateway.upload_request('progress', record), record['size'])
            self.update(identifier, state='uploading', offset=offset, message='Enviando blocos; original permanece intacto.')
            notify(offset, record['size'])
            empty_sent = False
            while offset < record['size'] or (record['size'] == 0 and not empty_sent):
                check()
                if identity(os.fstat(source)) != record['identity']:
                    raise PocketError('Arquivo de origem mudou durante envio. Parcial preservado; inicie nova versão.')
                os.lseek(source, offset, os.SEEK_SET)
                count = min(chunk_size, record['size'] - offset); data = bytearray()
                while len(data) < count:
                    check()
                    part = self.read(source, min(1024*1024, count - len(data)))
                    if not part:
                        raise PocketError('Arquivo mudou durante leitura. Bloco não enviado.')
                    data.extend(part)
                chunk = bytes(data)
                if identity(os.fstat(source)) != record['identity']:
                    raise PocketError('Arquivo mudou durante leitura. Bloco não enviado.')
                check()
                accepted = self.gateway.upload_request('chunk', record, offset=offset, chunk=chunk)
                acknowledged, chunk_size = self.progress(accepted, record['size'])
                if acknowledged != offset + len(chunk):
                    raise PocketError('Posição confirmada não confere. Retome para consultar progresso.')
                offset = acknowledged; empty_sent = True
                self.update(identifier, offset=offset); notify(offset, record['size'])
            check()
            if identity(os.fstat(source)) != record['identity']:
                raise PocketError('Origem mudou; confirmação interrompida. Original e parcial preservados.')
            self.update(identifier, state='committing', message='Confirmando e verificando conteúdo no notebook…')
            receipt = self.gateway.upload_request('commit', record)
            self.receipt(receipt, record)
            # A separate read verifies committed bytes; a successful POST alone
            # is never treated as a verified transfer.
            verified = self.receipt(self.gateway.upload_request('verify', record), record)
            self.update(identifier, state='completed', offset=record['size'], receipt=verified, message='Arquivo confirmado por releitura e SHA-256. Original preservado.')
            return verified
        except UploadPaused as error:
            self.update(identifier, state='paused', message=str(error)); raise
        except Exception as error:
            if leased:
                self.update(identifier, state='uncertain', message=str(error)[:2000] + ' Nada será reenviado sem retomada explícita.')
            raise
        finally:
            if source is not None:
                os.close(source)
            if lease is not None:
                os.close(lease)
            with self.lock:
                self.active.pop(identifier, None)
