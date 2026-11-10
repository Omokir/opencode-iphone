"""Private MCP registry. Saving declarations never starts a process or contacts a URL.

Runtime application is deliberately separate; records are not proof of connection.
All writes use optimistic revisions, atomic replacement and an interprocess lock.
"""
import fcntl
import json
import os
from pathlib import Path
import re
import secrets
import stat
import urllib.parse


class RegistryConflict(ValueError):
    pass


def declaration(value):
    if not isinstance(value, dict):
        raise ValueError('Invalid declaration')
    kind = value.get('type')
    fields = {'type', 'command', 'environment'} if kind == 'local' else {'type', 'url'}
    if kind not in ('local', 'remote') or set(value) - fields:
        raise ValueError('Unsupported MCP settings')
    if kind == 'remote':
        url = value.get('url')
        if not isinstance(url, str) or len(url) > 2048:
            raise ValueError('Invalid URL')
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme != 'https' or not parsed.hostname or parsed.username is not None or parsed.password is not None or parsed.query or parsed.fragment:
            raise ValueError('Use HTTPS without embedded credentials, query or fragment')
        _ = parsed.port  # Reject invalid ports before persisting.
        return {'type': 'remote', 'url': url}
    command = value.get('command')
    if not isinstance(command, list) or not 1 <= len(command) <= 64 or any(
            not isinstance(arg, str) or not arg or len(arg) > 4096 or '\x00' in arg for arg in command):
        raise ValueError('Command must be an argument array')
    environment = value.get('environment', {})
    if not isinstance(environment, dict) or len(environment) > 64:
        raise ValueError('Invalid environment references')
    for key, reference in environment.items():
        if not isinstance(key, str) or not re.fullmatch(r'[A-Z_][A-Z0-9_]{0,99}', key) or not isinstance(reference, str) or not re.fullmatch(r'\{env:[A-Z_][A-Z0-9_]{0,99}\}', reference):
            raise ValueError('Environment accepts references only; never literal credentials')
    # Commands are powerful user-reviewed declarations. Do not use shell=True or
    # evaluate them here. Users must not put secrets in command arguments.
    return {'type': 'local', 'command': command[:], 'environment': dict(environment)}


def project_path(value):
    if not isinstance(value, str) or not value.startswith('/') or len(value) > 4096 or '\x00' in value:
        raise ValueError('Invalid project')
    canonical = str(Path(value).resolve(strict=True))
    if not Path(canonical).is_dir() or canonical != value:
        raise ValueError('Use an existing canonical project directory')
    return canonical


class ConnectionRegistry:
    def __init__(self, root):
        self.root = Path(root)

    def _open_root(self):
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        info = os.fstat(fd)
        if info.st_uid != os.getuid() or info.st_mode & 0o077:
            os.close(fd)
            raise ValueError('Registry directory must be private and owned by current user')
        return fd

    def _read(self, root):
        try:
            fd = os.open('connections.json', os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=root)
        except FileNotFoundError:
            return {'version': 1, 'revision': 0, 'servers': {}}
        with os.fdopen(fd, 'rb') as file:
            info = os.fstat(file.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077 or info.st_nlink != 1 or info.st_size > 1024 * 1024:
                raise ValueError('Unsafe registry file')
            value = json.loads(file.read(1024 * 1024 + 1))
        if not isinstance(value, dict) or value.get('version') != 1 or type(value.get('revision')) is not int or value['revision'] < 0 or not isinstance(value.get('servers'), dict):
            raise ValueError('Invalid registry; preserved without overwriting')
        return value

    def read(self):
        root = self._open_root()
        try:
            return self._read(root)
        finally:
            os.close(root)

    def change(self, expected_revision, operation, name, config=None, directory=None):
        if type(expected_revision) is not int or expected_revision < 0:
            raise ValueError('Invalid revision')
        if not isinstance(name, str) or not re.fullmatch(r'[a-z][a-z0-9_-]{0,47}', name):
            raise ValueError('Invalid server name')
        if operation not in ('add', 'remove', 'grant', 'revoke'):
            raise ValueError('Invalid operation')
        # Validate before any mutation. A global declaration grants no project.
        config = declaration(config) if operation == 'add' else None
        directory = project_path(directory) if operation in ('grant', 'revoke') else None
        root = self._open_root()
        lock = None
        temporary = None
        try:
            lock = os.open('connections.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600, dir_fd=root)
            info = os.fstat(lock)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.getuid() or info.st_mode & 0o077:
                raise ValueError('Unsafe registry lock')
            fcntl.flock(lock, fcntl.LOCK_EX)
            value = self._read(root)
            if value['revision'] != expected_revision:
                raise RegistryConflict('Registry changed; read current state before another write')
            servers = value['servers']
            if operation == 'add':
                if name in servers or len(servers) >= 100:
                    raise ValueError('Server exists or registry is full')
                servers[name] = {'config': config, 'projects': []}
            else:
                if name not in servers:
                    raise ValueError('Unknown server')
                if operation == 'remove':
                    del servers[name]
                else:
                    projects = set(servers[name]['projects'])
                    if operation == 'grant':
                        projects.add(directory)
                    else:
                        projects.discard(directory)
                    if len(projects) > 100:
                        raise ValueError('Too many project grants')
                    servers[name]['projects'] = sorted(projects)
            value['revision'] += 1
            data = json.dumps(value, ensure_ascii=False).encode()
            if len(data) > 1024 * 1024:
                raise ValueError('Registry too large')
            temporary = '.connections-' + secrets.token_hex(16)
            fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=root)
            with os.fdopen(fd, 'wb') as file:
                file.write(data); file.flush(); os.fsync(file.fileno())
            os.replace(temporary, 'connections.json', src_dir_fd=root, dst_dir_fd=root)
            temporary = None
            os.fsync(root)
            return value
        finally:
            if temporary:
                os.unlink(temporary, dir_fd=root)
            if lock is not None:
                os.close(lock)
            os.close(root)
