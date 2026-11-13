"""Synthetic conversational assistance using the real broker/control/store."""

import unittest

from AutoCua.saccade.business_contract import BusinessError
from AutoCua.saccade.dext_control import DextRunControl
from AutoCua.saccade.navigation_correction import correction_routes, landmarks, NavigationTeaching
from AutoCua.saccade.operator_requests import OperatorRequests
from AutoCua.saccade.procedure_store import ProcedureStore
from tests.business_fixtures import BusinessFixture


class ConversationalOperatorContracts(unittest.TestCase):
    def setUp(self):
        self.fixture = BusinessFixture()
        self.addCleanup(self.fixture.close)
        self.broker = OperatorRequests()
        self.data = {'provider': 'fake', 'model': 'fake', 'task': 'Find synthetic purchase invoices', 'mode': 'web', 'platform_id': 'dext'}
        self.control = self.new_control()
        self.pause('question', 'How do I reach the purchase invoices section?')

    def new_control(self):
        control = DextRunControl(self.fixture.context, 'chat', project_root=self.fixture.root, conversational=True)
        self.addCleanup(control.close)
        self.broker.configure_teaching('chat', control)
        control.freeze_decision()
        return control

    def pause(self, category, text, data=None):
        self.broker.suspend('chat', 'synthetic-run', data or self.data,
            {'category': category, 'reason': 'authentication_required' if category == 'authentication' else 'missing_information', 'request': text})

    def event(self, answer):
        item = self.broker.status('chat')
        return {**{key: item[key] for key in ('run_id', 'intervention_id', 'revision', 'token')},
                'action': 'chat', 'answer': answer, 'non_sensitive': True, 'presentation_digest': item.get('presentation_digest')}

    def chat(self, answer):
        return self.broker.chat('chat', self.event(answer), control=self.control)

    def observe(self, controls=(), headings=()):
        elements = {str(n): {'name': name, 'role': role, 'rect': [1, 1, 50, 20]}
                    for n, (name, role) in enumerate([(name, 'link') for name in controls] + [(name, 'heading') for name in headings], 1)}
        elements['999'] = {'name': 'PRIVATE SYNTHETIC CUSTOMER 12345', 'role': 'heading', 'rect': [1, 1, 50, 20]}
        self.control.observe_native(elements, {'observer': 'synthetic-observer', 'tab': '1',
            'profile': 'saccade-dext', 'config_revision': self.fixture.context['config_revision']})

    def advance(self, controls=(), headings=()):
        self.control = self.new_control()
        self.observe(controls, headings)
        request = self.control.learning_intervention()
        self.control.close()
        self.broker.suspend('chat', 'next-run', self.data, request)
        self.broker.present_procedure('chat', self.control)
        return request

    def ready_proposal(self):
        self.observe(['Purchases'])
        self.control.close()
        kind, data = self.chat('Click Purchases, then Inbox.')
        self.assertEqual(kind, 'resume')
        self.assertIn(self.data['task'], data['task'])
        self.assertIn('grants no permissions', data['task'])
        request = self.advance(['Inbox'], ['Purchases'])
        self.assertEqual(request['category'], 'manual_action')
        self.assertIn('Inbox', request['request'])
        self.assertEqual(self.chat("C'est bon")[0], 'resume')
        request = self.advance([], ['Inbox'])
        self.assertEqual(request['category'], 'confirmation')
        return self.control.proposal.copy()

    def test_natural_french_and_english_authentication_confirmations_resume_same_task(self):
        for answer in ("C'est bon", "J'ai terminé", 'Je suis connecté', 'Done', 'Continue'):
            self.pause('authentication', 'Please sign in.')
            event = self.event(answer)
            kind, data = self.broker.chat('chat', event)
            self.assertEqual(kind, 'resume', answer)
            self.assertEqual(data['session_id'], 'chat')
            self.assertIn(self.data['task'], data['task'])
            self.assertNotIn(answer, data['task'])
            with self.assertRaises(BusinessError): self.broker.chat('chat', event)

    def test_negative_uncertain_and_secret_answers_never_resume_or_consume_a_model_call(self):
        self.pause('authentication', 'Please sign in.')
        for answer in ('Non, pas encore', 'No', 'Maybe', 'Yes, but not yet'):
            old = self.event(answer)
            self.assertEqual(self.chat(answer), ('waiting', None))
            self.assertEqual(self.broker.status('chat')['state'], 'waiting_operator')
            with self.assertRaises(BusinessError): self.broker.chat('chat', old)
        for answer in ('123456', 'password is synthetic', 'MFA code synthetic'):
            with self.assertRaises(BusinessError): self.chat(answer)

    def test_question_answer_is_information_and_cannot_publish_a_procedure(self):
        self.pause('question', 'Which non-sensitive option should be selected?')
        before = self.control.store.active()
        kind, data = self.chat('Option A')
        self.assertEqual(kind, 'resume')
        self.assertIn('Option A', data['task'])
        self.assertEqual(self.control.store.active(), before)

    def test_natural_navigation_requires_observed_manual_transitions_before_proposal(self):
        self.assertEqual(correction_routes('Ouvre les achats puis la boîte de réception.'), ['purchases', 'inbox'])
        self.observe(['Purchases'])
        self.control.close()
        self.chat('Open Purchases then Inbox')
        for _ in range(2):
            request = self.advance(['Purchases'])
            self.assertEqual(request['category'], 'manual_action')
            self.assertIsNone(self.control.proposal)
            self.chat('Done')
        self.assertEqual(self.broker.status('chat')['state'], 'resuming')

    def test_approved_markdown_is_local_immutable_incremental_and_loaded_by_later_runs(self):
        baseline = self.control.store.baseline_path.read_bytes()
        proposal = self.ready_proposal()
        before = self.control.store.pin('chat')
        event = self.event('Yes, save it.')
        self.assertEqual(self.broker.chat('chat', event)[0], 'resume')
        store = ProcedureStore(self.fixture.root)
        self.assertEqual(store.active()['current'], proposal['candidate_revision'])
        self.assertEqual(store.pin('chat'), before)
        path = store.root / 'snapshots' / (proposal['candidate_revision'] + '.md')
        self.assertEqual(path.read_text(encoding='utf-8'), proposal['new'])
        self.assertEqual(store.baseline_path.read_bytes(), baseline)
        new = DextRunControl(self.fixture.context, 'future-chat', project_root=self.fixture.root)
        self.addCleanup(new.close)
        self.assertIn('Purchases', new.overlay())
        self.assertIn('Inbox', new.overlay())
        self.assertIn('no action', new.overlay().lower())
        p = store.propose(['bank'], 'other-run', incremental=True)
        store.review(p['proposal_id'], p['base_revision'], p['candidate_revision'], True)
        self.assertIn('Purchases', store.markdown(store.active()['current']))
        self.assertIn('bank transactions', store.markdown(store.active()['current']))
        for item in store.root.rglob('*'):
            if item.is_file():
                contents = item.read_bytes()
                self.assertNotIn(b'PRIVATE SYNTHETIC', contents)
                self.assertNotIn(b'Click Purchases, then Inbox.', contents)
        with self.assertRaises(BusinessError): self.broker.chat('chat', event)

    def test_rejection_and_show_are_contextual_and_unrelated_yes_cannot_publish(self):
        self.ready_proposal()
        before = self.control.store.active()
        self.assertEqual(self.chat('Continue'), ('waiting', None))
        self.assertEqual(self.control.store.active(), before)
        self.assertEqual(self.chat('Show me what will be saved'), ('waiting', None))
        self.assertIn('Purchases', self.broker.status('chat')['procedure_summary'])
        self.assertEqual(self.chat("Don't remember this")[0], 'resume')
        self.assertEqual(self.control.store.active(), before)

    def test_unusable_checkpoint_cannot_publish_learning_and_foreign_chat_cannot_answer(self):
        self.ready_proposal()
        before = self.control.store.active()
        event = self.event('Yes')
        with self.assertRaises(BusinessError): self.broker.chat('other-chat', event)
        self.broker.pending['chat']['data']['_checkpoint_unavailable'] = True
        with self.assertRaises(BusinessError): self.broker.chat('chat', event)
        self.assertEqual(self.control.store.active(), before)

    def test_exact_presentation_and_candidate_tampering_are_rejected(self):
        self.ready_proposal()
        event = self.event('Yes')
        with self.assertRaises(BusinessError): self.broker.chat('chat', {**event, 'presentation_digest': 'foreign'})
        self.control.proposal['candidate_revision'] = 'f' * 64
        with self.assertRaises(BusinessError): self.broker.chat('chat', event)
        self.assertEqual(self.broker.status('chat')['state'], 'waiting_operator')

    def test_edit_requires_new_corroboration_and_no_unobserved_candidate_is_published(self):
        self.ready_proposal()
        self.assertEqual(self.chat('Change the second step'), ('waiting', None))
        self.assertNotIn('procedure_summary', self.broker.status('chat'))
        self.assertEqual(self.chat('Open bank transactions')[0], 'resume')
        self.assertEqual(self.broker._teaching['chat'].routes, ['purchases', 'bank'])
        self.assertEqual(self.broker._teaching['chat'].evidence, [])

    def test_unknown_or_private_navigation_details_require_clarification(self):
        for answer in ('Open purchases for Private Customer', 'Click #some-selector', 'Approve all downloads'):
            self.assertEqual(self.chat(answer), ('waiting', None))
            self.assertFalse(self.broker._teaching)

    def test_markdown_is_a_checked_projection_not_an_independent_source(self):
        store = self.control.store
        revision = store.active()['current']
        path = store.root / 'snapshots' / (revision + '.md')
        path.unlink()  # Synthetic fixture simulates a legacy JSON-only snapshot.
        self.assertEqual(store.markdown(revision), store.baseline)
        path.write_text('Unapproved synthetic alteration', encoding='utf-8')
        with self.assertRaisesRegex(BusinessError, 'markdown_corrupt'): store.markdown(revision)

    def test_unverified_record_identity_does_not_become_learned_action_authority(self):
        teaching = NavigationTeaching(['record'])
        self.assertEqual(teaching.intervention()['category'], 'blocked')
        self.assertEqual(teaching.evidence, [])

    def test_ambiguous_controls_and_foreign_tab_transitions_cannot_ground_a_route(self):
        duplicates = {str(n): {'name': 'Purchases', 'role': 'link', 'rect': [1, 1, 50, 20]} for n in (1, 2)}
        self.assertNotIn('purchases', landmarks(duplicates)[0])
        teaching = NavigationTeaching(['purchases'])
        teaching.observe({'purchases'}, set(), 'source-digest', 'tab-one')
        teaching.observe(set(), {'purchases'}, 'other-digest', 'tab-two')
        self.assertEqual(teaching.index, 0)
        self.assertEqual(teaching.evidence, [])


if __name__ == '__main__': unittest.main()
