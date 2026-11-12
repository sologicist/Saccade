"""Proposal-only functions. Authority and context come from the trusted worker."""

from __future__ import annotations

from typing import Annotated, Literal, TypedDict

try:
    from typing import NotRequired
except ImportError:  # Python 3.10 stores these postponed annotations unevaluated.
    NotRequired = None

from .runtime import current


class BankResult(TypedDict):
    compte: Annotated[str, {"minLength": 2, "maxLength": 20, "pattern": r"^(?!512)[A-Z0-9]{2,20}$"}] | None


class Entry(TypedDict):
    compte: str
    role: Literal["tiers", "base", "tva", "banque", "autre"]
    debit_centimes: Annotated[int, {"minimum": 0, "maximum": 100000000000}]
    credit_centimes: Annotated[int, {"minimum": 0, "maximum": 100000000000}]


class InvoiceProposal(TypedDict):
    type: Literal["facture", "avoir", "devis"] | None
    reference: str | None
    date: str | None
    description: str | None
    ecriture: list[Entry]
    fournisseur: NotRequired[str | None]
    client: NotRequired[str | None]
    journal: str | None
    total_ttc: str | None
    total_tva: str | None
    devise: str | None


def bank(string: Annotated[str, {"minLength": 1, "maxLength": 1000, "pattern": r"\S"}], client_id: str) -> BankResult:
    """Analyze an exact supplied label; ambiguous matches return null."""
    return current().bank(string, client_id)


def scribe(pdf: str, client_id: str, sens: Literal["achat", "vente"]) -> InvoiceProposal:
    """Validate an offline invoice proposal; pdf is a fixture ID, never a path."""
    return current().scribe(pdf, client_id, sens)
