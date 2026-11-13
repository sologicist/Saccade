"""Exercise the real PyO3 entry without launching a model or browser.

Set SACCADE_TEST_NATIVE to a freshly built agent_native extension artifact.
Each case uses an isolated interpreter and repository-local synthetic files so
native directory caches and profile ownership cannot affect a real session.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from AutoCua.saccade.session_context import build_platform_context


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
NATIVE_PATH = os.environ.get("SACCADE_TEST_NATIVE")
TEST_TEMP_ROOT = REPOSITORY_ROOT / ".cache" / "platform-session-native-tests"


_NATIVE_WORKER = r"""
import importlib.machinery
import importlib.util
import json
import os
import sys
import types
from pathlib import Path
from unittest.mock import Mock, patch

source_root = Path(sys.argv[1]).resolve()
native_path = Path(sys.argv[2]).resolve()
fixture_root = Path(sys.argv[3]).resolve()
sys.path.insert(0, str(source_root))
os.environ["AutoCua_DATA_DIR"] = str(fixture_root / "local-data")
os.environ["AutoCua_WEB_DIR"] = str(fixture_root / "native-web")
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

from AutoCua.saccade import profile_lease, session_context
from AutoCua.saccade.platform_config import load_platform

name = "AutoCua.web.agent_native"
loader = importlib.machinery.ExtensionFileLoader(name, str(native_path))
spec = importlib.util.spec_from_file_location(name, native_path, loader=loader)
native = importlib.util.module_from_spec(spec)
sys.modules[name] = native
loader.exec_module(native)
assert Path(native.__file__).resolve() == native_path

class DeliberateStartupFailure(RuntimeError):
    pass

# This is the existing shared Python provider boundary called by Rust. Failing
# here proves constructor unwind releases ownership before any Chrome startup.
llm = types.ModuleType("AutoCua.llm_provider.llm_manager")
llm.resolve_model_info = Mock(side_effect=DeliberateStartupFailure("Synthetic LLM startup failure."))
request = json.loads(sys.stdin.read())
kwargs = request["kwargs"]
profile = kwargs.get("browser_profile")
held = None
result = {}
with patch.object(session_context, "load_platform", side_effect=lambda platform_id, root=None: load_platform(platform_id, root=fixture_root)), \
     patch.object(session_context, "_registered_vision_model", return_value=True), \
     patch.dict(sys.modules, {llm.__name__: llm}):
    if request.get("learning"):
        from AutoCua.saccade.platform_learning import PlatformLearningControl
        selected = kwargs['platform_context']
        if request['learning'] == 'foreign':
            selected = session_context.build_platform_context('dext', root=fixture_root)
        kwargs['learning_control'] = PlatformLearningControl(selected, 'native-test-chat', project_root=fixture_root)
    if request.get("hold") or request.get("borrow"):
        held = profile_lease.acquire_web_profile(profile)
    if request.get("borrow"):
        kwargs["profile_lease"] = held
    if request.get("forged_lease"):
        kwargs["profile_lease"] = {"profile": profile, "owner": "untrusted"}
    try:
        native.AgentService(**kwargs)
    except Exception as error:
        result["error"] = type(error).__name__
        result["message"] = str(error)
    else:
        raise AssertionError("Synthetic native construction unexpectedly passed the LLM stop boundary.")
    result["llm_calls"] = llm.resolve_model_info.call_count
    result["borrowed_active"] = False
    if held is not None:
        result["borrowed_active"] = profile_lease.validate_web_profile_lease(held, profile) is held
    try:
        available = profile_lease.acquire_web_profile(profile)
    except profile_lease.ProfileBusyError:
        result["profile_available"] = False
    else:
        result["profile_available"] = True
        available.release()
    if held is not None:
        held.release()
print(json.dumps(result))
"""


@unittest.skipUnless(NATIVE_PATH, "Set SACCADE_TEST_NATIVE to verify the actual PyO3 entry.")
class NativePlatformEntryContracts(unittest.TestCase):
    """Validate authority and lease behavior through the compiled constructor."""

    def setUp(self):
        self.native_path = Path(NATIVE_PATH).resolve()
        self.assertTrue(self.native_path.is_file(), "The native extension artifact does not exist.")
        TEST_TEMP_ROOT.mkdir(parents=True, exist_ok=True)
        temporary = tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT)
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        domain = self.root / "AutoCua/default_skills/web/domain_skill"
        domain.mkdir(parents=True)
        (domain / "skills.json").write_text('{"app.dext.com":"dext.md"}', encoding="utf-8")
        (domain / "dext.md").write_bytes(b"")
        config = {
            "schema_version": 1, "id": "dext", "name": "Synthetic Dext",
            "engine": "web", "start_url": "https://app.dext.com/login",
            "allowed_hosts": ["app.dext.com"], "browser": "chrome", "max_steps": 45,
        }
        platform_dir = self.root / "platforms/dext"
        platform_dir.mkdir(parents=True)
        (platform_dir / "platform.json").write_text(json.dumps(config), encoding="utf-8")
        self.context = build_platform_context("dext", root=self.root)

    def invoke(self, *, context=True, hold=False, borrow=False, forged_lease=False, learning=None, **changes):
        kwargs = {
            "provider": "openai", "model": "synthetic", "speed": "quality",
            "browser_profile": "saccade-dext", "platform_context": self.context if context else None,
        }
        kwargs.update(changes)
        result = subprocess.run(
            [sys.executable, "-I", "-c", _NATIVE_WORKER, str(REPOSITORY_ROOT), str(self.native_path), str(self.root)],
            input=json.dumps({"kwargs": kwargs, "hold": hold, "borrow": borrow, "forged_lease": forged_lease, "learning": learning}),
            capture_output=True, text=True, cwd=self.root, timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return json.loads(result.stdout)

    def test_forged_context_is_rejected_before_model_or_browser_startup(self):
        for change in (
            {"platform_id": "unknown"}, {"allowed_hosts": ["evil.test"]},
            {"config_revision": "0" * 64}, {"allow_all": True}, {"schema_version": True},
        ):
            with self.subTest(change=change):
                result = self.invoke(platform_context=dict(self.context, **change))
                self.assertIn(result["error"], ("SessionContextError", "SessionConflictError"))
                self.assertEqual(result["llm_calls"], 0)
                self.assertTrue(result["profile_available"])

    def test_scoped_settings_are_checked_at_the_real_native_entry(self):
        for change in (
            {"headless": True}, {"speed": "fast"}, {"browser_profile": "other"},
            {"single_tab": True}, {"session_id": "parallel-child"}, {"browser_port": 9222},
        ):
            with self.subTest(change=change):
                result = self.invoke(**change)
                self.assertIn(result["error"], ("SessionContextError", "ValueError"))
                self.assertEqual(result["llm_calls"], 0)
                self.assertTrue(result["profile_available"])

    def test_existing_profile_owner_blocks_a_direct_native_generic_run(self):
        result = self.invoke(context=False, hold=True)
        self.assertEqual(result["error"], "ProfileBusyError")
        self.assertEqual(result["llm_calls"], 0)
        self.assertFalse(result["profile_available"])
        self.assertTrue(result["borrowed_active"])

    def test_forged_borrowed_lease_is_rejected_before_startup(self):
        result = self.invoke(forged_lease=True)
        self.assertEqual(result["error"], "ValueError")
        self.assertEqual(result["llm_calls"], 0)
        self.assertTrue(result["profile_available"])

    def test_owned_lease_is_released_when_native_model_startup_fails(self):
        result = self.invoke()
        self.assertEqual(result["error"], "DeliberateStartupFailure")
        self.assertEqual(result["llm_calls"], 1)
        self.assertTrue(result["profile_available"])

    def test_correction_restart_requires_scoped_paired_history_before_startup(self):
        for changes in ({}, {'prior_history': {'assistant_messages': ['step'], 'tool_responses': []}},
                        {'context': False, 'prior_history': {'assistant_messages': ['step'], 'tool_responses': ['result']}}):
            with self.subTest(changes=changes):
                result = self.invoke(correction_reopen=True, **changes)
                self.assertEqual(result['error'], 'ValueError')
                self.assertEqual(result['llm_calls'], 0)
                self.assertTrue(result['profile_available'])

    def test_confirmed_correction_restart_does_not_bypass_profile_ownership(self):
        history = {'assistant_messages': ['step'], 'tool_responses': ['result']}
        held = self.invoke(correction_reopen=True, prior_history=history, hold=True)
        self.assertEqual(held['error'], 'ProfileBusyError')
        self.assertEqual(held['llm_calls'], 0)
        valid = self.invoke(correction_reopen=True, prior_history=history)
        self.assertEqual(valid['error'], 'DeliberateStartupFailure')
        self.assertEqual(valid['llm_calls'], 1)

    def test_second_platform_control_is_checked_before_model_or_browser_startup(self):
        from tests.platform_learning_fixtures import install_synthetic
        context = install_synthetic(self.root)
        changes = {'platform_context': context, 'browser_profile': context['browser_profile']}
        foreign = self.invoke(learning='foreign', **changes)
        self.assertEqual(foreign['error'], 'BusinessError')
        self.assertEqual(foreign['llm_calls'], 0)
        self.assertTrue(foreign['profile_available'])
        valid = self.invoke(learning='valid', **changes)
        self.assertEqual(valid['error'], 'DeliberateStartupFailure')
        self.assertEqual(valid['llm_calls'], 1)
        self.assertTrue(valid['profile_available'])

    def test_forged_learning_control_is_not_accepted_as_native_authority(self):
        result = self.invoke(learning_control={'platform_id': 'dext', 'approved': True})
        self.assertEqual(result['error'], 'BusinessError')
        self.assertEqual(result['llm_calls'], 0)
        self.assertTrue(result['profile_available'])

    def test_borrowed_lease_remains_owned_by_its_caller_after_startup_failure(self):
        result = self.invoke(borrow=True)
        self.assertEqual(result["error"], "DeliberateStartupFailure")
        self.assertEqual(result["llm_calls"], 1)
        self.assertTrue(result["borrowed_active"])
        self.assertFalse(result["profile_available"])


if __name__ == "__main__":
    unittest.main()
