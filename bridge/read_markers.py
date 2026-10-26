"""Read-only projection for loaded older/pinned sessions; never marks anything read."""
import json
import math
import re
import time


def read_markers(ids, fetch, clock=time.monotonic):
    if not isinstance(ids, list) or len(ids) > 120 or any(
            not isinstance(identifier, str) or len(identifier) > 100 or
            not re.fullmatch(r'ses[a-zA-Z0-9_-]+', identifier) for identifier in ids):
        raise ValueError('Invalid marker session IDs')
    ids = list(dict.fromkeys(ids))
    viewed = {}; unavailable = []; began = clock()
    for index, identifier in enumerate(ids):
        if clock() - began >= 8:
            unavailable.extend(ids[index:]); break
        code, raw = fetch('GET', '/api/session/' + identifier, None)
        if code == 404:
            unavailable.append(identifier); continue
        if code != 200:
            raise RuntimeError('Core read-marker query unavailable')
        value = json.loads(raw)
        info = value.get('data', {})
        if not isinstance(info, dict) or info.get('id') != identifier:
            unavailable.append(identifier); continue
        stamp = (info.get('time') or {}).get('viewed')
        if type(stamp) in (int, float) and math.isfinite(stamp) and stamp > 0:
            viewed[identifier] = stamp
        else:
            unavailable.append(identifier)
    return {'viewed': viewed, 'unavailable': unavailable}
