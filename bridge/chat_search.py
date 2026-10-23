"""Search one real history page; opaque upstream cursor lets clients scan all pages."""
import unicodedata


def search_page(page, query):
    query = unicodedata.normalize('NFC', query).casefold()
    matches = []
    messages = page.get('data', [])
    for message in messages:
        if not isinstance(message, dict) or message.get('type') not in ('user', 'assistant'):
            continue
        parts = [message.get('text', '')] if isinstance(message.get('text'), str) else []
        parts += [p['text'] for p in (message.get('content') or [])
                  if isinstance(p, dict) and p.get('type') == 'text' and isinstance(p.get('text'), str)]
        text = unicodedata.normalize('NFC', '\n'.join(parts))
        index = text.casefold().find(query)
        if index < 0:
            continue
        start = max(0, index - 100)
        matches.append({'id': message['id'], 'type': message['type'],
                        'snippet': ('…' if start else '') + text[start:start + 400],
                        'created': (message.get('time') or {}).get('created', 0)})
    return {'matches': matches, 'scanned': len(messages),
            'cursor': (page.get('cursor') or {}).get('next')}
