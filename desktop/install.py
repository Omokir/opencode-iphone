#!/usr/bin/env python3
"""Install this reviewed native client for the current user, without sudo.

Never removes user preferences, signing files, or existing unknown applications.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex


def digest(data):
    return hashlib.sha256(data).hexdigest()


def install(home):
    source = Path(__file__).resolve().parent
    home = Path(home).resolve()
    destination = home / '.local/share/opencode-pocket-desktop'
    manifest = destination / 'install-manifest.json'
    old = json.loads(manifest.read_text()).get('files', {}) if manifest.exists() and not manifest.is_symlink() else {}
    desktop = home / '.local/share/applications/com.omokir.PocketDesktop.desktop'
    launcher = home / '.local/bin/opencode-pocket'
    primary = home / '.local/bin/kzl-agent'
    files = {destination/name: (source/name).read_bytes() for name in ('main.py', 'backend.py', 'account_client.py', 'voice.py', 'uploads.py', 'richtext.py', 'terminal.py', 'terminal_policy.py', 'KzL.png')}
    files[launcher] = ('#!/bin/sh\nexec /usr/bin/python3 ' + shlex.quote(str(destination/'main.py')) + ' "$@"\n').encode()
    files[primary] = files[launcher]
    exe = str(destination/'main.py').replace('\\', '\\\\').replace('"', '\\"').replace('%', '%%')
    files[desktop] = f'''[Desktop Entry]
Type=Application
Name=KzL Agent
Comment=Cliente nativo Linux para OpenCode — conversa, projetos e modo retrato
Exec=/usr/bin/python3 "{exe}"
Icon={destination / 'KzL.png'}
Terminal=false
Categories=Development;IDE;
StartupWMClass=com.omokir.PocketDesktop
Actions=Portrait;Demo;

[Desktop Action Portrait]
Name=Modo retrato
Exec=/usr/bin/python3 "{exe}" --portrait

[Desktop Action Demo]
Name=Demonstração sem API
Exec=/usr/bin/python3 "{exe}" --demo
'''.encode()
    for path, data in files.items():
        for parent in path.parents:
            if parent == home:
                break
            if parent.is_symlink():
                raise RuntimeError('Instalação interrompida: diretório simbólico ' + str(parent))
        if path.is_symlink():
            raise RuntimeError('Instalação interrompida: destino simbólico ' + str(path))
        if path.exists() and digest(path.read_bytes()) not in (old.get(str(path)), digest(data)):
            raise RuntimeError('Arquivo existente não reconhecido; preservado: ' + str(path))
    for path, data in files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(path.name + '.pocket-new')
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o755 if path in (launcher, primary) else 0o644)
        with os.fdopen(fd, 'wb') as file:
            file.write(data); file.flush(); os.fsync(file.fileno())
        os.replace(temporary, path)
    result = {'version': '0.7.0', 'files': {str(path): digest(data) for path, data in files.items()}}
    # Manifest carries only installation hashes, never credentials or prompts.
    temporary = destination / 'install-manifest.new'
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644)
    with os.fdopen(fd, 'w') as file:
        json.dump(result, file, indent=2); file.flush(); os.fsync(file.fileno())
    os.replace(temporary, manifest)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--home', default=str(Path.home()), help='Target user home (also used by isolated installation tests)')
    args = parser.parse_args()
    result = install(args.home)
    print(f'Installed KzL Agent {result["version"]}: {len(result["files"])} verified files. No preferences removed.')
