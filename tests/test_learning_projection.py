"""Canonical stable Markdown projection, using synthetic local stores only."""
import os
import subprocess
from pathlib import Path
import unittest
from unittest.mock import patch

from AutoCua.saccade.business_contract import BusinessError
from AutoCua.saccade.procedure_store import ProcedureStore
from AutoCua.saccade.dext_control import DextRunControl
from tests.business_fixtures import BusinessFixture


class LearningProjectionContracts(unittest.TestCase):
    def setUp(self):
        self.fixture = BusinessFixture()
        self.addCleanup(self.fixture.close)
        self.store = ProcedureStore(self.fixture.root)
        self.path = self.store.root / 'learning.md'

    def proposal(self):
        return self.store.propose(['purchases', 'inbox'], 'synthetic-run', incremental=True)

    def review(self, proposal, approve=True):
        return self.store.review(proposal['proposal_id'], proposal['base_revision'], proposal['candidate_revision'], approve)

    def test_initialization_approval_equality_rejection_and_immutable_snapshots(self):
        baseline = self.store.baseline_path.read_bytes()
        self.assertEqual(self.path.read_bytes(), baseline)
        proposal = self.proposal()
        before = self.path.read_bytes()
        self.assertEqual(self.review(proposal, False), self.store.active())
        self.assertEqual(self.path.read_bytes(), before)
        approved = self.proposal()
        self.review(approved)
        self.assertEqual(self.path.read_text(encoding='utf-8'), approved['new'])
        self.assertEqual((self.store.root / 'snapshots' / (approved['candidate_revision'] + '.md')).read_bytes(), self.path.read_bytes())
        self.assertEqual(self.store.baseline_path.read_bytes(), baseline)

    def test_missing_projection_and_legacy_store_migrate_from_canonical_content(self):
        proposal = self.proposal()
        self.review(proposal)
        self.path.unlink()  # Synthetic generated projection only.
        self.assertEqual(ProcedureStore(self.fixture.root).active()['current'], proposal['candidate_revision'])
        self.assertEqual(self.path.read_text(), proposal['new'])
        self.path.unlink()
        (self.store.root / 'learning.projection.json').unlink()
        reopened = ProcedureStore(self.fixture.root)
        self.assertEqual(reopened.active()['current'], proposal['candidate_revision'])
        self.assertEqual(self.path.read_text(), proposal['new'])

    def test_unknown_modification_and_unexpected_old_approved_content_fail_closed(self):
        old = self.path.read_bytes()
        self.review(self.proposal())
        expected = self.path.read_bytes()
        for value in (b'Unapproved synthetic text', old):
            self.path.write_bytes(value)
            with self.assertRaisesRegex(BusinessError, 'learning_markdown_modified'):
                ProcedureStore(self.fixture.root)
            self.assertEqual(self.path.read_bytes(), value)
            self.path.write_bytes(expected)

    def test_partial_projection_is_never_exposed_during_atomic_replace(self):
        proposal = self.proposal()
        old = self.path.read_bytes()
        original = os.replace
        observed = []
        def replace(source, target):
            if target == self.path:
                observed.append((self.path.read_bytes(), source.read_bytes()))
            return original(source, target)
        with patch('AutoCua.saccade.procedure_store.os.replace', side_effect=replace):
            self.review(proposal)
        self.assertEqual(observed, [(old, proposal['new'].encode())])
        self.assertEqual(self.path.read_text(), proposal['new'])

    def test_crash_before_pointer_swap_keeps_old_and_does_not_activate_orphan(self):
        before = self.store.active()
        proposal = self.proposal()
        original = self.store._write
        def fail(name, value, **kwargs):
            if name == 'active.json': raise OSError('Synthetic interruption before activation')
            return original(name, value, **kwargs)
        with patch.object(self.store, '_write', side_effect=fail):
            with self.assertRaises(OSError): self.review(proposal)
        self.assertEqual(ProcedureStore(self.fixture.root).active(), before)
        self.assertEqual(self.path.read_bytes(), self.store.baseline.encode())

    def test_crash_after_pointer_swap_recovers_recorded_stale_projection(self):
        proposal = self.proposal()
        old = self.path.read_bytes()
        original = self.store._write
        def fail(name, value, **kwargs):
            original(name, value, **kwargs)
            if name == 'active.json': raise OSError('Synthetic interruption after activation')
        with patch.object(self.store, '_write', side_effect=fail):
            with self.assertRaises(OSError): self.review(proposal)
        self.assertEqual(self.path.read_bytes(), old)
        self.assertEqual(ProcedureStore(self.fixture.root).active()['current'], proposal['candidate_revision'])
        self.assertEqual(self.path.read_text(), proposal['new'])

    def test_crash_after_markdown_swap_before_journal_settlement_recovers(self):
        proposal = self.proposal()
        original = self.store._write
        def fail(name, value, **kwargs):
            if name == 'learning.projection.json' and value['next'] is None and value['current']['current'] == proposal['candidate_revision']:
                raise OSError('Synthetic interruption before projection settlement')
            return original(name, value, **kwargs)
        with patch.object(self.store, '_write', side_effect=fail):
            with self.assertRaises(OSError): self.review(proposal)
        self.assertEqual(self.path.read_text(), proposal['new'])
        self.assertEqual(ProcedureStore(self.fixture.root).active()['current'], proposal['candidate_revision'])

    def test_pending_recovery_does_not_overwrite_unrecognized_text(self):
        proposal = self.proposal()
        original = self.store._publish
        def fail(name, value, **kwargs):
            if name == 'learning.md': raise OSError('Synthetic projection interruption')
            return original(name, value, **kwargs)
        with patch.object(self.store, '_publish', side_effect=fail):
            with self.assertRaises(OSError): self.review(proposal)
        self.path.write_text('Unexpected operator modification', encoding='utf-8')
        with self.assertRaisesRegex(BusinessError, 'learning_markdown_modified'): ProcedureStore(self.fixture.root)

    def test_rollback_refreshes_stable_document_without_switching_old_pin(self):
        old = self.store.pin('existing-chat')
        proposal = self.proposal()
        current = self.review(proposal)
        self.assertEqual(self.store.pin('existing-chat'), old)
        self.assertEqual(self.store.pin('new-chat'), current['current'])
        later = DextRunControl(self.fixture.context, 'later-chat', project_root=self.fixture.root)
        self.addCleanup(later.close)
        self.assertIn(proposal['new'], later.overlay())
        rolled = self.store.rollback(current['current'], old, 'reviewed-rollback')
        self.assertEqual(self.path.read_bytes(), self.store.snapshot(rolled['current'])['content'].encode())
        self.assertIn(proposal['new'], later.overlay())
        self.assertEqual(self.store.pin('existing-chat'), old)

    def test_unsafe_projection_and_journal_symlinks_fail_closed(self):
        target = self.fixture.root / 'synthetic-target'
        target.write_bytes(b'')
        for path in (self.path, self.store.root / 'learning.projection.json'):
            before = path.read_bytes()
            path.unlink()
            try:
                path.symlink_to(target)
            except OSError:
                path.write_bytes(before)
                self.skipTest('Windows symlink privilege is unavailable.')
            try:
                with self.assertRaises(BusinessError): ProcedureStore(self.fixture.root)
            finally:
                path.unlink()
                path.write_bytes(before)

    def test_directory_projection_and_invalid_recovery_marker_fail_closed(self):
        original = self.path.read_bytes()
        self.path.unlink()
        self.path.mkdir()
        with self.assertRaises(BusinessError): ProcedureStore(self.fixture.root)
        self.path.rmdir()
        self.path.write_bytes(original)
        (self.store.root / 'learning.projection.json').write_text('{}')
        with self.assertRaisesRegex(BusinessError, 'projection_corrupt'): ProcedureStore(self.fixture.root)

    def test_stable_learning_and_journal_remain_git_private(self):
        repository = Path(__file__).resolve().parents[1]
        paths = ['platforms/dext/data/navigation/learning.md', 'platforms/dext/data/navigation/learning.projection.json']
        result = subprocess.run(['git', '-c', 'safe.directory=' + repository.as_posix(), 'check-ignore', '--no-index', *paths],
            cwd=repository, capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines(), paths)


if __name__ == '__main__': unittest.main()
