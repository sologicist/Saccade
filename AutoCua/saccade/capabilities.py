"""Trusted platform-local callable contracts; no model-selected import paths."""
import ast
from pathlib import Path

from .business_contract import digest, dumps, loads, read_safe, reject, static_signature, validate
from .platform_config import load_platform, PLATFORM_ID_PATTERN


def catalogue(project, platform):
    load_platform(platform, root=project)
    root = project / 'platforms' / platform
    path = root / 'capabilities.json'
    try:
        path.lstat()
    except FileNotFoundError:
        value = {'schema_version':1,'platform_id':platform,'functions':[]}
    else:
        value = loads(read_safe(project, path, 65_536), 65_536)
    if type(value) is not dict or set(value) != {'schema_version', 'platform_id', 'functions'} or type(value['schema_version']) is not int or value['schema_version'] != 1 or value['platform_id'] != platform or type(value['functions']) is not list or len(value['functions']) > 32:
        reject('invalid_capability_registry')
    functions, sources = {}, {}
    if platform == 'dext':
        from .scribe_pdf import installed
        entry = installed(project)
        functions[entry['id']] = entry
        sources['builtin_scribe_pdf'] = entry['source_digest']
    for row in value['functions']:
        if type(row) is not dict or set(row) - {'id', 'source', 'symbol', 'effect', 'destination', 'description', 'output_visibility', 'verify', 'document_input', 'requires_verified_record'} or not {'id', 'source', 'symbol', 'effect', 'destination', 'description', 'output_visibility'} <= set(row):
            reject('invalid_capability_registry')
        if type(row['id']) is not str or not row['id'].startswith(platform + '.') or not PLATFORM_ID_PATTERN.fullmatch(row['id'][len(platform)+1:]) or row['id'] in functions:
            reject('foreign_or_invalid_capability')
        from .business_run import reserved_function_names
        if row['id'] in reserved_function_names(platform):
            reject('legacy_capability_override_denied')
        if type(row['source']) is not str or not row['source'].endswith('.py') or not PLATFORM_ID_PATTERN.fullmatch(row['source'][:-3]) or type(row['symbol']) is not str or not row['symbol'].isidentifier() or row['symbol'].startswith('_'):
            reject('invalid_capability_entrypoint')
        if row['effect'] not in ('read', 'compute', 'disclosure', 'mutation', 'delete') or row['output_visibility'] not in ('public', 'operator') or type(row['destination']) is not str or len(row['destination']) > 200 or type(row['description']) is not str or len(row['description']) > 1000:
            reject('invalid_capability_policy')
        source = read_safe(project, root / 'functions' / row['source'])
        tree = ast.parse(source.decode('utf-8'))
        # Single-file, explicitly installed implementations. Dependencies must
        # be declared through a future fingerprinted bundle contract, not an
        # ambient import which escapes this revision. Not a Python sandbox.
        if any(isinstance(n, (ast.Import, ast.ImportFrom)) or
               isinstance(n, ast.Name) and n.id in ('__import__', 'eval', 'exec', 'compile')
               for n in ast.walk(tree)):
            reject('unsupported_capability_dependency')
        if row['effect'] in ('disclosure', 'mutation', 'delete') and not row.get('verify'):
            reject('capability_verifier_required')
        if 'verify' in row:
            if type(row['verify']) is not str or not row['verify'].isidentifier() or row['verify'].startswith('_'):
                reject('invalid_capability_verifier')
            static_signature(source, row['verify'])
        inputs, output = static_signature(source, row['symbol'])
        if 'document_input' in row and (type(row['document_input']) is not str or row['document_input'] not in inputs['properties'] or inputs['properties'][row['document_input']].get('type') != 'string' or row['output_visibility'] != 'operator'):
            reject('invalid_document_capability')
        if type(row.get('requires_verified_record', False)) is not bool or row.get('requires_verified_record') and not row.get('document_input'):
            reject('invalid_document_capability')
        sources[row['source']] = digest(source)
        functions[row['id']] = {**row, 'input_schema': inputs, 'output_schema': output, 'source_digest':digest(source)}
    return {'revision': digest([platform, value, sources]), 'functions': functions}


def tool(snapshot):
    fields = {}
    for entry in snapshot['functions'].values():
        for name, schema in entry['input_schema']['properties'].items():
            fields[name] = {'anyOf':[fields[name], schema]} if name in fields and fields[name] != schema else schema
    return {'name': 'call_function', 'description': 'Call an installed platform capability. Exact inputs and effects: ' + dumps(snapshot['functions'], 32_768),
        'parameters': {'type': 'object', 'properties': {'version': {'type':'integer','enum':[1]},
            'name': {'type':'string','enum':list(snapshot['functions'])}, 'arguments': {'type':'object','properties':{k:{'anyOf':[v,{'type':'null'}]} for k,v in fields.items()},'required':list(fields),'additionalProperties':False}},
            'required':['version','name','arguments'], 'additionalProperties':False}}


def execute_worker(request):
    """Called by the existing bounded child process, never the UI interpreter."""
    project = Path(request['project_root'])
    from .session_context import _validate_context
    context = _validate_context(request['context'], root=project)
    snapshot = catalogue(project, context['platform_id'])
    if snapshot['revision'] != request['revision']:
        reject('capability_revision_changed')
    entry = snapshot['functions'].get(request['name'])
    if not entry:
        reject('unregistered_capability')
    validate(request['arguments'], entry['input_schema'])
    if request['name'] == 'dext.scribe_pdf' and context['platform_id'] == 'dext':
        from .scribe_pdf import execute
        return execute(request)
    arguments = dict(request['arguments'])
    if entry.get('document_input'):
        receipt = verified_download(project, context, request['session_id'], arguments[entry['document_input']])
        if entry.get('requires_verified_record') and not receipt['record_identity_verified']:
            reject('verified_record_identity_required')
        arguments[entry['document_input']] = receipt['path']
    source_path = project / 'platforms' / context['platform_id'] / 'functions' / entry['source']
    source = read_safe(project, source_path)
    if digest(source) != entry['source_digest']:
        reject('capability_revision_changed')
    namespace = {'__name__': 'installed_platform_capability'}
    # This is trusted installed code, not executable text from a tool argument.
    exec(compile(source, str(source_path), 'exec'), namespace)
    if catalogue(project, context['platform_id'])['revision'] != snapshot['revision']:
        reject('capability_revision_changed')
    result = namespace[entry['symbol']](**arguments)
    validate(result, entry['output_schema'])
    if entry.get('verify') and namespace[entry['verify']](result) is not True:
        reject('capability_effect_unverified')
    if catalogue(project, context['platform_id'])['revision'] != snapshot['revision']:
        reject('capability_revision_changed')
    dumps(result)
    return {'status':'success', 'result':result}


def verified_download(project, context, session, reference):
    import re
    if type(reference) is not str or not re.fullmatch(r'receipt:[a-f0-9]{48}', reference):
        reject('verified_download_receipt_required')
    key = reference[8:]
    root = project / 'platforms' / context['platform_id'] / 'data/navigation/downloads'
    receipt = loads(read_safe(project, root / (key + '.receipt.json'), 65_536), 65_536)
    if receipt.get('platform_id') != context['platform_id'] or receipt.get('session') != session or receipt.get('id') != key:
        reject('foreign_download_receipt')
    extension = {'application/pdf':'.pdf','application/octet-stream':'.bin','text/plain':'.txt'}.get(receipt.get('mime'))
    if extension is None or receipt.get('path') != str(root / (key + extension)):
        reject('invalid_download_receipt')
    content = read_safe(project, root / (key + extension), 8 * 1024 * 1024)
    if len(content) != receipt.get('bytes') or digest(content) != receipt.get('sha256'):
        reject('download_file_changed')
    return receipt


def merge_tools(legacy, generic):
    if legacy is None:
        return generic
    merged = loads(dumps(legacy))
    merged['description'] += '\n' + generic['description']
    prior = merged['parameters']['properties']
    current = generic['parameters']['properties']
    prior['name']['enum'] = sorted(set(prior['name'].get('enum', [])) | set(current['name']['enum']))
    fields = prior['arguments']['properties']
    for key, value in current['arguments']['properties'].items():
        fields[key] = {'anyOf':[fields[key], value]} if key in fields and fields[key] != value else value
    prior['arguments']['required'] = list(fields)
    return merged
