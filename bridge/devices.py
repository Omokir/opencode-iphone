"""Independent device tokens; registry stores only hashes, never bearer secrets."""
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import threading
import time
import uuid

LOCK = threading.RLock()


class DeviceTokens:
    def __init__(self, state):
        self.state = Path(state)
        self.path = self.state / 'devices.json'

    def load(self):
        return json.loads(self.path.read_text()) if self.path.exists() else {'devices': [], 'legacyRevoked': False}

    def save(self, value):
        self.state.mkdir(mode=0o700, parents=True, exist_ok=True)
        temporary = self.path.with_suffix('.tmp')
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'w') as out:
            json.dump(value, out)
            out.flush(); os.fsync(out.fileno())
        os.replace(temporary, self.path)

    def issue(self, name):
        with LOCK:
            value = self.load()
            if len(value['devices']) >= 100:
                raise ValueError('Device limit reached')
            token = secrets.token_urlsafe(48)
            value['devices'].append({'id': str(uuid.uuid4()), 'name': str(name or 'iPhone')[:80],
                'createdAt': time.time(), 'hash': hashlib.sha256(token.encode()).hexdigest()})
            self.save(value)
            return token

    def identify(self, token):
        if not token or len(token) > 512:
            return None
        with LOCK:
            value = self.load()
            digest = hashlib.sha256(token.encode()).hexdigest()
            for device in value['devices']:
                if hmac.compare_digest(digest, device['hash']):
                    return device['id']
            legacy = self.state / 'token.secret'
            if not value['legacyRevoked'] and legacy.exists() and hmac.compare_digest(token, legacy.read_text().strip()):
                return 'legacy'
        return None

    def listing(self, current):
        with LOCK:
            value = self.load()
            entries = [{k: d[k] for k in ('id', 'name', 'createdAt')} | {'current': d['id'] == current}
                       for d in value['devices']]
            if not value['legacyRevoked'] and (self.state / 'token.secret').exists():
                entries.append({'id': 'legacy', 'name': 'Conexão anterior (token compartilhado)', 'createdAt': None, 'current': current == 'legacy'})
            return {'devices': entries}

    def revoke(self, identifier):
        with LOCK:
            value = self.load()
            if identifier == 'legacy':
                value['legacyRevoked'] = True
            else:
                value['devices'] = [d for d in value['devices'] if d['id'] != identifier]
            self.save(value)
            return {'revoked': True}
