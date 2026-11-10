"""Read-only, location-scoped connection inventory. Never expose credentials/config."""
import json
import urllib.parse


STATES = {'connected', 'pending', 'disabled', 'failed', 'needs_auth'}


def inventory(request, directory):
    if not isinstance(directory, str) or not directory.startswith('/') or len(directory) > 4096 or '\x00' in directory:
        raise ValueError('Invalid directory')
    query = '?' + urllib.parse.urlencode({'location[directory]': directory})
    result = {'directory': directory, 'readOnly': True, 'mcp': [], 'integrations': [], 'unavailable': []}
    for kind in ('mcp', 'integration'):
        try:
            status, raw = request('GET', '/api/' + kind + query, None)
            if status != 200:
                raise ValueError('Unavailable')
            records = json.loads(raw)['data']
            if not isinstance(records, list) or len(records) > 2000:
                raise ValueError('Invalid inventory')
            projected = []
            for row in records:
                if not isinstance(row, dict):
                    raise ValueError('Invalid record')
                if kind == 'mcp':
                    state = (row.get('status') or {}).get('status')
                    projected.append({'name': text(row.get('name')), 'status': state if state in STATES else 'unknown'})
                else:
                    methods = row.get('methods', [])
                    connections = row.get('connections', [])
                    if not isinstance(methods, list) or not isinstance(connections, list):
                        raise ValueError('Invalid integration')
                    projected.append({'id': text(row.get('id')), 'name': text(row.get('name')),
                                      'methods': sorted({m['type'] for m in methods if isinstance(m, dict) and
                                                         m.get('type') in ('key', 'oauth', 'external', 'command', 'env')}),
                                      'connectionCount': len(connections)})
            result['mcp' if kind == 'mcp' else 'integrations'] = projected
        except Exception:
            # Upstream errors can contain tokens, commands, URLs and provider details.
            # A failed category is unavailable, never an empty successful inventory.
            result['unavailable'].append(kind)
    return result


def text(value):
    if not isinstance(value, str) or not value or len(value) > 200:
        raise ValueError('Invalid display metadata')
    return ''.join(c for c in value if c.isprintable())
