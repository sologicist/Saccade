"""Local-only onboarding with invented corpora; never open user archives."""

import contextlib
import concurrent.futures
import io
import json
import os
import unittest
from unittest.mock import patch

from AutoCua.saccade.business_catalogue import client_registration
from AutoCua.saccade.business_contract import BusinessError
from AutoCua.saccade.client_references import REFERENCE_FILES, require_reference_bundle
from AutoCua.saccade.reference_management import ReferenceManager, main
from tests.business_fixtures import BusinessFixture


class ReferenceOnboardingContracts(unittest.TestCase):
    def setUp(self):
        self.fixture = BusinessFixture()
        self.addCleanup(self.fixture.close)
        self.manager = ReferenceManager(self.fixture.root)

    def corpus(self, client):
        self.manager.initialize(client)
        for name in REFERENCE_FILES:
            (self.fixture.data / client / name).write_text("# Entire invented reference\nFictional local rule.\n", encoding="utf-8")

    def test_initialize_is_idempotent_and_never_creates_or_overwrites_references(self):
        registry = (self.fixture.data / "registration.json").read_bytes()
        result = self.manager.initialize("fictional-new")
        self.assertEqual(result["reference_files_created"], 0)
        self.assertEqual(list((self.fixture.data / "fictional-new").iterdir()), [])
        self.corpus("fictional-new")
        path = self.fixture.data / "fictional-new/comptable_banque.md"
        original = path.read_bytes()
        self.manager.initialize("fictional-new")
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual((self.fixture.data / "registration.json").read_bytes(), registry)

    def test_lowercase_ids_and_reserved_procedure_directory_are_enforced(self):
        for client in ("UPPERCASE", "../outside", "a/b", "navigation", "", 1):
            with self.subTest(client=client), self.assertRaises(BusinessError):
                self.manager.initialize(client)

    def test_missing_empty_binary_and_malformed_files_have_precise_redacted_diagnostics(self):
        self.manager.initialize("fictional-new")
        result = self.manager.validate("fictional-new")
        self.assertEqual([row["status"] for row in result["files"]], ["missing_reference"] * 3)
        tests = [(b" \n", "empty_reference"), (b"\xff", "invalid_reference_encoding"),
                 (b"SYNTHETIC_SECRET\x00", "invalid_reference_content"),
                 (b"%PDF-1.4 fictional", "invalid_reference_content"),
                 (b"s" * (2 * 1024 * 1024 + 1), "size_limit")]
        path = self.fixture.data / "fictional-new/comptable_banque.md"
        for content, code in tests:
            path.write_bytes(content)
            report = self.manager.validate("fictional-new")
            bank = next(row for row in report["files"] if row["name"] == "comptable_banque.md")
            self.assertEqual(bank["status"], code)
            self.assertNotIn("SYNTHETIC_SECRET", json.dumps(report))
            self.assertNotIn(str(self.fixture.root), json.dumps(report))

    def test_extra_generic_reference_is_rejected_without_reading_it(self):
        self.corpus("fictional-new")
        path = self.fixture.data / "fictional-new/comptable.md"
        path.write_text("SYNTHETIC_SECRET_NOT_TO_READ", encoding="utf-8")
        report = self.manager.validate("fictional-new")
        self.assertFalse(report["valid"])
        self.assertEqual(report["unexpected_markdown_files"], 1)
        self.assertNotIn("SYNTHETIC_SECRET", json.dumps(report))
        with self.assertRaisesRegex(BusinessError, "unexpected_reference_file"):
            require_reference_bundle(self.fixture.data, "fictional-new")

    def test_hard_linked_client_reference_is_not_accepted(self):
        self.corpus("fictional-new")
        path = self.fixture.data / "fictional-new/comptable_banque.md"
        linked = self.fixture.data / "synthetic-alpha/linked-private-copy"
        os.link(path, linked)
        report = self.manager.validate("fictional-new")
        self.assertEqual(report["files"][-1]["status"], "unsafe_reference_link")

    def test_register_real_is_metadata_only_preserves_active_client_and_stays_closed(self):
        self.corpus("fictional-new")
        before = self.manager.registry_status()
        after = self.manager.register_real("fictional-new", before["revision"])
        self.assertEqual(after["active_client"], "synthetic-alpha")
        self.assertFalse(after["real_analysis_authorized"])
        raw = json.loads((self.fixture.data / "registration.json").read_bytes())
        self.assertEqual(raw["clients"]["fictional-new"], {"synthetic": False, "bank_labels": [], "bank_responses": {}})
        run = self.fixture.run()
        self.manager.register_real("fictional-new", after["revision"], existing=True, activate=True)
        with self.assertRaisesRegex(BusinessError, "business_client_scope_changed"):
            run.prepare(self.fixture.action())
        clients, _ = client_registration(self.fixture.data)
        self.assertEqual(list(clients), ["fictional-new"])
        run = self.fixture.run()
        with self.assertRaisesRegex(BusinessError, "real_client_privacy_gate_closed"):
            run.prepare(self.fixture.action(arguments={"string": "invented", "client_id": "fictional-new"}))

    def test_stale_registry_and_missing_corpus_cannot_change_registration(self):
        before = (self.fixture.data / "registration.json").read_bytes()
        self.corpus("fictional-new")
        with self.assertRaisesRegex(BusinessError, "client_registration_changed"):
            self.manager.register_real("fictional-new", "0" * 64)
        self.manager.initialize("fictional-empty")
        with self.assertRaisesRegex(BusinessError, "client_references_invalid"):
            self.manager.register_real("fictional-empty", self.manager.registry_status()["revision"])
        self.assertEqual((self.fixture.data / "registration.json").read_bytes(), before)

    def test_atomic_registry_failure_preserves_previous_bytes(self):
        self.corpus("fictional-new")
        before = (self.fixture.data / "registration.json").read_bytes()
        with patch("AutoCua.saccade.reference_management.os.replace", side_effect=OSError("Synthetic interruption")):
            with self.assertRaises(OSError):
                self.manager.register_real("fictional-new", self.manager.registry_status()["revision"])
        self.assertEqual((self.fixture.data / "registration.json").read_bytes(), before)
        self.assertEqual(list(self.fixture.data.glob(".registration-*.pending")), [])

    def test_concurrent_registry_updates_use_compare_and_swap(self):
        for client in ("fictional-first", "fictional-second"):
            self.corpus(client)
        revision = self.manager.registry_status()["revision"]
        def register(client):
            try:
                self.manager.register_real(client, revision)
                return True
            except BusinessError:
                return False
        with concurrent.futures.ThreadPoolExecutor(2) as pool:
            results = list(pool.map(register, ["fictional-first", "fictional-second"]))
        self.assertEqual(results.count(True), 1)
        self.assertEqual(self.manager.registry_status()["active_client"], "synthetic-alpha")

    def test_cli_reports_only_metadata_and_missing_file_statuses(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = main(["--project-root", str(self.fixture.root), "initialize", "--client", "fictional-cli"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output.getvalue())["reference_files_created"], 0)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = main(["--project-root", str(self.fixture.root), "validate", "--client", "fictional-cli"])
        self.assertEqual(code, 2)
        self.assertFalse(json.loads(output.getvalue())["valid"])

    def test_first_registration_requires_explicit_active_selection(self):
        (self.fixture.data / "registration.json").unlink()  # Owned test fixture only.
        self.corpus("fictional-first")
        revision = self.manager.registry_status()["revision"]
        with self.assertRaisesRegex(BusinessError, "explicit_active_client_required"):
            self.manager.register_real("fictional-first", revision)
        result = self.manager.register_real("fictional-first", revision, activate=True)
        self.assertEqual(result["active_client"], "fictional-first")
        self.assertFalse(result["real_analysis_authorized"])

    def test_invalid_bundle_blocks_bank_before_the_worker(self):
        path = self.fixture.data / "synthetic-alpha/comptable_ventes.md"
        path.write_bytes(b"\x00 SYNTHETIC_INVALID")
        run = self.fixture.run()
        with patch("AutoCua.saccade.business_process.run_worker") as worker:
            result = run.execute(run.prepare(self.fixture.action()))
        self.assertEqual(result["code"], "invalid_reference_content")
        worker.assert_not_called()

    def test_redirected_client_directory_is_rejected(self):
        target = self.fixture.root / "outside-reference-root"
        target.mkdir()
        path = self.fixture.data / "fictional-link"
        try:
            path.symlink_to(target, target_is_directory=True)
        except OSError:
            self.skipTest("Windows symlink privilege is unavailable.")
        with self.assertRaises(BusinessError):
            self.manager.initialize("fictional-link")


if __name__ == "__main__":
    unittest.main()
