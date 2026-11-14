"""Synthetic-only operator and procedure contracts; no Chrome or customer data."""

import concurrent.futures
import json
import os
import subprocess
import sys
import threading
import time
import unittest
from unittest.mock import patch

from AutoCua.saccade.business_contract import BusinessError, digest
from AutoCua.saccade.business_functions.platforms.dext.runtime import AccountingContext
from AutoCua.saccade.dext_control import DextRunControl, validate_control
from AutoCua.saccade.procedure_store import ProcedureStore
from tests.business_fixtures import BusinessFixture


class ProcedureContracts(unittest.TestCase):
    def setUp(self):
        self.fixture = BusinessFixture()
        self.addCleanup(self.fixture.close)
        self.store = ProcedureStore(self.fixture.root)

    def propose(self, routes=None):
        return self.store.propose(routes or ["workspace", "invoices", "record", "review"], "synthetic-run")

    def review(self, proposal, approve=True):
        return self.store.review(proposal["proposal_id"], proposal["base_revision"], proposal["candidate_revision"], approve)

    def test_empty_baseline_candidate_diff_and_explicit_publication(self):
        baseline = self.store.baseline_path.read_bytes()
        before = self.store.active()
        proposal = self.propose()
        self.assertEqual(self.store.active(), before)
        self.assertEqual(proposal["old"], "")
        self.assertIn("+1.", proposal["diff"])
        after = self.review(proposal)
        self.assertEqual(after["current"], proposal["candidate_revision"])
        self.assertEqual(after["previous"], before["current"])
        self.assertEqual(self.store.baseline_path.read_bytes(), baseline)

    def test_rejected_proposal_is_consumed_without_active_change(self):
        before = self.store.active()
        p = self.propose()
        self.assertEqual(self.review(p, False), before)
        with self.assertRaisesRegex(BusinessError, "already_reviewed"):
            self.review(p)

    def test_exact_candidate_and_base_are_required(self):
        p = self.propose()
        for key in ("base_revision", "candidate_revision"):
            wrong = {**p, key: "f" * 64}
            with self.assertRaisesRegex(BusinessError, "identity_mismatch"):
                self.review(wrong)

    def test_stale_and_concurrent_publication_cannot_overwrite(self):
        a, b = self.propose(["invoices"]), self.propose(["bank"])
        def publish(p):
            try:
                return self.review(p)["current"]
            except BusinessError:
                return None
        with concurrent.futures.ThreadPoolExecutor(2) as pool:
            results = list(pool.map(publish, [a, b]))
        self.assertEqual(len([r for r in results if r]), 1)
        self.assertIn(self.store.active()["current"], results)
        loser = a if self.store.active()["current"] != a["candidate_revision"] else b
        self.assertEqual(self.review(loser, False), self.store.active())

    def test_pins_survive_resume_and_adopt_only_at_explicit_boundary(self):
        pinned = self.store.pin("synthetic-chat")
        self.review(self.propose())
        reopened = ProcedureStore(self.fixture.root)
        self.assertEqual(reopened.pin("synthetic-chat"), pinned)
        self.assertNotEqual(reopened.pin("new-chat"), pinned)
        self.assertEqual(reopened.pin("synthetic-chat", adopt=True), reopened.active()["current"])

    def test_crash_before_pointer_swap_leaves_old_active_and_never_adopts_orphan(self):
        before = self.store.active()
        p = self.propose()
        original = os.replace
        def fail_pointer(source, target):
            if target.name == "active.json":
                raise OSError("Synthetic interrupted publication")
            return original(source, target)
        with patch("AutoCua.saccade.procedure_store.os.replace", side_effect=fail_pointer):
            with self.assertRaises(OSError):
                self.review(p)
        reopened = ProcedureStore(self.fixture.root)
        self.assertEqual(reopened.active(), before)
        with self.assertRaisesRegex(BusinessError, "already_reviewed"):
            self.review(p)

    def test_crash_after_pointer_swap_reconstructs_complete_revision(self):
        p = self.propose()
        original = self.store._write
        def crash_after(name, value, **kwargs):
            original(name, value, **kwargs)
            if name == "active.json":
                raise OSError("Synthetic crash after replace")
        with patch.object(self.store, "_write", side_effect=crash_after):
            with self.assertRaises(OSError):
                self.review(p)
        self.assertEqual(ProcedureStore(self.fixture.root).active()["current"], p["candidate_revision"])

    def test_partial_write_and_corrupt_pointer_fail_closed(self):
        (self.store.root / "pending-incomplete").write_bytes(b'{"partial":')
        self.assertEqual(ProcedureStore(self.fixture.root).active(), self.store.active())
        (self.store.root / "active.json").write_text("{}", encoding="utf-8")
        with self.assertRaises(BusinessError):
            ProcedureStore(self.fixture.root)

    def test_immutable_snapshot_tampering_and_changed_baseline_are_rejected(self):
        revision = self.review(self.propose())["current"]
        path = self.store.root / "snapshots" / (revision + ".json")
        original = path.read_bytes()
        path.write_text("{}", encoding="utf-8")
        with self.assertRaises(BusinessError):
            self.store.snapshot(revision)
        path.write_bytes(original)
        self.store.baseline_path.write_text("Changed shipping baseline", encoding="utf-8")
        with self.assertRaises(BusinessError):
            ProcedureStore(self.fixture.root)

    def test_rollback_is_explicit_new_revision_with_previous_snapshot_preserved(self):
        before = self.store.active()
        current = self.review(self.propose())
        snapshot = (self.store.root / "snapshots" / (current["current"] + ".json")).read_bytes()
        rolled = self.store.rollback(current["current"], before["current"], "synthetic-run")
        self.assertEqual(self.store.snapshot(rolled["current"])["content"], "")
        self.assertEqual((self.store.root / "snapshots" / (current["current"] + ".json")).read_bytes(), snapshot)
        with self.assertRaises(BusinessError):
            self.store.rollback(current["current"], before["current"], "synthetic-run")

    def test_closed_route_grammar_never_persists_page_content_or_private_values(self):
        for routes in (["<script>fetch('secret')</script>"], ["client-private"], ["https://evil.test"], ["input"], ["download"], ["bank"] * 9, [], "invoices"):
            with self.subTest(routes=routes), self.assertRaises(BusinessError):
                self.store.propose(routes, "synthetic-run")
        p = self.propose()
        self.assertNotIn("synthetic-run", json.dumps(p))
        for path in self.store.root.rglob("*.json"):
            self.assertNotIn("SYNTHETIC BANK", path.read_text())

    def test_missing_pointer_or_pin_cannot_silently_adopt_a_new_revision(self):
        self.store.pin("synthetic-chat")
        pin = self.store.root / "pins" / (digest("synthetic-chat") + ".json")
        pin.unlink()  # Generated synthetic test data only.
        for adopt in (False, True):
            with self.assertRaisesRegex(BusinessError, "procedure_corrupt"):
                self.store.pin("synthetic-chat", adopt=adopt)
        (self.store.root / "active.json").unlink()
        with self.assertRaisesRegex(BusinessError, "procedure_corrupt"):
            ProcedureStore(self.fixture.root)

    def test_os_lock_is_exclusive_across_processes_and_released_after_use(self):
        code = """
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from AutoCua.saccade.procedure_store import ProcedureStore
from AutoCua.saccade.business_contract import BusinessError
try:
    ProcedureStore(Path(sys.argv[2]))
except (BusinessError, BlockingIOError):
    print('locked')
else:
    print('available')
"""
        command = [sys.executable, "-I", "-B", "-c", code, str(self.fixture.root.parents[2]), str(self.fixture.root)]
        def check():
            return subprocess.run(command, capture_output=True, text=True, timeout=10, check=True).stdout.strip()
        with self.store.lock():
            self.assertEqual(check(), "locked")
        self.assertEqual(check(), "available")

    def test_redirected_store_root_is_rejected(self):
        target = self.fixture.root / "redirected"
        target.mkdir()
        path = self.fixture.data / "synthetic-link"
        try:
            path.symlink_to(target, target_is_directory=True)
        except OSError:
            self.skipTest("Windows symlink privilege is unavailable.")
        with self.assertRaises(BusinessError):
            self.store._directories(path / "nested")


class DextControlContracts(unittest.TestCase):
    def setUp(self):
        self.fixture = BusinessFixture()
        self.addCleanup(self.fixture.close)
        self.stop = threading.Event()
        self.control = DextRunControl(self.fixture.context, "synthetic-chat", project_root=self.fixture.root, stop_event=self.stop)
        self.addCleanup(self.control.close)
        self.elements = {"1": {"name": "Synthetic invoices", "role": "link", "rect": [10, 10, 100, 20]}}
        self.stamp = {"observer": "synthetic-observer", "tab": "1", "profile": "saccade-dext", "config_revision": self.fixture.context["config_revision"]}

    def observe(self):
        self.control.freeze_decision()
        self.control.observe_native(self.elements, self.stamp)

    def event(self, event, **fields):
        return self.control.operator_event({"review_token": self.control.review_token, "event": event, **fields}, busy=not self.control.closed)

    def request(self):
        return self.control.propose_navigation({"type": "dext_navigation", "version": 1, "route": "invoices", "target_id": 1})

    def test_model_or_page_cannot_manufacture_operator_authority(self):
        for body in ({"event": "teach", "routes": ["bank"]}, {"review_token": "yes", "event": "teach", "routes": ["bank"]}):
            with self.assertRaisesRegex(BusinessError, "operator_channel_required"):
                self.control.operator_event(body, busy=False)
        with self.assertRaises(BusinessError):
            validate_control(object(), self.fixture.context)

    def test_navigation_preview_requires_observed_target_and_exact_schema(self):
        with self.assertRaisesRegex(BusinessError, "stale_navigation"):
            self.request()
        self.observe()
        for extra in ({"approved": True}, {"client_id": "synthetic-other"}, {"url": "https://evil.test"}):
            with self.assertRaises(BusinessError):
                self.control.propose_navigation({"type": "dext_navigation", "version": 1, "route": "invoices", "target_id": 1, **extra})
        result = self.request()
        self.assertEqual(result["status"], "error")
        self.assertNotIn(self.control.review_token, json.dumps(result))
        self.assertEqual(self.control.status()["navigation"]["label"], "Synthetic invoices")

    def test_independent_ui_approval_unblocks_wait_but_never_dispatches_live_input(self):
        self.observe()
        self.request()
        pending = self.control.pending.copy()
        result = []
        thread = threading.Thread(target=lambda: result.append(self.control.wait_navigation_review()))
        thread.start()
        answer = self.event("navigation_review", proposal_id=pending["proposal_id"], observation_id=pending["observation_id"], approve=True)
        thread.join(2)
        self.assertFalse(thread.is_alive())
        self.assertFalse(answer["executed"])
        self.assertEqual(result[0]["code"], "verified_dext_navigation_adapter_required")
        with self.assertRaises(BusinessError):
            self.event("navigation_review", proposal_id=pending["proposal_id"], observation_id=pending["observation_id"], approve=True)

    def test_same_url_new_observation_invalidates_target_and_dossier_claim(self):
        self.observe()
        old = self.control.observation["id"]
        self.request()
        self.event("bind", client_id="synthetic-alpha", observation_id=old)
        self.elements["1"]["name"] = "Different synthetic record at same URL"
        self.observe()
        self.assertIsNone(self.control.pending)
        self.assertIsNone(self.control.binding)
        with self.assertRaises(BusinessError):
            self.event("bind", client_id="synthetic-alpha", observation_id=old)

    def test_source_change_after_model_selection_invalidates_operator_approval(self):
        self.observe()
        self.request()
        pending = self.control.pending.copy()
        with patch("AutoCua.saccade.dext_control.catalogue", return_value={"revision": "0" * 64}):
            with self.assertRaisesRegex(BusinessError, "navigation_source_changed"):
                self.event("navigation_review", proposal_id=pending["proposal_id"], observation_id=pending["observation_id"], approve=True)

    def test_client_mapping_is_only_a_claim_and_never_live_business_permission(self):
        self.observe()
        observation = self.control.observation["id"]
        for client in ("synthetic-other", "../synthetic-alpha", "unregistered"):
            with self.assertRaises(BusinessError):
                self.event("bind", client_id=client, observation_id=observation)
        self.event("bind", client_id="synthetic-alpha", observation_id=observation)
        self.assertFalse(self.control.binding["verified_for_business"])
        self.assertNotIn("synthetic-alpha", json.dumps(self.control.binding))

    def test_wrong_profile_observer_and_context_remain_closed(self):
        for changes in ({"profile": "other"}, {"observer": ""}, {"tab": ""}, {"config_revision": "0" * 64}):
            with self.assertRaises(BusinessError):
                self.control.observe_native(self.elements, {**self.stamp, **changes})
        with self.assertRaises(BusinessError):
            validate_control(self.control, {**self.fixture.context, "execution_mode": "auto"})

    def test_rejection_timeout_and_stop_do_not_retry(self):
        self.observe()
        self.request()
        pending = self.control.pending.copy()
        self.event("navigation_review", proposal_id=pending["proposal_id"], observation_id=pending["observation_id"], approve=False)
        self.assertEqual(self.control.wait_navigation_review()["code"], "operator_rejected")
        self.request()
        self.control.pending["expires"] = time.monotonic() - 1
        self.assertEqual(self.control.wait_navigation_review()["code"], "navigation_approval_expired")
        self.observe()
        self.request()
        self.stop.set()
        self.assertEqual(self.control.wait_navigation_review()["status"], "stopped")
        self.assertIsNone(self.control.pending)

    def test_teaching_review_and_next_run_overlay_require_separate_decisions(self):
        self.event("teach", routes=["workspace", "invoices", "record", "review"])
        proposal = self.control.proposal.copy()
        self.assertEqual(self.control.overlay(), "")
        self.event("review", proposal_id=proposal["proposal_id"], base_revision=proposal["base_revision"], candidate_revision=proposal["candidate_revision"], approve=True)
        self.assertEqual(self.control.overlay(), "")
        with self.assertRaisesRegex(BusinessError, "safe_boundary"):
            self.event("adopt")
        resumed = DextRunControl(self.fixture.context, "synthetic-chat", project_root=self.fixture.root)
        self.addCleanup(resumed.close)
        self.assertEqual(resumed.overlay(), "")
        new = DextRunControl(self.fixture.context, "new-chat", project_root=self.fixture.root)
        self.addCleanup(new.close)
        self.assertIn("approved_navigation_guidance", new.overlay())
        self.control.close()
        self.event("adopt")
        self.assertIn("approved_navigation_guidance", self.control.overlay())

    def test_close_revokes_pending_navigation_and_bindings(self):
        self.observe()
        self.request()
        self.control.close()
        self.assertIsNone(self.control.status()["navigation"])
        self.assertEqual(self.control.wait_navigation_review()["status"], "stopped")


class ReferenceMigrationContracts(unittest.TestCase):
    def setUp(self):
        self.fixture = BusinessFixture()
        self.addCleanup(self.fixture.close)

    def test_exactly_three_approved_reference_filenames(self):
        clients = {"synthetic-alpha": self.fixture.registration["clients"]["synthetic-alpha"]}
        context = AccountingContext(self.fixture.data, clients)
        for name in ("comptable.md", "../comptable_banque.md", "secret.md"):
            with self.assertRaisesRegex(BusinessError, "unapproved_reference_file"):
                context.reference("synthetic-alpha", name)

    def test_near_two_megabyte_reference_is_read_fully_and_larger_is_rejected(self):
        clients = {"synthetic-alpha": self.fixture.registration["clients"]["synthetic-alpha"]}
        context = AccountingContext(self.fixture.data, clients)
        path = self.fixture.data / "synthetic-alpha/comptable_achats.md"
        text = "S" * 2_025_000 + "FINAL SYNTHETIC RULE"
        path.write_text(text, encoding="utf-8")
        self.assertEqual(context.reference("synthetic-alpha", "comptable_achats.md"), text)
        path.write_bytes(b"S" * (2 * 1024 * 1024 + 1))
        with self.assertRaisesRegex(BusinessError, "size_limit"):
            context.reference("synthetic-alpha", "comptable_achats.md")

    def test_reference_revision_changes_invalidate_prepared_and_worker_tickets(self):
        run = self.fixture.run()
        ticket = run.prepare(self.fixture.action())
        self.fixture.reference.write_text("Changed synthetic corpus", encoding="utf-8")
        with self.assertRaisesRegex(BusinessError, "revision_changed"):
            run.prepare(self.fixture.action())
        with patch("AutoCua.saccade.business_process.run_worker") as worker:
            self.assertEqual(run.execute(ticket)["code"], "business_revision_changed")
            worker.assert_not_called()
        from AutoCua.saccade.business_process import run_worker
        reply = run_worker({"version": 1, "ticket": ticket, "context": self.fixture.context,
                            "project_root": str(self.fixture.root), "offline_receipts": {},
                            "model": "offline-synthetic-v1"}, package_root=self.fixture.package)
        self.assertEqual(reply["error"], "business_revision_changed")

    def test_real_client_registration_never_prereads_private_corpus(self):
        self.fixture.registration["clients"]["synthetic-alpha"]["synthetic"] = False
        self.fixture.write_registration()
        from AutoCua.saccade import business_run
        def guarded(root, path, limit):
            self.fail("Closed real-client refresh must not read any accounting corpus")
        with patch.object(business_run, "read_safe", side_effect=guarded):
            run = self.fixture.run()
            with self.assertRaisesRegex(BusinessError, "real_client_privacy_gate_closed"):
                run.prepare(self.fixture.action())

    def test_credit_notes_and_quotes_require_operator_review_without_schema_change(self):
        for kind in ("avoir", "devis"):
            receipts = self.fixture.invoice()
            receipt = receipts["fixture-one"]
            raw = receipt["expected"]
            raw["type"] = receipt["critical"]["type"] = kind
            if kind == "avoir":
                for key in ("total_centimes", "tva_centimes"):
                    raw["piece"][key] *= -1
                    receipt["critical"]["piece"][key] *= -1
                for row in raw["ecriture"]:
                    row["debit_centimes"], row["credit_centimes"] = row["credit_centimes"], row["debit_centimes"]
            else:
                raw["statut"] = "sans_ecriture"
            run = self.fixture.run(offline_receipts=receipts)
            action = self.fixture.action(name="dext.scribe", arguments={"pdf": "fixture-one", "client_id": "synthetic-alpha", "sens": "achat"})
            result = run.execute(run.prepare(action))
            self.assertEqual(result["status"], "success", result)
            self.assertEqual(result["result"]["type"], kind)
            self.assertTrue(result["operator_review_required"])
            self.assertIsNone(result["result"]["description"])


if __name__ == "__main__":
    unittest.main()
