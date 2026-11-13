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
