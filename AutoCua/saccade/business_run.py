"""Per-run trusted selections and single-use business execution tickets."""

from __future__ import annotations

import os
import secrets
import threading
from pathlib import Path

from .business_catalogue import PACKAGE_ROOT, catalogue, client_registration, model_tool
from .business_contract import BusinessError, digest, dumps, loads, read_safe, reject, validate
from .session_context import _validate_context
from .client_references import require_reference_bundle


class BusinessRun:
    """Only the trusted host constructs this object; no model-supplied roots."""

    def __init__(self, context, *, project_root=None, package_root=PACKAGE_ROOT, offline_receipts=None):
        self.context = _validate_context(context, root=project_root)
        if self.context["platform_id"] != "dext" or self.context["execution_mode"] != "supervised":
            reject("unsupported_business_session")
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

    def snapshot(self):
        try:
            _validate_context(self.context, root=self.project_root)
        except ValueError:
            reject("business_revision_changed")
        current = catalogue("dext", package_root=self.package_root)
        clients, registration = client_registration(self.data_root)
        if tuple(clients) != self._clients:
            reject("business_client_scope_changed")
        references = {}
        for client, policy in clients.items():
            # The live boundary is still closed. Never pre-read a real corpus
            # merely because an operator registered its local client ID.
            if not policy["synthetic"]:
                continue
            for name in ("comptable_banque.md", "comptable_achats.md", "comptable_ventes.md"):
                path = self.data_root / client / name
                try:
                    path.lstat()
                except FileNotFoundError:
                    references[name] = digest(["reference-absent"])
                else:
                    references[name] = digest(["reference-present", digest(read_safe(self.data_root, path, 2 * 1024 * 1024))])
        current["revision"] = digest([current["revision"], registration, references, self.context, self.offline_receipts])
        return current, clients

    def refresh(self):
        """Called before every model decision, never after its chosen revision."""
        _validate_context(self.context, root=self.project_root)
        with self._lock:
            self._decision, _ = self.snapshot()
            self._pending.clear()
            return model_tool(self._decision)

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
            if clients[client]["synthetic"] is not True:
                reject("real_client_privacy_gate_closed")
            if action["name"] == "dext.bank" and arguments["string"] not in clients[client]["bank_labels"]:
                reject("operator_argument_required")
            if action["name"] == "dext.scribe":
                receipt = self.offline_receipts.get(arguments["pdf"])
                if not receipt or receipt.get("client_id") != client or receipt.get("sens") != arguments["sens"]:
                    reject("verified_download_receipt_required")
            token = secrets.token_hex(24)
            ticket = {"version": 1, "call_id": token, "run_id": self.run_id,
                      "platform_id": "dext", "context_revision": self.context["config_revision"],
                      "revision": current["revision"], "effect": entry["effect"],
                      "capabilities": entry["capabilities"], "action": loads(dumps(action)),
                      "arguments": arguments, "name": action["name"]}
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
            model = os.environ.get("COMPTABLE_LLM_MODEL", "offline-synthetic-v1")
            if model != "offline-synthetic-v1":
                reject("external_provider_consent_required")
            require_reference_bundle(self.data_root, ticket["arguments"]["client_id"])
            request = {"version": 1, "ticket": ticket, "context": self.context,
                       "project_root": str(self.project_root), "offline_receipts": self.offline_receipts,
                       "model": model}
            reply = run_worker(request, package_root=self.package_root, stop_event=stop_event)
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
            if ticket["name"] == "dext.bank" and reply["result"]["compte"] is None or ticket["name"] == "dext.scribe" and (reply["result"]["type"] != "facture" or not reply["result"]["ecriture"]):
                result["operator_review_required"] = True
            return result
        except OSError:
            return {"status": "error", "tool": "call_function", "code": "worker_unavailable", "operator_review_required": True}
        except BusinessError as error:
            return {"status": "stopped" if str(error) == "worker_cancelled" else "error",
                    "tool": "call_function", "code": str(error), "operator_review_required": True}


WORKER_ERRORS = {"business_revision_changed", "required_file_unavailable", "unsafe_path", "size_limit",
                 "invalid_bank_reference", "conflicting_bank_account", "invalid_provider_response",
                 "verified_download_receipt_required", "offline_fixture_identity_mismatch",
                 "invoice_critical_mismatch", "invoice_total_mismatch", "invoice_entries_mismatch",
                 "invalid_invoice_amount", "invalid_invoice_entry", "invalid_invoice_account",
                 "invalid_invoice_value", "external_provider_consent_required", "schema_mismatch",
                 "invalid_bank_label", "invalid_bank_account", "invalid_reference_encoding",
                 "invalid_invoice_direction", "invalid_invoice_entries", "invalid_invoice_journal",
                 "invalid_invoice_date", "invalid_invoice_currency", "incomplete_invoice_proposal",
                 "duplicate_json_key", "nonfinite_number", "invalid_json", "empty_reference", "file_changed_during_read",
                 "json_integer_limit", "schema_depth", "invalid_reference_content", "unsafe_reference_link",
                 "unexpected_reference_file", "unapproved_reference_file"}
