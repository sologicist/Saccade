"""Dext-only legacy vocabulary; never an execution or accounting permission."""

ROUTES = {
    "purchases": "Ask the operator to open Purchases manually, then reobserve and verify the section heading.",
    "inbox": "Ask the operator to open Inbox manually, then reobserve and verify the section heading.",
    "invoices": "Ask the operator to identify the invoices navigation control.",
    "bank": "Ask the operator to identify the bank transactions navigation control.",
    "workspace": "Confirm the active workspace with the operator before proceeding.",
    "record": "Confirm the exact record with the operator; a URL is insufficient.",
    "review": "Stop for operator review if target identity or the transition is uncertain.",
}
ROUTE_LABELS = {'purchases': 'Purchases', 'inbox': 'Inbox', 'invoices': 'Invoices', 'bank': 'Bank transactions',
                'workspace': 'Workspace check', 'record': 'Record check', 'review': 'Operator review'}
_ARTICLE = r"(?:(?:the|a|an|le|la|les|un|une)\s+|l')?"
_OPEN = r"(?:open|go to|go through|click|click on|ouvrir|ouvre|aller a|aller dans|passer par|va dans|va sur|clique sur|clique|cliquer sur)\s+"
_VERIFY = r"(?:verify|confirm|check|verifie|verifier|confirme|confirmer)\s+"
_SELECT = r"(?:select|open|selectionne|selectionner|ouvre|ouvrir)\s+"
PATTERNS = (
    ("purchases", _OPEN + _ARTICLE + r"(?:purchases|achats)"),
    ("inbox", _OPEN + _ARTICLE + r"(?:inbox|boite de reception)"),
    ("invoices", _OPEN + _ARTICLE + r"(?:invoices|factures)"),
    ("bank", _OPEN + _ARTICLE + r"(?:bank transactions|banking|bank|banque|transactions bancaires|mouvements bancaires)"),
    ("workspace", _VERIFY + _ARTICLE + r"(?:(?:active|current)\s+)?(?:workspace|dossier|espace de travail)(?:\s+actif)?"),
    ("record", _SELECT + _ARTICLE + r"(?:(?:test|selected|current)\s+)?(?:record|invoice|fiche|piece|facture)"),
    ("review", r"(?:ask for|stop for|request|demande|demander|arrete pour|arreter pour)\s+" + _ARTICLE + r"(?:operator review|human review|verification operateur|validation operateur|revue operateur)"),
)

LABELS = {'purchases': 'Purchases', 'inbox': 'Inbox', 'invoices': 'Invoices', 'bank': 'Bank transactions'}
ALIASES = {'purchases': {'purchases', 'achats'}, 'inbox': {'inbox', 'boite de reception'},
           'invoices': {'invoices', 'factures', "factures d'achat", 'purchase invoices'},
           'bank': {'bank transactions', 'transactions bancaires', 'bank', 'banque'}}
