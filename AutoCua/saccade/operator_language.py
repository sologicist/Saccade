"""Deterministic, contextual operator replies. Never an authorization parser."""

import re
import unicodedata


def normalized(text):
    text = ''.join(c for c in unicodedata.normalize('NFKD', text.casefold()) if not unicodedata.combining(c))
    return re.sub(r'\s+', ' ', re.sub(r"[^a-z0-9']+", ' ', text.replace('’', "'"))).strip()


def reply_intent(text):
    value = normalized(text)
    if value in {'maybe', 'not sure', "i don't know", 'peut etre', 'pas sur', 'je ne sais pas', 'je ne suis pas sur'}:
        return 'uncertain'
    if value in {'cancel', 'cancel task', 'stop', 'annuler', 'annule', 'annule la tache'}:
        return 'cancel'
    if value in {'no', 'non', 'not yet', 'no not yet', 'non pas encore', 'pas encore', 'not done', 'je ne sais pas', "i don't know"}:
        return 'negative'
    if value in {'yes', 'oui', 'ok', 'okay', "c'est bon", 'c est bon', "j'ai termine", 'je suis connecte',
                 'je suis connectee', 'done', 'continue', 'continuer', "i'm connected", 'i am connected',
                 "i'm signed in", 'i am signed in', "i'm logged in", 'i am logged in', 'finished', 'termine', 'fait', 'oui continue'}:
        return 'affirmative'
    if value in {'yes save it', 'yes remember this', 'save it', 'oui enregistre', 'oui enregistre la procedure',
                 'oui memorise', 'oui sauvegarde', 'oui garde cette procedure', 'enregistre la procedure'}:
        return 'save'
    if value in {"don't remember this", 'do not remember this', 'ne memorise pas', "n'enregistre pas", 'ne retiens pas ca'}:
        return 'reject'
    if value in {'show me what will be saved', 'show the procedure', 'montre la procedure', 'montre ce qui sera enregistre'}:
        return 'show'
    if value in {'change the second step', 'change la deuxieme etape', 'modifie la deuxieme etape'}:
        return 'edit_second'
    return 'ambiguous'


def navigation_question(text):
    value = normalized(text)
    return any(word in value.split() for word in ('navigation', 'route', 'path', 'reach', 'chemin', 'atteindre', 'acceder')) or bool(
        re.search(r'\b(how|comment)\b.*\b(open|ouvrir|ouvre|find|trouver|invoices|factures)\b', value))


def navigation_context(task, history, adapter=None):
    """Use the bound objective or actual recent native calls, not page prose."""
    value = normalized(task)
    from .learning_adapter import dext_adapter
    adapter = adapter or dext_adapter()
    if re.search(r'\b(open|find|navigate|reach|ouvrir|ouvre|trouver|cherche|acceder)\b', value) and any(re.search(r"\b" + re.escape(name) + r"\b", value) for names in adapter.aliases.values() for name in names):
        return True
    import json
    for row in (history or {}).get('assistant_messages', [])[-5:]:
        try:
            calls = json.loads(row).get('tool_calls', [])
            if any(call.get('function', {}).get('name') in ('dext_navigation', 'navigate', 'new_tab') for call in calls):
                return True
        except (ValueError, TypeError, AttributeError):
            pass
    return False


def spontaneous_correction(text, *, eligible, navigation, adapter=None):
    """Return a correction/clarification only within a verified Web conversation."""
    from .navigation_correction import correction_framing, correction_routes
    from .business_contract import BusinessError
    if not eligible or reply_intent(text) != 'ambiguous':
        return 'ordinary', None
    _, explicit = correction_framing(text)
    try:
        routes = correction_routes(text, adapter)
    except BusinessError:
        routes = None
    if routes and navigation:
        return 'correction', routes
    if explicit or routes:
        return 'clarify', routes
    return 'ordinary', None
