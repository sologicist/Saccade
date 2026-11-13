"""Trusted local UI review. Page/model content cannot approve host operations."""

from __future__ import annotations

import secrets
import threading
import time
from pathlib import Path

from .business_catalogue import catalogue, client_registration
from .business_contract import digest, dumps, loads, reject
from .procedure_store import ProcedureStore, ROUTES
from .session_context import _validate_context

NAVIGATION_TOOL = {"name": "dext_navigation", "description":
    "Request a one-step Dext navigation preview for independent operator review. "
    "This never clicks. Live target semantics and record identity are unverified; "
    "approved requests remain blocked pending a verified native Dext adapter. "
    "No authority, URLs, scripts, labels or client IDs can be supplied.",
    "parameters": {"type": "object", "properties": {
        "version": {"type": "integer", "enum": [1]},
        "route": {"type": "string", "enum": list(ROUTES)},
        "target_id": {"type": "integer", "minimum": 1}},
        "required": ["version", "route", "target_id"], "additionalProperties": False}}


class DextRunControl:
    """One UI-owned run, separate from the model and PR4 business permissions.

    Current native scope proves host/profile/download denial, not the semantic
    identity of a Dext workspace, record, frame or control. Human confirmation
    is recorded as a claim, never upgraded into a verified live adapter.
    """

    def __init__(self, context, session_id, *, project_root=None, stop_event=None, conversational=False):
        from .platform_config import PROJECT_ROOT
        self.project = Path(project_root or PROJECT_ROOT)
        self.context = _validate_context(context, root=self.project)
        if self.context["platform_id"] != "dext" or self.context["execution_mode"] != "supervised":
            reject("unsupported_navigation_session")
        if type(session_id) is not str or not 1 <= len(session_id) <= 128:
            reject("invalid_control_session")
        self.store = ProcedureStore(self.project)
        self.session_id = session_id
        self.run_id = secrets.token_hex(32)
        self.review_token = secrets.token_urlsafe(32)
        self.pin_revision = self.store.pin(session_id)
        self.stop_event = stop_event
        self.lock = threading.RLock()
        self.closed = False
        self.observation = None
        self.pending = None
        self.binding = None
        self.proposal = None
        self._navigation_decided = threading.Event()
        self._navigation_result = None
        self._source_revision = None
        self._last_observation_digest = None
        self.conversational = conversational
        self.teaching = None
        self.teaching_baseline = None

    def attach_teaching(self, teaching):
        from .navigation_correction import NavigationTeaching
        if type(teaching) is not NavigationTeaching:
            reject('invalid_navigation_teaching')
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
                    teaching_source='operator_chat_correction', observation_digest=digest(self.teaching.evidence), incremental=True)
            return {'category': 'confirmation', 'reason': 'condition_confirmation',
                    'request': 'I have corroborated the manually demonstrated sections. May I remember the proposed operator-assisted navigation procedure for future sessions?'}

    def freeze_decision(self):
        self.validate_native(self.context)
        self._source_revision = catalogue("dext")["revision"]

    def validate_native(self, context):
        if _validate_context(context, root=self.project) != self.context or self.closed:
            reject("control_context_changed")
        return True

    def overlay(self):
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
            if type(stamp) is not dict or set(stamp) != {"observer", "tab", "profile", "config_revision"} or any(type(stamp[k]) is not str or not 1 <= len(stamp[k]) <= 128 for k in ("observer", "tab")) or stamp["profile"] != "saccade-dext" or stamp["config_revision"] != self.context["config_revision"]:
                reject("unverified_navigation_observation")
            if type(elements) is not dict:
                reject("unverified_navigation_observation")
            dumps(elements, 524_288)
            # A fresh observation invalidates pending navigation and client claims,
            # even at the same URL and with a visually similar record.
            self.pending = self.binding = None
            self._navigation_result = None
            self._navigation_decided.set()
            self.observation = {"id": secrets.token_hex(32), "stamp": dict(stamp),
                                "elements": loads(dumps(elements, 524_288), 524_288),
                                "expires": time.monotonic() + 60}
            # Retain only a scope-evidence digest across handoff. Never save DOM
            # text, target IDs, raw record fields or the correction in the SOP.
            self._last_observation_digest = digest([self.run_id, self.observation["id"], stamp])
            from .navigation_correction import landmarks
            controls, headings = landmarks(elements)
            self.teaching_baseline = (controls, headings, self._last_observation_digest, stamp['tab'])
            if self.teaching:
                self.teaching.observe(controls, headings, self._last_observation_digest, stamp['tab'])

    def propose_navigation(self, action):
        with self.lock:
            if self.closed or self.stop_event is not None and self.stop_event.is_set():
                reject("control_stopped")
            if type(action) is not dict or set(action) != {"type", "version", "route", "target_id"} or action["type"] != "dext_navigation" or type(action["version"]) is not int or action["version"] != 1 or type(action["route"]) is not str or action["route"] not in ROUTES or type(action["target_id"]) is not int or not 1 <= action["target_id"] <= 2**31 - 1:
                reject("invalid_navigation_request")
            observation = self.observation
            if not observation or time.monotonic() >= observation["expires"]:
                reject("stale_navigation_observation")
            self._observation(observation["id"])
            target = observation["elements"].get(str(action["target_id"]))
            if type(target) is not dict or type(target.get("rect")) is not list or len(target["rect"]) != 4:
                reject("unobserved_navigation_target")
            if any(type(n) not in (int, float) or not -100_000 <= n <= 100_000 for n in target["rect"]) or target["rect"][2] <= 0 or target["rect"][3] <= 0:
                reject("unobserved_navigation_target")
            # No raw DOM text is persisted or returned to the model as a grant.
            # UI displays data through React text nodes, never innerHTML.
            name = target.get("name", "")
            role = target.get("role", "")
            if type(name) is not str or type(role) is not str or len(name) > 1000 or len(role) > 80:
                reject("unobserved_navigation_target")
            self.pending = {"proposal_id": secrets.token_hex(32), "observation_id": observation["id"],
                            "target_digest": digest(target), "target_id": action["target_id"],
                            "label": name, "role": role, "rect": target["rect"],
                            "route": action["route"], "expected_postcondition": ROUTES[action["route"]],
                            "procedure_revision": self.pin_revision, "policy_revision": self.context["config_revision"],
                            "stamp": observation["stamp"], "run_id": self.run_id,
                            "expires": observation["expires"]}
            self._navigation_result = None
            self._navigation_decided.clear()
            return {"status": "error", "tool": "dext_navigation", "code": "navigation_operator_review_required",
                    "proposal_id": self.pending["proposal_id"], "operator_review_required": True,
                    "message": "Review the exact target in Saccade. Live gesture execution remains blocked: Dext semantic/frame/record verification is unavailable."}

    def wait_navigation_review(self):
        """Park the existing native tool call; Event.wait releases the GIL."""
        if self.conversational:
            with self.lock:
                self.pending = None
                return {'status': 'error', 'tool': 'dext_navigation', 'code': 'verified_dext_navigation_adapter_required',
                        'operator_review_required': True, 'executed': False}
        while True:
            with self.lock:
                if self._navigation_result:
                    return {"status": "error", "tool": "dext_navigation", "operator_review_required": True,
                            **self._navigation_result}
                if self.closed or self.stop_event is not None and self.stop_event.is_set():
                    self.pending = None
                    return {"status": "stopped", "tool": "dext_navigation", "code": "control_stopped"}
                if not self.pending or time.monotonic() >= self.pending["expires"]:
                    self.pending = None
                    return {"status": "error", "tool": "dext_navigation", "code": "navigation_approval_expired", "operator_review_required": True}
            self._navigation_decided.wait(0.1)

    def status(self):
        with self.lock:
            clients, _ = client_registration(self.project / "platforms/dext/data")
            active = self.store.active()
            return {"session_id": self.session_id, "run_id": self.run_id, "review_token": self.review_token,
                    "closed": self.closed, "pinned_revision": self.pin_revision,
                    "active": active, "proposal": self.proposal,
                    "previous_content": self.store.snapshot(active["previous"])["content"] if active["previous"] else None,
                    "navigation": self.pending, "observation_id": self.observation["id"] if self.observation else None,
                    "binding": self.binding, "clients": list(clients), "routes": list(ROUTES),
                    "capabilities": {"navigation": "blocked_unverified_dext_semantics", "download": "blocked_native_deny",
                                     "live_bank": "blocked_record_and_disclosure_boundary", "live_scribe": "verified_download_receipt_required",
                                     "accounting_entry": "blocked_future_write_effect_phase"}}

    def operator_event(self, body, *, busy):
        """Called only behind the existing app authentication and Origin guard."""
        if type(body) is not dict or type(body.get("review_token")) is not str or not secrets.compare_digest(body["review_token"], self.review_token):
            reject("operator_channel_required")
        event = body.get("event")
        fields = {"teach": {"routes"}, "teach_correction": {"correction"}, "review": {"proposal_id", "base_revision", "candidate_revision", "approve"},
                  "adopt": set(), "rollback": {"expected", "target"},
                  "bind": {"client_id", "observation_id"}, "navigation_review": {"proposal_id", "observation_id", "approve"}}
        if type(event) is not str or event not in fields or set(body) != fields[event] | {"review_token", "event"}:
            reject("invalid_operator_event")
        with self.lock:
            if event in ("teach", "teach_correction"):
                if self.proposal:
                    reject("procedure_review_pending")
                if event == "teach_correction":
                    from .navigation_correction import correction_routes
                    routes = correction_routes(body["correction"])
                else:
                    routes = body["routes"]
                self.proposal = self.store.propose(routes, self.run_id,
                    teaching_source="operator_chat_correction" if event == "teach_correction" else "route_selection",
                    observation_digest=self._last_observation_digest)
            elif event == "review":
                if not self.proposal or any(body[k] != self.proposal[k] for k in ("proposal_id", "base_revision", "candidate_revision")):
                    reject("proposal_identity_mismatch")
                self.store.review(body["proposal_id"], body["base_revision"], body["candidate_revision"], body["approve"])
                self.proposal = None
            elif event in ("adopt", "rollback"):
                if busy or self.pending or self.proposal:
                    reject("safe_boundary_required")
                if event == "rollback":
                    self.store.rollback(body["expected"], body["target"], self.run_id)
                else:
                    self.pin_revision = self.store.pin(self.session_id, adopt=True)
            elif event == "bind":
                clients, registration = client_registration(self.project / "platforms/dext/data")
                self._observation(body["observation_id"])
                if type(body["client_id"]) is not str or body["client_id"] not in clients:
                    reject("unauthorized_client")
                self.binding = {"client_digest": digest(body["client_id"]), "registration_revision": registration,
                                "observation_id": body["observation_id"], "verified_for_business": False,
                                "status": "operator_claim_only_record_identity_unverified"}
            else:
                if type(body["approve"]) is not bool:
                    reject("invalid_operator_decision")
                self._observation(body["observation_id"])
                if not self.pending or self.pending["proposal_id"] != body["proposal_id"] or self.pending["observation_id"] != body["observation_id"]:
                    reject("stale_navigation_approval")
                self.pending = None  # Consumed even if execution is unavailable.
                self._navigation_result = {"code": "verified_dext_navigation_adapter_required" if body["approve"] else "operator_rejected", "executed": False}
                self._navigation_decided.set()
                return {"status": "blocked" if body["approve"] else "rejected", **self._navigation_result}
            return {"status": "reviewed", "executed": False}

    def _observation(self, observation_id):
        if self.closed or not self.observation or self.observation["id"] != observation_id or time.monotonic() >= self.observation["expires"] or self.stop_event is not None and self.stop_event.is_set():
            reject("stale_navigation_observation")
        try:
            self.validate_native(self.context)
        except ValueError:
            reject("control_context_changed")
        self.overlay()  # Verify the persisted pinned revision again.
        if self._source_revision is None or catalogue("dext")["revision"] != self._source_revision:
            reject("navigation_source_changed")

    def close(self):
        with self.lock:
            self.closed = True
            self.observation = self.pending = self.binding = None
            self._navigation_decided.set()


def validate_control(control, context):
    if type(control) is not DextRunControl:
        reject("operator_channel_required")
    control.validate_native(context)
    return control
