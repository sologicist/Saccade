"""Same-process continuation broker. Answers never confer execution authority."""
import copy
import re
import secrets
import threading

from .business_contract import digest, reject

CATEGORIES = ('question', 'manual_action', 'authentication', 'confirmation', 'blocked')
REASONS = ('missing_information', 'manual_intervention', 'authentication_required', 'condition_confirmation', 'unsafe_or_blocked', 'no_progress')
_SECRET = re.compile(r'password|mot de passe|\bmfa\b|\botp\b|\b2fa\b|\bpin\b|verification.?code|authentication.?code|code de verification|api.?key|(?:session|access).?token|bearer|private.?key|secret|credential|\b\d{6}\b|sk-[A-Za-z0-9]+', re.I)


def validate_request(value):
    if type(value) is not dict or set(value) != {'category', 'reason', 'request'}:
        reject('invalid_operator_request')
    if value['category'] not in CATEGORIES or value['reason'] not in REASONS or type(value['request']) is not str or not 1 <= len(value['request']) <= 1000:
        reject('invalid_operator_request')
    if value['category'] == 'authentication':
        return {**value, 'request': 'Complete authentication privately in the external environment, then resume. Do not enter credentials in chat.'}
    if _SECRET.search(value['request']) or re.search(r'[<>]|[A-Za-z]:\\|(?:^|\s)/\w|https?://|javascript:|\beval\(|powershell|cmd\.exe|\bbash\b|\bshell\b|python\s+-', value['request'], re.I):
        reject('unsafe_operator_request')
    return dict(value)


class OperatorRequests:
    """No waiting execution thread, timers, model polling or persisted answers.

    Continuation uses the existing launcher/conversation and fresh native scanning.
    Passive browser ownership stays here until resume or explicit cleanup. No
    execution thread or model client is running while waiting. Process restart
    recovery is intentionally absent.
    """
    def __init__(self):
        self.lock = threading.RLock()
        self.pending = {}
        self._browsers = {}

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
            original = previous['data'] if previous and previous['state'] == 'resuming' else data
            item = {'session_id': session, 'run_id': run, 'intervention_id': secrets.token_hex(24),
                    'revision': secrets.token_hex(32), 'token': secrets.token_urlsafe(32),
                    'state': 'waiting_operator', 'request': request, 'data': copy.deepcopy(original), 'error': None,
                    'policy_revision': digest({k: original.get(k) for k in ('platform_id', 'execution_mode', 'browser_profile', 'mode', 'speed')})}
            self.pending[session] = item

    def status(self, session):
        with self.lock:
            item = self.pending.get(session)
            return {k: copy.deepcopy(v) for k, v in item.items() if k != 'data'} if item else None

    def consume(self, session, event):
        with self.lock:
            item = self.pending.get(session)
            keys = {'run_id', 'intervention_id', 'revision', 'token', 'action', 'answer', 'non_sensitive'}
            if not item or type(event) is not dict or set(event) != keys or (item['state'] != 'waiting_operator' and not (item['state'] == 'resuming' and event.get('action') == 'cancel')):
                reject('stale_operator_response')
            if any(type(event[k]) is not str or not secrets.compare_digest(event[k], item[k]) for k in ('run_id', 'intervention_id', 'revision', 'token')):
                reject('stale_operator_response')
            if event['action'] == 'cancel':
                item['state'] = 'cancelled'
                return None
            if event['action'] != 'resume':
                reject('invalid_operator_response')
            if item['data'].get('_checkpoint_unavailable'):
                reject('continuation_checkpoint_unavailable')
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
            data['task'] = (item['data']['task'] + '\n\nOperator intervention completed. Reobserve the environment before acting. '
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


operator_requests = OperatorRequests()
