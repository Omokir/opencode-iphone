"""Read recorded computer-use steps. Never runs tools or fetches arbitrary URIs."""
import base64

NAMES = ('linux_computer_', 'linux_browser', 'computer_', 'browser_', 'desktop_')
MIMES = {'image/png', 'image/jpeg', 'image/webp'}

def is_computer(name):
    return isinstance(name, str) and any(n in name.lower() for n in NAMES)

def images(part):
    result = []
    for index, content in enumerate(part.get('state', {}).get('content', [])[:32]):
        if isinstance(content, dict) and content.get('type') == 'file' and content.get('mime') in MIMES:
            uri = content.get('uri', '')
            if isinstance(uri, str) and uri.startswith('data:' + content['mime'] + ';base64,') and len(uri) <= 12 * 1024 * 1024:
                result.append({'index': index, 'mime': content['mime']})
    return result

def project(messages):
    steps = []
    for message in messages[:100]:
        if not isinstance(message, dict): continue
        for part in message.get('content', []):
            if not isinstance(part, dict) or part.get('type') != 'tool' or not is_computer(part.get('name')): continue
            phase = part.get('state', {}).get('status')
            steps.append({'messageID': message.get('id'), 'toolID': part.get('id'), 'name': part['name'][:160],
                'state': phase if phase in ('running', 'streaming', 'completed', 'error') else 'unknown',
                'time': part.get('time', {}).get('created', 0), 'images': images(part)})
    return sorted(steps, key=lambda step: step['time'], reverse=True)[:30]

def image_bytes(message, tool_id, index):
    if not isinstance(index, int) or not 0 <= index < 32: raise ValueError('Invalid image index')
    for part in message.get('content', []):
        if part.get('id') != tool_id or not is_computer(part.get('name')): continue
        descriptor = next((item for item in images(part) if item['index'] == index), None)
        if descriptor is None: break
        data = base64.b64decode(part['state']['content'][index]['uri'].split(',', 1)[1], validate=True)
        if not data or len(data) > 8 * 1024 * 1024: break
        mime = descriptor['mime']
        valid = ((mime == 'image/png' and data.startswith(b'\x89PNG\r\n\x1a\n')) or
                 (mime == 'image/jpeg' and data.startswith(b'\xff\xd8\xff')) or
                 (mime == 'image/webp' and data.startswith(b'RIFF') and data[8:12] == b'WEBP'))
        if valid: return mime, data
    raise ValueError('Recorded image unavailable')
