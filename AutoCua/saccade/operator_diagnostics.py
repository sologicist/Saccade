"""Bounded lifecycle diagnostics containing codes and hashed correlations only."""

import hashlib
import logging
import threading
from collections import deque

CODES = frozenset(('handoff_retained', 'resume_requested', 'resume_attached', 'resume_observed',
    'conversation_binding_invalid', 'browser_process_unavailable', 'chrome_pipe_disconnected',
    'profile_lease_lost', 'foreign_browser_ownership', 'native_checkpoint_invalid',
    'paired_history_mismatch', 'platform_scope_mismatch', 'configuration_revision_mismatch',
    'operator_control_mismatch', 'observation_failed', 'unsupported_navigation',
    'unverified_external_effect', 'internal_exception'))
HARD_FAILURES = CODES - {'handoff_retained', 'resume_requested', 'resume_attached', 'resume_observed', 'unsupported_navigation'}
_events = deque(maxlen=128)
_lock = threading.RLock()


def correlation(value):
    return hashlib.sha256(str(value or '')[:256].encode('utf-8')).hexdigest()[:16]


def record(code, session, run, phase):
    if code not in CODES or phase not in ('startup', 'handoff', 'resume', 'observation', 'execution'):
        code, phase = 'internal_exception', 'execution'
    event = {'code': code, 'session': correlation(session), 'run': correlation(run), 'phase': phase}
    with _lock:
        _events.append(event)
    # No exception objects, messages, arbitrary fields, URLs or browser data.
    logging.getLogger('saccade.operator').warning('operator_lifecycle %s', event)
    return code


def events(session):
    with _lock:
        return [dict(row) for row in _events if row['session'] == correlation(session)]


def classify(error):
    """Use typed/stable contracts only; never echo unknown exception content."""
    message = str(error)
    if message.startswith('operator_resume:') and message[16:] in HARD_FAILURES:
        return message[16:]
    from .profile_lease import ProfileBusyError
    from .session_context import SessionContextError, SessionConflictError
    if isinstance(error, SessionConflictError):
        return 'configuration_revision_mismatch'
    if isinstance(error, SessionContextError):
        return 'conversation_binding_invalid'
    if isinstance(error, ProfileBusyError):
        return 'profile_lease_lost'
    return {'control_context_changed': 'operator_control_mismatch',
            'control_stopped': 'operator_control_mismatch',
            'learning_platform_mismatch': 'platform_scope_mismatch',
            'learning_adapter_changed': 'configuration_revision_mismatch',
            'procedure_pin_changed': 'native_checkpoint_invalid'}.get(message, 'internal_exception')
