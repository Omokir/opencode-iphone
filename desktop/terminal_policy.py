"""Pure local-terminal validation; no GTK imports and no process execution."""
import os
from pathlib import Path
import unicodedata

SHELLS = ('/usr/bin/zsh', '/bin/zsh', '/usr/bin/bash', '/bin/bash', '/usr/bin/fish', '/bin/sh')


def directory_path(value):
    if not isinstance(value, str) or len(value) > 4096 or not Path(value).is_absolute() or any(unicodedata.category(c) in ('Cc', 'Cf', 'Cs') for c in value):
        raise ValueError('Escolha uma pasta local absoluta, sem caracteres de controle.')
    resolved = Path(value).resolve(strict=True)
    if not resolved.is_dir():
        raise ValueError('O projeto não é uma pasta local existente.')
    return str(resolved)


def shell_path(value=None):
    candidate = value or os.environ.get('SHELL')
    if value and value not in SHELLS:
        raise ValueError('Shell não suportado.')
    if candidate in SHELLS and os.path.isfile(candidate) and os.access(candidate, os.X_OK):
        return candidate
    if value:
        raise ValueError('Shell não está instalado.')
    for path in SHELLS:
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return path
    raise ValueError('Nenhum shell local suportado está instalado.')


def paste_text(value):
    if not isinstance(value, str) or len(value.encode('utf-8', 'strict')) > 65536:
        raise ValueError('Colagem limitada a 64 KiB de texto UTF-8.')
    if any((ord(c) < 32 and c not in '\n\r\t') or ord(c) == 127 or unicodedata.category(c) in ('Cf', 'Cs') for c in value):
        raise ValueError('Colagem contém caracteres de controle não permitidos.')
    return value
