"""Trusted, declarative public landmarks for operator-assisted learning.

An adapter proves only a manual control-to-heading transition. It grants no
gesture, record, disclosure, download or business authority. Missing vocabulary
blocks learning rather than treating page text as reusable public knowledge.
"""

import re
from dataclasses import dataclass

from .business_contract import digest, loads, read_safe, reject
from .platform_config import load_platform


@dataclass(frozen=True)
class LearningAdapter:
    platform_id: str
    revision: str
    labels: dict
    aliases: dict
    legacy: bool = False

    def summary_label(self, route):
        if route in self.labels:
            return self.labels[route]
        if self.legacy:
            from .dext_learning import ROUTE_LABELS
            if route in ROUTE_LABELS:
                return ROUTE_LABELS[route]
        reject('unsupported_navigation_correction')

    def validate_routes(self, routes):
        if type(routes) is not list or not 1 <= len(routes) <= 8 or any(type(r) is not str or r not in self.labels for r in routes):
            reject('unsupported_navigation_correction')
        return routes

    def steps(self, routes):
        return [{'landmark': r, 'verification': 'manual_heading_transition'} for r in self.validate_routes(routes)]

    def routes(self, steps):
        if type(steps) is not list or any(type(s) is not dict or set(s) != {'landmark', 'verification'} or s['verification'] != 'manual_heading_transition' for s in steps):
            reject('invalid_procedure_steps')
        return self.validate_routes([s['landmark'] for s in steps])


def dext_adapter():
    """Compatibility for shipped Dext installs, without changing old hashes."""
    from .dext_learning import LABELS, ALIASES
    value = {'labels': LABELS, 'aliases': {k: sorted(v) for k, v in ALIASES.items()}}
    return LearningAdapter('dext', digest(value), dict(LABELS), {k: set(v) for k, v in ALIASES.items()}, True)


def load_adapter(project, platform_id):
    platform = load_platform(platform_id, root=project)
    path = project / 'platforms' / platform.id / 'learning.json'
    if not path.exists() and not path.is_symlink():
        if platform.id == 'dext':
            return dext_adapter()
        return LearningAdapter(platform.id, digest({'platform_id': platform.id, 'landmarks': []}), {}, {})
    value = loads(read_safe(project, path, 16_384), 16_384)
    if type(value) is not dict or set(value) != {'schema_version', 'platform_id', 'landmarks'} or type(value['schema_version']) is not int or value['schema_version'] != 1 or value['platform_id'] != platform.id or type(value['landmarks']) is not list or not 1 <= len(value['landmarks']) <= 32:
        reject('invalid_learning_adapter')
    from .operator_language import normalized
    from .operator_requests import _SECRET
    labels, aliases, names = {}, {}, set()
    for entry in value['landmarks']:
        if type(entry) is not dict or set(entry) != {'id', 'label', 'aliases'} or type(entry['id']) is not str or not re.fullmatch(r'[a-z][a-z0-9_-]{0,31}', entry['id']) or entry['id'] in labels or type(entry['aliases']) is not list or len(entry['aliases']) > 8:
            reject('invalid_learning_adapter')
        public = [entry['label'], *entry['aliases']]
        # Installed configuration is trusted to declare public labels, never
        # extracted from DOM/chat. Restrict syntax to non-executable short names.
        if any(type(v) is not str or not 1 <= len(v) <= 64 or not re.fullmatch(r"[\w][\w '\-]{0,63}", v) or _SECRET.search(normalized(v)) for v in public):
            reject('invalid_learning_adapter')
        closed = {normalized(v) for v in public}
        if names & closed or '' in closed:
            reject('ambiguous_learning_adapter')
        labels[entry['id']], aliases[entry['id']] = entry['label'], closed
        names |= closed
    return LearningAdapter(platform.id, digest(value), labels, aliases)
