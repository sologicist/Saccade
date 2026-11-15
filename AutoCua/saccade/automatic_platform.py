"""Installed website identity for the native generic Web controller."""
from urllib.parse import urlsplit

from .platform_registry import list_platforms


def detect_platform(url, *, root=None):
    """Only HTTPS browser observations may select installed platform resources."""
    if not isinstance(url, str):
        return None
    try:
        parsed = urlsplit(url)
        if parsed.scheme != 'https' or parsed.username or parsed.password or parsed.port not in (None, 443):
            return None
        host = parsed.hostname
    except ValueError:
        return None
    matches = [platform.id for platform in list_platforms(root) if host in platform.allowed_hosts]
    if len(matches) > 1:
        raise ValueError('Ambiguous installed platform hostname')
    return matches[0] if matches else None


def business_for_platform(platform):
    """Construct only installed business implementations; never a model import."""
    from .business_run import BusinessRun
    from .session_context import build_platform_context
    if platform != 'dext':
        return None
    # This is the existing worker's contract, not a browser/profile policy.
    return BusinessRun(build_platform_context(platform), automatic=True)
