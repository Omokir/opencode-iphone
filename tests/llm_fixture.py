"""Offline OpenAI-compatible model fixture. Emits one deterministic tool call."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import time


class FixtureModel(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        payload = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        tools = payload.get('tools', [])
        names = [t.get('function', {}).get('name') for t in tools]
        last = payload['messages'][-1]
        with Path('/scratch/model-events.jsonl').open('a') as file:
            file.write(json.dumps({'path': self.path, 'names': names, 'lastRole': last.get('role')}) + '\n')
        # Completion after a tool response; new sessions always ask for fixture.
        finished = any(m.get('role') == 'tool' for m in payload['messages'])
        if finished:
            delta = {'content': 'Fixture turn complete.'}
            finish = 'stop'
        else:
            delta = {'tool_calls': [{'index': 0, 'id': 'call_fixture_ping', 'type': 'function',
                     'function': {'name': 'execute', 'arguments': json.dumps({
                         'code': 'return await tools.kzl_center_fixture.ping({});'})}}]}
            finish = 'tool_calls'
        base = {'id': 'fixture-completion', 'created': int(time.time()), 'model': 'fixture-model'}
        if payload.get('stream'):
            self.send_response(200); self.send_header('Content-Type', 'text/event-stream'); self.end_headers()
            chunks = [dict(base, object='chat.completion.chunk', choices=[{'index': 0, 'delta': delta, 'finish_reason': None}]),
                      dict(base, object='chat.completion.chunk', choices=[{'index': 0, 'delta': {}, 'finish_reason': finish}],
                           usage={'prompt_tokens': 1, 'completion_tokens': 1, 'total_tokens': 2})]
            for chunk in chunks:
                self.wfile.write(('data: ' + json.dumps(chunk) + '\n\n').encode())
            self.wfile.write(b'data: [DONE]\n\n'); self.wfile.flush()
        else:
            for call in delta.get('tool_calls', []):
                call.pop('index', None)
            data = json.dumps(dict(base, object='chat.completion', choices=[{'index': 0,
                'message': dict(delta, role='assistant'), 'finish_reason': finish}],
                usage={'prompt_tokens': 1, 'completion_tokens': 1, 'total_tokens': 2})).encode()
            self.send_response(200); self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(data))); self.end_headers(); self.wfile.write(data)


def model_server():
    return ThreadingHTTPServer(('127.0.0.1', 0), FixtureModel)
