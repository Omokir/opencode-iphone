#!/usr/bin/env python3
"""Create one-time pairing code locally. No Apple credentials required."""
import json
import os
from pathlib import Path
import secrets
import subprocess
import time

os.umask(0o077)
state = Path.home() / '.local/state/opencode-iphone'
state.mkdir(parents=True, exist_ok=True)
token = state / 'token.secret'
if not token.exists():
    token.write_text(secrets.token_urlsafe(48))
code = f'{secrets.randbelow(1000000):06d}'
(state / 'pairing.json').write_text(json.dumps({'code': code, 'expires': time.time() + 300}))
status = json.loads(subprocess.check_output(['tailscale', 'status', '--json']))
host = status['Self']['DNSName'].rstrip('.')
message = f'Servidor: https://{host}:8443\n\nCódigo: {code}\n\nVálido por 5 minutos, uso único.\nAtive Tailscale no iPhone antes de conectar.'
subprocess.run(['zenity', '--info', '--title=Conectar OpenCode no iPhone', '--width=440', '--text=' + message], check=False)
