"""Conservative local chat-to-guidance compiler; raw corrections are not saved."""

from __future__ import annotations

import re
import unicodedata

from .business_contract import reject

_ARTICLE = r"(?:(?:the|a|an|le|la|les|un|une|l)\s+)?"
_OPEN = r"(?:open|go to|ouvrir|ouvre|aller a|va dans|va sur)\s+"
_VERIFY = r"(?:verify|confirm|check|verifie|verifier|confirme|confirmer)\s+"
_SELECT = r"(?:select|open|selectionne|selectionner|ouvre|ouvrir)\s+"
_PATTERNS = (
    ("invoices", _OPEN + _ARTICLE + r"(?:invoices|factures)"),
    ("bank", _OPEN + _ARTICLE + r"(?:bank transactions|banking|bank|banque|transactions bancaires|mouvements bancaires)"),
    ("workspace", _VERIFY + _ARTICLE + r"(?:(?:active|current)\s+)?(?:workspace|dossier|espace de travail)(?:\s+actif)?"),
    ("record", _SELECT + _ARTICLE + r"(?:(?:test|selected|current)\s+)?(?:record|invoice|fiche|piece|facture)"),
    ("review", r"(?:ask for|stop for|request|demande|demander|arrete pour|arreter pour)\s+" + _ARTICLE + r"(?:operator review|human review|verification operateur|validation operateur|revue operateur)"),
)


def correction_routes(text):
    """Accept only recognized complete sentences; never discard unknown details.

    This is not an LLM or a general instruction interpreter. It cannot learn
    selectors, accounting rules, client values, permissions or arbitrary prose.
    The caller is the independent UI operator channel, never a model tool.
    """
    if type(text) is not str or not 1 <= len(text) <= 2000 or any(ord(c) < 32 and c not in "\n\r\t" for c in text):
        reject("invalid_navigation_correction")
    normalized = "".join(c for c in unicodedata.normalize("NFKD", text.casefold()) if not unicodedata.combining(c))
    normalized = normalized.replace("’", "'")
    normalized = re.sub(r"\b(?:first|d'abord)\b\s*[:,]?\s*", "", normalized)
    parts = [part.strip() for part in re.split(r"[.;\n]+|\b(?:and then|then|puis|ensuite)\b", normalized) if part.strip()]
    if not 1 <= len(parts) <= 8:
        reject("unsupported_navigation_correction")
    routes = []
    for part in parts:
        matches = [route for route, pattern in _PATTERNS if re.fullmatch(pattern, part)]
        if len(matches) != 1:
            reject("unsupported_navigation_correction")
        routes.append(matches[0])
    return routes
