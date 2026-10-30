"""Read recorded computer-use steps. Never runs tools or fetches arbitrary URIs."""
import base64
import re
import urllib.parse

def task_sessions(request, root):
    """Bounded discovery through Core parent links, never client-supplied ancestry."""
    found = [root]
    frontier = [root]
    for _ in range(3):
        next_level = []
        for parent in frontier:
            children = request('GET', '/api/session?' + urllib.parse.urlencode({'parentID': parent, 'limit': 20}))
            for child in children if isinstance(children, list) else []:
                sid = child.get('id')
                if child.get('parentID') != parent or not isinstance(sid, str) or not re.fullmatch(r'ses[A-Za-z0-9_-]{1,160}', sid):
                    continue
                if sid not in found:
                    found.append(sid); next_level.append(sid)
                    if len(found) >= 20: return found
        frontier = next_level
        if not frontier: break
    return found

def task_steps(request, root):
    sessions = task_sessions(request, root)
    steps = []
    for sid in sessions:
        messages = request('GET', '/api/session/' + sid + '/message?limit=100&order=desc')
        for step in project(messages):
            step['sessionID'] = sid
            steps.append(step)
    return sorted(steps, key=lambda step: step['time'], reverse=True)[:60]

def task_image(request, root, selected, message_id, tool_id, index):
    if selected not in task_sessions(request, root):
        raise ValueError('Image session does not belong to this task')
    message = request('GET', '/api/session/' + selected + '/message/' + message_id)
    return image_bytes(message, tool_id, index)

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
