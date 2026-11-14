"""Session-local execution decisions. Procedure text is never authority."""
import copy
import secrets
import threading
import time
from pathlib import Path

from .business_contract import digest, dumps, reject
from .session_context import _validate_context

EFFECTS = ('navigation', 'interaction', 'download', 'read', 'compute', 'disclosure', 'mutation', 'delete')



def execution_policy(project, context):
    """Common execution contract; no per-platform click whitelist."""
    _validate_context(context, root=project)

    policy = {
        'schema_version': 1,
        'navigation': [],
    }

    return policy, digest(policy)



class ExecutionAuthority:
    """Host-only, one-use, exact action approval retained by the existing broker.

    The native scanner provides session/tab/config and a target fingerprint.
    Approval survives an observer refresh, never a replacement browser. Pending
    decisions are not persisted or resurrected after process restart.
    """
    def __init__(self, project, context, session):
        self.project, self.context, self.session = Path(project), copy.deepcopy(context), session
        self.lock = threading.RLock()
        self.pending = None
        self.receipts = {}
        self.policy, self.policy_revision = execution_policy(self.project, self.context)

    def validate(self):
        if digest(self.policy) != self.policy_revision or _validate_context(self.context, root=self.project) != self.context or execution_policy(self.project, self.context)[1] != self.policy_revision:
            reject('execution_policy_changed')

    def decide(self, action, stamp, target, *, effect, destination='', revision='', run_id=''):
        with self.lock:
            self.validate()
            if self.context['execution_mode'] != 'supervised':
                reject('supervised_execution_required')
            if effect not in EFFECTS or type(action) is not dict or type(stamp) is not dict or stamp.get('platform_id') != self.context['platform_id'] or stamp.get('profile') != self.context['browser_profile'] or stamp.get('config_revision') != self.context['config_revision'] or not stamp.get('session') or not stamp.get('tab'):
                reject('execution_context_invalid')
            dumps([action, target], 65_536)
            binding = {'context': self.context, 'session': self.session, 'browser': stamp['session'], 'tab': stamp['tab'],
                       'page':stamp.get('page'), 'policy': self.policy_revision, 'action': action, 'target': target, 'effect': effect,
                       'destination': destination, 'revision': revision}
            identity = digest(binding)
            pending = self.pending
            if pending and pending['identity'] == identity and pending['expires'] > time.monotonic() and pending['state'] == 'approved':
                # Consume BEFORE dispatch; failures never restore this grant.
                pending['state'] = 'consumed'
                return {'allowed': True, 'decision_id': pending['id'], 'effect': effect}
            if pending and pending['state'] in ('consumed', 'executing', 'completed', 'failed', 'rejected') and pending['identity'] == identity:
                reject('execution_decision_consumed')
            if pending and pending['identity'] == identity and pending['expires'] > time.monotonic():
                return {'allowed': False}
            self.pending = {'id': secrets.token_hex(24), 'identity': identity, 'binding': copy.deepcopy(binding),
                'origin_run':run_id, 'state': 'pending', 'expires': time.monotonic() + 300,
                'summary': dumps({'operation': action, 'target': target, 'effect': effect, 'destination': destination}, 65_536)}
            return {'allowed': False}

    def review(self, identity, approve):
        with self.lock:
            self.validate()
            item = self.pending
            if type(approve) is not bool or not item or item['id'] != identity or item['state'] != 'pending' or item['expires'] <= time.monotonic():
                reject('stale_execution_decision')
            item['state'] = 'approved' if approve else 'rejected'

    def cancel(self):
        with self.lock:
            if self.pending:
                self.pending['state'] = 'rejected'

