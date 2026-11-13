"""The identical learning engine on two trusted, separate installed platforms."""

import json
import os
import subprocess
import shutil
import unittest
from unittest.mock import patch

from AutoCua.saccade.business_contract import BusinessError, digest
from AutoCua.saccade.learning_adapter import load_adapter
from AutoCua.saccade.navigation_correction import correction_routes, NavigationTeaching
from AutoCua.saccade.operator_language import navigation_context, spontaneous_correction
from AutoCua.saccade.operator_requests import OperatorRequests
from AutoCua.saccade.platform_learning import PlatformLearningControl
from AutoCua.saccade.platform_registry import list_platforms
from AutoCua.saccade.procedure_store import ProcedureStore
from AutoCua.saccade.session_context import build_platform_context
from tests.business_fixtures import BusinessFixture
from tests.platform_learning_fixtures import install_synthetic, PLATFORM


class SharedPlatformLearning(unittest.TestCase):
    def setUp(self):
        self.fixture = BusinessFixture()
        self.addCleanup(self.fixture.close)
        self.root = self.fixture.root
        self.other = install_synthetic(self.root)

    def control(self, context, chat='chat'):
        return PlatformLearningControl(context, chat, project_root=self.root, conversational=True)

    def event(self, broker, chat, answer):
        item = broker.status(chat)
        return {**{k: item[k] for k in ('run_id', 'intervention_id', 'revision', 'token')}, 'action': 'chat',
                'answer': answer, 'non_sensitive': True, 'presentation_digest': item.get('presentation_digest')}

    def observe(self, control, controls=(), headings=(), **changes):
        elements = {str(n): {'name': name, 'role': role, 'rect': [1, 1, 60, 20]}
                    for n, (name, role) in enumerate([(n, 'link') for n in controls] + [(n, 'heading') for n in headings])}
        elements['private'] = {'name': 'PRIVATE SYNTHETIC ACCOUNT', 'role': 'heading', 'rect': [1, 1, 60, 20]}
        stamp = {'observer': 'synthetic-observer', 'tab': '1', 'platform_id': control.context['platform_id'],
                 'profile': control.context['browser_profile'], 'config_revision': control.context['config_revision'], **changes}
        control.observe_native(elements, stamp)

    def test_shared_chat_lifecycle_and_isolation_for_both_platforms(self):
        for context, labels, text in [(self.fixture.context, ['Purchases', 'Inbox'], 'Click Purchases, then Inbox.'),
                                      (self.other, ['Settings', 'Billing'], 'The correct path is Settings, then Billing.')]:
            with self.subTest(platform=context['platform_id']):
                broker, chat = OperatorRequests(), 'same-chat-' + context['platform_id']
                data = {'task': 'Open ' + labels[1], 'platform_id': context['platform_id'], 'mode': 'web'}
                control = self.control(context, chat)
                initial_pin = control.pin_revision
                broker.configure_teaching(chat, control)
                control.freeze_decision()
                self.observe(control, [labels[0]])
                control.close()
                broker.suspend(chat, 'first-run', data, {'category': 'question', 'reason': 'missing_information', 'request': 'How do I navigate to the section?'})
                kind, continuation = broker.chat(chat, self.event(broker, chat, text), control=control)
                self.assertEqual(kind, 'resume')
                self.assertIn(data['task'], continuation['task'])
                for controls, headings in [([labels[1]], [labels[0]]), ([], [labels[1]])]:
                    control = self.control(context, chat)
                    broker.configure_teaching(chat, control)
                    control.freeze_decision()
                    self.observe(control, controls, headings)
                    request = control.learning_intervention()
                    control.close()
                    broker.suspend(chat, control.run_id, data, request)
                    broker.present_procedure(chat, control)
                    if request['category'] == 'manual_action':
                        self.assertEqual(broker.chat(chat, self.event(broker, chat, 'Done'), control=control)[0], 'resume')
                stale = self.event(broker, chat, 'Yes, remember this')
                self.assertEqual(broker.chat(chat, stale, control=control)[0], 'resume')
                with self.assertRaises(BusinessError):
                    broker.chat(chat, stale, control=control)
                store = ProcedureStore(self.root, context['platform_id'])
                snapshot = store.snapshot(store.active()['current'])
                self.assertEqual(snapshot['schema_version'], 2)
                self.assertEqual(snapshot['platform_id'], context['platform_id'])
                self.assertEqual(snapshot['steps'][0]['verification'], 'manual_heading_transition')
                markdown = (store.root / 'learning.md').read_text(encoding='utf-8')
                self.assertIn(labels[1], markdown)
                self.assertNotIn('PRIVATE', markdown)
                self.assertNotIn('rect', markdown)
                self.assertEqual(store.pin(chat), initial_pin)
                self.assertEqual(self.control(context, chat).overlay(), '')
                future = self.control(context, 'future-' + chat)
                self.assertIn(labels[0], future.overlay())
                foreign = 'Settings' if context['platform_id'] == 'dext' else 'Purchases'
                self.assertNotIn(foreign, future.overlay())
                self.assertNotEqual(store.root, ProcedureStore(self.root, PLATFORM if context['platform_id'] == 'dext' else 'dext').root)

    def test_registry_and_adapter_have_distinct_hosts_profiles_labels_baselines(self):
        self.assertEqual({p.id for p in list_platforms(root=self.root)}, {'dext', PLATFORM})
        self.assertNotEqual(self.fixture.context['browser_profile'], self.other['browser_profile'])
        self.assertNotEqual(self.fixture.context['allowed_hosts'], self.other['allowed_hosts'])
        self.assertNotEqual(ProcedureStore(self.root).baseline, ProcedureStore(self.root, PLATFORM).baseline)
        adapter = load_adapter(self.root, PLATFORM)
        self.assertNotIn('purchases', adapter.labels)

    def test_contextual_spontaneous_correction_unknown_and_ordinary_chat(self):
        for context, task, correction, expected in [(self.fixture.context, 'Open Purchases', 'Non, tu dois ouvrir Achats.', ['purchases']),
                 (self.other, 'Open Billing', 'The correct path is Settings, then Billing.', ['settings_page', 'billing_page'])]:
            adapter = load_adapter(self.root, context['platform_id'])
            self.assertTrue(navigation_context(task, {}, adapter))
            self.assertEqual(spontaneous_correction(correction, eligible=True, navigation=True, adapter=adapter), ('correction', expected))
            self.assertEqual(spontaneous_correction('Please summarize the weather', eligible=True, navigation=True, adapter=adapter)[0], 'ordinary')
            self.assertEqual(spontaneous_correction('No, click the private customer X', eligible=True, navigation=True, adapter=adapter)[0], 'clarify')
            self.assertEqual(spontaneous_correction(correction, eligible=True, navigation=False, adapter=adapter)[0], 'clarify')

    def test_active_correction_requires_checkpoint_and_keeps_binding(self):
        control = self.control(self.other)
        broker = OperatorRequests()
        broker.configure_teaching('chat', control)
        data = {'task': 'Open Billing', 'platform_id': PLATFORM}
        broker.begin_run('chat', 'run', data)
        broker.propose_correction('chat', 'run', data, ['billing_page'], active=True)
        self.assertEqual(broker.status('chat')['state'], 'pausing_operator')
        with self.assertRaises(BusinessError):
            broker.chat('chat', self.event(broker, 'chat', 'Continue'), control=control)
        broker.complete_correction_pause('chat', 'run', available=True, control=control)
        # Worker end_run/suspend changes the checkpoint state in production.
        broker.pending['chat']['state'] = 'waiting_operator'
        self.assertEqual(broker.chat('chat', self.event(broker, 'chat', 'Continue'), control=control)[0], 'resume')
        self.assertEqual(broker._teaching['chat'].adapter.platform_id, PLATFORM)
        resumed = self.control(self.other)
        broker.configure_teaching('chat', resumed)
        resumed.freeze_decision()
        self.observe(resumed, ['Billing'])
        self.assertEqual(resumed.learning_intervention()['category'], 'manual_action')

    def test_foreign_stamp_tracker_proposal_and_pin_are_rejected(self):
        first, second = self.control(self.fixture.context), self.control(self.other)
        with self.assertRaises(BusinessError):
            second.attach_teaching(NavigationTeaching(['purchases']))
        with self.assertRaises(BusinessError):
            self.observe(second, ['Billing'], platform_id='dext')
        with self.assertRaises(BusinessError):
            self.observe(second, ['Billing'], profile='saccade-dext')
        proposal = first.store.propose_steps(first.store.adapter.steps(['purchases']), 'run')
        shutil.copyfile(first.store.root / ('proposals/' + proposal['proposal_id'] + '.json'), second.store.root / ('proposals/' + proposal['proposal_id'] + '.json'))
        with self.assertRaises(BusinessError):
            second.store.review(proposal['proposal_id'], proposal['base_revision'], proposal['candidate_revision'], True)
        foreign = first.store.pin('foreign')
        shutil.copyfile(first.store.root / ('snapshots/' + foreign + '.json'), second.store.root / ('snapshots/' + foreign + '.json'))
        with self.assertRaises(BusinessError):
            second.store.snapshot(foreign)
        broker = OperatorRequests()
        broker.suspend('chat', 'run', {'task': 'Open Billing', 'platform_id': PLATFORM}, {'category': 'question', 'reason': 'missing_information', 'request': 'Which section?'})
        with self.assertRaises(BusinessError):
            broker.configure_teaching('chat', first)

    def test_legacy_dext_hash_pins_and_revisions_stay_immutable(self):
        store = ProcedureStore(self.root)
        initial = {'schema_version': 1, 'source': 'baseline', 'content': '', 'baseline_digest': digest(''), 'routes': []}
        self.assertEqual(store.pin('old'), digest(initial))
        proposal = store.propose(['purchases'], 'legacy')
        store.review(proposal['proposal_id'], proposal['base_revision'], proposal['candidate_revision'], True)
        old_bytes = (store.root / ('snapshots/' + proposal['candidate_revision'] + '.json')).read_bytes()
        self.control(self.fixture.context, 'new')
        self.assertEqual((store.root / ('snapshots/' + proposal['candidate_revision'] + '.json')).read_bytes(), old_bytes)
        self.assertEqual(store.pin('old'), digest(initial))
        addition = store.propose_steps(store.adapter.steps(['bank']), 'new')
        store.review(addition['proposal_id'], addition['base_revision'], addition['candidate_revision'], True)
        self.assertIn('Purchases', (store.root / 'learning.md').read_text(encoding='utf-8'))
        self.assertEqual(store.pin('old'), digest(initial))

    def test_legacy_identity_cautions_survive_new_neutral_learning_without_reapproval_of_history(self):
        store = ProcedureStore(self.root)
        proposal = store.propose(['workspace', 'record', 'review'], 'legacy')
        store.review(proposal['proposal_id'], proposal['base_revision'], proposal['candidate_revision'], True)
        old = store.snapshot(proposal['candidate_revision'])['content']
        addition = store.propose_steps(store.adapter.steps(['purchases']), 'new')
        self.assertIn(old, addition['new'])
        store.review(addition['proposal_id'], addition['base_revision'], addition['candidate_revision'], True)
        next_addition = store.propose_steps(store.adapter.steps(['bank']), 'next')
        self.assertIn(old, next_addition['new'])
        self.assertIn('Purchases', next_addition['new'])
        self.assertEqual(store.snapshot(proposal['candidate_revision'])['content'], old)

    def test_matching_baselines_do_not_allow_foreign_snapshot_or_approval(self):
        (self.root / 'AutoCua/default_skills/web/domain_skill' / (PLATFORM + '.md')).write_text('', encoding='utf-8')
        first, second = ProcedureStore(self.root), ProcedureStore(self.root, PLATFORM)
        self.assertEqual(first.baseline_digest, second.baseline_digest)
        revision = first.active()['current']
        shutil.copyfile(first.root / ('snapshots/' + revision + '.json'), second.root / ('snapshots/' + revision + '.json'))
        with self.assertRaisesRegex(BusinessError, 'platform_mismatch'):
            second.snapshot(revision)
        proposal = first.propose_steps(first.adapter.steps(['purchases']), 'source')
        shutil.copyfile(first.root / ('proposals/' + proposal['proposal_id'] + '.json'), second.root / ('proposals/' + proposal['proposal_id'] + '.json'))
        with self.assertRaises(BusinessError):
            second.review(proposal['proposal_id'], proposal['base_revision'], proposal['candidate_revision'], True)

    def test_crash_recovery_and_tampering_are_platform_local(self):
        first, second = ProcedureStore(self.root), ProcedureStore(self.root, PLATFORM)
        before = first.active()
        proposal = second.propose_steps(second.adapter.steps(['billing_page']), 'run')
        original = second._publish
        def crash(name, content, **kwargs):
            if name == 'learning.md':
                raise OSError('synthetic publication crash')
            return original(name, content, **kwargs)
        with patch.object(second, '_publish', side_effect=crash), self.assertRaises(OSError):
            second.review(proposal['proposal_id'], proposal['base_revision'], proposal['candidate_revision'], True)
        recovered = ProcedureStore(self.root, PLATFORM)
        self.assertEqual(recovered.active()['current'], proposal['candidate_revision'])
        self.assertIn('Billing', (recovered.root / 'learning.md').read_text(encoding='utf-8'))
        self.assertEqual(first.active(), before)
        (recovered.root / 'learning.md').write_text('unapproved private changes', encoding='utf-8')
        with self.assertRaises(BusinessError):
            ProcedureStore(self.root, PLATFORM)
        self.assertEqual(first.active(), before)

    def test_invalid_identity_unsupported_labels_and_changed_metadata_fail_closed(self):
        for platform in ('../dext', '/dext', 'missing', 'DEXT'):
            with self.subTest(platform=platform), self.assertRaises(ValueError):
                ProcedureStore(self.root, platform)
        adapter = load_adapter(self.root, PLATFORM)
        for text in ('Open Purchases', 'Open Billing for PRIVATE CUSTOMER', 'Open https://evil.test', 'Open Billing and execute script', 'Open Billing password 123456'):
            with self.subTest(text=text), self.assertRaises(BusinessError):
                correction_routes(text, adapter)
        control = self.control(self.other)
        path = self.root / 'platforms' / PLATFORM / 'learning.json'
        value = json.loads(path.read_text(encoding='utf-8'))
        value['landmarks'][0]['label'] = 'Other settings'
        path.write_text(json.dumps(value), encoding='utf-8')
        with self.assertRaises(BusinessError):
            control.overlay()

    def test_rejection_rollback_and_locks_remain_independent(self):
        stores = [ProcedureStore(self.root), ProcedureStore(self.root, PLATFORM)]
        for store, route in zip(stores, ('purchases', 'billing_page')):
            with self.subTest(platform=store.platform_id):
                initial = store.active()
                refused = store.propose_steps(store.adapter.steps([route]), 'rejected')
                store.review(refused['proposal_id'], refused['base_revision'], refused['candidate_revision'], False)
                self.assertEqual(store.active(), initial)
                proposal = store.propose_steps(store.adapter.steps([route]), 'approved')
                store.review(proposal['proposal_id'], proposal['base_revision'], proposal['candidate_revision'], True)
                store.rollback(proposal['candidate_revision'], initial['current'], 'rollback')
                self.assertEqual((store.root / 'learning.md').read_bytes().decode('utf-8'), store.baseline)
                self.assertEqual(store.snapshot(initial['current'])['content'], store.baseline)
        with stores[0].lock(), stores[1].lock():
            self.assertNotEqual(stores[0].root / 'store.lock', stores[1].root / 'store.lock')

    def test_source_heading_evidence_does_not_cross_observer_or_tab(self):
        control = self.control(self.other)
        control.freeze_decision()
        control.attach_teaching(NavigationTeaching(['billing_page'], adapter=control.store.adapter))
        self.observe(control, ['Billing'])
        self.observe(control, [], ['Billing'], observer='different-observer')
        self.assertEqual(control.teaching.index, 0)
        self.observe(control, ['Billing'], observer='different-observer')
        self.observe(control, [], ['Billing'], observer='different-observer', tab='2')
        self.assertEqual(control.teaching.index, 0)
        self.assertIsNone(control.proposal)

    def test_second_platform_directory_reparse_is_rejected_before_publication(self):
        target = self.root / 'synthetic-redirect'
        target.mkdir()
        data = self.root / 'platforms' / PLATFORM / 'data'
        if os.name == 'nt':
            result = subprocess.run(['cmd', '/c', 'mklink', '/J', str(data), str(target)], capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))
        else:
            data.symlink_to(target, target_is_directory=True)
        with self.assertRaises(BusinessError):
            ProcedureStore(self.root, PLATFORM)
        self.assertEqual(list(target.iterdir()), [])

    def test_untrusted_adapter_configuration_never_enables_learning(self):
        path = self.root / 'platforms' / PLATFORM / 'learning.json'
        original = path.read_bytes()
        for mutate in (
            lambda v: v.update(platform_id='dext'),
            lambda v: v.update(execute_script='forbidden'),
            lambda v: v['landmarks'].append(v['landmarks'][0]),
            lambda v: v['landmarks'][1].update(aliases=['Settings']),
            lambda v: v['landmarks'][0].update(label='password'),
            lambda v: v['landmarks'][0].update(label='https://evil.test'),
        ):
            value = json.loads(original)
            mutate(value)
            path.write_text(json.dumps(value), encoding='utf-8')
            with self.subTest(value=value), self.assertRaises(BusinessError):
                load_adapter(self.root, PLATFORM)
        path.write_bytes(original.replace(b'"schema_version": 1', b'"schema_version": 1, "schema_version": 1'))
        with self.assertRaises(BusinessError):
            load_adapter(self.root, PLATFORM)

    def test_missing_adapter_contract_requires_clarification_and_has_no_authority(self):
        fixture = BusinessFixture()
        self.addCleanup(fixture.close)
        context = install_synthetic(fixture.root, learning=False)
        empty = load_adapter(fixture.root, PLATFORM)
        self.assertEqual(empty.labels, {})
        control = PlatformLearningControl(context, 'adapter-free-chat', project_root=fixture.root)
        self.assertEqual(control.overlay(), '')
        self.assertEqual(spontaneous_correction('No, open Settings', eligible=True, navigation=True, adapter=empty)[0], 'clarify')
        with self.assertRaises(BusinessError):
            empty.steps(['settings_page'])
