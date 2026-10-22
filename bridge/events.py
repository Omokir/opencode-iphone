"""Reduce Core SSE events to session-scoped invalidation hints, never raw data."""
import json


def belongs_to_session(value, session_id, depth=0):
    if not isinstance(value, dict) or depth > 6:
        return False
    if value.get('sessionID') == session_id or value.get('sessionId') == session_id:
        return True
    for key in ('data', 'properties', 'session', 'info', 'message', 'inbox', 'request'):
        nested = value.get(key)
        if isinstance(nested, dict) and (nested.get('id') == session_id or belongs_to_session(nested, session_id, depth + 1)):
            return True
    return False


def session_hint(encoded, session_id):
    try:
        value = json.loads(encoded)
        if isinstance(value, str):
            value = json.loads(value)
    except (ValueError, TypeError, RecursionError):
        return None
    if not isinstance(value, dict) or not belongs_to_session(value, session_id):
        return None
    return {'type': str(value.get('type', 'session.changed'))[:160], 'sessionID': session_id}
