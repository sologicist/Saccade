"""Disposable installed platform; no user data, browser or remote provider."""

import json

from AutoCua.saccade.session_context import build_platform_context

PLATFORM = 'synthetic_portal'
HOST = 'portal.example.test'
BASELINE = 'Synthetic portal baseline: operator-assisted public sections only.\n'
LANDMARKS = [
    {'id': 'settings_page', 'label': 'Settings', 'aliases': ['Parametres']},
    {'id': 'billing_page', 'label': 'Billing', 'aliases': ['Facturation']},
    {'id': 'customers_page', 'label': 'Customers', 'aliases': ['Clients']},
    {'id': 'documents_page', 'label': 'Documents', 'aliases': []},
]


def install_synthetic(root, *, learning=True, platform_id=PLATFORM, host=HOST, landmarks=None):
    directory = root / 'platforms' / platform_id
    directory.mkdir(parents=True)
    source = json.loads((root / 'platforms/dext/platform.json').read_text(encoding='utf-8'))
    source.update(id=platform_id, name='Synthetic Portal', start_url=f'https://{host}/login', allowed_hosts=[host])
    (directory / 'platform.json').write_text(json.dumps(source), encoding='utf-8')
    if learning:
        (directory / 'learning.json').write_text(json.dumps({'schema_version': 1, 'platform_id': platform_id, 'landmarks': LANDMARKS if landmarks is None else landmarks}), encoding='utf-8')
    domain = root / 'AutoCua/default_skills/web/domain_skill'
    manifest = json.loads((domain / 'skills.json').read_text(encoding='utf-8'))
    manifest[host] = platform_id + '.md'
    (domain / 'skills.json').write_text(json.dumps(manifest), encoding='utf-8')
    (domain / (platform_id + '.md')).write_text(BASELINE, encoding='utf-8')
    return build_platform_context(platform_id, root=root)
