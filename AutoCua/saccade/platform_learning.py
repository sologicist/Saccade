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
    """Session hooks for learning and exact execution decisions; no agent loop."""

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
        from .execution import ExecutionAuthority
        self.execution = ExecutionAuthority(self.project, self.context, self.session_id)

    def execution_tools(self):
        if self.context['execution_mode'] != 'supervised':
            return None
        from .capabilities import catalogue, tool
        snapshot = catalogue(self.project, self.context['platform_id'])
        return tool(snapshot) if snapshot['functions'] else None

    def authorize_execution(self, action, stamp, elements):
        self.validate_native(self.context)
        if self.context['execution_mode'] != 'supervised':
            return {'unavailable':True}
        from .capabilities import catalogue
        kind = action.get('type')
        if kind == 'call_function':
            snapshot = catalogue(self.project, self.context['platform_id'])
            entry = snapshot['functions'].get(action.get('name'))
            if not entry:
                return {'unavailable': True}
            from .business_contract import validate
            arguments = action.get('arguments')
            if type(arguments) is not dict: reject('schema_mismatch')
            arguments = {k:v for k,v in arguments.items() if v is not None or k in entry['input_schema']['properties']}
            validate(arguments, entry['input_schema'])
            target = {'function':entry['id'], 'arguments':action['arguments'],
                      'result_visibility':entry['output_visibility'], 'description':entry['description']}
            if entry.get('builtin') and entry['id'] == 'dext.scribe_pdf':
                from .scribe_pdf import prepare
                target['scribe'] = prepare(self.project,self.context,self.session_id,arguments,stamp,elements)
            if entry.get('document_input'):
                from .capabilities import verified_download
                receipt = verified_download(self.project, self.context, self.session_id, arguments[entry['document_input']])
                if entry.get('requires_verified_record') and not receipt['record_identity_verified']:
                    reject('verified_record_identity_required')
                target['document'] = {k:receipt[k] for k in ('id','sha256','bytes','record_identity_verified')}
            return self.execution.decide(action, stamp, target,
                effect=entry['effect'], destination=entry['destination'], revision=snapshot['revision'], run_id=self.run_id)
        if kind not in ('click', 'hold_click', 'input', 'keyboard', 'dialog', 'download'):
            return {'unavailable': True}
        if kind == 'keyboard':
            # Reuse the native renderer-only shortcut parser and dispatch.
            # Exact approval still binds the observed focus and page.
            if type(stamp.get('focus')) is not dict or stamp['focus'].get('type') in ('password','file') or stamp['focus'].get('tag') in ('IFRAME','FRAME'):
                reject('private_manual_input_required')
            target = {'page_digest':digest(elements),'focus':stamp['focus']}
        elif kind == 'dialog':
            if not stamp.get('dialog'): reject('unobserved_execution_target')
            target = {'page_digest':digest(elements),'dialog':stamp['dialog']}
        else:
            key = action.get('target_id') if kind == 'download' else action.get('id')
            target = elements.get(str(key))
            if type(target) is not dict:
                reject('unobserved_execution_target')
            line = str(target.get('line', '')).lower()
            if 'password' in line or 'type="file"' in line:
                reject('private_manual_input_required')
        
        # Supervised uses the normal AutoCua Web interactions.
        # No platform-specific navigation whitelist is required.
        # The native controller still validates the observed target,
        # browser ownership and platform scope.
        download_click = kind in ('click','hold_click') and (
            str(target.get('name','')).strip().casefold() in ('download','download pdf','telecharger','télécharger','télécharger pdf')
            or ' download=' in str(target.get('line','')))
        if kind in ('click', 'hold_click', 'input', 'keyboard') and not download_click:
            return {
                'allowed': True,
                'effect': 'interaction',
            }

        # Downloads and confirmation dialogs remain subject
        # to separate, explicit authorization.
        effect = 'download' if kind == 'download' or download_click else 'interaction'

        target = {
            **target,
            'observation_digest': digest(elements),
        }

        return self.execution.decide(
            action,
            stamp,
            target,
            effect=effect,
            destination=(
                'Chrome-managed destination (unverified; scoped downloads remain denied)'
                if download_click else 'private platform download storage'
                if effect == 'download'
                else self.context['platform_id']
            ),
            run_id=self.run_id,
        )


    def execute_capability(self, action):
        self.validate_native(self.context)
        self.execution.validate()
        from .capabilities import catalogue
        from .business_process import run_worker
        snapshot = catalogue(self.project, self.context['platform_id'])
        entry = snapshot['functions'].get(action['name'])
        if not entry:
            reject('unregistered_capability')
        decision = self.execution.pending
        if not decision or decision['state'] != 'consumed' or decision['binding']['revision'] != snapshot['revision'] or decision['binding']['action'] != action:
            reject('capability_authorization_required')
        authorization = loads(dumps(decision)) if entry.get('builtin') else None
        decision['state'] = 'executing'
        extra = {}
        if authorization:
            from .scribe_pdf import credentials
            extra = {'authorization':authorization}
            provider_environment = credentials(self.project)
        else:
            provider_environment = None
        result = run_worker({'version':2, 'session_id':self.session_id, 'context':self.context, 'project_root':str(self.project),
            **extra, 'revision':snapshot['revision'], 'name':action['name'], 'arguments':{k:v for k,v in action['arguments'].items() if v is not None or k in entry['input_schema']['properties']}},
            package_root=Path(__file__).resolve().parents[1], stop_event=self.stop_event,
            timeout=100 if authorization else 10, provider_environment=provider_environment)
        decision['state'] = 'completed' if result.get('status') == 'success' else 'failed'
        if entry['output_visibility'] == 'operator' and result.get('status') == 'success':
            key = secrets.token_hex(24)
            self.store._write('results/' + key + '.json', {'session':self.session_id, 'platform':self.context['platform_id'], 'result':result['result']}, exclusive=True)
            self.execution.receipts[key] = result['result']
            return {'status':'success','tool':'call_function','result_receipt':key,
                    'message':'The actual result is available locally to the operator; it was not disclosed to the model.'}
        return {**result, 'tool':'call_function'}

    def fail_execution(self):
        """An uncertain effect never restores a consumed one-use approval."""
        with self.execution.lock:
            if self.execution.pending:
                self.execution.pending['state'] = 'failed'

    def save_download(self, result):
        import base64
        from .business_contract import read_safe
        self.validate_native(self.context)
        decision = self.execution.pending
        if not decision or decision['state'] != 'consumed' or decision['binding']['effect'] != 'download':
            reject('download_authorization_required')
        decision['state'] = 'executing'
        if type(result) is not dict or set(result) != {'base64','size','mime'} or result['mime'] not in ('application/pdf','application/octet-stream','text/plain'):
            reject('invalid_download_receipt')
        if type(result['base64']) is not str or len(result['base64']) > 12 * 1024 * 1024:
            reject('download_size_limit')
        try:
            content = base64.b64decode(result['base64'], validate=True)
        except Exception:
            reject('invalid_download_receipt')
        if type(result['size']) is not int or not 0 < len(content) == result['size'] <= 8 * 1024 * 1024:
            reject('invalid_download_receipt')
        if result['mime'] == 'application/pdf' and not content.startswith(b'%PDF-'):
            reject('invalid_pdf_download')
        # Reuse the store's path and atomic publication protections; downloaded
        # data remains under this platform's Git/package-excluded data directory.
        identifier = secrets.token_hex(24)
        extension = {'application/pdf':'.pdf', 'text/plain':'.txt', 'application/octet-stream':'.bin'}[result['mime']]
        relative = 'downloads/' + identifier + extension
        self.store._publish(relative, content, exclusive=True)
        path = self.store.root / relative
        verified = read_safe(self.project, path, 8 * 1024 * 1024)
        if verified != content:
            reject('download_file_changed')
        receipt = {'id':identifier, 'platform_id':self.context['platform_id'], 'session':self.session_id,
            'sha256':digest(content), 'bytes':len(content), 'mime':result['mime'],
            'path':str(path), 'decision_id':decision['id'], 'binding_digest':decision['identity'],
            'source':{k:decision['binding'][v] for k,v in (('session','browser'),('tab','tab'),('page','page'))},
            'observation_digest':decision['binding']['target'].get('observation_digest'),
            'record_identity_verified':False}
        self.store._write('downloads/' + identifier + '.receipt.json', receipt, exclusive=True)
        decision['state'] = 'completed'
        self.execution.receipts[identifier] = receipt
        # Path/contents stay operator-local; only the receipt metadata enters the model.
        return {'status':'success','tool':'download','receipt_id':identifier,'sha256':receipt['sha256'],
            'bytes':len(content), 'relative_path':str(path.relative_to(self.project)), 'record_identity_verified':False}

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
