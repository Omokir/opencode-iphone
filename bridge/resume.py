"""Bounded chunks for phone inbox. Acknowledged offset is actual durable file size."""
import hashlib
import json
import os
import re
import stat
import threading
from files import FileError


class ResumableInbox:
    chunk_bytes = 4 * 1024 * 1024

    def __init__(self, inbox):
        self.inbox = inbox
        self.lock = threading.Lock()

    def parameters(self, path, identifier, size, digest):
        identifier = self.inbox.validate(path, identifier)
        if not isinstance(size, int) or isinstance(size, bool) or not 0 <= size <= 1024 ** 4:
            raise FileError(400, 'Tamanho inválido; limite de 1 TiB por envio retomável.')
        if not re.fullmatch('[0-9a-f]{64}', digest or ''):
            raise FileError(400, 'Checksum inválido.')
        return identifier, {'path': path, 'id': identifier, 'size': size, 'sha256': digest}

    def open_stage(self, parent, identifier, metadata, create=False):
        name = '.pocket-resume-' + identifier
        meta_name = name + '.json'
        if create:
            # Fixed hidden names under rooted no-follow destination directory.
            try:
                fd = os.open(meta_name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=parent)
            except FileExistsError:
                pass
            else:
                with os.fdopen(fd, 'w') as out:
                    json.dump(metadata, out); out.flush(); os.fsync(out.fileno())
                os.fsync(parent)
        try:
            mfd = os.open(meta_name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        except FileNotFoundError:
            return None
        with os.fdopen(mfd) as source:
            info = os.fstat(source.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size > 2048 or json.load(source) != metadata:
                raise FileError(409, 'Identificador pertence a outro envio. Original preservado.')
        try:
            fd = os.open(name, os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK | (os.O_CREAT if create else 0), 0o600, dir_fd=parent)
        except FileNotFoundError:
            return None
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > metadata['size']:
            os.close(fd)
            raise FileError(409, 'Parcial inválido. Original preservado.')
        return fd

    def progress(self, path, identifier, size, digest):
        identifier, metadata = self.parameters(path, identifier, size, digest)
        with self.lock, self.inbox.files.directory('home', self.inbox.files.parts(path)[:-1]) as parent:
            fd = self.open_stage(parent, identifier, metadata)
            if fd is None:
                return {'offset': 0, 'chunkBytes': self.chunk_bytes}
            try:
                return {'offset': os.fstat(fd).st_size, 'chunkBytes': self.chunk_bytes}
            finally:
                os.close(fd)

    def append(self, path, identifier, size, digest, offset, chunk, chunk_digest):
        identifier, metadata = self.parameters(path, identifier, size, digest)
        if not 0 <= offset <= size or len(chunk) > self.chunk_bytes or offset + len(chunk) > size:
            raise FileError(400, 'Bloco fora do tamanho declarado.')
        if hashlib.sha256(chunk).hexdigest() != chunk_digest:
            raise FileError(400, 'Checksum do bloco não confere.')
        with self.lock, self.inbox.files.directory('home', self.inbox.files.parts(path)[:-1]) as parent:
            if os.fstatvfs(parent).f_bavail * os.fstatvfs(parent).f_frsize < len(chunk) + 16 * 1024 * 1024:
                raise FileError(507, 'Espaço insuficiente no computador. Original preservado.')
            fd = self.open_stage(parent, identifier, metadata, create=True)
            try:
                current = os.fstat(fd).st_size
                # Exact replay of the last acknowledged chunk is read-only.
                if offset < current:
                    if offset + len(chunk) <= current:
                        os.lseek(fd, offset, os.SEEK_SET)
                        if os.read(fd, len(chunk)) == chunk:
                            return {'offset': current, 'chunkBytes': self.chunk_bytes}
                    raise FileError(409, 'Bloco conflitante. Consulte posição antes de retomar.')
                if offset != current:
                    raise FileError(409, 'Posição desatualizada. Consulte progresso.')
                os.lseek(fd, current, os.SEEK_SET)
                view = memoryview(chunk)
                while view:
                    written = os.write(fd, view)
                    view = view[written:]
                os.fsync(fd)
                return {'offset': os.fstat(fd).st_size, 'chunkBytes': self.chunk_bytes}
            finally:
                os.close(fd)

    def commit(self, path, identifier, size, digest):
        identifier, metadata = self.parameters(path, identifier, size, digest)
        with self.lock, self.inbox.files.directory('home', self.inbox.files.parts(path)[:-1]) as parent:
            # A previous commit response can be lost; verify destination, never rewrite.
            try:
                saved = self.inbox.verify(path, identifier)
            except FileError as error:
                if error.status != 404:
                    raise
            else:
                if saved['sha256'] != digest or saved['size'] != size:
                    raise FileError(409, 'Destino existente não corresponde ao envio.')
                return saved
            fd = self.open_stage(parent, identifier, metadata)
            if fd is None:
                raise FileError(409, 'Envio parcial não encontrado.')
            with os.fdopen(fd, 'rb') as source:
                if os.fstat(source.fileno()).st_size != size:
                    raise FileError(409, 'Envio incompleto. Retome blocos pendentes.')
                if os.fstatvfs(parent).f_bavail * os.fstatvfs(parent).f_frsize < size + 16 * 1024 * 1024:
                    raise FileError(507, 'Espaço insuficiente para confirmar arquivo. Parcial preservado.')
                receipt = self.inbox.upload(path, source, size, identifier, digest)
            for name in ('.pocket-resume-' + identifier, '.pocket-resume-' + identifier + '.json'):
                os.unlink(name, dir_fd=parent)
            os.fsync(parent)
            return receipt
