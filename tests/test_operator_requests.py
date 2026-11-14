"""Synthetic same-process checkpoints; no model, browser or secret input."""
import unittest
from unittest.mock import Mock
from AutoCua.saccade.operator_requests import OperatorRequests, validate_request
from AutoCua.saccade.business_contract import BusinessError


class OperatorRequestContracts(unittest.TestCase):
    def setUp(self):
        self.broker = OperatorRequests()
        self.data = {'task': 'Original invented task', 'mode': 'web', 'provider': 'fake', 'model': 'fake'}
        self.broker.suspend('chat', 'run', self.data, {'category':'question','reason':'missing_information','request':'Which invented option should be selected?'})

    def event(self, action='resume', answer='Option A'):
        value = self.broker.status('chat')
        return {**{k:value[k] for k in ('run_id','intervention_id','revision','token')}, 'action':action,'answer':answer,'non_sensitive':True}

    def test_same_task_and_conversation_resume_once_without_permissions(self):
        event = self.event()
        data = self.broker.consume('chat', event)
        self.assertIn(self.data['task'], data['task'])
        self.assertEqual(data['session_id'], 'chat')
        self.assertIn('grants no permissions', data['task'])
        with self.assertRaises(BusinessError): self.broker.consume('chat', event)

    def test_foreign_stale_duplicate_or_extra_authority_is_rejected(self):
        event = self.event()
        for key in ('run_id','intervention_id','revision','token'):
            with self.assertRaises(BusinessError): self.broker.consume('chat', {**event,key:'foreign'})
        with self.assertRaises(BusinessError): self.broker.consume('other-chat', event)
        with self.assertRaises(BusinessError): self.broker.consume('chat', {**event,'approved':True})

    def test_failure_keeps_waiting_and_rotates_continuation_revision(self):
        old = self.event()
        self.broker.consume('chat', old)
        self.broker.finish('chat', failed=True)
        self.assertEqual(self.broker.status('chat')['state'], 'waiting_operator')
        with self.assertRaises(BusinessError): self.broker.consume('chat', old)

    def test_cancel_waiting_and_resuming(self):
        event = self.event()
        self.broker.consume('chat', event)
        self.broker.consume('chat', {**event,'action':'cancel'})
        self.assertEqual(self.broker.status('chat')['state'], 'cancelled')

    def test_private_authentication_never_accepts_text(self):
        request = validate_request({'category':'authentication','reason':'authentication_required','request':'Enter a password'})
        self.assertIn('privately', request['request'])
        self.broker.suspend('auth','run',self.data,request)
        value = self.broker.status('auth')
        event = {**{k:value[k] for k in ('run_id','intervention_id','revision','token')},'action':'resume','answer':'anything','non_sensitive':True}
        with self.assertRaises(BusinessError): self.broker.consume('auth',event)
        self.assertIsNotNone(self.broker.consume('auth',{**event,'answer':''}))

    def test_secrets_and_script_requests_are_not_accepted(self):
        for text in ('What is your password?', 'Send an API key', '<script>code</script>'):
            with self.assertRaises(BusinessError): validate_request({'category':'question','reason':'missing_information','request':text})
        with self.assertRaises(BusinessError): self.broker.consume('chat',self.event(answer='123456'))

    def test_refresh_status_is_read_only_and_process_recovery_is_not_claimed(self):
        before = self.broker.status('chat')
        for _ in range(10): self.assertEqual(self.broker.status('chat'), before)
        self.assertIsNone(OperatorRequests().status('chat'))

    def test_new_intervention_preserves_original_task_during_continuation(self):
        data = self.broker.consume('chat', self.event())
        self.broker.suspend('chat','next-run',data,{'category':'blocked','reason':'unsafe_or_blocked','request':'Review the external environment.'})
        self.assertEqual(self.broker.pending['chat']['data']['task'],self.data['task'])

    def test_passive_browser_is_private_and_cleanup_precedes_lease_release(self):
        events = []
        agent, lease = Mock(), Mock()
        agent.close_operator_session.side_effect = lambda: events.append('close')
        lease.release.side_effect = lambda: events.append('release')
        self.broker.retain_browser('chat', agent, lease)
        self.assertIsNone(self.broker.browser_for_resume('chat'))
        self.assertNotIn('browser', str(self.broker.status('chat')))
        self.broker.consume('chat', self.event())
        self.assertEqual(self.broker.browser_for_resume('chat'), (agent, lease))
        self.broker.close_browser('chat')
        self.assertEqual(events, ['close', 'release'])
        self.broker.close_browser('chat')
        self.assertEqual(events, ['close', 'release'])

    def test_unverified_cleanup_retains_lease_and_rejects_different_owner(self):
        agent, lease = Mock(), Mock()
        self.broker.retain_browser('chat', agent, lease)
        with self.assertRaises(BusinessError): self.broker.retain_browser('chat', Mock(), Mock())
        agent.close_operator_session.side_effect = RuntimeError('unverified cleanup')
        with self.assertRaises(RuntimeError): self.broker.close_browser('chat')
        lease.release.assert_not_called()
        self.assertTrue(self.broker.owns_lease('chat', lease))
        with self.assertRaises(BusinessError): self.broker.consume('chat', self.event())
        agent.close_operator_session.side_effect = None
        self.broker.close_all_browsers()
        lease.release.assert_called_once()


if __name__ == '__main__': unittest.main()
