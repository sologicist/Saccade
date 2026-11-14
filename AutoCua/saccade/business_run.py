"""Per-run trusted selections and single-use business execution tickets."""

from __future__ import annotations

import secrets
import threading
import time
from pathlib import Path

from .business_catalogue import PACKAGE_ROOT, catalogue, client_registration, model_tool
from .business_contract import BusinessError, digest, dumps, loads, reject, validate
from .session_context import _validate_context


class BusinessRun:
    """Only the trusted host constructs this object; no model-supplied roots."""

    def __init__(self, context, *, project_root=None, package_root=PACKAGE_ROOT, offline_receipts=None, automatic=True, downloads_dir=None, download_since_ns=None):
        self.context = _validate_context(context, root=project_root)
        if self.context["platform_id"] != "dext" or self.context["execution_mode"] != "supervised":
            reject("unsupported_business_session")
        self.automatic = automatic
        self.downloads_dir = downloads_dir
        self.download_since_ns = time.time_ns() if download_since_ns is None else download_since_ns
        self._documents = {}
        self._google_model = None
        self._google_key = None
        self._current_download = None
        self._download_operation = None
        self.package_root = package_root
        self.project_root = Path(project_root) if project_root else package_root.parent
        self.data_root = self.project_root / "platforms/dext/data"
        self.offline_receipts = offline_receipts or {}
        self.run_id = secrets.token_hex(24)
        self._lock = threading.Lock()
        self._decision = None
        self._pending = {}
        self.receipts = []
        self._clients = tuple(client_registration(self.data_root)[0])

    def set_google_runtime(self, provider, model, api_key):
        """Host-only application settings, never model-selected arguments."""
        self._google_model = model if provider == 'google' else None
        self._google_key = api_key if provider == 'google' else None

    def snapshot(self):
        try:
            _validate_context(self.context, root=self.project_root)
        except ValueError:
            reject("business_revision_changed")
        current = catalogue("dext", package_root=self.package_root)
        if self.automatic:
            # Live accounting includes a provider disclosure, while explicit
            # offline test contexts retain the PR4 compute-only contract.
            for function in current['functions'].values():
                function['effect'] = 'disclosure'
        clients, registration = client_registration(self.data_root)
        if tuple(clients) != self._clients:
            reject("business_client_scope_changed")
        current["revision"] = digest([current["revision"], registration, self.context, self.offline_receipts, self.automatic])
        return current, clients

    def note_download(self, absolute_path, started_ns):
        """Host-only Chrome result, never a model-selected folder setting."""
        with self._lock:
            if not self.automatic or type(started_ns) is not int or not self._download_operation or started_ns != self._download_operation:
                reject('download_operation_changed')
            # A failed new file check must not leave an earlier PDF selectable.
            self._current_download = (None, None)
            self._pending.clear()
            self._documents.clear()
            from .downloaded_pdf import resolve_download
            try:
                path = Path(absolute_path)
                if not path.is_absolute():
                    reject('invalid_download_path')
                absolute, content = resolve_download(str(path),folder=path.parent,since_ns=self.download_since_ns)
            except BusinessError:
                self._download_operation = None
                raise
            self.downloads_dir = path.parent
            self._current_download = (absolute, digest(content))

    def begin_download(self, started_ns):
        """Host click timestamp replaces the earlier file-selection window."""
        if not self.automatic or type(started_ns) is not int or started_ns <= 0:
            reject('invalid_download_observation')
        with self._lock:
            if started_ns == self._download_operation:
                return
            self.download_since_ns = started_ns
            self._download_operation = started_ns
            self._current_download = None
            self._pending.clear()
            self._documents.clear()

    def invalidate_download(self, started_ns):
        """A failed observation cannot leave an earlier PDF or ticket usable."""
        with self._lock:
            if started_ns == self._download_operation:
                self._current_download = None
                self._download_operation = None
                self._pending.clear()
                self._documents.clear()

    def refresh(self):
        """Called before every model decision, never after its chosen revision."""
        _validate_context(self.context, root=self.project_root)
        with self._lock:
            self._decision, clients = self.snapshot()
            self._pending.clear()
            self._documents.clear()
            definition = model_tool(self._decision, offline=not self.automatic)
            if self.automatic:
                definition["description"] += " Active operator-registered client: " + (next(iter(clients), "unconfigured")) + ". Only analyze the document explicitly requested by the user. Scribe uses the configured AutoCua Gemini provider and sends that PDF and its client reference for the requested analysis."
            return definition

    def prepare(self, action):
        with self._lock:
            dumps(action, 32_768)
            if type(action) is not dict or set(action) != {"type", "version", "name", "arguments"} or action["type"] != "call_function" or type(action["version"]) is not int or action["version"] != 1:
                reject("invalid_business_request")
            if not self._decision:
                reject("business_decision_required")
            current, clients = self.snapshot()
            if current["revision"] != self._decision["revision"]:
                reject("business_revision_changed")
            if type(action["name"]) is not str or action["name"] not in current["functions"]:
                reject("unapproved_callable")
            entry = current["functions"][action["name"]]
            if type(action["arguments"]) is not dict:
                reject("schema_mismatch")
            if set(action["arguments"]) - {"string", "client_id", "pdf", "sens"}:
                reject("schema_mismatch")
            fields = entry["input_schema"]["properties"]
            arguments = {k: v for k, v in action["arguments"].items() if k in fields or v is not None}
            validate(arguments, entry["input_schema"])
            client = arguments["client_id"]
            if client not in clients:
                reject("unauthorized_client")
            if not self.automatic and clients[client]["synthetic"] is not True:
                reject("real_client_privacy_gate_closed")
            if not self.automatic and action["name"] == "dext.bank" and arguments["string"] not in clients[client]["bank_labels"]:
                reject("operator_argument_required")
            document_hash = None
            if self.automatic and action["name"] == "dext.scribe":
                if not self._download_operation or not self._current_download or not all(self._current_download):
                    reject('chrome_confirmed_download_required')
                from .downloaded_pdf import resolve_download
                absolute, content = resolve_download(arguments["pdf"],folder=self.downloads_dir,since_ns=self.download_since_ns)
                if self._current_download != (absolute,digest(content)):
                    reject('download_file_changed')
                arguments["pdf"] = absolute
                document_hash = digest(content)
            if not self.automatic and action["name"] == "dext.scribe":
                receipt = self.offline_receipts.get(arguments["pdf"])
                if not receipt or receipt.get("client_id") != client or receipt.get("sens") != arguments["sens"]:
                    reject("verified_download_receipt_required")
            token = secrets.token_hex(24)
            ticket = {"version": 1, "call_id": token, "run_id": self.run_id,
                      "platform_id": "dext", "context_revision": self.context["config_revision"],
                      "revision": current["revision"], "effect": entry["effect"],
                      "capabilities": entry["capabilities"], "action": loads(dumps(action)),
                      "arguments": arguments, "name": action["name"]}
            if document_hash:
                self._documents[token] = document_hash
            self._pending[token] = ticket
            return loads(dumps(ticket))

    def execute(self, ticket, stop_event=None):
        from .business_process import run_worker
        try:
            with self._lock:
                token = ticket.get("call_id") if type(ticket) is dict else None
                trusted = self._pending.pop(token, None)
                if trusted is None or ticket != trusted:
                    reject("invalid_or_consumed_business_ticket")
                current, _ = self.snapshot()
                if current["revision"] != ticket["revision"]:
                    reject("business_revision_changed")
            model = 'offline-synthetic-v1'
            options = {}
            request = {"version": 1, "ticket": ticket, "context": self.context,
                       "project_root": str(self.project_root), "offline_receipts": self.offline_receipts,
                       "model": model}
            if self.automatic:
                from .accounting_provider import settings
                model, provider_environment = settings(self._google_model,self._google_key)
                request['model'] = model
                from .downloaded_pdf import downloads_folder
                request.update(automatic=True, download_since_ns=self.download_since_ns,
                    downloads_dir=str(self.downloads_dir or downloads_folder()),
                    document_sha256=self._documents.pop(token,None))
                options = {'provider_environment':provider_environment, 'timeout':100}
            reply = run_worker(request, package_root=self.package_root, stop_event=stop_event, **options)
            if type(reply) is not dict or set(reply) != {"version", "call_id", "run_id", "status", "result", "error", "references"} or type(reply["version"]) is not int or reply["version"] != 1 or reply["call_id"] != token or reply["run_id"] != self.run_id:
                reject("invalid_worker_response")
            if reply["status"] != "success":
                reject(reply["error"] if type(reply["error"]) is str and reply["error"] in WORKER_ERRORS else "worker_failed")
            references = reply["references"]
            if type(references) is not dict or not references or set(references) - {"comptable_banque.md", "comptable_achats.md", "comptable_ventes.md"} or any(type(v) is not str or len(v) != 64 or any(c not in "0123456789abcdef" for c in v) for v in references.values()):
                reject("invalid_worker_response")
            validate(reply["result"], current["functions"][ticket["name"]]["output_schema"])
            self.receipts.append({"call_id": token, "run_id": self.run_id, "revision": ticket["revision"],
                                  "client_digest": digest(ticket["arguments"]["client_id"]),
                                  "references": reply["references"]})
            result = {"status": "success", "tool": "call_function", "result": reply["result"]}
            if ticket["name"] == "dext.bank" and reply["result"]["compte"] is None or ticket["name"] == "dext.scribe" and reply["result"]["type"] != "devis" and not reply["result"]["ecriture"]:
                result["operator_review_required"] = True
            return result
        except OSError:
            return {"status": "error", "tool": "call_function", "code": "worker_unavailable", "operator_review_required": True}
        except BusinessError as error:
            return {"status": "stopped" if str(error) == "worker_cancelled" else "error",
                    "tool": "call_function", "code": str(error), "operator_review_required": True}


WORKER_ERRORS = {"accounting_model_required", "accounting_model_unavailable", "accounting_provider_key_missing", "accounting_provider_dependency_missing",
                 "accounting_provider_incomplete", "accounting_provider_invalid_response", "accounting_provider_failed",
                 "invalid_download_path", "invalid_download_filename", "download_outside_folder",
                 "invalid_download_pdf", "download_incomplete", "download_file_missing", "download_stale", "download_file_changed","business_revision_changed", "required_file_unavailable", "unsafe_path", "size_limit",
                 "chrome_confirmed_download_required", "download_operation_changed",
                 "invalid_bank_reference", "conflicting_bank_account", "invalid_provider_response",
                 "verified_download_receipt_required", "offline_fixture_identity_mismatch",
                 "invoice_critical_mismatch", "invoice_total_mismatch", "invoice_entries_mismatch",
                 "invalid_invoice_amount", "invalid_invoice_entry", "invalid_invoice_account",
                 "invalid_invoice_value", "unsupported_offline_model", "schema_mismatch",
                 "invalid_bank_label", "invalid_bank_account", "invalid_reference_encoding",
                 "invalid_invoice_direction", "invalid_invoice_entries", "invalid_invoice_journal",
                 "invalid_invoice_date", "invalid_invoice_currency", "incomplete_invoice_proposal",
                 "duplicate_json_key", "nonfinite_number", "invalid_json", "empty_reference", "file_changed_during_read",
                 "json_integer_limit", "schema_depth"}
