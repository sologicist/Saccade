"""Shared session-bound learning control for the existing native Web agent."""

import secrets
import threading
import time
from pathlib import Path

from .business_contract import digest, dumps, loads, reject
from .learning_adapter import load_adapter
from .procedure_store import ProcedureStore
from .session_context import _validate_context


class PlatformLearningControl:
    """No browser driver, execution permission or independent run loop."""

    def __init__(self, context, session_id, *, project_root=None, stop_event=None, conversational=False):
        from .platform_config import PROJECT_ROOT
        self.project = Path(project_root or PROJECT_ROOT)
        self.context = _validate_context(context, root=self.project)
        if type(session_id) is not str or not 1 <= len(session_id) <= 128:
            reject("invalid_control_session")
        self.store = ProcedureStore(self.project, self.context['platform_id'])
        self.session_id = session_id
        self.run_id = secrets.token_hex(32)
        self.review_token = secrets.token_urlsafe(32)
        self.pin_revision = self.store.pin(session_id)
        self.stop_event = stop_event
        self.lock = threading.RLock()
        self.closed = False
        self.observation = None
        self.proposal = None
        self._source_revision = None
        self._last_observation_digest = None
        self.conversational = conversational
        self.teaching = None
        self.teaching_baseline = None

    def _invalidate_observation(self):
        pass

    def attach_teaching(self, teaching):
        from .navigation_correction import NavigationTeaching
        if type(teaching) is not NavigationTeaching:
            reject('invalid_navigation_teaching')
        if teaching.adapter != self.store.adapter:
            reject('teaching_platform_mismatch')
        self.teaching = teaching

    def learning_intervention(self):
        """Read only by the native loop after a fresh, scope-checked observation."""
        with self.lock:
            if not self.teaching:
                return None
            self._observation(self.observation['id'] if self.observation else None)
            request = self.teaching.intervention()
            if request:
                return request
            if self.proposal is None:
                self.proposal = self.store.propose(self.teaching.routes, self.run_id,
                    teaching_source='operator_chat_correction', observation_digest=digest(self.teaching.evidence), incremental=True, neutral=True)
            return {'category': 'confirmation', 'reason': 'condition_confirmation',
                    'request': 'I have corroborated the manually demonstrated sections. May I remember the proposed operator-assisted navigation procedure for future sessions?'}

    def freeze_decision(self):
        self.validate_native(self.context)
        self._source_revision = self.store.adapter.revision

    def validate_native(self, context):
        if _validate_context(context, root=self.project) != self.context or self.closed:
            reject("control_context_changed")
        if load_adapter(self.project, self.context["platform_id"]) != self.store.adapter:
            reject("learning_adapter_changed")
        return True

    def overlay(self):
        if _validate_context(self.context, root=self.project) != self.context:
            reject("control_context_changed")
        # Reopening verifies the persisted pin; active pointer changes cannot
        # silently alter a run or a resumed conversation's guidance.
        if self.store.pin(self.session_id) != self.pin_revision:
            reject("procedure_pin_changed")
        snapshot = self.store.snapshot(self.pin_revision)
        if snapshot["source"] == "baseline":
            return ""
        return ("<approved_navigation_guidance revision=\"" + self.pin_revision + "\">\n"
                "Operator-approved guidance only. It grants no action, disclosure or download permission.\n"
                + self.store.markdown(self.pin_revision) + "</approved_navigation_guidance>")

    def observe_native(self, elements, stamp):
        with self.lock:
            if self.closed or self.stop_event is not None and self.stop_event.is_set():
                reject("control_stopped")
            self.validate_native(self.context)
            required = {"observer", "tab", "profile", "config_revision", "platform_id"}
            if type(stamp) is not dict or set(stamp) not in (required, required | {"session"}) or ("session" in stamp and (type(stamp["session"]) is not str or not 1 <= len(stamp["session"]) <= 128)) or any(type(stamp[k]) is not str or not 1 <= len(stamp[k]) <= 128 for k in ("observer", "tab")) or stamp["profile"] != self.context["browser_profile"] or stamp["platform_id"] != self.context["platform_id"] or stamp["config_revision"] != self.context["config_revision"]:
                reject("unverified_navigation_observation")
            if type(elements) is not dict:
                reject("unverified_navigation_observation")
            dumps(elements, 524_288)
            self._invalidate_observation()
            self.observation = {"id": secrets.token_hex(32), "stamp": dict(stamp),
                                "elements": loads(dumps(elements, 524_288), 524_288),
                                "expires": time.monotonic() + 60}
            # Retain only a scope-evidence digest across handoff. Never save DOM
            # text, target IDs, raw record fields or the correction in the SOP.
            self._last_observation_digest = digest([self.run_id, self.observation["id"], stamp])
            from .navigation_correction import landmarks
            controls, headings = landmarks(elements, self.store.adapter)
            # Observer generations change on a verified handoff. The native
            # retained scanner's session identity remains stable; a new browser
            # can never corroborate the previous browser's source observation.
            surface = digest([stamp.get('session', stamp['observer']), *[stamp[k] for k in ('tab', 'profile', 'config_revision', 'platform_id')]])
            self.teaching_baseline = (controls, headings, self._last_observation_digest, surface)
            if self.teaching:
                self.teaching.observe(controls, headings, self._last_observation_digest, surface)

    def _observation(self, observation_id):
        if self.closed or not self.observation or self.observation["id"] != observation_id or time.monotonic() >= self.observation["expires"] or self.stop_event is not None and self.stop_event.is_set():
            reject("stale_navigation_observation")
        try:
            self.validate_native(self.context)
        except ValueError:
            reject("control_context_changed")
        self.overlay()  # Verify the persisted pinned revision again.
        if self._source_revision is None or self.store.adapter.revision != self._source_revision:
            reject("navigation_source_changed")

    def operator_event(self, body, *, busy):
        fields = {'review': {'proposal_id', 'base_revision', 'candidate_revision', 'approve'},
                  'adopt': set(), 'rollback': {'expected', 'target'}}
        if type(body) is not dict or type(body.get('review_token')) is not str or not secrets.compare_digest(body['review_token'], self.review_token):
            reject('operator_channel_required')
        event = body.get('event')
        if type(event) is not str or event not in fields or set(body) != fields[event] | {'event', 'review_token'}:
            reject('invalid_operator_event')
        with self.lock:
            # A closed execution may still receive its exact sealed review;
            # metadata and immutable pin must remain verified before publication.
            self.overlay()
            if event == 'review':
                if not self.proposal or any(body[k] != self.proposal[k] for k in ('proposal_id', 'base_revision', 'candidate_revision')):
                    reject('proposal_identity_mismatch')
                self.store.review(body['proposal_id'], body['base_revision'], body['candidate_revision'], body['approve'])
                self.proposal = None
            else:
                if busy or self.proposal:
                    reject('safe_boundary_required')
                if event == 'rollback':
                    self.store.rollback(body['expected'], body['target'], self.run_id)
                else:
                    self.pin_revision = self.store.pin(self.session_id, adopt=True)
            return {'status': 'reviewed', 'executed': False}

    def close(self):
        with self.lock:
            self.closed = True
            self.observation = None


def validate_learning_control(control, context):
    from .dext_control import DextRunControl
    if type(control) not in (PlatformLearningControl, DextRunControl):
        reject('operator_channel_required')
    control.validate_native(context)
    return control
