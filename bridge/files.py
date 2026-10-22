"""Authenticated home-folder transfers. No deletion, execution or symlink following."""
from contextlib import contextmanager
import hashlib
import json
import mimetypes
import os
from pathlib import Path
import re
import stat
import tempfile
import threading
import uuid


class FileError(Exception):
    def __init__(self, status, message, existing=None):
        self.status = status
        self.body = {'error': message}
        if existing:
            self.body['existing'] = existing
        super().__init__(message)


def blocked(name):
    lower = name.casefold()
    return (not name or name in ('.', '..') or name.startswith('.') or '/' in name or '\\' in name
            or any(ord(char) < 32 or ord(char) == 127 for char in name)
            or Path(lower).suffix in ('.pem', '.key', '.p12', '.pfx', '.kdbx', '.mobileprovision')
            or lower in ('id_rsa', 'id_ed25519', 'auth.json')
            or lower.endswith('.json') and any(word in lower for word in ('credential', 'secret', 'token')))


def version(info):
    value = f'{info.st_dev}:{info.st_ino}:{info.st_size}:{info.st_mtime_ns}:{info.st_ctime_ns}'
    return hashlib.sha256(value.encode()).hexdigest()


class FileBrowser:
    def __init__(self, state, roots=None, max_bytes=64 * 1024 * 1024):
        self.state = Path(state)
        self.configured_roots = roots
        self.max_bytes = max_bytes
        self.lock = threading.Lock()

    def roots(self):
        if self.configured_roots is not None:
            return self.configured_roots
        file = self.state / 'file-browser.json'
        if file.exists():
            try:
                values = json.loads(file.read_text())['roots']
                return {v['id']: {'name': v['name'], 'path': str(Path(v['path']).expanduser().resolve(strict=True))}
                        for v in values if re.fullmatch(r'[a-zA-Z0-9_-]+', v['id'])}
            except (OSError, ValueError, KeyError, TypeError):
                raise FileError(503, 'Pastas permitidas precisam ser revisadas no notebook.') from None
        return {'home': {'name': 'Pasta pessoal do notebook', 'path': str(Path.home())}}

    def root_list(self):
        return {'roots': [{'id': key, 'name': value['name']} for key, value in self.roots().items()],
                'maxBytes': self.max_bytes}

    def context(self, directory):
        if not isinstance(directory, str) or not directory.startswith('/'):
            raise FileError(400, 'Pasta de projeto inválida.')
        for identifier, value in self.roots().items():
            try:
                relative = str(Path(directory).relative_to(Path(value['path'])))
            except ValueError:
                continue
            relative = '' if relative == '.' else relative
            parts = self.parts(relative)
            with self.directory(identifier, parts):
                return {'root': identifier, 'path': relative}
        raise FileError(403, 'Projeto fora das pastas liberadas. Abra pela pasta pessoal ou libere raiz no notebook.')

    def parts(self, relative):
        if not isinstance(relative, str) or len(relative) > 4096 or relative.startswith('/'):
            raise FileError(400, 'Caminho inválido.')
        if relative == '':
            return []
        parts = relative.split('/')
        try:
            relative.encode('utf-8', 'strict')
        except UnicodeError:
            raise FileError(400, 'Nome de arquivo incompatível.') from None
        if any(blocked(part) for part in parts):
            raise FileError(403, 'Caminho protegido, oculto ou inválido. Não será acessado pelo app.')
        return parts

    @contextmanager
    def directory(self, root, parts):
        allowed = self.roots()
        if root not in allowed:
            raise FileError(403, 'Pasta não autorizada no notebook.')
        fd = None
        try:
            fd = os.open(allowed[root]['path'], os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            for part in parts:
                next_fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                os.close(fd)
                fd = next_fd
            yield fd
        except FileError:
            raise
        except FileNotFoundError:
            raise FileError(404, 'Pasta ou arquivo não encontrado.') from None
        except OSError:
            raise FileError(403, 'Sem acesso à pasta, ou caminho é um link simbólico.') from None
        finally:
            if fd is not None:
                os.close(fd)

    def metadata(self, name, relative, info):
        kind = ('directory' if stat.S_ISDIR(info.st_mode) else 'file' if stat.S_ISREG(info.st_mode)
                else 'link' if stat.S_ISLNK(info.st_mode) else 'other')
        return {'name': name, 'path': relative, 'kind': kind,
                'size': info.st_size if kind == 'file' else None,
                'modifiedAt': info.st_mtime, 'version': version(info),
                'readable': kind in ('file', 'directory') and not blocked(name)}

    def listing(self, root, relative):
        parts = self.parts(relative)
        entries = []
        truncated = False
        with self.directory(root, parts) as fd, os.scandir(fd) as iterator:
            for entry in iterator:
                if entry.name.startswith('.'):
                    continue
                try:
                    entry.name.encode('utf-8', 'strict')
                    info = os.stat(entry.name, dir_fd=fd, follow_symlinks=False)
                except (OSError, UnicodeError):
                    continue
                path = '/'.join(parts + [entry.name])
                entries.append(self.metadata(entry.name, path, info))
                if len(entries) >= 2000:
                    truncated = True
                    break
        entries.sort(key=lambda item: (item['kind'] != 'directory', item['name'].casefold()))
        return {'root': root, 'path': relative, 'parent': '/'.join(parts[:-1]) if parts else None,
                'entries': entries, 'truncated': truncated}

    @contextmanager
    def download(self, root, relative, expected=None):
        parts = self.parts(relative)
        if not parts:
            raise FileError(400, 'Selecione arquivo para baixar.')
        with self.directory(root, parts[:-1]) as parent:
            fd = None
            try:
                fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
                initial = os.fstat(fd)
                if not stat.S_ISREG(initial.st_mode):
                    raise FileError(403, 'Somente arquivos regulares podem ser baixados.')
                if initial.st_size > self.max_bytes:
                    raise FileError(413, 'Limite de 64 MB por transferência.')
                if expected and expected != version(initial):
                    raise FileError(409, 'Arquivo mudou. Atualize pasta antes de baixar.')
                with tempfile.SpooledTemporaryFile(max_size=2 * 1024 * 1024) as snapshot:
                    digest = hashlib.sha256()
                    remaining = initial.st_size
                    while remaining:
                        chunk = os.read(fd, min(65536, remaining))
                        if not chunk:
                            raise FileError(409, 'Arquivo mudou durante leitura. Tente após atualizar pasta.')
                        snapshot.write(chunk)
                        digest.update(chunk)
                        remaining -= len(chunk)
                    if version(os.fstat(fd)) != version(initial):
                        raise FileError(409, 'Arquivo mudou durante leitura. Atualize pasta.')
                    snapshot.seek(0)
                    yield {'stream': snapshot, 'size': initial.st_size, 'name': parts[-1],
                           'mime': mimetypes.guess_type(parts[-1])[0] or 'application/octet-stream',
                           'sha256': digest.hexdigest(), 'version': version(initial)}
            except FileError:
                raise
            except FileNotFoundError:
                raise FileError(404, 'Arquivo não encontrado.') from None
            except OSError:
                raise FileError(403, 'Sem acesso ao arquivo, ou arquivo é um link simbólico.') from None
            finally:
                if fd is not None:
                    os.close(fd)

    def receipt_path(self, identifier):
        try:
            identifier = str(uuid.UUID(identifier))
        except (ValueError, AttributeError):
            raise FileError(400, 'Identificador de envio inválido.') from None
        return self.state / 'file-receipts' / (identifier + '.json')

    def receipt(self, identifier):
        path = self.receipt_path(identifier)
        if not path.exists():
            raise FileError(404, 'Envio ainda não confirmado.')
        return json.loads(path.read_text())

    def target(self, parent, parts):
        try:
            info = os.stat(parts[-1], dir_fd=parent, follow_symlinks=False)
        except FileNotFoundError:
            return None
        if not stat.S_ISREG(info.st_mode):
            raise FileError(403, 'Destino não é arquivo regular. Não será substituído.')
        return info

    def condition(self, parent, parts, expected):
        current = self.target(parent, parts)
        if expected == '*':
            if current is not None:
                raise FileError(409, 'Arquivo já existe. Confirme substituição no app.', self.metadata(parts[-1], '/'.join(parts), current))
        elif current is None or expected != version(current):
            raise FileError(409, 'Destino mudou. Atualize e confirme novamente.', self.metadata(parts[-1], '/'.join(parts), current) if current else None)
        return current

    def upload(self, root, relative, source, length, identifier, digest, expected):
        parts = self.parts(relative)
        if not parts or not expected or not re.fullmatch('[0-9a-f]{64}', digest or ''):
            raise FileError(400, 'Nome, condição e checksum do envio são obrigatórios.')
        if length < 0 or length > self.max_bytes:
            raise FileError(413, 'Limite de 64 MB por transferência.')
        receipt_file = self.receipt_path(identifier)
        identifier = receipt_file.stem
        with self.directory(root, parts[:-1]) as parent:
            with self.lock:
                if receipt_file.exists():
                    saved = json.loads(receipt_file.read_text())
                    if (saved['root'], saved['path'], saved['sha256'], saved['size']) != (root, relative, digest, length):
                        raise FileError(409, 'Identificador já foi usado para outro envio.')
                    current = self.target(parent, parts)
                    if current is None or version(current) != saved['version']:
                        raise FileError(409, 'Envio anterior terminou, mas destino mudou depois. Verifique pasta.')
                    # Replay is read-only, but still verify request content.
                    hasher = hashlib.sha256()
                    remaining = length
                    while remaining:
                        chunk = source.read(min(65536, remaining))
                        if not chunk:
                            raise FileError(400, 'Envio incompleto.')
                        hasher.update(chunk); remaining -= len(chunk)
                    if hasher.hexdigest() != digest:
                        raise FileError(400, 'Checksum não confere.')
                    return saved
                original = self.condition(parent, parts, expected)
            temporary = '.pocket-upload-' + identifier
            fd = None
            created_temporary = False
            try:
                fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=parent)
                created_temporary = True
                hasher = hashlib.sha256()
                remaining = length
                with os.fdopen(fd, 'wb') as output:
                    fd = None
                    while remaining:
                        chunk = source.read(min(65536, remaining))
                        if not chunk:
                            raise FileError(400, 'Envio incompleto; arquivo de destino não foi alterado.')
                        output.write(chunk); hasher.update(chunk); remaining -= len(chunk)
                    output.flush()
                    os.fsync(output.fileno())
                if hasher.hexdigest() != digest:
                    raise FileError(400, 'Checksum não confere; destino não foi alterado.')
                with self.lock:
                    self.condition(parent, parts, expected)
                    if original:
                        permissions_fd = os.open(temporary, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=parent)
                        try:
                            os.fchmod(permissions_fd, stat.S_IMODE(original.st_mode) & 0o777)
                        finally:
                            os.close(permissions_fd)
                    if expected == '*':
                        os.link(temporary, parts[-1], src_dir_fd=parent, dst_dir_fd=parent, follow_symlinks=False)
                        os.unlink(temporary, dir_fd=parent)
                    else:
                        os.replace(temporary, parts[-1], src_dir_fd=parent, dst_dir_fd=parent)
                    os.fsync(parent)
                    saved = {'uploadID': identifier, 'root': root, 'path': relative, 'size': length,
                             'sha256': digest, 'version': version(os.stat(parts[-1], dir_fd=parent, follow_symlinks=False))}
                    receipt_file.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                    temp_receipt = receipt_file.with_suffix('.tmp')
                    receipt_fd = os.open(temp_receipt, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
                    with os.fdopen(receipt_fd, 'w') as output:
                        json.dump(saved, output)
                    os.replace(temp_receipt, receipt_file)
                    return saved
            except FileError:
                raise
            except FileExistsError:
                raise FileError(409, 'Destino ou envio concorrente já existe. Atualize pasta antes de tentar novamente.') from None
            except OSError:
                raise FileError(503, 'Não foi possível confirmar gravação. Verifique pasta e recibo antes de tentar novamente.') from None
            finally:
                if fd is not None:
                    os.close(fd)
                if created_temporary:
                    try:
                        os.unlink(temporary, dir_fd=parent)
                    except FileNotFoundError:
                        pass
