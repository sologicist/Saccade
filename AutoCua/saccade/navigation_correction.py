"""Conservative local chat-to-guidance compiler; raw corrections are not saved."""

from __future__ import annotations

import re
import unicodedata

from .business_contract import reject

_ARTICLE = r"(?:(?:the|a|an|le|la|les|un|une)\s+|l')?"
_OPEN = r"(?:open|go to|click|click on|ouvrir|ouvre|aller a|va dans|va sur|clique sur|clique|cliquer sur)\s+"
_VERIFY = r"(?:verify|confirm|check|verifie|verifier|confirme|confirmer)\s+"
_SELECT = r"(?:select|open|selectionne|selectionner|ouvre|ouvrir)\s+"
_PATTERNS = (
    ("purchases", _OPEN + _ARTICLE + r"(?:purchases|achats)"),
    ("inbox", _OPEN + _ARTICLE + r"(?:inbox|boite de reception)"),
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
    parts = [part.strip() for part in re.split(r"[.;,→\n]+|->|\b(?:and then|then|puis|ensuite)\b", normalized) if part.strip()]
    if not 1 <= len(parts) <= 8:
        reject("unsupported_navigation_correction")
    routes = []
    for part in parts:
        # A following label may share the preceding verb: "Purchases, then Inbox".
        if re.fullmatch(_ARTICLE + r"(?:inbox|boite de reception|purchases|achats)", part):
            part = "open " + part
        matches = [route for route, pattern in _PATTERNS if re.fullmatch(pattern, part)]
        if len(matches) != 1:
            reject("unsupported_navigation_correction")
        routes.append(matches[0])
    return routes


LABELS = {'purchases': 'Purchases', 'inbox': 'Inbox', 'invoices': 'Invoices', 'bank': 'Bank transactions'}
ALIASES = {'purchases': {'purchases', 'achats'}, 'inbox': {'inbox', 'boite de reception'},
           'invoices': {'invoices', 'factures', "factures d'achat", 'purchase invoices'},
           'bank': {'bank transactions', 'transactions bancaires', 'bank', 'banque'}}


def landmarks(elements):
    """Discard all page text except exact closed-vocabulary navigation labels.

    Presence is corroboration of a manual route, never proof that a control is
    safe to click, that a record is identified, or that a business effect is allowed.
    """
    from .operator_language import normalized
    controls, headings = {}, {}
    for value in elements.values():
        if type(value) is not dict or type(value.get('name')) is not str:
            continue
        name = normalized(value['name'])
        rect = value.get('rect')
        if type(rect) is not list or len(rect) != 4 or any(type(n) not in (int, float) or not -100_000 <= n <= 100_000 for n in rect) or rect[2] <= 0 or rect[3] <= 0:
            continue
        for route, names in ALIASES.items():
            if name in names:
                if value.get('role') in ('link', 'button', 'tab', 'menuitem'):
                    controls[route] = controls.get(route, 0) + 1
                if value.get('role') == 'heading':
                    headings[route] = headings.get(route, 0) + 1
    return {route for route, count in controls.items() if count == 1}, {route for route, count in headings.items() if count == 1}


class NavigationTeaching:
    """Bounded evidence attached by the host to the existing run control.

    Each step needs a visible source control and a later, changed native
    observation showing its section heading. Only canonical route names and
    scope-evidence digests survive the run; raw labels and records never do.
    """
    def __init__(self, routes, *, baseline=None):
        from .procedure_store import ProcedureStore
        ProcedureStore.render(routes)
        self.routes = list(routes)
        self.index = 0
        self.source = None
        self.tab = None
        self.evidence = []
        self.proposal = None
        if baseline:
            self.observe(*baseline)

    def observe(self, controls, headings, observation_digest, tab=None):
        if self.index == len(self.routes):
            return
        if self.tab is not None and tab != self.tab:
            self.index, self.source, self.evidence = 0, None, []
        self.tab = tab
        route = self.routes[self.index]
        if self.source and observation_digest != self.source and route in headings:
            from .business_contract import digest
            self.evidence.append(digest([route, self.source, observation_digest]))
            self.index += 1
            self.source = None
            if self.index == len(self.routes):
                return
            route = self.routes[self.index]
        # A heading already present in the source cannot prove a transition.
        if route in controls and route not in headings:
            self.source = observation_digest

    def intervention(self):
        if self.index == len(self.routes):
            return None
        route = self.routes[self.index]
        if route not in LABELS:
            return {'category': 'blocked', 'reason': 'unsafe_or_blocked',
                    'request': 'This step requires verified workspace or record identity. Please clarify a section-only navigation path; I cannot remember record identities from chat.'}
        label = LABELS[route]
        return {'category': 'manual_action', 'reason': 'manual_intervention',
                'request': (f'Please open {label} manually in the dedicated Chrome window, then tell me when it is done. '
                            if self.source else f'Please show the {label} navigation control in the dedicated Chrome window, then tell me when it is visible. ') +
                           'I will verify the visible section before proposing reusable guidance; automatic navigation is still unavailable.'}
