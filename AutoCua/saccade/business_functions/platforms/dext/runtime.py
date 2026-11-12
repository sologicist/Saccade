"""Synthetic accounting boundary; no network provider or customer disclosure.

The fake provider is explicitly registered by the operator. It does not implement
accounting inference. Real provider calls are external effects and unavailable.
"""

from __future__ import annotations

import contextvars
import re

from AutoCua.saccade.business_contract import digest, dumps, loads, read_safe, reject

_CURRENT = contextvars.ContextVar("dext_business_context")


def current():
    return _CURRENT.get()


class SyntheticAccountingProvider:
    """Trusted deterministic responses for offline tests and the initial pilot."""

    def __init__(self, clients):
        self.clients = clients

    def bank(self, label, reference_markdown, client_id):
        # Accept the entire freshly read Markdown, as the real provider would.
        # This fake returns operator-supplied fixtures; it never infers an account.
        return self.clients[client_id]["bank_responses"].get(label, {"compte": None})

    def scribe(self, pdf, reference_markdown, description_rule, expected):
        return expected


class AccountingContext:
    def __init__(self, root, clients, *, provider=None, model="offline-synthetic-v1", offline_receipts=None):
        if model != "offline-synthetic-v1":
            reject("external_provider_consent_required")
        self.root, self.clients = root, clients
        self.provider = provider or SyntheticAccountingProvider(clients)
        self.offline_receipts = offline_receipts or {}
        self.references = {}

    def reference(self, client_id, name, *, optional=False):
        if name not in ("comptable_banque.md", "comptable_achats.md", "comptable_ventes.md"):
            reject("unapproved_reference_file")
        if client_id not in self.clients:
            reject("unauthorized_client")
        if self.clients[client_id].get("synthetic") is not True:
            reject("real_client_privacy_gate_closed")
        path = self.root / client_id / name
        if optional:
            try:
                path.lstat()  # Do not mistake a broken reparse point for absence.
            except FileNotFoundError:
                self.references[name] = digest(["reference-absent"])
                return ""
            except OSError:
                reject("required_file_unavailable")
        content = read_safe(self.root, path, 8192 if optional else 2 * 1024 * 1024)
        self.references[name] = digest(["reference-present", digest(content)])
        try:
            text = content.decode("utf-8-sig")
            if not optional and not text.strip():
                reject("empty_reference")
            return text
        except UnicodeError:
            reject("invalid_reference_encoding")

    def bank(self, label, client_id):
        if type(label) is not str or not label.strip() or len(label) > 1000:
            reject("invalid_bank_label")
        if label not in self.clients.get(client_id, {}).get("bank_labels", []):
            reject("operator_argument_required")
        markdown = self.reference(client_id, "comptable_banque.md")
        result = self.provider.bank(label, markdown, client_id)
        # Always round-trip fake dict responses through the same strict codec.
        result = loads(result if isinstance(result, (str, bytes)) else dumps(result), 32_000)
        if type(result) is not dict or set(result) != {"compte"}:
            reject("invalid_provider_response")
        account = result["compte"]
        if account is not None and (type(account) is not str or not re.fullmatch(r"[A-Z0-9]{2,20}", account) or account.startswith("512")):
            reject("invalid_bank_account")
        return result

    def scribe(self, fixture_id, client_id, sens):
        if sens not in ("achat", "vente"):
            reject("invalid_invoice_direction")
        receipt = self.offline_receipts.get(fixture_id)
        if not receipt or receipt.get("client_id") != client_id or receipt.get("sens") != sens:
            reject("verified_download_receipt_required")
        if type(receipt.get("critical")) is not dict or set(receipt["critical"]) != {"type", "piece", "journal", "accounts"}:
            reject("verified_download_receipt_required")
        markdown = self.reference(client_id, "comptable_achats.md" if sens == "achat" else "comptable_ventes.md")
        # Exactly three client reference files exist. No generic description
        # corpus is read or inferred; the supported result field remains null.
        description = ""
        path = self.root / receipt["relative_path"]
        if path.suffix.lower() != ".pdf":
            reject("offline_fixture_identity_mismatch")
        pdf = read_safe(self.root / client_id, path, 262_144)
        if not pdf.startswith(b"%PDF-") or digest(pdf) != receipt["sha256"]:
            reject("offline_fixture_identity_mismatch")
        raw = self.provider.scribe(pdf, markdown, description, receipt["expected"])
        from .invoice_validation import analysis
        return analysis(raw, sens, has_description_rule=bool(description), expected=receipt.get("critical"))
