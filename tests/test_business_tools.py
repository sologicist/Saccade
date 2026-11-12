"""Static discovery, trusted selection and real bounded offline worker tests."""

import copy
import json
import threading
import unittest
from unittest.mock import patch

from AutoCua.saccade.business_catalogue import catalogue, client_registration
from AutoCua.saccade.business_contract import BusinessError, loads, static_signature, validate
from AutoCua.saccade.business_process import run_worker
from AutoCua.saccade.business_functions.platforms.dext.runtime import AccountingContext
from AutoCua.saccade.business_functions.platforms.dext.invoice_validation import analysis
from tests.business_fixtures import BusinessFixture


class BusinessContracts(unittest.TestCase):
    def setUp(self):
        self.fixture = BusinessFixture()
        self.addCleanup(self.fixture.close)

    def test_discovery_never_executes_top_level_code(self):
        path = self.fixture.functions / "functions.py"
        path.write_bytes(path.read_bytes() + b'\nraise RuntimeError("must not execute during discovery")\n')
        self.assertEqual(set(catalogue("dext", package_root=self.fixture.package)["functions"]), {"dext.bank", "dext.scribe"})

    def test_static_supported_schemas_are_closed(self):
        source = b'''from typing import TypedDict, Literal, Annotated, Optional
class Result(TypedDict):
    value: Optional[str]
    flags: list[bool]
def public(x: Annotated[int, {"minimum": 1, "maximum": 4}], mode: Literal["one", "two"]) -> Result:
    pass
'''
        inputs, output = static_signature(source, "public")
        validate({"x": 2, "mode": "one"}, inputs)
        validate({"value": None, "flags": [True]}, output)
        for value in ({"x": True, "mode": "one"}, {"x": 5, "mode": "one"}, {"x": 2, "mode": "one", "extra": 1}):
            with self.subTest(value=value), self.assertRaises(BusinessError):
                validate(value, inputs)

    def test_unsupported_or_ambiguous_signatures_fail_closed(self):
        for source, name in [
            (b'def public(x: int) -> str: pass', 'public'), (b'def public(x: dict) -> str: pass', 'public'),
            (b'def public(*args: str) -> str: pass', 'public'), (b'def public(**kwargs: str) -> str: pass', 'public'),
            (b'def public(x: str="default") -> str: pass', 'public'), (b'def _private(x: str) -> str: pass', '_private'),
            (b'def public(x: "arbitrary.Type") -> str: pass', 'public'),
            (b'def public(x: str) -> str: pass\ndef public(x: str) -> str: pass', 'public'),
            (b'def broken(', 'public'), (b'def public(x: __import__("os")) -> str: pass', 'public')]:
            with self.subTest(source=source), self.assertRaises(BusinessError):
                static_signature(source, name)

    def test_shadowed_annotation_bindings_are_not_guessed(self):
        for source in (b'str = bool\ndef public(x: str) -> str: pass',
                       b'from arbitrary import Literal\ndef public(x: Literal["one"]) -> str: pass',
                       b'import typing as str\ndef public(x: str) -> str: pass'):
            with self.subTest(source=source), self.assertRaisesRegex(BusinessError, "ambiguous_annotation_binding"):
                static_signature(source, "public")

    def test_json_rejects_duplicates_nonfinite_invalid_and_oversized(self):
        for value in ('{"x":1,"x":2}', '{"x":NaN}', '{"x":Infinity}', '{', '"' + 'a' * 40_000 + '"'):
            with self.subTest(value=value[:20]), self.assertRaises(BusinessError):
                loads(value)

    def test_policy_rejects_effects_modules_hidden_symbols_and_duplicates(self):
        path = self.fixture.functions / "policy.json"
        original = json.loads(path.read_bytes())
        for key, value in (("effect", "mutation"), ("effect", "external_effect"), ("module", "../../os.py"),
                           ("module", "builtins"), ("symbol", "_private"), ("capabilities", ["download"])):
            policy = copy.deepcopy(original)
            policy["functions"][0][key] = value
            path.write_text(json.dumps(policy), encoding="utf-8")
            with self.subTest(key=key, value=value), self.assertRaises(BusinessError):
                catalogue("dext", package_root=self.fixture.package)
        original["functions"].append(original["functions"][0])
        path.write_text(json.dumps(original), encoding="utf-8")
        with self.assertRaises(BusinessError):
            catalogue("dext", package_root=self.fixture.package)

    def test_unknown_platform_and_forged_context_are_rejected(self):
        from AutoCua.saccade.business_run import BusinessRun
        for platform in ("other", "../dext", "dext.functions", None):
            with self.subTest(platform=platform), self.assertRaises(BusinessError):
                catalogue(platform)
        for change in ({"allowed_hosts": ["evil.test"]}, {"execution_mode": "auto"}, {"config_revision": "a" * 64}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                BusinessRun(dict(self.fixture.context, **change), project_root=self.fixture.root, package_root=self.fixture.package)

    def test_model_arguments_cannot_expand_authority_or_paths(self):
        run = self.fixture.run()
        for change in ({"effect": "compute"}, {"platform_id": "dext"}, {"name": "os.system"},
                       {"name": "other.bank"}, {"name": "dext._private"}, {"version": True},
                       {"arguments": {"client_id": "../synthetic-alpha", "string": "SYNTHETIC BANK"}},
                       {"arguments": {"client_id": "synthetic-other", "string": "OTHER BANK"}},
                       {"arguments": {"client_id": "synthetic-alpha", "string": "not operator supplied"}},
                       {"arguments": {"client_id": "synthetic-alpha", "string": "SYNTHETIC BANK", "module": "os"}}):
            with self.subTest(change=change), self.assertRaises(BusinessError):
                run.prepare(self.fixture.action(**change))

    def test_stale_main_helper_policy_and_registration_are_rejected(self):
        for path in (self.fixture.functions / "functions.py", self.fixture.functions / "runtime.py",
                     self.fixture.functions / "policy.json", self.fixture.data / "registration.json"):
            with self.subTest(path=path.name):
                original = path.read_bytes()
                run = self.fixture.run()
                ticket = run.prepare(self.fixture.action())
                path.write_bytes(original + b"\n")
                with self.assertRaisesRegex(BusinessError, "business_revision_changed"):
                    run.prepare(self.fixture.action())
                with patch("AutoCua.saccade.business_process.run_worker") as worker:
                    self.assertEqual(run.execute(ticket)["code"], "business_revision_changed")
                    worker.assert_not_called()
                path.write_bytes(original)

    def test_real_worker_success_and_fresh_reference_receipts(self):
        run = self.fixture.run()
        result = run.execute(run.prepare(self.fixture.action()))
        self.assertEqual(result["result"], {"compte": "40100000"})
        first = run.receipts[-1]["references"]
        self.fixture.reference.write_text("Entire changed synthetic Markdown.", encoding="utf-8")
        self.assertEqual(run.execute(run.prepare(self.fixture.action()))["status"], "success")
        self.assertNotEqual(first, run.receipts[-1]["references"])
        self.assertNotIn("synthetic-alpha", json.dumps(run.receipts))

    def test_ambiguous_and_unknown_accounts_return_only_null(self):
        run = self.fixture.run()
        for label in ("AMBIGUOUS", "UNKNOWN"):
            result = run.execute(run.prepare(self.fixture.action(arguments={"string": label, "client_id": "synthetic-alpha"})))
            self.assertEqual(result["result"], {"compte": None})

    def test_missing_reference_is_typed_and_redacted(self):
        # Point at a distinct valid client without creating its reference.
        self.fixture.registration["active_client"] = "synthetic-other"
        self.fixture.write_registration()
        run = self.fixture.run()
        action = self.fixture.action(arguments={"string": "OTHER BANK", "client_id": "synthetic-other"})
        result = run.execute(run.prepare(action))
        self.assertEqual(result["code"], "required_file_unavailable")
        self.assertNotIn(str(self.fixture.root), json.dumps(result))

    def test_tickets_are_single_use(self):
        run = self.fixture.run()
        ticket = run.prepare(self.fixture.action())
        self.assertEqual(run.execute(ticket)["status"], "success")
        with patch("AutoCua.saccade.business_process.run_worker") as worker:
            self.assertEqual(run.execute(ticket)["code"], "invalid_or_consumed_business_ticket")
            worker.assert_not_called()

    def test_real_client_privacy_gate_is_closed(self):
        self.fixture.registration["clients"]["synthetic-alpha"]["synthetic"] = False
        self.fixture.write_registration()
        run = self.fixture.run()
        with self.assertRaisesRegex(BusinessError, "real_client_privacy_gate_closed"):
            run.prepare(self.fixture.action())

    def test_unverified_pdf_is_denied_before_worker(self):
        self.fixture.invoice()
        run = self.fixture.run()
        for pdf in ("fixture-one", str(self.fixture.data / "synthetic-alpha/synthetic.pdf"), "../../invoice.pdf"):
            with patch("AutoCua.saccade.business_process.run_worker") as worker:
                with self.assertRaisesRegex(BusinessError, "verified_download_receipt_required"):
                    run.prepare(self.fixture.action(name="dext.scribe", arguments={"pdf": pdf, "client_id": "synthetic-alpha", "sens": "achat"}))
                worker.assert_not_called()

    def test_trusted_synthetic_invoice_runs_in_real_worker(self):
        run = self.fixture.run(offline_receipts=self.fixture.invoice())
        action = self.fixture.action(name="dext.scribe", arguments={"pdf": "fixture-one", "client_id": "synthetic-alpha", "sens": "achat"})
        result = run.execute(run.prepare(action))
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["result"]["total_ttc"], "120.00")
        self.assertEqual(result["result"]["fournisseur"], "Synthetic Party")
        self.assertEqual(result["result"]["description"], None)
        self.assertEqual(len(result["result"]["ecriture"]), 3)

    def test_bank_exact_label_full_markdown_and_provider_validation(self):
        clients, _ = client_registration(self.fixture.data)
        for response in ({"compte": "512001"}, {"compte": "bad"}, {"compte": "A"}, {"compte": 401},
                         {"compte": "401", "extra": True}, '{"compte":null,"compte":"401"}', 'x' * 32001):
            class Fake:
                def bank(inner, label, markdown, client):
                    self.assertEqual(label, "SYNTHETIC BANK")
                    self.assertEqual(markdown, self.fixture.reference.read_bytes().decode("utf-8"))
                    self.assertEqual(client, "synthetic-alpha")
                    return response
            with self.subTest(response=str(response)[:40]), self.assertRaises(BusinessError):
                AccountingContext(self.fixture.data, clients, provider=Fake()).bank("SYNTHETIC BANK", "synthetic-alpha")

    def test_invoice_validator_rejects_malformed_critical_conflicting_and_nonfinite(self):
        receipt = self.fixture.invoice()["fixture-one"]
        good = receipt["expected"]
        variants = ["not JSON", '{"type":NaN}', dict(good, extra="unapproved"), dict(good, journal="INVENTED")]
        bad_account = copy.deepcopy(good)
        bad_account["ecriture"][0]["compte"] = "699999"
        variants.append(bad_account)
        for field, value in (("total_centimes", 12100), ("reference", "DIFFERENT"), ("devise", "USD"), ("date", "20260101"), ("tva_centimes", float("nan"))):
            response = copy.deepcopy(good)
            response["piece"][field] = value
            variants.append(response)
        for response in variants:
            with self.subTest(response=str(response)[:80]), self.assertRaises(BusinessError):
                analysis(response, "achat", has_description_rule=False, expected=receipt["critical"])

    def test_review_quote_and_unknown_never_return_entries(self):
        good = self.fixture.invoice()["fixture-one"]["expected"]
        for kind, status, reasons in (("devis", "sans_ecriture", []), (None, "a_revoir", ["Unclear synthetic invoice"]), ("facture", "a_revoir", [])):
            result = analysis(dict(good, type=kind, statut=status, motifs=reasons), "achat", has_description_rule=False)
            self.assertEqual(result["ecriture"], [])
            self.assertIsNone(result["journal"])
        receipt = self.fixture.invoice()["fixture-one"]
        result = analysis(dict(good, statut="a_revoir", piece=None, ecriture=[]), "achat",
                          has_description_rule=False, expected=receipt["critical"])
        self.assertEqual(result["ecriture"], [])
        self.assertIsNone(result["total_ttc"])

    def test_credit_note_and_sale_reverse_sides(self):
        good = self.fixture.invoice()["fixture-one"]["expected"]
        for sens, kind in (("vente", "facture"), ("achat", "avoir")):
            proposal = copy.deepcopy(good)
            proposal["type"] = kind
            if kind == "avoir":
                proposal["piece"]["total_centimes"] *= -1
                proposal["piece"]["tva_centimes"] *= -1
            for row in proposal["ecriture"]:
                row["debit_centimes"], row["credit_centimes"] = row["credit_centimes"], row["debit_centimes"]
            result = analysis(proposal, sens, has_description_rule=True)
            self.assertEqual(len(result["ecriture"]), 3)
            self.assertIn("client" if sens == "vente" else "fournisseur", result)
            self.assertEqual(result["description"], "Synthetic fixture")

    def test_unbalanced_entries_and_wrong_schema_are_rejected(self):
        good = self.fixture.invoice()["fixture-one"]["expected"]
        good["ecriture"][0]["debit_centimes"] += 1
        with self.assertRaisesRegex(BusinessError, "invoice_entries_mismatch"):
            analysis(good, "achat", has_description_rule=False)

    def test_worker_validates_response_identity_independently(self):
        run = self.fixture.run()
        ticket = run.prepare(self.fixture.action())
        with patch("AutoCua.saccade.business_process.run_worker", return_value={"status": "success"}):
            self.assertEqual(run.execute(ticket)["code"], "invalid_worker_response")

    def test_worker_stdout_contamination_and_exceptions_are_redacted(self):
        source = self.fixture.functions / "functions.py"
        for injected in (b'\nprint("SYNTHETIC_SECRET")\n', b'\nraise RuntimeError("SYNTHETIC_SECRET")\n'):
            original = source.read_bytes()
            source.write_bytes(original + injected)
            run = self.fixture.run()
            result = run.execute(run.prepare(self.fixture.action()))
            self.assertEqual(result["status"], "error")
            self.assertNotIn("SYNTHETIC_SECRET", json.dumps(result))
            source.write_bytes(original)

    def test_worker_timeout_cancellation_and_output_limits_cleanup(self):
        source = self.fixture.functions / "functions.py"
        original = source.read_bytes()
        for injected, expected in ((b'\nimport time\ntime.sleep(30)\n', "worker_timeout"),
                                   (b'\nimport sys\nsys.stdout.write("x" * 200000)\n', "worker_output_limit"),
                                   (b'\nimport sys\nsys.stderr.write("x" * 200000)\n', "worker_output_limit")):
            source.write_bytes(original + injected)
            run = self.fixture.run()
            def bounded(request, **kwargs):
                return run_worker(request, timeout=1.5 if expected == "worker_timeout" else 10.0, **kwargs)
            with self.subTest(expected=expected), patch("AutoCua.saccade.business_process.run_worker", side_effect=bounded):
                self.assertEqual(run.execute(run.prepare(self.fixture.action()))["code"], expected)
            source.write_bytes(original)
        stop = threading.Event()
        stop.set()
        run = self.fixture.run()
        self.assertEqual(run.execute(run.prepare(self.fixture.action()), stop)["status"], "stopped")

    def test_symlink_escape_is_refused_when_supported(self):
        link = self.fixture.functions / "escape.py"
        try:
            link.symlink_to(self.fixture.reference)
        except OSError:
            self.skipTest("This account cannot create symbolic links.")
        with self.assertRaisesRegex(BusinessError, "unsafe_path"):
            catalogue("dext", package_root=self.fixture.package)

    def test_bank_reloads_full_markdown_and_keeps_exact_label(self):
        clients, _ = client_registration(self.fixture.data)
        observed = []
        class Fake:
            def bank(self, label, markdown, client):
                observed.append((label, markdown, client))
                return {"compte": "40100000"}
        context = AccountingContext(self.fixture.data, clients, provider=Fake())
        context.bank("SYNTHETIC BANK", "synthetic-alpha")
        self.fixture.reference.write_bytes(b"Changed full synthetic reference.\nFinal rule remains present.\n")
        context.bank("SYNTHETIC BANK", "synthetic-alpha")
        self.assertNotEqual(observed[0][1], observed[1][1])
        self.assertEqual(observed[1], ("SYNTHETIC BANK", self.fixture.reference.read_bytes().decode(), "synthetic-alpha"))

    def test_empty_reference_and_invalid_bank_labels_are_refused(self):
        clients, _ = client_registration(self.fixture.data)
        context = AccountingContext(self.fixture.data, clients)
        for label in ("", " ", "x" * 1001, None, 3):
            with self.subTest(label=str(label)[:10]), self.assertRaises(BusinessError):
                context.bank(label, "synthetic-alpha")
        self.fixture.reference.write_bytes(b"")
        with self.assertRaisesRegex(BusinessError, "empty_reference"):
            context.bank("SYNTHETIC BANK", "synthetic-alpha")

    def test_changed_pdf_and_cross_client_fixture_paths_are_refused(self):
        receipt = self.fixture.invoice()
        clients, _ = client_registration(self.fixture.data)
        context = AccountingContext(self.fixture.data, clients, offline_receipts=receipt)
        receipt["fixture-one"]["sha256"] = "0" * 64
        with self.assertRaisesRegex(BusinessError, "offline_fixture_identity_mismatch"):
            context.scribe("fixture-one", "synthetic-alpha", "achat")
        receipt["fixture-one"]["relative_path"] = "../outside.pdf"
        with self.assertRaises(BusinessError):
            context.scribe("fixture-one", "synthetic-alpha", "achat")

    def test_complex_vat_or_invalid_roles_require_review(self):
        good = self.fixture.invoice()["fixture-one"]["expected"]
        for change in ("multi-rate", "wrong-tax-account", "wrong-party-account"):
            proposal = copy.deepcopy(good)
            if change == "multi-rate":
                proposal["ecriture"][1]["debit_centimes"] = 1000
                proposal["ecriture"].append({"compte":"445661", "role":"tva", "debit_centimes":1000, "credit_centimes":0})
            elif change == "wrong-tax-account":
                proposal["ecriture"][1]["compte"] = "601001"
            else:
                proposal["ecriture"][2]["compte"] = "9DIV"
            with self.subTest(change=change):
                result = analysis(proposal, "achat", has_description_rule=False)
                self.assertEqual(result["ecriture"], [])
                self.assertIsNone(result["journal"])

    def test_mid_execution_stop_releases_real_worker(self):
        import time
        source = self.fixture.functions / "functions.py"
        marker = self.fixture.root / "worker-started.txt"
        source.write_bytes(source.read_bytes() + ('\nfrom pathlib import Path\nimport time\nPath(' + repr(str(marker)) + ').write_text("synthetic ready")\ntime.sleep(30)\n').encode())
        run = self.fixture.run()
        stop = threading.Event()
        def cancel_started_worker():
            deadline = time.monotonic() + 5
            while not marker.exists() and time.monotonic() < deadline:
                time.sleep(0.01)
            stop.set()
        timer = threading.Thread(target=cancel_started_worker)
        timer.start()
        try:
            result = run.execute(run.prepare(self.fixture.action()), stop)
            self.assertEqual(result["status"], "stopped")
            self.assertEqual(result["code"], "worker_cancelled")
            self.assertTrue(marker.is_file())
        finally:
            timer.join()

    def test_windows_job_failure_never_delivers_request(self):
        import os
        if os.name != "nt":
            self.skipTest("Windows job boundary only.")
        run = self.fixture.run()
        with patch("AutoCua.saccade.business_process.WindowsJob", side_effect=BusinessError("worker_job_unavailable")):
            result = run.execute(run.prepare(self.fixture.action()))
        self.assertEqual(result["code"], "worker_job_unavailable")
        self.assertEqual(run.receipts, [])

    def test_active_client_change_requires_new_run(self):
        run = self.fixture.run()
        self.fixture.registration["active_client"] = "synthetic-other"
        self.fixture.write_registration()
        with self.assertRaisesRegex(BusinessError, "business_client_scope_changed"):
            run.refresh()

    def test_parent_rejects_invalid_result_even_from_correlated_worker(self):
        run = self.fixture.run()
        ticket = run.prepare(self.fixture.action())
        reply = {"version":1,"call_id":ticket["call_id"],"run_id":ticket["run_id"],"status":"success",
                 "result":{"compte":"512001"},"error":None,"references":{"comptable_banque.md":"a"*64}}
        with patch("AutoCua.saccade.business_process.run_worker", return_value=reply):
            self.assertEqual(run.execute(ticket)["code"], "schema_mismatch")

    def test_reference_changed_during_read_is_refused(self):
        import os
        from types import SimpleNamespace
        from AutoCua.saccade.business_contract import read_safe
        real = self.fixture.reference.stat()
        before = SimpleNamespace(st_size=real.st_size, st_mtime_ns=real.st_mtime_ns, st_ctime_ns=real.st_ctime_ns, st_ino=real.st_ino)
        after = SimpleNamespace(st_size=real.st_size, st_mtime_ns=real.st_mtime_ns+1, st_ctime_ns=real.st_ctime_ns, st_ino=real.st_ino)
        with patch.object(os, "fstat", side_effect=[before, after]):
            with self.assertRaisesRegex(BusinessError, "file_changed_during_read"):
                read_safe(self.fixture.data, self.fixture.reference)

    def test_unfingerprinted_or_dynamic_business_imports_are_refused(self):
        path = self.fixture.functions / "runtime.py"
        original = path.read_bytes()
        for statement in (b'\nimport AutoCua.utils.rust\n', b'\nimport AutoCua.saccade_other\n',
                          b'\nfrom AutoCua import utils\n', b'\nimport litellm\n',
                          b'\n__import__("os")\n', b'\nimportlib.import_module("arbitrary")\n'):
            path.write_bytes(original + statement)
            with self.subTest(statement=statement), self.assertRaisesRegex(BusinessError, "unsupported_business_dependency"):
                catalogue("dext", package_root=self.fixture.package)
        path.write_bytes(original)

    def test_external_accounting_model_is_denied_before_worker(self):
        run = self.fixture.run()
        ticket = run.prepare(self.fixture.action())
        with patch.dict("os.environ", {"COMPTABLE_LLM_MODEL": "gemini/unapproved"}), patch("AutoCua.saccade.business_process.run_worker") as worker:
            self.assertEqual(run.execute(ticket)["code"], "external_provider_consent_required")
            worker.assert_not_called()

    def test_worker_executes_fingerprinted_source_instead_of_stale_bytecode(self):
        import py_compile
        path = self.fixture.functions / "functions.py"
        original = path.read_bytes()
        path.write_bytes(original + b'\nraise RuntimeError("stale bytecode must not execute")\n')
        py_compile.compile(str(path), doraise=True, invalidation_mode=py_compile.PycInvalidationMode.UNCHECKED_HASH)
        path.write_bytes(original)
        run = self.fixture.run()
        self.assertEqual(run.execute(run.prepare(self.fixture.action()))["result"], {"compte":"40100000"})

    def test_absent_reference_revision_cannot_alias_present_content(self):
        clients, _ = client_registration(self.fixture.data)
        context = AccountingContext(self.fixture.data, clients)
        context.reference("synthetic-alpha", "comptable.md", optional=True)
        absent = context.references["comptable.md"]
        (self.fixture.data / "synthetic-alpha/comptable.md").write_bytes(b"absent")
        context.reference("synthetic-alpha", "comptable.md", optional=True)
        self.assertNotEqual(context.references["comptable.md"], absent)


if __name__ == "__main__":
    unittest.main()
