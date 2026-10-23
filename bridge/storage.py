"""Local destination-volume capacity, not RAM or combined unrelated mounts."""
import os
from pathlib import Path


def storage_status(path=None):
    target = Path(path or Path.home() / 'Downloads' / 'Iphone 11 Omoki')
    try:
        while not target.exists() and target != target.parent:
            target = target.parent
        value = os.statvfs(target)
        total = value.f_blocks * value.f_frsize
        free = min(total, max(0, value.f_bavail * value.f_frsize))
        if total <= 0:
            return None
        return {'totalBytes': total, 'freeBytes': free}
    except OSError:
        return None
