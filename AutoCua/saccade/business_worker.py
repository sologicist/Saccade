"""One bounded JSON request on inherited stdin; no listener or agent loop."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

from .business_contract import BusinessError, MAX_OUTPUT, dumps, loads, reject, validate


def execute(request):
    if type(request) is dict and request.get('version') == 2:
        if type(request['version']) is not int or set(request) != {'version','context','project_root','revision','name','arguments','session_id'}:
            reject('invalid_worker_request')
        from .capabilities import execute_worker
        try:
            return execute_worker(request)
        except BusinessError as error:
            code = str(error)
            allowed = {'capability_revision_changed','unregistered_capability','schema_mismatch','verified_download_receipt_required','foreign_download_receipt','download_file_changed','verified_record_identity_required','capability_effect_unverified'}
            return {'status':'error','error':code if code in allowed else 'capability_execution_failed','result':None}
        except Exception:
            return {'status':'error','error':'capability_execution_failed','result':None}
    from .business_run import BusinessRun, WORKER_ERRORS
    if type(request) is not dict or set(request) != {"version", "ticket", "context", "project_root", "offline_receipts", "model"} or type(request["version"]) is not int or request["version"] != 1:
        reject("invalid_worker_request")
    ticket = request["ticket"]
    if type(ticket) is not dict or set(ticket) != {"version", "call_id", "run_id", "platform_id", "context_revision", "revision", "effect", "capabilities", "action", "arguments", "name"} or type(ticket["version"]) is not int or ticket["version"] != 1:
        reject("invalid_worker_request")
    response = {"version": 1, "call_id": ticket.get("call_id"), "run_id": ticket.get("run_id"),
                "status": "error", "result": None, "error": "worker_failed", "references": {}}
    try:
        run = BusinessRun(request["context"], project_root=Path(request["project_root"]), offline_receipts=request["offline_receipts"])
        run.refresh()
        checked = run.prepare(ticket["action"])
        for key in ("platform_id", "context_revision", "revision", "effect", "capabilities", "arguments", "name"):
            if checked[key] != ticket[key]:
                reject("business_revision_changed")
        snapshot, clients = run.snapshot()
        if snapshot["revision"] != ticket["revision"]:
            reject("business_revision_changed")
        from .client_references import require_reference_bundle
        require_reference_bundle(run.data_root, ticket["arguments"]["client_id"])
        from AutoCua.saccade.business_functions.platforms.dext.runtime import AccountingContext, _CURRENT
        context = AccountingContext(run.data_root, clients, model=request["model"], offline_receipts=run.offline_receipts)
        token = _CURRENT.set(context)
        try:
            # This literal installed module is the only import target. Policy and
            # schema are checked again before selecting its approved public symbol.
            module = importlib.import_module("AutoCua.saccade.business_functions.platforms.dext.functions")
            symbol = snapshot["functions"][ticket["name"]]["symbol"]
            if run.snapshot()[0]["revision"] != ticket["revision"]:
                reject("business_revision_changed")
            result = getattr(module, symbol)(**ticket["arguments"])
            validate(result, snapshot["functions"][ticket["name"]]["output_schema"])
            dumps(result)
        finally:
            _CURRENT.reset(token)
        response.update(status="success", result=result, error=None, references=context.references)
    except BusinessError as error:
        response["error"] = str(error) if str(error) in WORKER_ERRORS else "worker_failed"
    except Exception:
        # Exceptions can contain labels, document contents, credentials or paths.
        # Neither their text nor tracebacks are sent to stdout/stderr.
        pass
    return response


def main():
    try:
        request = loads(sys.stdin.buffer.read(131_073), 131_072)
        response = execute(request)
        sys.stdout.write(dumps(response, MAX_OUTPUT))
    except Exception:
        sys.stdout.write('{"version":1,"status":"error","error":"invalid_worker_request"}')


if __name__ == "__main__":
    main()
