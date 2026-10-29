import json
from pathlib import Path
import tempfile
import unittest

from kzl import KzL, KzLError


class Core:
    def __init__(self):
        self.sessions = {}
        self.messages = {}
        self.writes = []
        self.fail_send = False

    def __call__(self, method, path, raw):
        body = json.loads(raw) if raw else None
        if method != 'GET':
            self.writes.append((method, path, body))
        path = path.split('?')[0]
        if path == '/api/session' and method == 'POST':
            self.sessions[body['id']] = dict(body, agent=body.get('agent', 'plan'), model=body.get('model', {'providerID': 'fixture', 'id': 'test'}))
            self.messages[body['id']] = []
            result = self.sessions[body['id']]
        elif path == '/api/mcp':
            result = [{'name': 'fixture', 'status': {'type': 'connected'}, 'headers': {'secret': 'never-return'}},
                      {'name': 'offline', 'status': {'type': 'failed', 'error': 'never-return'}}]
        elif path == '/api/agent':
            result = [{'id': 'plan', 'name': 'Plan', 'hidden': False, 'system': 'never-return'}]
        else:
            sid = path.split('/')[3]
            if sid not in self.sessions:
                return 404, b'{}'
            if path.endswith('/prompt'):
                if self.fail_send:
                    raise TimeoutError()
                item = {'id': body['id'], 'type': 'user', 'text': body['text'], 'metadata': body.get('metadata', {})}
                self.messages[sid].append(item)
                result = item
            elif path.endswith('/message'):
                result = list(reversed(self.messages[sid]))
            elif '/message/' in path:
                result = next((item for item in self.messages[sid] if item['id'] == path.split('/')[-1]), None)
                if result is None:
                    return 404, b'{}'
            elif path.endswith('/permission') or path.endswith('/form'):
                result = []
            elif path.endswith('/interrupt'):
                self.sessions[sid]['outcome'] = 'interrupted'
                result = {}
            elif path.endswith('/synthetic'):
                result = {}
            else:
                result = self.sessions[sid]
        return 200, json.dumps({'data': result}).encode()


class KzLTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.core = Core()
        self.kzl = KzL(Path(self.temp.name), self.core)
        self.parent = self.kzl.ensure()

    def tearDown(self):
        self.kzl.close()
        self.temp.cleanup()

    def submit(self, call='call_1', text='Inspect fixture only'):
        return self.kzl.submit({'callID': call, 'text': text}, 'device')

    def test_single_permanent_session_across_restart_and_missing_does_not_reset(self):
        other = KzL(Path(self.temp.name), self.core)
        self.assertEqual(other.ensure()['id'], self.parent['id'])
        self.assertEqual(len(self.core.sessions), 1)
        self.core.sessions.clear()
        with self.assertRaises(KzLError):
            other.ensure()
        self.assertEqual(len(self.core.sessions), 0)

    def test_submit_only_records_and_deduplicates_before_execution(self):
        task = self.submit()
        self.assertEqual(task['state'], 'queued')
        self.assertEqual(self.submit()['id'], task['id'])
        self.assertEqual(len(self.core.sessions), 1)
        with self.assertRaises(KzLError):
            self.submit(text='Different request')

    def test_inherits_plan_and_model_and_worker_survives_phone_disconnection(self):
        task = self.submit()
        restarted = KzL(Path(self.temp.name), self.core)
        restarted.tick()
        child = self.core.sessions[task['child']]
        self.assertEqual(child['agent'], 'plan')
        self.assertEqual(child['model'], self.parent['model'])
        self.assertEqual(child['parentID'], self.parent['id'])
        self.assertEqual(restarted.jobs()[0]['state'], 'admitted')
        restarted.tick()
        self.assertEqual(len([w for w in self.core.writes if w[1].endswith('/prompt')]), 1)

    def test_uncertain_send_is_never_replayed(self):
        self.submit()
        self.core.fail_send = True
        self.kzl.tick()
        self.assertEqual(self.kzl.jobs()[0]['state'], 'uncertain')
        self.core.fail_send = False
        KzL(Path(self.temp.name), self.core).tick()
        self.assertEqual(len([w for w in self.core.writes if w[1].endswith('/prompt')]), 1)

    def test_result_identified_and_mirrored_once_without_resuming_parent(self):
        task = self.submit()
        self.kzl.tick()
        self.core.messages[task['child']].append({'id': 'msg_answer', 'type': 'assistant',
            'time': {'created': 1, 'completed': 2}, 'content': [{'type': 'text', 'text': 'Fixture complete'}]})
        self.core.sessions[task['child']]['outcome'] = 'succeeded'
        self.kzl.tick()
        self.kzl.tick()
        result = self.kzl.jobs()[0]
        self.assertEqual(result['state'], 'completed')
        self.assertEqual(result['result_id'], 'msg_answer')
        self.assertEqual(result['result'], 'Fixture complete')
        mirrors = [w for w in self.core.writes if w[1].endswith('/synthetic')]
        self.assertEqual(len(mirrors), 1)
        self.assertFalse(mirrors[0][2]['resume'])

    def test_foreign_messages_never_report_as_result(self):
        task = self.submit()
        self.kzl.tick()
        self.core.messages[task['child']].append({'id': 'msg_foreign', 'type': 'user'})
        self.core.sessions[task['child']]['outcome'] = 'succeeded'
        self.kzl.tick()
        self.assertEqual(self.kzl.jobs()[0]['state'], 'uncertain')

    def test_cancelling_queued_task_never_submits_it(self):
        task = self.submit()
        self.kzl.cancel(task['id'])
        self.kzl.tick()
        self.assertEqual(self.kzl.jobs()[0]['state'], 'cancelled')
        self.assertEqual(len(self.core.sessions), 1)

    def test_limits_and_validation(self):
        for i in range(4):
            self.submit(call='call_' + str(i))
        with self.assertRaises(KzLError):
            self.submit(call='call_5')
        for payload in ({'callID': '../secret', 'text': 'x'}, {'callID': 'ok', 'text': ''}, {'callID': 'ok', 'text': 'x', 'shell': 'bad'}):
            with self.assertRaises(KzLError):
                self.kzl.submit(payload, 'device')

    def test_new_task_queues_without_concurrent_workspace_writes(self):
        first = self.submit(call='first')
        second = self.submit(call='second')
        self.kzl.tick()
        self.kzl.tick()
        by_id = {job['id']: job for job in self.kzl.jobs()}
        self.assertEqual(by_id[first['id']]['state'], 'running')
        self.assertEqual(by_id[second['id']]['state'], 'queued')

    def test_uncertain_admission_blocks_queue_until_resolved(self):
        first = self.submit(call='first')
        second = self.submit(call='second')
        self.core.fail_send = True
        self.kzl.tick()
        self.core.fail_send = False
        self.kzl.tick()
        self.assertEqual({j['id']: j['state'] for j in self.kzl.jobs()}[second['id']], 'queued')
        self.kzl.cancel(first['id'])
        self.kzl.tick()
        self.kzl.tick()
        self.assertEqual({j['id']: j['state'] for j in self.kzl.jobs()}[second['id']], 'admitted')

    def test_capabilities_only_allowlisted_metadata(self):
        value = self.kzl.capabilities()
        self.assertNotIn('never-return', json.dumps(value))
        self.assertFalse(value['toolCatalogComplete'])
        self.assertTrue(value['servers'][0]['connected'])
        self.assertFalse(value['servers'][1]['connected'])

    def test_persistent_turns_are_idempotent_and_bounded(self):
        turn = {'id': 'turn_1', 'role': 'user', 'text': 'Remember fixture'}
        self.kzl.remember(turn)
        self.kzl.remember(turn)
        self.assertEqual(len(self.kzl.context()['history']), 1)
        with self.assertRaises(KzLError):
            self.kzl.remember(dict(turn, role='system'))

    def test_update_preserves_identity_and_is_not_foreign_input(self):
        task = self.submit()
        self.kzl.tick()
        self.kzl.update(task['id'], 'Read only', 'msg_update')
        self.kzl.tick()
        self.assertEqual(self.kzl.jobs()[0]['state'], 'running')
        with self.assertRaises(KzLError):
            self.kzl.update('../outside', 'x', 'msg_update')
