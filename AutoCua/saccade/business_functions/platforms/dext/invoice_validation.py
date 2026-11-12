"""Validate legacy Dext analysis semantics without importing legacy orchestration."""

from __future__ import annotations

from datetime import date
import re

from AutoCua.saccade.business_contract import dumps, loads, reject

LIMIT = 100_000_000_000


def _text(value, limit=300):
    return type(value) is str and bool(value.strip()) and len(value) <= limit


def _amount(value, *, signed=False):
    return type(value) is int and (abs(value) if signed else value) in range(LIMIT + 1)


def _money(cents):
    if cents is None:
        return None
    units, fraction = divmod(abs(cents), 100)
    return f"{'-' if cents < 0 else ''}{units}.{fraction:02d}"


def _rows(value):
    if type(value) is not list or len(value) > 100:
        reject("invalid_invoice_entries")
    for row in value:
        if type(row) is not dict or set(row) != {"compte", "role", "debit_centimes", "credit_centimes"}:
            reject("invalid_invoice_entries")
        if type(row["compte"]) is not str or not re.fullmatch(r"[A-Z0-9]{2,20}", row["compte"]) or row["compte"].startswith("512") or row["role"] not in ("tiers", "base", "tva", "banque", "autre") or not _amount(row["debit_centimes"]) or not _amount(row["credit_centimes"]) or bool(row["debit_centimes"]) == bool(row["credit_centimes"]):
            reject("invalid_invoice_entries")
    if sum(row["debit_centimes"] for row in value) != sum(row["credit_centimes"] for row in value):
        reject("invoice_entries_mismatch")
    return value


def _simple_invoice(piece, rows, sens, kind):
    """Complex, multi-rate, unknown-party or incompatible roles require review."""
    if any(not _text(piece[key]) for key in ("tiers", "reference", "date", "devise")):
        return False
    total, tax = piece["total_centimes"], piece["tva_centimes"]
    if total is None or tax is None or total == 0 or abs(tax) >= abs(total):
        return False
    total, tax = abs(total), abs(tax)
    side, opposite = ("debit_centimes", "credit_centimes") if (sens == "achat") != (kind == "avoir") else ("credit_centimes", "debit_centimes")
    base = [r for r in rows if r["role"] == "base"]
    parties = [r for r in rows if r["role"] == "tiers"]
    taxes = [r for r in rows if r["role"] == "tva"]
    if len(base) != 1 or len(parties) != 1 or len(taxes) > 1 or len(rows) != 2 + len(taxes):
        return False
    party, base = parties[0], base[0]
    if party["compte"] in ("9DIV", "0DIV") or base["compte"] == party["compte"] or base["compte"].startswith("445"):
        return False
    return not (base[opposite] or party[side] or any(r[opposite] for r in taxes)
                or base[side] != total - tax or party[opposite] != total
                or sum(r[side] for r in taxes) != tax
                or any(not r["compte"].startswith("445") for r in taxes))


def analysis(raw, sens, *, has_description_rule, expected=None):
    """Parse a bounded provider response and return a proposal, never an action."""
    if sens not in ("achat", "vente"):
        reject("invalid_invoice_direction")
    parsed = loads(raw if isinstance(raw, (str, bytes)) else dumps(raw), 32_000)
    if type(parsed) is not dict or set(parsed) != {"type", "statut", "motifs", "journal", "piece", "ecriture"}:
        reject("invalid_provider_response")
    kind, status = parsed["type"], parsed["statut"]
    if kind not in ("facture", "avoir", "devis", None) or status not in ("proposee", "a_revoir", "sans_ecriture") or status == "sans_ecriture" and kind != "devis":
        reject("invalid_provider_response")
    if type(parsed["motifs"]) is not list or len(parsed["motifs"]) > 20 or any(not _text(v, 500) for v in parsed["motifs"]):
        reject("invalid_provider_response")
    journal = parsed["journal"]
    if journal is not None and (type(journal) is not str or not re.fullmatch(r"[A-Z0-9]{1,12}", journal)):
        reject("invalid_invoice_journal")
    piece = parsed["piece"]
    if piece is not None:
        if type(piece) is not dict or set(piece) != {"tiers", "identifiant_tiers", "reference", "date", "description", "devise", "total_centimes", "tva_centimes"}:
            reject("invalid_provider_response")
        for key in ("tiers", "identifiant_tiers", "reference", "date", "description", "devise"):
            if piece[key] is not None and not _text(piece[key]):
                reject("invalid_invoice_value")
        if piece["date"] is not None:
            try:
                if date.fromisoformat(piece["date"]).isoformat() != piece["date"]:
                    reject("invalid_invoice_date")
            except ValueError:
                reject("invalid_invoice_date")
        if piece["devise"] is not None and not re.fullmatch(r"[A-Z]{3}", piece["devise"]):
            reject("invalid_invoice_currency")
        if any(piece[k] is not None and not _amount(piece[k], signed=kind == "avoir") for k in ("total_centimes", "tva_centimes")):
            reject("invalid_invoice_amount")
    if expected is not None:
        # Only synthetic host receipts can bind known fixture facts in PR4.
        # Real extraction provenance must be supplied by a later download PR.
        reviewing = kind in ("devis", None) or status == "a_revoir" or bool(parsed["motifs"])
        if type(expected) is not dict or kind is not None and expected.get("type") != kind:
            reject("invoice_critical_mismatch")
        for key, value in expected.get("piece", {}).items():
            actual = piece.get(key) if piece is not None else None
            if actual != value and (actual is not None or not reviewing):
                reject("invoice_critical_mismatch")
    rows = _rows(parsed["ecriture"])
    if expected is not None and not reviewing and (journal != expected.get("journal") or [row["compte"] for row in rows] != expected.get("accounts")):
        reject("invoice_critical_mismatch")
    result = {"date": piece["date"] if piece else None, "type": kind, "ecriture": [],
              "reference": piece["reference"] if piece else None,
              "description": piece["description"] if piece and has_description_rule else None,
              "journal": None, "total_ttc": _money(piece["total_centimes"]) if piece else None,
              "total_tva": _money(piece["tva_centimes"]) if piece else None,
              "devise": piece["devise"] if piece else None,
              "fournisseur" if sens == "achat" else "client": piece["tiers"] if piece else None}
    if kind in ("devis", None) or status == "a_revoir" or parsed["motifs"]:
        return result
    if not rows or not journal or piece is None:
        reject("incomplete_invoice_proposal")
    if _simple_invoice(piece, rows, sens, kind):
        result.update(journal=journal, ecriture=rows)
    return result
