import json
import os
from pathlib import Path
import tempfile
import time
import unittest
import sys

from backend import Store, Gateway, DemoGateway, PocketError, ReadRetry, activity_rows, search_loaded_messages, tool_state_label, tool_progress, conversation_export, attachment, prompt_payload, field_visible, form_answers, artifacts, save_download, experimental_session_path, schedule_payload

# Reuse only the synthetic fixture server, never the installed gateway.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'preview'))
from transport_fixture import start_fixture, FixtureGateway


class BackendTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_loaded_search_is_literal_case_insensitive_and_excludes_tools(self):
        messages = [{'id': 'msg_a', 'type': 'user', 'text': 'Before [x].* ÁUDIO after'},
                    {'id': 'msg_a', 'type': 'user', 'text': 'duplicate [x].* áudio'},
                    {'id': 'msg_b', 'type': 'assistant', 'content': [{'type': 'tool', 'text': 'private needle'}]},
                    {'id': 'msg_c', 'type': 'system', 'text': 'private needle'}]
        self.assertEqual(search_loaded_messages(messages, '[x].* áudio'), [{'id': 'msg_a', 'role': 'user', 'preview': 'Before [x].* ÁUDIO after'}])
        self.assertFalse(search_loaded_messages(messages, 'private needle'))
        self.assertFalse(search_loaded_messages(messages, '   '))
        with self.assertRaises(PocketError):
            search_loaded_messages(messages, 'x'*257)

    def test_loaded_search_caps_results_and_shows_context_near_match(self):
        messages = [{'id': f'msg_{i}', 'type': 'assistant', 'text': 'x'*1000 + 'needle' + 'y'*1000} for i in range(101)]
        found = search_loaded_messages(messages, 'needle')
        self.assertEqual(len(found), 100)
        self.assertIn('needle', found[0]['preview'])
        self.assertLess(len(found[0]['preview']), 200)

    def test_tool_progress_never_labels_error_or_unknown_as_completed(self):
        tools = [{'state': {'status': status}} for status in ('running', 'streaming', 'completed', 'error', 'future')]
        summary = tool_progress(tools)
        for expected in ('Em execução: 1', 'Preparando entrada: 1', 'Concluída: 1', 'Falhou: 1', 'Estado não confirmado: 1'):
            self.assertIn(expected, summary)
        self.assertNotIn('Concluída', tool_progress([{'state': {'status': 'error'}}, {'state': None}]))
        self.assertEqual(tool_state_label({'state': 'invalid'}), 'Estado não confirmado')

    def test_conversation_export_is_literal_text_not_state_or_attachment_dump(self):
        session = {'id': 'ses_a', 'title': 'Review', 'token': 'private credential'}
        messages = [{'id': 'msg_a', 'type': 'user', 'text': '<script>literal</script> á\n\tcode', 'files': [{'uri': 'data:SECRET_FILE'}]},
                    {'id': 'msg_a', 'type': 'user', 'text': 'duplicate'},
                    {'id': 'msg_b', 'type': 'assistant', 'content': [{'type': 'text', 'text': 'Answer'}, {'type': 'tool', 'text': 'SECRET_TOOL'}]},
                    {'id': 'msg_c', 'type': 'system', 'text': 'SECRET_SYSTEM'}]
        text = conversation_export(session, messages).decode('utf-8')
        self.assertIn('Cópia parcial', text); self.assertIn('<script>literal</script> á\n\tcode', text); self.assertIn('Answer', text)
        for omitted in ('SECRET_FILE', 'SECRET_TOOL', 'SECRET_SYSTEM', 'private credential', 'duplicate'):
            self.assertNotIn(omitted, text)

    def test_conversation_export_refuses_oversize_without_truncation(self):
        with self.assertRaises(PocketError):
            conversation_export({'id': 'ses_a'}, [{'id': 'msg_a', 'type': 'user', 'text': 'x'*(8*1024*1024)}])

    def test_creation_intent_survives_reload_and_requires_explicit_review(self):
        store = Store(self.root/'creations')
        identifier = store.begin_creation('/fixture/a')
        again = Store(self.root/'creations')
        self.assertEqual(again.pending_creations('/fixture/a')[0]['state'], 'attempted')
        with self.assertRaises(PocketError):
            again.begin_creation('/fixture/a')
        again.mark_creation(identifier, 'uncertain'); again.save()
        self.assertEqual(Store(self.root/'creations').pending_creations('/fixture/a')[0]['state'], 'uncertain')
        again.mark_creation(identifier, 'reviewed'); again.save()
        next_id = again.begin_creation('/fixture/a')
        self.assertNotEqual(identifier, next_id)
        again.mark_creation(next_id, 'acknowledged', 'ses_new'); again.mark_creation(next_id, 'uncertain')
        self.assertFalse(again.pending_creations('/fixture/a'))
        self.assertEqual(again.data['creations'][next_id]['sessionID'], 'ses_new')

    def test_creation_capacity_and_invalid_directory_never_drop_pending_intent(self):
        store = Store(self.root/'creations')
        for value in ('', 'bad\npath', 4):
            with self.assertRaises(PocketError):
                store.begin_creation(value)
        store.data['creations'] = {str(i): {'directory': str(i), 'state': 'uncertain'} for i in range(100)}
        with self.assertRaises(PocketError):
            store.begin_creation('/fixture/new')
        self.assertEqual(len(store.data['creations']), 100)

    def test_review_journal_locks_question_and_opposite_permission_after_restart(self):
        store = Store(self.root/'reviews'); binding = {'id': 'ses_a'}
        permission = store.begin_action(binding, 'permission', {'id': 'per_a', 'decision': 'once'})
        store.mark_action(permission, 'uncertain'); store.save()
        again = Store(self.root/'reviews')
        with self.assertRaises(PocketError):
            again.begin_action(binding, 'permission', {'id': 'per_a', 'decision': 'reject'})
        form = again.begin_action(binding, 'form', {'id': 'form_a', 'answer': {'text': 'snapshot'}})
        again.mark_action(form, 'uncertain'); again.save()
        with self.assertRaises(PocketError):
            Store(self.root/'reviews').begin_action(binding, 'form', {'id': 'form_a', 'answer': {'text': 'different'}})
        with self.assertRaises(PocketError):
            again.begin_action(binding, 'permission', {'id': 'per_other', 'decision': 'always'})
        again.mark_action(permission, 'acknowledged')
        with self.assertRaises(PocketError):
            again.begin_action(binding, 'permission', {'id': 'per_a', 'decision': 'once'})

    def test_rename_interrupt_journal_validates_and_locks_unresolved_actions(self):
        store = Store(self.root/'mutations'); binding = {'id': 'ses_a', 'title': 'Original', 'directory': '/fixture'}
        rename = store.begin_action(binding, 'rename', {'title': 'New'})
        store.mark_action(rename, 'uncertain'); store.save()
        again = Store(self.root/'mutations')
        with self.assertRaises(PocketError):
            again.begin_action(binding, 'rename', {'title': 'Different'})
        interrupt = again.begin_action(binding, 'interrupt', {})
        with self.assertRaises(PocketError):
            again.begin_action(binding, 'interrupt', {})
        again.mark_action(interrupt, 'acknowledged')
        self.assertEqual(again.action_records('ses_a')[0]['state'], 'acknowledged')
        for kind, payload in [('rename', {'title': ''}), ('rename', {'title': 'x'*201}), ('interrupt', {'unexpected': True})]:
            with self.assertRaises(PocketError):
                again.begin_action(binding, kind, payload)

    def test_activity_diff_is_literal_bounded_and_explicit_about_truncation(self):
        rows = activity_rows('diff', {'data': [{'file': '<script>$(touch x)', 'patch': 'x'*13000, 'status': 'modified', 'additions': 3, 'deletions': 1}]}, 'ses_a')
        self.assertEqual(rows[0]['title'], '<script>$(touch x)')
        self.assertIn('+3 / −1', rows[0]['detail'])
        self.assertIn('Prévia limitada', rows[0]['body'])
        self.assertLess(len(rows[0]['body']), 12100)

    def test_activity_tasks_filter_conversation_and_do_not_invent_confirmation(self):
        tasks = [{'parent': 'ses_a', 'text': 'Review', 'state': 'running', 'confirmed': False}, {'parent': 'ses_b', 'text': 'Foreign', 'state': 'completed'}]
        rows = activity_rows('tasks', {'tasks': tasks}, 'ses_a')
        self.assertEqual(len(rows), 1)
        self.assertIn('Sem confirmação', rows[0]['detail'])
        self.assertEqual(activity_rows('terminal', {'data': None}, 'ses_a'), [])

    def test_action_journal_restart_lock_review_and_snapshot(self):
        store = Store(self.root/'actions')
        binding = {'id': 'ses_a', 'title': 'A', 'directory': '/fixture/a'}
        payload = {'name': 'check', 'text': 'original'}
        identifier = store.begin_action(binding, 'command', payload)
        payload['text'] = 'changed'
        again = Store(self.root/'actions')
        self.assertEqual(again.action_records('ses_a')[0]['payload']['text'], 'original')
        with self.assertRaises(PocketError):
            again.begin_action(binding, 'command', payload)
        again.mark_action(identifier, 'uncertain'); again.save()
        self.assertEqual(Store(self.root/'actions').action_records('ses_a')[0]['state'], 'uncertain')
        again.mark_action(identifier, 'reviewed'); again.save()
        self.assertNotEqual(identifier, again.begin_action(binding, 'command', payload))

    def test_action_acknowledgement_is_not_downgraded_and_records_are_copies(self):
        store = Store(self.root/'actions')
        identifier = store.begin_action({'id': 'ses_a'}, 'skill', {'id': 'fixture', 'resume': True})
        store.mark_action(identifier, 'acknowledged'); store.mark_action(identifier, 'uncertain')
        records = store.action_records('ses_a'); records[0]['payload']['id'] = 'changed'
        self.assertEqual(store.action_records('ses_a')[0]['state'], 'acknowledged')
        self.assertEqual(store.action_records('ses_a')[0]['payload']['id'], 'fixture')
        self.assertEqual(store.action_records('ses_b'), [])

    def test_action_capacity_preserves_unresolved_records(self):
        store = Store(self.root/'actions')
        store.data['actions'] = {str(i): {'state': 'uncertain'} for i in range(200)}
        with self.assertRaises(PocketError):
            store.begin_action({'id': 'ses_a'}, 'skill', {'id': 'fixture', 'resume': True})
        self.assertEqual(len(store.data['actions']), 200)

    def test_inbox_requires_matching_session_user_and_delivery(self):
        store = Store(self.root/'inbox'); draft = {'text': 'queued', 'files': []}
        store.data['drafts']['ses_a'] = draft; payload = store.begin_prompt('ses_a', draft)
        valid = {'id': payload['id'], 'sessionID': 'ses_a', 'type': 'user', 'delivery': 'queue'}
        for changes in ({'sessionID': 'ses_b'}, {'type': 'synthetic'}, {'delivery': 'other'}):
            result = store.reconcile_inbox('ses_a', [dict(valid, **changes)])
            self.assertFalse(result['admitted']); self.assertEqual(draft['text'], 'queued')
        draft['text'] = 'new edit'
        result = store.reconcile_inbox('ses_a', [valid])
        self.assertTrue(result['admitted']); self.assertFalse(result['draft_cleared'])
        self.assertEqual(draft['text'], 'new edit')

    def test_read_retry_single_flight_backoff_and_manual_retry(self):
        gate = ReadRetry()
        self.assertTrue(gate.begin(now=0))
        self.assertFalse(gate.begin(manual=True, now=0))
        gate.failure(now=0)
        self.assertFalse(gate.begin(now=1))
        self.assertTrue(gate.begin(now=2))
        gate.failure(now=2)
        self.assertEqual(gate.next_at, 6)
        self.assertFalse(gate.begin(now=5))
        self.assertTrue(gate.begin(manual=True, now=5))
        gate.success()
        self.assertTrue(gate.ready)
        self.assertFalse(gate.begin(now=100))
        self.assertTrue(gate.begin(repeat=True, now=100))

    def test_read_retry_delay_is_capped_and_stale_work_can_be_abandoned(self):
        gate = ReadRetry()
        for _ in range(20):
            gate.failure(now=10)
        self.assertEqual(gate.next_at, 40)
        self.assertTrue(gate.begin(now=40))
        gate.invalidate()
        self.assertFalse(gate.begin(manual=True, now=40))
        gate.abandon()
        self.assertTrue(gate.begin(now=40))

    def test_private_persistence(self):
        store = Store(self.root / 'state')
        store.data['drafts']['ses_test'] = {'text': 'rascunho', 'files': []}
        store.save()
        again = Store(self.root / 'state')
        self.assertEqual(again.data['drafts']['ses_test']['text'], 'rascunho')
        self.assertEqual(os.stat(self.root / 'state/preferences.json').st_mode & 0o777, 0o600)
        self.assertEqual(os.stat(self.root / 'state').st_mode & 0o777, 0o700)

    def test_corrupt_preferences_preserved(self):
        path = self.root / 'preferences.json'; path.write_text('broken')
        with self.assertRaises(ValueError):
            Store(self.root)
        self.assertEqual(path.read_text(), 'broken')

    def test_attachment_types_and_limits(self):
        path = self.root / 'code.py'; path.write_text('print("fixture")')
        file = attachment(path)
        self.assertTrue(file['uri'].startswith('data:text/plain;base64,'))
        path.write_bytes(b'\xff\xfe\x00')
        with self.assertRaises(PocketError):
            attachment(path)
        path.write_bytes(b'x' * (4*1024*1024+1))
        with self.assertRaises(PocketError):
            attachment(path)

    def test_stable_request_id_until_content_changes(self):
        draft = {'text': 'hello', 'files': []}
        first = prompt_payload(draft); second = prompt_payload(draft)
        self.assertEqual(first['id'], second['id'])
        draft['text'] = 'changed'
        self.assertNotEqual(first['id'], prompt_payload(draft)['id'])
        draft = {'text': '', 'files': []}
        with self.assertRaises(PocketError):
            prompt_payload(draft)

    def test_outgoing_attempt_survives_restart_before_acknowledgement(self):
        store = Store(self.root/'journal'); draft = {'text': 'fixture request', 'files': []}
        store.data['drafts']['ses_fixture'] = draft
        payload = store.begin_prompt('ses_fixture', draft)
        again = Store(self.root/'journal')
        self.assertEqual(again.pending_prompts('ses_fixture'), [payload['id']])
        self.assertEqual(again.data['drafts']['ses_fixture']['requestID'], payload['id'])
        retry = again.begin_prompt('ses_fixture', again.data['drafts']['ses_fixture'])
        self.assertEqual(retry['id'], payload['id'])

    def test_history_admission_clears_only_identical_draft(self):
        store = Store(self.root/'journal'); draft = {'text': 'fixture request', 'files': []}
        store.data['drafts']['ses_fixture'] = draft; payload = store.begin_prompt('ses_fixture', draft)
        result = store.reconcile_prompts('ses_fixture', [{'id': payload['id'], 'type': 'user'}])
        self.assertTrue(result['draft_cleared']); self.assertFalse(result['pending'])
        self.assertEqual(store.data['outgoing'][payload['id']]['state'], 'admitted')
        self.assertEqual(store.data['drafts']['ses_fixture']['text'], '')

    def test_history_does_not_erase_new_text_or_accept_assistant_as_admission(self):
        store = Store(self.root/'journal'); draft = {'text': 'original', 'files': []}
        store.data['drafts']['ses_fixture'] = draft; payload = store.begin_prompt('ses_fixture', draft)
        draft['text'] = 'new user draft'
        self.assertFalse(store.reconcile_prompts('ses_fixture', [{'id': payload['id'], 'type': 'assistant'}])['admitted'])
        result = store.reconcile_prompts('ses_fixture', [{'id': payload['id'], 'type': 'user'}])
        self.assertTrue(result['admitted']); self.assertFalse(result['draft_cleared'])
        self.assertEqual(draft['text'], 'new user draft')
        self.assertTrue(store.mark_prompt(payload['id'], 'uncertain'))  # Later transport error cannot undo proof of admission.
        self.assertEqual(store.data['outgoing'][payload['id']]['state'], 'admitted')

    def test_changed_retry_keeps_prior_uncertain_request_record(self):
        store = Store(self.root/'journal'); draft = {'text': 'one', 'files': []}
        store.data['drafts']['ses_fixture'] = draft; first = store.begin_prompt('ses_fixture', draft)
        store.mark_prompt(first['id'], 'uncertain'); draft['text'] = 'two'
        second = store.begin_prompt('ses_fixture', draft)
        self.assertNotEqual(first['id'], second['id'])
        self.assertEqual(set(store.pending_prompts('ses_fixture')), {first['id'], second['id']})

    def test_outgoing_capacity_never_discards_uncertain_records(self):
        store = Store(self.root/'journal')
        store.data['outgoing'] = {f'msg_{index:032x}': {'sessionID': 'ses_old', 'state': 'uncertain'} for index in range(200)}
        with self.assertRaises(PocketError):
            store.begin_prompt('ses_fixture', {'text': 'not sent', 'files': []})
        self.assertEqual(len(store.pending_prompts('ses_old')), 200)

    def test_total_attachment_limit(self):
        file = {'name': 'fixture', 'size': 4*1024*1024, 'uri': 'data:text/plain;base64,eA=='}
        with self.assertRaises(PocketError):
            prompt_payload({'text': '', 'files': [file]*3})

    def test_demo_new_chat_send_and_deduplication(self):
        demo = DemoGateway()
        session = demo.request('/api/session', 'POST', {'location': {'directory': '/fixture'}})['data']
        self.assertEqual(session['location']['directory'], '/fixture')
        path = '/api/session/' + session['id']
        payload = prompt_payload({'text': 'fixture', 'files': []})
        demo.request(path+'/prompt', 'POST', payload); demo.request(path+'/prompt', 'POST', payload)
        self.assertEqual(len(demo.request(path+'/message')['data']), 2)
        time.sleep(.03)
        self.assertTrue(demo.request(path+'/message')['data'][-1]['text'])
        demo.request(path+'/interrupt', 'POST', {})
        self.assertTrue(demo.request(path+'/message')['data'][-1]['time']['completed'])

    def test_demo_modes_and_permissions(self):
        demo = DemoGateway(); path = '/api/session/ses_demo'
        demo.request(path+'/agent', 'POST', {'agent': 'plan'})
        demo.request(path, 'PATCH', {'title': 'Renamed'})
        self.assertEqual(demo.request(path)['data']['agent'], 'plan')
        self.assertEqual(demo.request(path)['data']['title'], 'Renamed')
        demo.permissions['ses_demo'] = [{'id': 'per_fixture'}]
        demo.request(path+'/permission/per_fixture/reply', 'POST', {'decision': 'reject'})
        self.assertFalse(demo.request(path+'/permission')['data'])

    def test_real_transport_against_isolated_fixture(self):
        server = start_fixture()
        try:
            gateway = Gateway(self.root, server.server_port)
            with self.assertRaises(PocketError):
                gateway.request('/api/session')
            gateway.pair('123456')
            self.assertEqual(os.stat(self.root/'connection.json').st_mode & 0o777, 0o600)
            data = gateway.request('/api/session?limit=30')
            self.assertEqual(data['data'][0]['id'], 'ses_connected')
            self.assertEqual(FixtureGateway.calls[-1][2], 'Bearer fixture-secret-only')
            self.assertEqual(gateway.request('/phone/files/download?root=home&path=fixture', binary=True), b'fixture file\n')
            with self.assertRaises(PocketError):
                gateway.request('/phone/files/download?root=home&path=fixture&corrupt=true', binary=True)
            again = Gateway(self.root, server.server_port)
            self.assertEqual(again.token, gateway.token)
            with self.assertRaisesRegex(PocketError, 'Agendamentos estão desativados'):
                gateway.request('/api/experimental/schedule?disabled=true')
            for path in ['https://evil.invalid', '/api/../secret', '/api/%73ession', '/phone/power/off', '/api/experimental/voice/session', '/phone/control/start']:
                with self.assertRaises(PocketError):
                    gateway.request(path)
        finally:
            server.shutdown(); server.server_close()

    def test_form_visibility_validation_and_types(self):
        form = {'fields': [{'key': 'mode', 'type': 'string', 'required': True, 'options': [{'value': 'build'}]}, {'key': 'count', 'type': 'integer', 'required': True, 'when': [{'key': 'mode', 'op': 'eq', 'value': 'build'}]}, {'key': 'hidden', 'type': 'string', 'hidden': True}]}
        self.assertFalse(field_visible(form['fields'][1], {'mode': 'plan'}))
        self.assertEqual(form_answers(form, {'mode': 'build', 'count': '2', 'hidden': 'omit'}), {'mode': 'build', 'count': 2})
        for answers in [{}, {'mode': 'unknown'}, {'mode': 'build', 'count': 'NaN'}, {'mode': 'build', 'count': '1.5'}]:
            with self.assertRaises(PocketError):
                form_answers(form, answers)

    def test_experimental_skill_path_has_no_duplicated_api(self):
        self.assertEqual(experimental_session_path('ses_test', 'skill'), '/api/experimental/session/ses_test/skill')
        with self.assertRaises(PocketError):
            experimental_session_path('../invalid', 'skill')

    def test_generated_reference_paths_are_local_and_bounded(self):
        message = {'text': '[Report](out/report.pdf) [Remote](https://evil.invalid/a) [Traversal](%2e%2e/secret) [Host](file://evil.invalid/a) [Abs](file:///home/test/result.txt)'}
        found = artifacts(message, '/home/test/project')
        self.assertEqual([f['path'] for f in found], ['/home/test/project/out/report.pdf', '/home/test/result.txt'])
        self.assertFalse(artifacts(message, 'relative'))
        self.assertFalse(artifacts({'text': '[bad](out/%00name.txt)'}, '/home/test/project'))

    def test_atomic_download_save_and_no_unapproved_overwrite(self):
        path = self.root / 'output.txt'
        save_download(path, b'original')
        with self.assertRaises(PocketError):
            save_download(path, b'changed')
        self.assertEqual(path.read_bytes(), b'original')
        save_download(path, b'confirmed replacement', overwrite=True)
        self.assertEqual(path.read_bytes(), b'confirmed replacement')
        link = self.root / 'link'; link.symlink_to(path)
        with self.assertRaises(PocketError):
            save_download(link, b'unsafe', overwrite=True)
        self.assertFalse(list(self.root.glob('.pocket-download-*')))

    def test_schedule_create_pause_resume_delete_and_validation(self):
        demo = DemoGateway()
        payload = schedule_payload('ses_demo', 'fixture scheduled task', '2030-01-01T15:00:00+03:00', now=0)
        self.assertEqual(payload['when']['at'], '2030-01-01T12:00:00Z')
        item = demo.request('/api/experimental/schedule', 'POST', payload)['data']
        route = '/api/experimental/schedule/' + item['id']
        demo.request(route+'/pause', 'POST', {})
        self.assertEqual(demo.request('/api/experimental/schedule')['data'][0]['status'], 'paused')
        demo.request(route+'/resume', 'POST', {})
        self.assertEqual(demo.request('/api/experimental/schedule')['data'][0]['status'], 'active')
        demo.request(route, 'DELETE')
        self.assertFalse(demo.request('/api/experimental/schedule')['data'])
        for text, date in [('', '2030-01-01T12:00:00Z'), ('task', '2030-01-01T12:00:00'), ('task', 'bad'), ('task', '2000-01-01T12:00:00Z')]:
            with self.assertRaises(PocketError):
                schedule_payload('ses_demo', text, date)


if __name__ == '__main__':
    unittest.main()
