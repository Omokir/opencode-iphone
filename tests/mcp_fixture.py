"""Minimal offline MCP stdio fixture; no filesystem/network tools exposed."""
import json
from pathlib import Path
import sys

log = Path(sys.argv[1])
for line in sys.stdin:
    message = json.loads(line)
    method = message.get('method')
    with log.open('a') as output:
        output.write(json.dumps({'method': method}) + '\n')
    if 'id' not in message:
        continue
    if method == 'initialize':
        result = {'protocolVersion': '2024-11-05', 'capabilities': {'tools': {}},
                  'serverInfo': {'name': 'kzl-offline-fixture', 'version': '1'}}
    elif method == 'tools/list':
        result = {'tools': [{'name': 'ping', 'description': 'Return a synthetic fixture greeting.',
                             'inputSchema': {'type': 'object', 'properties': {}, 'additionalProperties': False}}]}
    elif method == 'tools/call':
        result = {'content': [{'type': 'text', 'text': 'KZL_FIXTURE_OK'}]}
    elif method in ('resources/list', 'prompts/list', 'resources/templates/list'):
        result = {'resources': []} if method == 'resources/list' else {'prompts': []} if method == 'prompts/list' else {'resourceTemplates': []}
    elif method == 'ping':
        result = {}
    else:
        print(json.dumps({'jsonrpc': '2.0', 'id': message['id'], 'error': {'code': -32601, 'message': 'Fixture method unavailable'}}), flush=True)
        continue
    print(json.dumps({'jsonrpc': '2.0', 'id': message['id'], 'result': result}), flush=True)
