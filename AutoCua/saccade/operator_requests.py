"""Same-process continuation broker. Answers never confer execution authority."""
import copy
import re
import secrets
import threading

from .business_contract import digest, reject

CATEGORIES = ('question', 'manual_action', 'authentication', 'confirmation', 'blocked')
REASONS = ('missing_information', 'manual_intervention', 'authentication_required', 'condition_confirmation', 'unsafe_or_blocked', 'no_progress', 'awaiting_instructions')
_SECRET = re.compile(r'password|mot de passe|\bmfa\b|\botp\b|\b2fa\b|\bpin\b|verification.?code|authentication.?code|code de verification|api.?key|(?:session|access).?token|bearer|private.?key|secret|credential|\b\d{6}\b|sk-[A-Za-z0-9]+', re.I)


def validate_request(value):
    if type(value) is not dict or set(value) != {'category', 'reason', 'request'}:
        reject('invalid_operator_request')
    if value['category'] not in CATEGORIES or value['reason'] not in REASONS or type(value['request']) is not str or not 1 <= len(value['request']) <= 1000:
        reject('invalid_operator_request')
    if value['category'] == 'authentication':
        return {**value, 'request': 'Please sign in privately in the dedicated Chrome window, then tell me when you are connected. Do not enter credentials in chat.'}
    if _SECRET.search(value['request']) or re.search(r'[<>]|[A-Za-z]:\\|(?:^|\s)/\w|https?://|javascript:|\beval\(|powershell|cmd\.exe|\bbash\b|\bshell\b|python\s+-', value['request'], re.I):
        reject('unsafe_operator_request')
    return dict(value)


class OperatorRequests:
    """No waiting execution thread, model polling or independent answer journal.

    Continuation uses the existing launcher/conversation and fresh native scanning.
    Passive browser ownership stays here until resume or explicit cleanup. No
    execution thread or model client is running while waiting. Process restart
    recovery is intentionally absent.
    """
    def __init__(self):
        self.lock = threading.RLock()
        self.pending = {}
        self._browsers = {}
        self._teaching = {}
        self._reviews = {}
        self._controls = {}
        self._run_contexts = {}
        self._correction_claims = {}
        self._queued_corrections = {}

    def begin_run(self, session, run, data):
        with self.lock:
            self._run_contexts[session] = {'run_id': run, 'active': True, 'data': copy.deepcopy(data)}

    def end_run(self, session, run):
        with self.lock:
            context = self._run_contexts.get(session)
            if context and context['run_id'] == run:
                context['active'] = False
            if (self.pending.get(session) or {}).get('state') == 'cancelled':
                self._queued_corrections.pop(session, None)

    def cancel_queued_run(self, run):
        with self.lock:
            for session, queued in self._queued_corrections.items():
                if queued['run_id'] == run:
                    self.pending[session]['state'] = 'cancelled'

    def run_context(self, session):
        with self.lock:
            return copy.deepcopy(self._run_contexts.get(session))

    def correction_claim(self, session, signature):
        with self.lock:
            value = self._correction_claims.get(session)
            if not value or value['signature'] != signature:
                value = {'signature': signature, 'token': secrets.token_hex(32)}
                self._correction_claims[session] = value
            return dict(value)

    def consume_correction_claim(self, session, claim, signature):
        with self.lock:
            expected = self._correction_claims.get(session)
            if type(claim) is not dict or not expected or claim != expected or signature != expected['signature']:
                reject('stale_navigation_correction')
            del self._correction_claims[session]

    def propose_correction(self, session, run, data, routes, *, active, clarify=False):
        """Queue bounded guidance only; a running worker must acknowledge its pause."""
        with self.lock:
            if (self.pending.get(session) or {}).get('state') in ('waiting_operator', 'pausing_operator') or (not active and (self.pending.get(session) or {}).get('state') == 'resuming'):
                reject('operator_intervention_pending')
            request = {'category': 'question', 'reason': 'missing_information',
                       'request': 'Which navigation path should replace the previous attempt? Describe the sections only.'}
            self.suspend(session, run, data, request)
            self._queued_corrections[session] = {'run_id': run, 'routes': routes, 'clarify': clarify}
            if active:
                self.pending[session]['state'] = 'pausing_operator'
                self.pending[session]['chat_message'] = 'I have queued your correction and requested a pause. It is not applied yet; I am waiting for a safe browser checkpoint.'

    def correction_queued(self, session, run):
        with self.lock:
            return (self._queued_corrections.get(session) or {}).get('run_id') == run

    def complete_correction_pause(self, session, run, *, available, control=None, reopen=False, adapter=None):
        from .navigation_correction import NavigationTeaching
        with self.lock:
            queued = self._queued_corrections.pop(session, None)
            if not queued or queued['run_id'] != run:
                return
            item = self.pending[session]
            if not available:
                item['data']['_checkpoint_unavailable'] = True
                item['request'] = {'category': 'blocked', 'reason': 'unsafe_or_blocked',
                    'request': 'The correction is not applied. Browser ownership or the saved checkpoint could not be verified; cancel and review the original task.'}
                return
            if reopen:
                item['correction_reopen'] = True
            self._verify_control(session, control, item)
            routes = queued['routes']
            adapter = control.store.adapter if control else adapter
            if routes and (adapter is None or adapter.platform_id != item['data'].get('platform_id')):
                reject('learning_platform_mismatch')
            if routes and not queued['clarify']:
                self._teaching[session] = NavigationTeaching(routes, baseline=control.teaching_baseline if control else None, adapter=adapter)
                item['request'] = {'category': 'confirmation', 'reason': 'condition_confirmation',
                    'request': 'Proposed route: ' + ' → '.join(adapter.summary_label(route) for route in routes) +
                    '. I will verify it before saving. Reply Continue to ' + ('open a dedicated browser and reobserve' if reopen else 'reobserve in the same browser') + ' and continue the original task.'}
            elif routes:
                item['correction_intent_routes'] = routes
                item['request'] = {'category': 'confirmation', 'reason': 'condition_confirmation',
                    'request': 'Is this a correction to the previous navigation, rather than a new task? Reply Yes to verify the proposed route, or No to leave it unapplied.'}
            else:
                item['request'] = {'category': 'question', 'reason': 'missing_information',
                    'request': 'What is the corrected navigation path? Use only public section names supported by this platform; unknown details cannot be inferred.'}
            item['chat_message'] = item['request']['request']

    def correction_reopen(self, session):
        with self.lock:
            item = self.pending.get(session) or {}
            return item.get('state') == 'resuming' and item.get('correction_reopen') is True

    def _verify_control(self, session, control, item=None):
        if control is None:
            return
        if control.session_id != session or item and item["data"].get("platform_id") != control.context["platform_id"]:
            reject("learning_platform_mismatch")
        if item and any(item["data"].get(k, control.context[k]) != control.context[k] for k in ("execution_mode", "browser_profile")):
            reject("learning_platform_mismatch")
        control.overlay()

    def configure_teaching(self, session, control):
        with self.lock:
            self._verify_control(session, control, self.pending.get(session))
            self._controls[session] = control
            if session in self._teaching:
                control.attach_teaching(self._teaching[session])

    def control_for(self, session):
        with self.lock:
            return self._controls.get(session)

    def present_procedure(self, session, control):
        """Seal the exact host-generated candidate to this suspended request."""
        with self.lock:
            item = self.pending.get(session)
            if not item or item['state'] != 'waiting_operator' or not control.teaching or not control.proposal or control.teaching.index != len(control.teaching.routes):
                return
            if control.proposal['teaching_source'] != 'operator_chat_correction' or control.proposal['observation_digest'] != digest(control.teaching.evidence):
                reject('unverified_navigation_teaching')
            self._verify_control(session, control, item)
            self._reviews[session] = (control, copy.deepcopy(control.proposal))
            item['procedure_summary'] = control.proposal['new']
            item['procedure_diff'] = control.proposal['diff']
            item['procedure_label'] = control.proposal['summary']
            item['presentation_digest'] = digest([session, control.context, control.store.adapter.revision, control.pin_revision, control.run_id, item['run_id'], item['intervention_id'], item['revision'],
                {key: control.proposal[key] for key in ('proposal_id', 'base_revision', 'candidate_revision', 'new', 'diff', 'summary')}])

    def _rotate(self, item, message):
        item.update(revision=secrets.token_hex(32), token=secrets.token_urlsafe(32), chat_message=message)
        # A clarification is still a presentation of the same exact proposal.
        if item.get('presentation_digest'):
            item['presentation_digest'] = digest([item['presentation_digest'], item['revision']])

    def _event_item(self, session, event):
        item = self.pending.get(session)
        keys = {'run_id', 'intervention_id', 'revision', 'token', 'action', 'answer', 'non_sensitive'}
        if not item or type(event) is not dict or set(event) != keys or (item['state'] != 'waiting_operator' and not (item['state'] in ('resuming', 'pausing_operator') and event.get('action') == 'cancel')):
            reject('stale_operator_response')
        if any(type(event[k]) is not str or not secrets.compare_digest(event[k], item[k]) for k in ('run_id', 'intervention_id', 'revision', 'token')):
            reject('stale_operator_response')
        return item

    def _review(self, session, approve):
        control, proposal = self._reviews[session]
        self._verify_control(session, control, self.pending[session])
        if not control.proposal or any(control.proposal.get(key) != proposal[key] for key in ('proposal_id', 'base_revision', 'candidate_revision', 'new', 'diff', 'summary')):
            reject('proposal_identity_mismatch')
        control.operator_event({'event': 'review', 'review_token': control.review_token, 'approve': approve,
            **{key: proposal[key] for key in ('proposal_id', 'base_revision', 'candidate_revision')}}, busy=False)
        del self._reviews[session]
        item = self.pending[session]
        for key in ('procedure_summary', 'procedure_diff', 'procedure_label', 'presentation_digest'):
            item.pop(key, None)

    def chat(self, session, event, *, control=None):
        """The ordinary composer enters the same one-use continuation broker.

        Informational answers, exact procedure decisions and external-effect
        authorization never share a permission or dispatch path.
        """
        from .operator_language import normalized, reply_intent, intervention_intent, navigation_question
        from .navigation_correction import correction_routes, NavigationTeaching
        from .business_contract import BusinessError
        with self.lock:
            control = control or self._controls.get(session)
            if type(event) is not dict or set(event) != {'run_id', 'intervention_id', 'revision', 'token', 'action', 'answer', 'non_sensitive', 'presentation_digest'} or event['action'] != 'chat':
                reject('invalid_operator_response')
            presentation = event['presentation_digest']
            base = {key: value for key, value in event.items() if key != 'presentation_digest'}
            answer = base['answer']
            intent = reply_intent(answer) if type(answer) is str else 'ambiguous'
            item = self._event_item(session, {**base, 'action': 'cancel' if intent == 'cancel' else 'resume'})
            intent = intervention_intent(answer, item['request']['category']) if type(answer) is str else 'ambiguous'
            if type(answer) is not str or not 1 <= len(answer.strip()) <= 2000 or base['non_sensitive'] is not True or _SECRET.search(answer) or _SECRET.search(normalized(answer)) or any(ord(c) < 32 and c not in '\n\r\t' for c in answer):
                reject('non_sensitive_answer_required')
            if intent == 'cancel':
                return 'cancel', self.consume(session, {**base, 'action': 'cancel', 'answer': ''})
            if item['data'].get('_checkpoint_unavailable'):
                reject('continuation_checkpoint_unavailable')
            if session in self._reviews:
                if type(presentation) is not str or not secrets.compare_digest(presentation, item['presentation_digest']):
                    reject('stale_procedure_presentation')
                if intent == 'show':
                    self._rotate(item, 'Here is the complete procedure proposed for future sessions. Should I remember it?')
                    return 'waiting', None
                if intent == 'edit_second':
                    self._review(session, False)
                    item['edit_second'] = True
                    item['request'] = {'category': 'question', 'reason': 'missing_information', 'request': 'What should the second navigation step be? Describe the section only.'}
                    self._rotate(item, item['request']['request'])
                    return 'waiting', None
                approve = intent == 'save' or normalized(answer) in ('yes', 'oui')
                decline = intent == 'reject' or normalized(answer) in ('no', 'non', 'no thanks', 'non merci')
                if not approve and not decline:
                    self._rotate(item, 'Should I save this exact navigation procedure, or leave it unremembered?')
                    return 'waiting', None
                approved = approve
                self._review(session, approved)
                self._teaching.pop(session, None)
                item['request'] = {'category': 'confirmation', 'reason': 'condition_confirmation',
                                   'request': 'The procedure decision is recorded. Shall I continue the original task?'}
                data = self.consume(session, {**base, 'action': 'resume', 'answer': ''})
                data['task'] += '\nProcedure ' + ('saved for future sessions. The current conversation retains its pinned version.' if approved else 'not saved.') + ' No external effect is authorized.'
                return 'resume', data
            self._verify_control(session, control, item)
            category = item['request']['category']
            if item.get('correction_intent_routes'):
                if intent == 'negative':
                    item.pop('correction_intent_routes', None)
                    item['request'] = {'category': 'confirmation', 'reason': 'condition_confirmation',
                        'request': 'The correction was not applied. Reply Continue to resume the original task, or Cancel before sending a new request.'}
                    self._rotate(item, item['request']['request'])
                    return 'waiting', None
                if intent == 'affirmative':
                    self._teaching[session] = NavigationTeaching(item.pop('correction_intent_routes'), baseline=control.teaching_baseline if control else None, adapter=control.store.adapter if control else None)
            if intent in ('negative', 'reject', 'uncertain'):
                self._rotate(item, 'Take your time. Tell me when the manual step is complete, or clarify what is still missing. You can also cancel the task.')
                return 'waiting', None
            if category in ('authentication', 'manual_action', 'confirmation'):
                if intent != 'affirmative':
                    self._rotate(item, 'Is the requested manual step complete? Please confirm when it is done; never send credentials or authentication codes.')
                    return 'waiting', None
                return 'resume', self.consume(session, {**base, 'action': 'resume', 'answer': ''})
            routes = None
            try:
                routes = correction_routes(answer, control.store.adapter) if control else None
            except BusinessError:
                pass
            if item.get('edit_second') and routes:
                old = self._teaching.get(session)
                if not old or len(old.routes) < 2 or len(routes) != 1:
                    reject('invalid_navigation_correction')
                routes = old.routes[:1] + routes + old.routes[2:]
            if routes and control is not None:
                self._teaching[session] = NavigationTeaching(routes, baseline=control.teaching_baseline, adapter=control.store.adapter)
                item.pop('edit_second', None)
            elif not routes and (category == 'blocked' or navigation_question(item['request']['request']) or item.get('edit_second')):
                if category == 'blocked' and not navigation_question(item['request']['request']):
                    item['request'] = {'category': 'question', 'reason': 'missing_information',
                        'request': 'What information has changed? Describe non-sensitive context; I will recheck it before continuing. This cannot authorize an external action.'}
                    self._rotate(item, item['request']['request'])
                else:
                    self._rotate(item, 'Which section should be opened next? Describe public sections configured for this platform. I cannot infer selectors, record identities or permissions.')
                return 'waiting', None
            # Existing informational continuation is the only path to the model.
            item['request'] = {**item['request'], 'category': 'question'}
            return 'resume', self.consume(session, {**base, 'action': 'resume'})

    def retain_browser(self, session, agent, lease):
        """Host-only ownership transfer; native objects never enter JSON checkpoints."""
        with self.lock:
            previous = self._browsers.get(session)
            if previous and previous[1] is not lease:
                reject('operator_browser_ownership_conflict')
            self._browsers[session] = (agent, lease)

    def browser_for_resume(self, session):
        with self.lock:
            item = self.pending.get(session)
            if not item or item['state'] != 'resuming':
                return None
            return self._browsers.get(session)

    def owns_lease(self, session, lease):
        with self.lock:
            value = self._browsers.get(session)
            return value is not None and value[1] is lease

    def close_browser(self, session):
        """Close the native transport before releasing its exclusive profile lease.

        A failed native cleanup retains ownership for explicit operator review.
        Never call while the corresponding agent is executing.
        """
        with self.lock:
            value = self._browsers.get(session)
            if value:
                try:
                    value[0].close_operator_session()
                    value[1].release()
                except Exception:
                    item = self.pending.get(session)
                    if item:
                        item.update(state='waiting_operator', revision=secrets.token_hex(32), token=secrets.token_urlsafe(32),
                                    error='Browser cleanup could not be verified. Ownership remains reserved. Review the environment and retry Cancel.',
                                    request={'category': 'blocked', 'reason': 'unsafe_or_blocked', 'request': 'Verify browser ownership before retrying cleanup.'})
                        item['data']['_checkpoint_unavailable'] = True
                    raise
                del self._browsers[session]
                self._controls.pop(session, None)

    def close_all_browsers(self):
        with self.lock:
            failure = None
            for session in list(self._browsers):
                try:
                    self.close_browser(session)
                except Exception as error:
                    failure = error
            if failure:
                raise failure

    def suspend(self, session, run, data, request):
        request = validate_request(request)
        with self.lock:
            previous = self.pending.get(session)
            original = previous['data'] if previous and previous['state'] in ('resuming', 'pausing_operator') else data
            item = {'session_id': session, 'run_id': run, 'intervention_id': secrets.token_hex(24),
                    'revision': secrets.token_hex(32), 'token': secrets.token_urlsafe(32),
                    'state': 'waiting_operator', 'request': request, 'data': copy.deepcopy(original), 'error': None,
                    'policy_revision': digest({k: original.get(k) for k in ('platform_id', 'execution_mode', 'browser_profile', 'mode', 'speed')})}
            self.pending[session] = item

    def block_recovery(self, session, code):
        """Hard ownership/checkpoint failures cannot become information loops."""
        from .operator_diagnostics import HARD_FAILURES
        if code not in HARD_FAILURES:
            return
        with self.lock:
            item = self.pending.get(session)
            if item:
                item['data']['_checkpoint_unavailable'] = True
                item.update(diagnostic_code=code, recovery='cancel_restart',
                    request={'category': 'blocked', 'reason': 'unsafe_or_blocked',
                        'request': 'This browser session cannot safely continue. Cancel this task, then start a new conversation after reviewing the dedicated browser. No replacement browser was started.'})

    def status(self, session):
        with self.lock:
            item = self.pending.get(session)
            return {k: copy.deepcopy(v) for k, v in item.items() if k != 'data'} if item else None

    def consume(self, session, event):
        with self.lock:
            item = self._event_item(session, event)
            if event['action'] == 'cancel':
                if session in self._reviews:
                    try:
                        self._review(session, False)
                    except (ValueError, OSError):
                        # Cancellation never needs a successful procedure decision.
                        self._reviews.pop(session, None)
                self._teaching.pop(session, None)
                self._controls.pop(session, None)
                item['state'] = 'cancelled'
                return None
            if event['action'] != 'resume':
                reject('invalid_operator_response')
            if item['data'].get('_checkpoint_unavailable'):
                reject('continuation_checkpoint_unavailable')
            self._verify_control(session, self._controls.get(session), item)
            answer = event['answer']
            if type(answer) is not str or len(answer) > 2000:
                reject('invalid_operator_answer')
            if item['request']['category'] != 'question' and answer:
                reject('text_not_allowed_for_manual_intervention')
            if item['request']['category'] == 'question' and (not answer.strip() or event['non_sensitive'] is not True or _SECRET.search(answer)):
                reject('non_sensitive_answer_required')
            item['state'] = 'resuming'
            data = copy.deepcopy(item['data'])
            data['session_id'] = session
            claim = ('Operator claims authentication is complete; login is not verified. Reobserve the same browser and check visible authentication state. '
                     if item['request']['category'] == 'authentication' else 'Operator intervention completed. Reobserve the environment before acting. ')
            data['task'] = (item['data']['task'] + '\n\n' + claim +
                            'This response grants no permissions. Informational answer: ' + (answer or '[manual completion confirmed]'))
            return data

    def retry(self, session):
        with self.lock:
            item = self.pending.get(session)
            if item and item['state'] == 'resuming':
                item.update(state='waiting_operator', revision=secrets.token_hex(32), token=secrets.token_urlsafe(32), error='Resource or session revalidation failed. Review browser ownership and current state before retrying.')

    def finish(self, session, failed=False):
        with self.lock:
            item = self.pending.get(session)
            if item and item['state'] == 'resuming':
                if failed:
                    self.retry(session)
                else:
                    item['state'] = 'completed'
                    self._teaching.pop(session, None)
            if not item or item['state'] not in ('waiting_operator', 'resuming'):
                self._controls.pop(session, None)


operator_requests = OperatorRequests()
