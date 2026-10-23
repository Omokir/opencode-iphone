"""Dedicated, no-clobber phone inbox; verification reads actual committed bytes."""
import os
import hashlib
import stat
from pathlib import Path
import uuid
from files import FileBrowser, FileError, version


class PhoneInbox:
    prefix = 'Downloads/Iphone 11 Omoki/'

    def __init__(self, state, home=None):
        self.files = FileBrowser(state, roots={'home': {'name': 'Home', 'path': str(home or Path.home())}}, max_bytes=None)

    def prepare(self):
        parts = []
        for name in ['Downloads', 'Iphone 11 Omoki']:
            with self.files.directory('home', parts) as fd:
                try:
                    os.mkdir(name, 0o700, dir_fd=fd)
                    os.fsync(fd)
                except FileExistsError:
                    pass
            parts.append(name)
            with self.files.directory('home', parts):
                pass
        return {'root': 'home', 'path': self.prefix.rstrip('/'), 'maxBytes': self.files.max_bytes}

    def validate(self, path, identifier):
        try:
            identifier = str(uuid.UUID(identifier))
        except (ValueError, AttributeError):
            raise FileError(400, 'Identificador inválido.') from None
        if not path.startswith(self.prefix + identifier + '-'):
            raise FileError(403, 'Destino fora da caixa de entrada.')
        suffix = path[len(self.prefix):]
        if len(self.files.parts(suffix)) != 1:
            raise FileError(403, 'Somente arquivos diretos na caixa de entrada.')
        return identifier

    def upload(self, path, source, length, identifier, digest):
        identifier = self.validate(path, identifier)
        return self.files.upload('home', path, source, length, identifier, digest, '*')

    def verify(self, path, identifier):
        identifier = self.validate(path, identifier)
        parts = self.files.parts(path)
        with self.files.directory('home', parts[:-1]) as parent:
            fd = None
            try:
                fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
                initial = os.fstat(fd)
                if not stat.S_ISREG(initial.st_mode):
                    raise FileError(403, 'Destino não é arquivo regular.')
                digest = hashlib.sha256()
                remaining = initial.st_size
                while remaining:
                    chunk = os.read(fd, min(1024 * 1024, remaining))
                    if not chunk:
                        raise FileError(409, 'Destino mudou durante verificação.')
                    digest.update(chunk)
                    remaining -= len(chunk)
                if version(initial) != version(os.fstat(fd)):
                    raise FileError(409, 'Destino mudou durante verificação.')
                return {'uploadID': identifier, 'root': 'home', 'path': path,
                        'size': initial.st_size, 'sha256': digest.hexdigest(), 'version': version(initial)}
            except FileNotFoundError:
                raise FileError(404, 'Arquivo ainda não encontrado.') from None
            except OSError:
                raise FileError(403, 'Destino indisponível ou protegido.') from None
            finally:
                if fd is not None:
                    os.close(fd)
