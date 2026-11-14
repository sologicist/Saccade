"""Synthetic regression for natural authentication claims and safe recovery."""

import unittest
from unittest.mock import patch

from AutoCua.saccade.business_contract import BusinessError
from AutoCua.saccade.operator_diagnostics import classify, events, record
from AutoCua.saccade.operator_language import intervention_intent, spontaneous_correction
from AutoCua.saccade.operator_requests import OperatorRequests
from AutoCua.saccade.platform_learning import PlatformLearningControl
from tests.business_fixtures import BusinessFixture
from tests.platform_learning_fixtures import install_synthetic


class OperatorResumeContracts(unittest.TestCase):
    def setUp(self):
        self.fixture = BusinessFixture()
        self.addCleanup(self.fixture.close)
        self.other = install_synthetic(self.fixture.root)

    def event(self, broker, answer):
        item = broker.status('chat')
        return {**{k: item[k] for k in ('run_id', 'intervention_id', 'revision', 'token')},
                'action': 'chat', 'answer': answer, 'non_sensitive': True, 'presentation_digest': None}

    def test_natural_authentication_claims_resume_same_objective_without_authority(self):
        for context in (self.fixture.context, self.other):
            control = PlatformLearningControl(context, 'chat', project_root=self.fixture.root)
            for text in ("c'est connecté", 'je suis connecté', 'je suis connectée', 'je suis bien connecté',
                         'la connexion est faite', "c'est bon", 'oui', 'ok', "I'm connected", "I'm logged in", "I've signed in", 'done'):
                with self.subTest(platform=context['platform_id'], text=text):
                    broker = OperatorRequests()
                    broker.configure_teaching('chat', control)
                    original = {'task': 'Open a public section, then wait for instructions.', 'platform_id': context['platform_id']}
                    broker.suspend('chat', 'run', original, {'category': 'authentication', 'reason': 'authentication_required', 'request': 'Sign in privately.'})
                    event = self.event(broker, text)
                    kind, data = broker.chat('chat', event, control=control)
                    self.assertEqual(kind, 'resume')
                    self.assertIn(original['task'], data['task'])
                    self.assertIn('login is not verified', data['task'])
                    self.assertIn('grants no permissions', data['task'])
                    self.assertEqual(data['session_id'], 'chat')
                    self.assertNotIn('approved', data)
                    with self.assertRaises(BusinessError):
                        broker.chat('chat', event, control=control)

    def test_contextual_claims_do_not_create_login_state_in_unrelated_chat(self):
        self.assertEqual(intervention_intent("c'est connecté", 'authentication'), 'affirmative')
        self.assertEqual(intervention_intent("c'est connecté", 'question'), 'ambiguous')
        self.assertEqual(spontaneous_correction("c'est connecté", eligible=True, navigation=False), ('ordinary', None))

    def test_hard_ownership_failure_only_allows_explicit_cancellation(self):
        broker = OperatorRequests()
        broker.suspend('chat', 'run', {'task': 'Original task'}, {'category': 'blocked', 'reason': 'unsafe_or_blocked', 'request': 'Review the browser.'})
        broker.block_recovery('chat', 'chrome_pipe_disconnected')
        self.assertEqual(broker.status('chat')['recovery'], 'cancel_restart')
        for text in ('oui', "c'est connecté", 'What information has changed?', 'Open Settings'):
            with self.assertRaisesRegex(BusinessError, 'checkpoint_unavailable'):
                broker.chat('chat', self.event(broker, text))
        self.assertEqual(broker.chat('chat', self.event(broker, 'Cancel'))[0], 'cancel')

    def test_intentional_wait_is_an_informational_pause_with_same_task(self):
        broker = OperatorRequests()
        broker.suspend('chat', 'run', {'task': 'Open the public section and wait.'},
            {'category': 'question', 'reason': 'awaiting_instructions', 'request': 'I have reached the requested page and stopped. What would you like me to do next?'})
        self.assertEqual(broker.status('chat')['request']['reason'], 'awaiting_instructions')
        kind, data = broker.chat('chat', self.event(broker, 'Describe the public page.'))
        self.assertEqual(kind, 'resume')
        self.assertIn('Open the public section and wait.', data['task'])
        self.assertIn('Describe the public page.', data['task'])

    def test_diagnostics_bound_content_and_never_emit_exception_or_private_data(self):
        private = 'PRIVATE https://example.test/path?token=SYNTHETIC cookie=password'
        with patch('AutoCua.saccade.operator_diagnostics.logging.getLogger') as logger:
            for _ in range(150):
                record(classify(RuntimeError(private)), private, private, 'resume')
            rows = events(private)
            self.assertEqual(len(rows), 128)
            self.assertNotIn(private, str(rows))
            self.assertNotIn('https://', str(logger.mock_calls))
            self.assertEqual(set(rows[0]), {'code', 'session', 'run', 'phase'})
            self.assertEqual(rows[0]['code'], 'internal_exception')
            self.assertEqual(events('other-session'), [])
        for code in ('chrome_pipe_disconnected', 'browser_process_unavailable', 'profile_lease_lost', 'paired_history_mismatch'):
            self.assertEqual(classify(ValueError('operator_resume:' + code)), code)

    def test_learning_evidence_survives_new_observer_only_in_same_native_session(self):
        from AutoCua.saccade.navigation_correction import NavigationTeaching
        control = PlatformLearningControl(self.other, 'chat', project_root=self.fixture.root)
        control.freeze_decision()
        control.attach_teaching(NavigationTeaching(['billing_page'], adapter=control.store.adapter))
        stamp = {'observer': 'generation-one', 'tab': '1', 'profile': self.other['browser_profile'],
                 'platform_id': self.other['platform_id'], 'config_revision': self.other['config_revision'], 'session': 'native-retained-session'}
        control.observe_native({'1': {'name': 'Billing', 'role': 'link', 'rect': [1, 1, 50, 20]}}, stamp)
        control.observe_native({'1': {'name': 'Billing', 'role': 'heading', 'rect': [1, 1, 50, 20]}}, {**stamp, 'observer': 'generation-two'})
        self.assertEqual(control.teaching.index, 1)
        self.assertIsNotNone(control.learning_intervention())
        other = NavigationTeaching(['billing_page'], adapter=control.store.adapter)
        control.attach_teaching(other)
        control.observe_native({'1': {'name': 'Billing', 'role': 'link', 'rect': [1, 1, 50, 20]}}, stamp)
        control.observe_native({'1': {'name': 'Billing', 'role': 'heading', 'rect': [1, 1, 50, 20]}}, {**stamp, 'session': 'new-browser'})
        self.assertEqual(other.index, 0)
