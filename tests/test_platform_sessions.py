"""Synthetic platform session, persistence, profile ownership and API contracts."""

from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys
import tempfile
import threading
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from AutoCua.agent_conversation.service import ConversationService
from AutoCua.saccade import profile_lease, session_context
from AutoCua.saccade.platform_config import load_platform


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
TEST_TEMP_ROOT = REPOSITORY_ROOT / ".cache" / "platform-session-python-tests"


class SyntheticConversation(ConversationService):
    def __init__(self, root):
        self.synthetic_root = root
        self.next_id = 0

    def root(self):
        self.synthetic_root.mkdir(parents=True, exist_ok=True)
        return self.synthetic_root

    def _new_id(self):
        self.next_id += 1
        return f"chat_synthetic_{self.next_id}"


class SessionFixtures(unittest.TestCase):
    def setUp(self):
        TEST_TEMP_ROOT.mkdir(parents=True, exist_ok=True)
        temporary = tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT)
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.domain = self.root / "AutoCua/default_skills/web/domain_skill"
        self.domain.mkdir(parents=True)
        (self.domain / "skills.json").write_text(
            json.dumps({"app.dext.com": "dext.md"}), encoding="utf-8"
        )
        (self.domain / "dext.md").write_bytes(b"")
        self.config = {
            "schema_version": 1, "id": "dext", "name": "Synthetic Dext",
            "engine": "web", "start_url": "https://app.dext.com/login",
            "allowed_hosts": ["app.dext.com"], "browser": "chrome", "max_steps": 45,
        }
        self.config_path = self.root / "platforms/dext/platform.json"
        self.config_path.parent.mkdir(parents=True)
        self.write_config()
        platform_patch = patch.object(
            session_context, "load_platform", lambda platform_id, root=None: load_platform(platform_id, root=self.root)
        )
        platform_patch.start()
        self.addCleanup(platform_patch.stop)
        environment = patch.dict(os.environ, {"AutoCua_DATA_DIR": str(self.root / "local-data")})
        environment.start()
        self.addCleanup(environment.stop)
        self.conversation = SyntheticConversation(self.root / "chats")

    def write_config(self):
        self.config_path.write_text(json.dumps(self.config), encoding="utf-8")

    def context(self, mode="supervised"):
        return session_context.build_platform_context("dext", mode)

    def acquire(self, name):
        lease = profile_lease.acquire_web_profile(name)
        self.addCleanup(lease.release)
        return lease


class PlatformSessionContracts(SessionFixtures):
    def test_valid_empty_platform_defaults_to_supervised(self):
        context = session_context.resolve_platform_context({"platform_id": "dext"})
        self.assertEqual(context["execution_mode"], "supervised")
        self.assertEqual(context["browser_profile"], "saccade-dext")
        self.assertEqual(context["allowed_hosts"], ["app.dext.com"])
        self.assertEqual(len(context["config_revision"]), 64)
        self.assertEqual((self.domain / "dext.md").read_bytes(), b"")

    def test_unknown_and_malformed_platform_ids_are_rejected(self):
        for platform_id in ("unknown", "../dext", "Dext", ["dext"], True, 1):
            with self.subTest(platform_id=platform_id), self.assertRaises(session_context.SessionContextError):
                session_context.resolve_platform_context({"platform_id": platform_id})

    def test_generic_context_is_distinct_and_auto_requires_explicit_selection(self):
        self.assertIsNone(session_context.resolve_platform_context({}))
        self.assertIsNone(session_context.resolve_platform_context({"platform_id": None}))
        self.assertEqual(session_context.resolve_platform_context(
            {"platform_id": "dext", "execution_mode": "auto"})["execution_mode"], "auto")
        for request in ({"execution_mode": "auto"}, {"platform_id": "dext", "execution_mode": True}):
            with self.assertRaises(session_context.SessionContextError):
                session_context.resolve_platform_context(request)

    def test_resume_preserves_binding_and_rejects_platform_or_mode_changes(self):
        original = self.context()
        self.assertEqual(session_context.resolve_platform_context({}, saved_context=original), original)
        for request in ({"platform_id": None}, {"platform_id": "other"}, {"execution_mode": "auto"}):
            with self.assertRaises(session_context.SessionConflictError):
                session_context.resolve_platform_context(request, saved_context=original)
        with self.assertRaises(session_context.SessionConflictError):
            session_context.resolve_platform_context({"platform_id": "dext"}, saved_context=None)

    def test_changed_config_requires_operator_review_in_new_chat(self):
        original = self.context()
        self.config["max_steps"] = 46
        self.write_config()
        with self.assertRaises(session_context.SessionConflictError):
            session_context.resolve_platform_context({}, saved_context=original)

    def test_native_context_rejects_forged_hosts_unknown_fields_and_schema_types(self):
        for change in ({"allowed_hosts": ["evil.test"]}, {"extra": True},
                       {"schema_version": True}, {"max_steps": True}):
            with self.subTest(change=change), self.assertRaises(session_context.SessionContextError):
                session_context.validate_native_context(
                    dict(self.context(), **change), "openai", "synthetic", "quality", False, "saccade-dext"
                )

    def test_scoped_settings_require_visible_quality_known_vision_and_dedicated_profile(self):
        context = self.context()
        with patch.object(session_context, "_registered_vision_model", return_value=True):
            session_context.validate_session_settings(context, "p", "m", "quality", False, "saccade-dext")
            for speed, headless, profile in (("fast", False, "saccade-dext"),
                                             ("quality", True, "saccade-dext"),
                                             ("quality", 0, "saccade-dext"),
                                             ("quality", False, "other")):
                with self.subTest(speed=speed, headless=headless, profile=profile):
                    with self.assertRaises(session_context.SessionContextError):
                        session_context.validate_session_settings(context, "p", "m", speed, headless, profile)
        with patch.object(session_context, "_registered_vision_model", return_value=False):
            with self.assertRaises(session_context.SessionContextError):
                session_context.validate_session_settings(context, "p", "m", "quality", False, "saccade-dext")
        session_context.validate_session_settings(None, "custom", "custom", "fast", True, None)

    def test_unknown_model_fallback_never_grants_image_capability(self):
        view = types.SimpleNamespace(MODEL_MAPPINGS={"known": {"vision": True}, "text": {"vision": False}})
        with patch.object(session_context.importlib, "import_module", return_value=view):
            self.assertTrue(session_context._registered_vision_model("openai", "known"))
            self.assertFalse(session_context._registered_vision_model("openai", "text"))
            self.assertFalse(session_context._registered_vision_model("openai", "unknown"))
            self.assertFalse(session_context._registered_vision_model("unknown", "known"))

    def test_context_persists_independently_of_history_and_resumes_safely(self):
        sid, _ = self.conversation.start_or_resume("new", "Synthetic request", agent_mode="web")
        self.conversation.bind_platform_context(sid, self.context())
        self.conversation.save_run(sid, ["Synthetic step"], ["Synthetic result"], "success", "Done", "Synthetic request", run_pkg="web", agent_mode="web")
        resumed, history = self.conversation.start_or_resume(sid, "Continue", agent_mode="web")
        self.assertEqual(resumed, sid)
        self.assertIn("Synthetic step", history["assistant_messages"])
        self.assertEqual(self.conversation.get_session(sid)["platform_context"], self.context())
        self.assertEqual(self.conversation.list_sessions()[0]["platform_context"], self.context())
        with self.assertRaises(session_context.SessionConflictError):
            self.conversation.bind_platform_context(sid, None)

    def test_generic_binding_and_corrupt_binding_never_become_scoped_or_unrestricted(self):
        sid, _ = self.conversation.start_or_resume("new", "Synthetic generic", agent_mode="web")
        self.conversation.bind_platform_context(sid, None)
        self.assertEqual(self.conversation.get_platform_binding(sid), (True, None))
        with self.assertRaises(session_context.SessionConflictError):
            self.conversation.bind_platform_context(sid, self.context())
        path = self.conversation._session_dir(sid) / "platform_session.json"
        path.write_text('{"schema_version":2,"platform_context":null}', encoding="utf-8")
        with self.assertRaises(session_context.SessionContextError):
            self.conversation.get_session(sid)
        self.assertIn("platform_context_error", self.conversation.list_sessions()[0])

    def test_missing_binding_cannot_downgrade_a_saved_scoped_chat(self):
        sid, _ = self.conversation.start_or_resume("new", "Synthetic request", agent_mode="web")
        self.conversation.bind_platform_context(sid, self.context())
        self.conversation.save_run(sid, [], [], "incomplete", "Paused", "Synthetic request", run_pkg="web", agent_mode="web")
        (self.conversation._session_dir(sid) / "platform_session.json").unlink()
        with self.assertRaises(session_context.SessionConflictError):
            self.conversation.get_platform_binding(sid)
        with self.assertRaises(session_context.SessionConflictError):
            self.conversation.get_session(sid)
        # Even if the expendable sidebar index is lost, saved history keeps the
        # binding marker and cannot be replayed with an unrestricted context.
        self.conversation._index_file().unlink()
        with self.assertRaises(session_context.SessionConflictError):
            self.conversation.get_platform_binding(sid)


class ProfileOwnershipContracts(SessionFixtures):
    def test_same_profile_conflicts_but_other_profiles_can_be_reserved(self):
        held = self.acquire("saccade-dext")
        with self.assertRaises(profile_lease.ProfileBusyError):
            self.acquire("saccade-dext")
        self.acquire("synthetic-other")
        self.assertIs(profile_lease.validate_web_profile_lease(held, "saccade-dext"), held)
        with self.assertRaises(ValueError):
            profile_lease.validate_web_profile_lease(held, "synthetic-other")
        with self.assertRaises(ValueError):
            profile_lease.validate_web_profile_lease({"token": "forged"}, "saccade-dext")

    def test_release_is_idempotent_and_reacquire_never_steals_another_owner(self):
        held = self.acquire("saccade-dext")
        held.release()
        held.release()
        other = self.acquire("saccade-dext")
        with self.assertRaises(profile_lease.ProfileBusyError):
            held.ensure_held()
        other.release()
        held.ensure_held()
        self.assertIs(profile_lease.validate_web_profile_lease(held, "saccade-dext"), held)

    def test_os_lock_conflicts_across_processes_and_is_released_after_process_exit(self):
        code = """
import os, sys
sys.path.insert(0, sys.argv[1])
from AutoCua.saccade.profile_lease import acquire_web_profile
held = acquire_web_profile("saccade-dext")
print("ready", flush=True)
sys.stdin.readline()
os._exit(0)
"""
        process = subprocess.Popen(
            [sys.executable, "-I", "-c", code, str(REPOSITORY_ROOT)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, cwd=self.root, env=os.environ.copy(),
        )
        try:
            self.assertEqual(process.stdout.readline().strip(), "ready")
            with self.assertRaises(profile_lease.ProfileBusyError):
                self.acquire("saccade-dext")
            process.communicate("exit\n", timeout=15)
            self.assertEqual(process.returncode, 0)
            self.acquire("saccade-dext")
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate(timeout=15)


class LauncherProfileContracts(unittest.TestCase):
    def test_parallel_web_is_rejected_before_chrome_or_native_startup(self):
        from AutoCua import agent_launcher
        with patch("AutoCua.utils.chrome.ensure_chrome") as chrome:
            with patch.object(agent_launcher, "resolve_agent_service") as native:
                with self.assertRaisesRegex(ValueError, "one Chrome profile"):
                    agent_launcher.run_agent("web", "openai", "synthetic", "one", extra_tasks=["two"])
                with self.assertRaisesRegex(ValueError, "one Chrome profile"):
                    agent_launcher.run_parallel_web_agents(["one", "two"], "openai", "synthetic")
                chrome.assert_not_called()
                native.assert_not_called()


class PlatformSessionAPI(SessionFixtures):
    def setUp(self):
        super().setUp()
        try:
            import flask  # noqa: F401
            import PIL  # noqa: F401
        except ImportError:
            self.skipTest("Flask and Pillow are required for actual UI route tests.")
        # Keep the broker in the module-map snapshot: restoring the temporary
        # webview stub must not evict it and create a second test-only singleton.
        import AutoCua.saccade.operator_requests  # noqa: F401
        with patch.dict(sys.modules, {"webview": types.ModuleType("webview")}):
            self.service = importlib.import_module("AutoCua.ui.service")
        self.release = threading.Event()
        self.release.set()
        self.started = threading.Event()
        self.created = []
        self.outcomes = []
        self.fail_reattachment = False
        self.fail_runtime = False
        self.fail_cleanup = False
        self.scan = None
        self.provider_calls = 0
        self.handoff_available = True
        test = self

        class FakeWebAgent:
            def __init__(self, **kwargs):
                if test.fail_reattachment and kwargs.get('operator_session'):
                    raise ValueError('operator_resume:chrome_pipe_disconnected')
                self.kwargs = kwargs
                self.closed = False
                self.operator_resume_observed = False
                self.assistant_messages = ["Synthetic step"]
                self.tool_responses = ["Synthetic result"]
                test.created.append(self)

            def process_request(self, task):
                self.task = task
                test.started.set()
                if not test.release.wait(10):
                    raise RuntimeError("Synthetic test release timed out.")
                if getattr(self.kwargs['stop_event'], 'operator_pause', False):
                    return {'status': 'waiting_operator', 'message': json.dumps({'category': 'question',
                        'reason': 'missing_information', 'request': 'Navigation is paused for correction.'})}
                if test.fail_runtime:
                    raise RuntimeError('PRIVATE SYNTHETIC https://example.test/?token=not-for-logs')
                self.operator_resume_observed = True
                control = self.kwargs.get('learning_control')
                if test.scan is not None and control:
                    control.freeze_decision()
                    control.observe_native(test.scan, {'observer': 'synthetic-observer', 'tab': '1',
                        'platform_id': control.context['platform_id'], 'profile': control.context['browser_profile'], 'config_revision': control.context['config_revision']})
                    intervention = control.learning_intervention()
                    if intervention:
                        return {'status': 'waiting_operator', 'message': json.dumps(intervention)}
                test.provider_calls += 1
                return test.outcomes.pop(0) if test.outcomes else {"status": "success", "message": "Synthetic completion"}

            def close_operator_session(self):
                if test.fail_cleanup:
                    raise RuntimeError('Synthetic ownership release is unverified.')
                self.closed = True

            @property
            def operator_handoff_available(self):
                return test.handoff_available

        original_import = importlib.import_module

        def import_agent(name, *args, **kwargs):
            if name == "AutoCua.web.agent":
                return types.SimpleNamespace(AgentService=FakeWebAgent)
            return original_import(name, *args, **kwargs)

        from AutoCua.saccade import platform_registry
        operator_module = original_import("AutoCua.saccade.operator_requests")
        isolated_broker = operator_module.OperatorRequests()
        patches = (
            patch.object(operator_module, "operator_requests", isolated_broker),
            patch.object(self.service, "operator_requests", isolated_broker),
            patch.object(self.service, "conversation", self.conversation),
            patch.object(self.service, "_run_thread", None),
            patch.object(self.service, "active_agent_session_id", None),
            patch.object(self.service, "webview_window", None),
            patch.object(self.service, "get_provider_api_key", return_value="synthetic"),
            patch.object(self.service, "get_platform_path", side_effect=lambda pkg=None: self.root / "runtime" / (pkg or "web")),
            patch.object(self.service, "_reset_todo_file"),
            patch.object(self.service, "_reset_scratchpad_file"),
            patch.object(self.service, "raise_app_window"),
            patch.object(self.service.agent_glow, "stop"),
            patch.object(session_context, "_registered_vision_model", return_value=True),
            patch.object(platform_registry, "PROJECT_ROOT", self.root),
            patch.object(self.service.importlib, "import_module", side_effect=import_agent),
            patch("AutoCua.utils.chrome.ensure_chrome", return_value=Path("synthetic-chrome")),
        )
        for mocked in patches:
            mocked.start()
            self.addCleanup(mocked.stop)
        self.addCleanup(self.finish_run)
        self.client = self.service.app.test_client()
        self.base_url = f"http://127.0.0.1:{self.service._app_port}"
        self.headers = {self.service._TOKEN_HEADER: self.service._API_TOKEN}

    def finish_run(self):
        self.release.set()
        thread = self.service._run_thread
        if thread is not None:
            thread.join(timeout=15)
            self.assertFalse(thread.is_alive())

    def post(self, **changes):
        data = {"provider": "openai", "model": "synthetic", "task": "Synthetic request", "mode": "web", "speed": "quality", "session_id": "new"}
        data.update(changes)
        return self.client.post("/api/start-agent", json=data, headers=self.headers, base_url=self.base_url)

    def test_registry_endpoint_returns_dynamic_validated_metadata(self):
        response = self.client.get("/api/platforms", headers=self.headers, base_url=self.base_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["platforms"][0]["name"], "Synthetic Dext")
        self.assertNotIn("procedure", response.json["platforms"][0])

    def test_valid_selection_binds_launch_and_restores_context(self):
        response = self.post(platform_id="dext")
        self.assertEqual(response.status_code, 200, response.json)
        self.finish_run()
        self.assertEqual(response.json["platform_context"], self.context())
        self.assertEqual(self.created[0].kwargs["browser_profile"], "saccade-dext")
        self.assertEqual(self.created[0].kwargs["platform_context"], self.context())
        sid = response.json["session_id"]
        reopened = self.client.get(f"/api/chats/{sid}", headers=self.headers, base_url=self.base_url)
        self.assertEqual(reopened.status_code, 200, reopened.json)
        self.assertEqual(reopened.json["platform_context"], self.context())
        resumed = self.post(session_id=sid)
        self.assertEqual(resumed.status_code, 200, resumed.json)
        self.finish_run()
        self.assertEqual(resumed.json["platform_context"], self.context())
        self.assertIsNotNone(self.created[-1].kwargs["prior_history"])

    def test_generic_mode_remains_available_and_explicit_switch_is_rejected(self):
        response = self.post()
        self.assertEqual(response.status_code, 200, response.json)
        self.finish_run()
        self.assertIsNone(response.json["platform_context"])
        changed = self.post(session_id=response.json["session_id"], platform_id="dext")
        self.assertEqual(changed.status_code, 409, changed.json)

    def test_invalid_selection_and_unsupported_settings_are_rejected_before_agent_creation(self):
        for changes in ({"platform_id": "unknown"}, {"platform_id": "../dext"},
                        {"platform_id": ["dext"]}, {"platform_id": "dext", "mode": "computer"},
                        {"platform_id": "dext", "speed": "fast"},
                        {"platform_id": "dext", "headless": True},
                        {"platform_id": "dext", "browser_profile": "other"},
                        {"platform_id": "dext", "browser_port": 9222}):
            with self.subTest(changes=changes):
                response = self.post(**changes)
                self.assertEqual(response.status_code, 400, response.json)
                self.assertIn("error", response.json)
        self.assertEqual(self.created, [])

    def test_concurrent_start_returns_busy_without_replacing_the_first_run(self):
        self.release.clear()
        first = self.post(platform_id="dext")
        self.assertEqual(first.status_code, 200, first.json)
        self.assertTrue(self.started.wait(5))
        run_id = self.service.active_agent_session_id
        stop_event = self.service.active_agent_stop_event
        second = self.post(platform_id="dext")
        self.assertEqual(second.status_code, 409, second.json)
        self.assertIn("busy", second.json["error"])
        self.assertEqual(self.service.active_agent_session_id, run_id)
        self.assertIs(self.service.active_agent_stop_event, stop_event)
        self.assertEqual(len(self.created), 1)

    def test_corrupt_persisted_scope_returns_error_instead_of_generic_resume(self):
        response = self.post(platform_id="dext")
        self.finish_run()
        sid = response.json["session_id"]
        (self.conversation._session_dir(sid) / "platform_session.json").write_text("{}", encoding="utf-8")
        reopened = self.client.get(f"/api/chats/{sid}", headers=self.headers, base_url=self.base_url)
        self.assertEqual(reopened.status_code, 409, reopened.json)
        resumed = self.post(session_id=sid)
        self.assertEqual(resumed.status_code, 409, resumed.json)

    def test_missing_persisted_scope_requires_operator_review(self):
        response = self.post(platform_id="dext")
        self.finish_run()
        sid = response.json["session_id"]
        (self.conversation._session_dir(sid) / "platform_session.json").unlink()
        reopened = self.client.get(f"/api/chats/{sid}", headers=self.headers, base_url=self.base_url)
        self.assertEqual(reopened.status_code, 409, reopened.json)
        resumed = self.post(session_id=sid)
        self.assertEqual(resumed.status_code, 409, resumed.json)

    def test_another_profile_cannot_replace_an_active_ui_run(self):
        self.release.clear()
        first = self.post(platform_id="dext")
        self.assertEqual(first.status_code, 200, first.json)
        self.assertTrue(self.started.wait(5))
        run_id = self.service.active_agent_session_id
        second = self.post(browser_profile="synthetic-other-profile")
        self.assertEqual(second.status_code, 409, second.json)
        self.assertEqual(self.service.active_agent_session_id, run_id)
        self.assertEqual(len(self.created), 1)

    def test_dext_operator_route_is_authenticated_origin_bound_and_chat_bound(self):
        response = self.post(platform_id="dext")
        self.finish_run()
        sid = response.json["session_id"]
        url = f"/api/dext/control?session_id={sid}"
        self.assertEqual(self.client.get(url, base_url=self.base_url).status_code, 403)
        self.assertEqual(self.client.get("/api/dext/control?session_id=other", headers=self.headers, base_url=self.base_url).status_code, 409)
        status = self.client.get(url, headers=self.headers, base_url=self.base_url)
        self.assertEqual(status.status_code, 200, status.json)
        self.assertEqual(status.headers['Cache-Control'], 'no-store')
        self.assertIs(self.created[0].kwargs["dext_control"], self.service._dext_control)
        body = {"event": "teach", "review_token": status.json["review_token"], "routes": ["workspace", "invoices", "record"]}
        for origin in (None, "https://app.dext.com", "https://evil.test"):
            headers = {**self.headers, **({"Origin": origin} if origin else {})}
            self.assertEqual(self.client.post(url, json=body, headers=headers, base_url=self.base_url).status_code, 403)
        headers = {**self.headers, "Origin": self.base_url}
        wrong = self.client.post(url, json={**body, "review_token": "yes"}, headers=headers, base_url=self.base_url)
        self.assertEqual(wrong.status_code, 409)
        self.assertEqual(self.client.post(url, json=body, headers=headers, base_url=self.base_url).status_code, 200)
        preview = self.client.get(url, headers=self.headers, base_url=self.base_url).json
        proposal = preview["proposal"]
        review = {"event": "review", "review_token": status.json["review_token"], "approve": True,
                  **{key: proposal[key] for key in ("proposal_id", "base_revision", "candidate_revision")}}
        self.assertEqual(self.client.post(url, json=review, headers=headers, base_url=self.base_url).status_code, 200)
        active = self.client.get(url, headers=self.headers, base_url=self.base_url).json
        self.assertNotEqual(active["active"]["current"], active["pinned_revision"])
        self.assertEqual(self.client.post(url, json=review, headers=headers, base_url=self.base_url).status_code, 409)

    def test_local_chat_correction_uses_review_channel_without_starting_a_model_run(self):
        response = self.post(platform_id="dext")
        self.finish_run()
        sid = response.json["session_id"]
        url = f"/api/dext/control?session_id={sid}"
        status = self.client.get(url, headers=self.headers, base_url=self.base_url).json
        headers = {**self.headers, "Origin": self.base_url}
        raw = "Open invoices then confirm the workspace then select the record."
        body = {"event": "teach_correction", "review_token": status["review_token"], "correction": raw}
        result = self.client.post(url, json=body, headers=headers, base_url=self.base_url)
        self.assertEqual(result.status_code, 200, result.json)
        self.assertEqual(len(self.created), 1)
        preview = self.client.get(url, headers=self.headers, base_url=self.base_url).json
        self.assertEqual(preview["proposal"]["teaching_source"], "operator_chat_correction")
        self.assertNotIn(raw, json.dumps(preview))
        self.assertEqual(preview["active"], status["active"])
        forged = self.client.post(url, json={**body, "approve": True}, headers=headers, base_url=self.base_url)
        self.assertEqual(forged.status_code, 409)

    def test_generic_operator_resume_reuses_chat_and_revalidates_launcher(self):
        from AutoCua.saccade.operator_requests import operator_requests
        sid, _, _ = self.pause_browser()
        data = {'provider':'openai','model':'synthetic','mode':'web','speed':'quality','platform_id':'dext','task':'Original synthetic objective'}
        operator_requests.suspend(sid, 'originating-run', data, {'category':'question','reason':'missing_information','request':'Which invented option?'})
        url = '/api/operator?session_id=' + sid
        status = self.client.get(url, headers=self.headers, base_url=self.base_url)
        self.assertEqual(status.headers['Cache-Control'], 'no-store')
        self.assertEqual(len(self.created), 1)
        event = {**{k:status.json[k] for k in ('run_id','intervention_id','revision','token')},'action':'resume','answer':'Option A','non_sensitive':True}
        self.assertEqual(self.client.post(url,json=event,headers=self.headers,base_url=self.base_url).status_code,403)
        headers = {**self.headers,'Origin':self.base_url}
        self.assertEqual(self.client.post(url,json={**event,'token':'foreign'},headers=headers,base_url=self.base_url).status_code,409)
        resumed = self.client.post(url,json=event,headers=headers,base_url=self.base_url)
        self.assertEqual(resumed.status_code,200,resumed.json)
        self.finish_run()
        self.assertEqual(resumed.json['session_id'],sid)
        self.assertIsNotNone(self.created[-1].kwargs['prior_history'])
        self.assertEqual(self.created[-1].kwargs['browser_profile'],'saccade-dext')
        self.assertEqual(self.client.post(url,json=event,headers=headers,base_url=self.base_url).status_code,409)

    def pause_browser(self):
        from AutoCua.saccade.operator_requests import operator_requests
        self.outcomes.append({'status': 'waiting_operator', 'message': json.dumps({
            'category': 'authentication', 'reason': 'authentication_required',
            'request': 'Complete private authentication.'})})
        response = self.post(platform_id='dext')
        self.assertEqual(response.status_code, 200, response.json)
        self.finish_run()
        sid = response.json['session_id']
        self.addCleanup(lambda: operator_requests.pending.pop(sid, None))
        self.addCleanup(lambda: operator_requests.close_browser(sid))
        return sid, self.created[-1], operator_requests

    def operator_event(self, sid, broker, action='resume'):
        item = broker.status(sid)
        return {**{k: item[k] for k in ('run_id', 'intervention_id', 'revision', 'token')},
                'action': action, 'answer': '', 'non_sensitive': False}

    def respond_operator(self, sid, event):
        return self.client.post('/api/operator?session_id=' + sid, json=event,
                                headers={**self.headers, 'Origin': self.base_url}, base_url=self.base_url)

    def test_authentication_handoff_retains_lease_same_chat_and_platform_without_model_polling(self):
        with patch.object(self.service, 'webview_window') as window:
            sid, previous, broker = self.pause_browser()
            scripts = '\n'.join(call.args[0] for call in window.evaluate_js.call_args_list)
            self.assertIn('window.agentPaused', scripts)
            self.assertNotIn('Stopped without completing', scripts)
        lease = previous.kwargs['profile_lease']
        self.assertTrue(broker.owns_lease(sid, lease))
        with self.assertRaises(profile_lease.ProfileBusyError): self.acquire('saccade-dext')
        for _ in range(12):
            self.assertEqual(broker.status(sid)['state'], 'waiting_operator')
        self.assertEqual(len(self.created), 1)
        saved = self.conversation.get_session(sid)
        self.assertIn('Paused for operator', saved['exchanges'][-1]['done_message'])
        event = self.operator_event(sid, broker)
        resumed = self.respond_operator(sid, event)
        self.assertEqual(resumed.status_code, 200, resumed.json)
        self.finish_run()
        current = self.created[-1]
        self.assertEqual(resumed.json['session_id'], sid)
        self.assertEqual(resumed.json['platform_context'], self.context())
        self.assertIs(current.kwargs['operator_session'], previous)
        self.assertIs(current.kwargs['profile_lease'], lease)
        self.assertIsNotNone(current.kwargs['prior_history'])
        self.assertTrue(current.closed)
        self.assertFalse(broker.owns_lease(sid, lease))
        self.acquire('saccade-dext')
        self.assertEqual(self.respond_operator(sid, event).status_code, 409)

    def test_authentication_claim_resumes_to_intentional_wait_on_both_platforms(self):
        from tests.platform_learning_fixtures import install_synthetic, PLATFORM
        from AutoCua.saccade.operator_requests import operator_requests as broker
        install_synthetic(self.root)
        for platform in ('dext', PLATFORM):
            with self.subTest(platform=platform):
                self.outcomes = [{'status':'waiting_operator','message':json.dumps({'category':'authentication',
                    'reason':'authentication_required','request':'Please sign in privately in the dedicated Chrome window.'})}]
                first = self.post(platform_id=platform, task='Open a harmless section and wait for instructions.')
                self.assertEqual(first.status_code, 200, first.json)
                self.finish_run()
                sid = first.json['session_id']
                self.clean_correction(sid)
                previous = self.created[-1]
                before = self.provider_calls
                event = self.chat_event(sid, broker, "c'est connecté")
                self.outcomes = [{'status':'waiting_operator','message':json.dumps({'category':'question',
                    'reason':'awaiting_instructions','request':'I have reached the requested page and stopped. What would you like me to do next?'})}]
                result = self.respond_operator(sid, event)
                self.assertEqual(result.status_code, 200, result.json)
                self.finish_run()
                current = self.created[-1]
                self.assertIs(current.kwargs['operator_session'], previous)
                self.assertIs(current.kwargs['profile_lease'], previous.kwargs['profile_lease'])
                self.assertIsNot(current.kwargs['stop_event'], previous.kwargs['stop_event'])
                self.assertEqual(current.kwargs['platform_context'], previous.kwargs['platform_context'])
                self.assertIn('wait for instructions', current.task)
                self.assertIn('login is not verified', current.task)
                self.assertEqual(len(current.kwargs['prior_history']['assistant_messages']), len(current.kwargs['prior_history']['tool_responses']))
                self.assertEqual(self.provider_calls, before + 1)
                self.assertEqual(broker.status(sid)['request']['reason'], 'awaiting_instructions')
                for _ in range(3):
                    self.client.get('/api/operator?session_id=' + sid, headers=self.headers, base_url=self.base_url)
                self.assertEqual(self.provider_calls, before + 1)
                self.assertFalse(previous.closed)
                self.assertFalse(current.closed)
                self.assertEqual(self.respond_operator(sid, self.operator_event(sid, broker, 'cancel')).status_code, 200)

    def test_lost_operator_lease_is_not_reacquired_by_resume(self):
        sid, previous, broker = self.pause_browser()
        lease = previous.kwargs['profile_lease']
        lease.release()
        response = self.respond_operator(sid, self.chat_event(sid, broker, "c'est connecté"))
        self.assertEqual(response.status_code, 400)
        self.assertEqual(broker.status(sid)['diagnostic_code'], 'profile_lease_lost')
        self.assertEqual(broker.status(sid)['recovery'], 'cancel_restart')
        self.assertEqual(len(self.created), 1)
        self.assertIsNone(lease._file)
        self.assertEqual(self.respond_operator(sid, self.operator_event(sid, broker, 'cancel')).status_code, 200)

    def test_runtime_failure_is_not_misreported_as_browser_reattachment_and_requires_cancel(self):
        sid, previous, broker = self.pause_browser()
        self.fail_runtime = True
        self.assertEqual(self.respond_operator(sid, self.chat_event(sid, broker, 'oui')).status_code, 200)
        self.finish_run()
        self.assertEqual(len(self.created), 2)
        pending = broker.status(sid)
        self.assertEqual(pending['recovery'], 'cancel_restart')
        self.assertEqual(pending['diagnostic_code'], 'internal_exception')
        diagnostics = self.client.get('/api/operator/diagnostics?session_id=' + sid, headers=self.headers, base_url=self.base_url)
        self.assertEqual(diagnostics.status_code, 200)
        self.assertIn({'code':'internal_exception','phase':'execution'}, [{k: r[k] for k in ('code','phase')} for r in diagnostics.json['events']])
        self.assertNotIn('https://', diagnostics.get_data(as_text=True))
        self.assertNotIn('PRIVATE', diagnostics.get_data(as_text=True))
        for answer in ('oui', 'What information has changed?', 'Continue'):
            self.assertEqual(self.respond_operator(sid, self.chat_event(sid, broker, answer)).status_code, 409)
        self.assertEqual(len(self.created), 2)
        self.assertTrue(broker.owns_lease(sid, previous.kwargs['profile_lease']))
        self.assertEqual(self.respond_operator(sid, self.operator_event(sid, broker, 'cancel')).status_code, 200)

    def test_failed_reattachment_keeps_browser_and_rotates_resume_token_without_fresh_launch(self):
        sid, previous, broker = self.pause_browser()
        event = self.operator_event(sid, broker)
        self.fail_reattachment = True
        response = self.respond_operator(sid, event)
        self.assertEqual(response.status_code, 200, response.json)
        self.finish_run()
        self.assertEqual(len(self.created), 1)
        self.assertFalse(previous.closed)
        self.assertTrue(broker.owns_lease(sid, previous.kwargs['profile_lease']))
        self.assertEqual(broker.status(sid)['state'], 'waiting_operator')
        self.assertEqual(broker.status(sid)['diagnostic_code'], 'chrome_pipe_disconnected')
        self.assertEqual(broker.status(sid)['recovery'], 'cancel_restart')
        self.assertNotEqual(broker.status(sid)['revision'], event['revision'])
        self.assertEqual(self.respond_operator(sid, event).status_code, 409)
        cancelled = self.respond_operator(sid, self.operator_event(sid, broker, 'cancel'))
        self.assertEqual(cancelled.status_code, 200, cancelled.json)
        self.assertTrue(previous.closed)
        self.acquire('saccade-dext')

    def test_cancel_resuming_defers_transport_cleanup_until_worker_exits(self):
        sid, previous, broker = self.pause_browser()
        self.release.clear()
        self.started.clear()
        event = self.operator_event(sid, broker)
        self.assertEqual(self.respond_operator(sid, event).status_code, 200)
        self.assertTrue(self.started.wait(5))
        cancelled = self.respond_operator(sid, {**event, 'action': 'cancel'})
        self.assertEqual(cancelled.status_code, 200)
        self.assertTrue(self.service.active_agent_stop_event.is_set())
        self.assertFalse(previous.closed)
        self.finish_run()
        self.assertTrue(self.created[-1].closed)
        self.assertEqual(broker.status(sid)['state'], 'cancelled')

    def test_failed_cancel_cleanup_reserves_ownership_and_disables_resume(self):
        sid, previous, broker = self.pause_browser()
        self.fail_cleanup = True
        self.assertEqual(self.respond_operator(sid, self.operator_event(sid, broker, 'cancel')).status_code, 409)
        self.assertFalse(previous.closed)
        self.assertTrue(broker.owns_lease(sid, previous.kwargs['profile_lease']))
        self.assertEqual(broker.status(sid)['state'], 'waiting_operator')
        self.assertEqual(self.respond_operator(sid, self.operator_event(sid, broker)).status_code, 409)
        self.assertEqual(len(self.created), 1)
        self.fail_cleanup = False
        self.assertEqual(self.respond_operator(sid, self.operator_event(sid, broker, 'cancel')).status_code, 200)
        self.assertTrue(previous.closed)

    def test_missing_suspended_browser_cannot_fall_back_to_a_fresh_chrome(self):
        from AutoCua.saccade.operator_requests import operator_requests as broker
        response = self.post(platform_id='dext')
        self.finish_run()
        sid = response.json['session_id']
        self.addCleanup(lambda: broker.pending.pop(sid, None))
        broker.suspend(sid, 'orphaned-run', {
            'provider': 'openai', 'model': 'synthetic', 'mode': 'web',
            'platform_id': 'dext', 'task': 'Original synthetic objective'
        }, {'category': 'manual_action', 'reason': 'manual_intervention', 'request': 'Review the environment.'})
        result = self.respond_operator(sid, self.operator_event(sid, broker))
        self.assertEqual(result.status_code, 400, result.json)
        self.assertEqual(result.json['error'], 'operator_resume:native_checkpoint_invalid')
        self.assertEqual(broker.status(sid)['recovery'], 'cancel_restart')
        self.assertEqual(len(self.created), 1)
        self.assertEqual(broker.status(sid)['state'], 'waiting_operator')

    def chat_event(self, sid, broker, text):
        return {**self.operator_event(sid, broker), 'action': 'chat', 'answer': text,
                'non_sensitive': True, 'presentation_digest': broker.status(sid).get('presentation_digest')}

    def correction(self, sid, text, claim=None):
        url = '/api/operator/correction?session_id=' + sid
        if claim is None:
            response = self.client.get(url, headers=self.headers, base_url=self.base_url)
            self.assertEqual(response.status_code, 200, response.json)
            claim = response.json
        return self.client.post(url, json={'text': text, 'claim': claim},
            headers={**self.headers, 'Origin': self.base_url}, base_url=self.base_url)

    def clean_correction(self, sid):
        from AutoCua.saccade.operator_requests import operator_requests as broker
        self.addCleanup(lambda: broker.pending.pop(sid, None))
        self.addCleanup(lambda: broker.close_browser(sid))

    def test_second_platform_uses_shared_active_handoff_chat_approval_and_native_control(self):
        from tests.platform_learning_fixtures import install_synthetic, PLATFORM
        from AutoCua.saccade.operator_requests import operator_requests as broker
        from AutoCua.saccade.platform_learning import PlatformLearningControl
        from AutoCua.saccade.procedure_store import ProcedureStore
        context = install_synthetic(self.root)
        self.release.clear()
        first = self.post(platform_id=PLATFORM, task='Open Billing.')
        self.assertEqual(first.status_code, 200, first.json)
        self.assertTrue(self.started.wait(5))
        sid = first.json['session_id']
        self.clean_correction(sid)
        agent = self.created[0]
        self.assertIs(type(agent.kwargs['learning_control']), PlatformLearningControl)
        self.assertIsNone(agent.kwargs['dext_control'])
        self.assertEqual(first.json['platform_context'], context)
        correction = self.correction(sid, 'The correct path is Settings, then Billing.')
        self.assertEqual(correction.status_code, 200, correction.json)
        self.assertEqual(correction.json['pending']['state'], 'pausing_operator')
        self.finish_run()
        self.assertEqual(self.provider_calls, 0)
        self.assertFalse(agent.closed)
        self.assertIn('Settings', broker.status(sid)['request']['request'])
        self.assertTrue(broker.owns_lease(sid, agent.kwargs['profile_lease']))
        for label, role, more in [('Settings', 'link', {}), ('Settings', 'heading', {'2': {'name':'Billing', 'role':'link', 'rect':[1,1,40,20]}}), ('Billing', 'heading', {})]:
            self.scan = {'1': {'name': label, 'role': role, 'rect': [1,1,40,20]}, **more}
            result = self.respond_operator(sid, self.chat_event(sid, broker, 'Continue'))
            self.assertEqual(result.status_code, 200, result.json)
            self.finish_run()
            self.assertEqual(self.provider_calls, 0)
            self.assertEqual(result.json['session_id'], sid)
            self.assertEqual(result.json['platform_context'], context)
            self.assertIs(self.created[-1].kwargs['operator_session'], self.created[-2])
            self.assertIn('Open Billing.', self.created[-1].task)
        self.assertIn('Billing', broker.status(sid)['procedure_summary'])
        self.scan = None
        saved = self.respond_operator(sid, self.chat_event(sid, broker, 'Yes, remember this'))
        self.assertEqual(saved.status_code, 200, saved.json)
        self.finish_run()
        self.assertEqual(self.provider_calls, 1)
        self.assertIn('Billing', (ProcedureStore(self.root, PLATFORM).root / 'learning.md').read_text(encoding='utf-8'))
        self.assertFalse((self.root / 'platforms/dext/data/navigation/active.json').exists())

    def test_spontaneous_french_correction_after_end_keeps_objective_and_requires_fresh_surface_confirmation(self):
        from AutoCua.saccade.operator_requests import operator_requests as broker
        first = self.post(platform_id='dext', task='Find the purchase invoices in Dext.')
        self.finish_run()
        sid = first.json['session_id']
        self.clean_correction(sid)
        result = self.correction(sid, "Tu dois d'abord cliquer sur Achats, puis sur Boîte de réception.")
        self.assertEqual(result.status_code, 200, result.json)
        self.assertEqual(result.json['status'], 'waiting_operator')
        self.assertIn('Purchases', result.json['pending']['request']['request'])
        self.assertEqual(len(self.created), 1)
        self.scan = {'2': {'name': 'Purchases', 'role': 'link', 'rect': [1, 1, 40, 20]}}
        resumed = self.respond_operator(sid, self.chat_event(sid, broker, 'Continue'))
        self.assertEqual(resumed.status_code, 200, resumed.json)
        self.finish_run()
        self.assertTrue(self.created[-1].kwargs['correction_reopen'])
        self.assertIsNone(self.created[-1].kwargs['operator_session'])
        self.assertIn('Find the purchase invoices', self.created[-1].task)
        self.assertIsNotNone(self.created[-1].kwargs['prior_history'])
        self.assertEqual(self.provider_calls, 1)

    def test_active_correction_waits_for_safe_handoff_and_preserves_browser_without_second_run(self):
        from AutoCua.saccade.operator_requests import operator_requests as broker
        self.release.clear()
        first = self.post(platform_id='dext', task='Find purchase invoices in Dext.')
        self.assertTrue(self.started.wait(5))
        sid = first.json['session_id']
        self.clean_correction(sid)
        agent = self.created[0]
        result = self.correction(sid, 'No, you are going the wrong way. Open Purchases first, then Inbox.')
        self.assertEqual(result.status_code, 200, result.json)
        self.assertEqual(result.json['pending']['state'], 'pausing_operator')
        self.assertEqual(len(self.created), 1)
        self.assertFalse(broker.owns_lease(sid, agent.kwargs['profile_lease']))
        self.assertTrue(self.service.active_agent_stop_event.operator_pause)
        self.finish_run()
        pending = broker.status(sid)
        self.assertEqual(pending['state'], 'waiting_operator')
        self.assertIn('same browser', pending['request']['request'])
        self.assertTrue(broker.owns_lease(sid, agent.kwargs['profile_lease']))
        self.assertFalse(agent.closed)
        self.assertEqual(self.provider_calls, 0)
        self.assertEqual(self.respond_operator(sid, self.chat_event(sid, broker, 'Continue')).status_code, 200)
        self.finish_run()
        self.assertIs(self.created[-1].kwargs['operator_session'], agent)
        self.assertFalse(self.created[-1].kwargs['correction_reopen'])
        self.assertIn('Find purchase invoices', self.created[-1].task)

    def test_failed_correction_handoff_does_not_claim_application_or_allow_resume(self):
        from AutoCua.saccade.operator_requests import operator_requests as broker
        self.release.clear()
        first = self.post(platform_id='dext', task='Open the invoices in Dext.')
        self.assertTrue(self.started.wait(5))
        sid = first.json['session_id']
        self.clean_correction(sid)
        self.handoff_available = False
        self.assertEqual(self.correction(sid, 'Le bon chemin est Achats → Boîte de réception.').status_code, 200)
        self.finish_run()
        self.assertIn('not applied', broker.status(sid)['request']['request'])
        self.assertEqual(self.respond_operator(sid, self.chat_event(sid, broker, 'Continue')).status_code, 409)
        self.assertEqual(len(self.created), 1)

    def test_spontaneous_correction_can_pause_an_already_resumed_run(self):
        from AutoCua.saccade.operator_requests import operator_requests as broker
        sid, previous, broker = self.pause_browser()
        self.release.clear()
        self.started.clear()
        self.assertEqual(self.respond_operator(sid, self.chat_event(sid, broker, 'Continue')).status_code, 200)
        self.assertTrue(self.started.wait(5))
        self.assertEqual(broker.status(sid)['state'], 'resuming')
        response = self.correction(sid, 'No, you are going the wrong way. Open Purchases first, then Inbox.')
        self.assertEqual(response.status_code, 200, response.json)
        self.assertEqual(response.json['pending']['state'], 'pausing_operator')
        self.finish_run()
        self.assertEqual(broker.status(sid)['state'], 'waiting_operator')
        self.assertIs(self.created[-1].kwargs['profile_lease'], previous.kwargs['profile_lease'])
        self.assertEqual(self.provider_calls, 1)

    def test_correction_context_is_one_use_pending_answers_win_and_ordinary_messages_do_not_learn(self):
        from AutoCua.saccade.operator_requests import operator_requests as broker
        first = self.post(platform_id='dext', task='Open invoices in Dext.')
        self.finish_run()
        sid = first.json['session_id']
        self.clean_correction(sid)
        for text in ('Summarize the current page.', "I'm connected."):
            self.assertEqual(self.correction(sid, text).json['status'], 'ordinary')
            self.assertNotIn(sid, broker._teaching)
        url = '/api/operator/correction?session_id=' + sid
        claim = self.client.get(url, headers=self.headers, base_url=self.base_url).json
        self.assertEqual(self.correction(sid, 'Summarize the page.', claim).json['status'], 'ordinary')
        self.assertEqual(self.correction(sid, 'First open Purchases, then Inbox.', claim).status_code, 409)
        self.assertEqual(self.correction(sid, "Tu t'es trompé.").status_code, 200)
        before = broker.status(sid)
        self.assertIn('corrected navigation path', before['request']['request'])
        self.assertEqual(self.correction(sid, 'Open Purchases then Inbox.').json['pending']['intervention_id'], before['intervention_id'])

    def test_stop_during_correction_queue_cancels_and_cleans_up_after_worker(self):
        from AutoCua.saccade.operator_requests import operator_requests as broker
        self.release.clear()
        first = self.post(platform_id='dext', task='Find invoices in Dext.')
        self.assertTrue(self.started.wait(5))
        sid = first.json['session_id']
        self.clean_correction(sid)
        self.correction(sid, 'First open Purchases then Inbox.')
        stopped = self.client.post('/api/stop-agent', headers=self.headers, base_url=self.base_url)
        self.assertEqual(stopped.status_code, 200)
        self.assertFalse(self.created[0].closed)
        self.finish_run()
        self.assertTrue(self.created[0].closed)
        self.assertEqual(broker.status(sid)['state'], 'cancelled')

    def test_chat_french_authentication_negative_reply_and_same_browser_continuation(self):
        sid, previous, broker = self.pause_browser()
        saved = self.conversation.get_session(sid)['exchanges'][-1]['done_message']
        self.assertIn('sign in privately', saved)
        self.assertNotIn('authentication_required', saved)
        event = self.chat_event(sid, broker, 'Non, pas encore')
        answer = self.respond_operator(sid, event)
        self.assertEqual(answer.status_code, 200, answer.json)
        self.assertEqual(answer.json['status'], 'waiting_operator')
        self.assertEqual(self.conversation.get_session(sid)['exchanges'][-1]['task'], 'Non, pas encore')
        self.assertEqual(len(self.created), 1)
        self.assertEqual(self.provider_calls, 1)
        self.assertTrue(broker.owns_lease(sid, previous.kwargs['profile_lease']))
        self.assertEqual(self.respond_operator(sid, event).status_code, 409)
        for _ in range(12): self.client.get('/api/operator?session_id=' + sid, headers=self.headers, base_url=self.base_url)
        self.assertEqual(self.provider_calls, 1)
        resumed = self.respond_operator(sid, self.chat_event(sid, broker, 'Je suis connecté'))
        self.assertEqual(resumed.status_code, 200, resumed.json)
        self.finish_run()
        self.assertEqual(resumed.json['session_id'], sid)
        self.assertIs(self.created[-1].kwargs['operator_session'], previous)
        self.assertIs(self.created[-1].kwargs['profile_lease'], previous.kwargs['profile_lease'])
        self.assertIn('Synthetic request', self.created[-1].task)
        self.assertEqual(self.conversation.get_session(sid)['exchanges'][-1]['task'], 'Je suis connecté')

    def test_chat_authentication_never_accepts_codes_and_cancel_preserves_cleanup(self):
        sid, previous, broker = self.pause_browser()
        self.assertEqual(self.respond_operator(sid, self.chat_event(sid, broker, '123456')).status_code, 409)
        self.assertEqual(len(self.created), 1)
        self.assertEqual(self.respond_operator(sid, self.chat_event(sid, broker, 'Cancel')).json['status'], 'cancelled')
        self.assertTrue(previous.closed)
        self.assertEqual(self.conversation.get_session(sid)['exchanges'][-1]['status'], 'cancelled')

    def test_paused_dext_control_stays_bound_when_another_chat_is_used(self):
        sid, previous, broker = self.pause_browser()
        original_control = broker.control_for(sid)
        self.assertIs(original_control, previous.kwargs['dext_control'])
        other = self.post()
        self.assertEqual(other.status_code, 200, other.json)
        self.finish_run()
        self.assertIsNone(self.service._dext_control)
        self.assertIs(broker.control_for(sid), original_control)
        self.assertTrue(broker.owns_lease(sid, previous.kwargs['profile_lease']))

    def test_chat_teaching_exact_approval_markdown_and_continuation_through_real_routes(self):
        from AutoCua.saccade.operator_requests import operator_requests as broker
        from AutoCua.saccade.dext_control import DextRunControl
        def elements(control=(), heading=()):
            return {str(n): {'name': name, 'role': role, 'rect': [1, 1, 100, 20]}
                    for n, (name, role) in enumerate([(x, 'link') for x in control] + [(x, 'heading') for x in heading], 1)}
        self.scan = elements(['Purchases'])
        self.outcomes.append({'status': 'waiting_operator', 'message': json.dumps({
            'category': 'question', 'reason': 'missing_information', 'request': 'How do I reach the purchase invoices section?'})})
        response = self.post(platform_id='dext')
        self.finish_run()
        sid = response.json['session_id']
        self.addCleanup(lambda: broker.pending.pop(sid, None))
        self.addCleanup(lambda: broker.close_browser(sid))
        original = self.created[0]
        pinned = original.kwargs['dext_control'].pin_revision
        self.scan = elements(['Inbox'], ['Purchases'])
        resumed = self.respond_operator(sid, self.chat_event(sid, broker, 'Ouvre les achats puis la boîte de réception.'))
        self.assertEqual(resumed.status_code, 200, resumed.json)
        self.finish_run()
        self.assertEqual(broker.status(sid)['request']['category'], 'manual_action')
        self.assertEqual(self.provider_calls, 1)
        self.scan = elements([], ['Inbox'])
        self.assertEqual(self.respond_operator(sid, self.chat_event(sid, broker, "C'est bon")).status_code, 200)
        self.finish_run()
        presented = broker.status(sid)
        self.assertIn('Purchases', presented['procedure_summary'])
        self.assertIn('Inbox', presented['procedure_summary'])
        self.assertEqual(self.provider_calls, 1)
        event = self.chat_event(sid, broker, 'Yes, save it.')
        self.assertEqual(self.respond_operator(sid, event).status_code, 200)
        self.finish_run()
        self.assertEqual(self.provider_calls, 2)
        self.assertEqual(self.created[-1].kwargs['dext_control'].pin_revision, pinned)
        self.assertEqual(self.respond_operator(sid, event).status_code, 409)
        future = DextRunControl(self.context(), 'future-chat', project_root=self.root)
        self.addCleanup(future.close)
        self.assertIn('Purchases', future.overlay())
        self.assertIn('Inbox', future.overlay())
        self.assertNotIn('Ouvre les achats', future.overlay())
        self.assertTrue((future.store.root / 'snapshots' / (future.pin_revision + '.md')).is_file())
        self.assertIs(self.created[-1].kwargs['profile_lease'], original.kwargs['profile_lease'])

    def test_generic_chat_has_no_dext_operator_control(self):
        response = self.post()
        self.finish_run()
        self.assertIsNone(self.created[0].kwargs["dext_control"])
        url = "/api/dext/control?session_id=" + response.json["session_id"]
        self.assertEqual(self.client.get(url, headers=self.headers, base_url=self.base_url).status_code, 409)

    def test_exact_execution_chat_review_reuses_browser_and_authority_without_polling_model(self):
        sid, previous, broker = self.pause_browser()
        control=broker.control_for(sid)
        action={'type':'click','id':2,'times':1}
        stamp={'platform_id':'dext','profile':'saccade-dext','config_revision':control.context['config_revision'],
               'session':'retained-native-session','tab':'1'}
        # The physical scanner is the boundary stub in this route test; native
        # dispatch and scanning have their own three-platform integration test.
        control.execution.decide(action,stamp,{'name':'Unclassified control'},effect='interaction',run_id=control.run_id)
        broker.present_execution(sid,control)
        status=self.client.get('/api/operator?session_id='+sid,headers=self.headers,base_url=self.base_url)
        self.assertIn('Unclassified control',status.json['execution_summary'])
        calls=self.provider_calls
        self.assertEqual(self.respond_operator(sid,self.chat_event(sid,broker,'Yes, remember this')).json['status'],'waiting_operator')
        for _ in range(3):
            self.client.get('/api/operator?session_id='+sid,headers=self.headers,base_url=self.base_url)
        self.assertEqual(self.provider_calls,calls)
        response=self.respond_operator(sid,self.chat_event(sid,broker,'Approve this interaction'))
        self.assertEqual(response.status_code,200,response.json)
        self.finish_run()
        self.assertEqual(response.json['session_id'],sid)
        self.assertIs(self.created[-1].kwargs['operator_session'],previous)
        self.assertIs(self.created[-1].kwargs['profile_lease'],previous.kwargs['profile_lease'])
        self.assertIs(self.created[-1].kwargs['learning_control'].execution,control.execution)

    def test_local_results_require_api_auth_and_same_conversation_platform(self):
        from AutoCua.saccade.procedure_store import ProcedureStore
        first=self.post(platform_id='dext')
        self.finish_run()
        one=first.json['session_id']
        second=self.post(platform_id='dext')
        self.finish_run()
        two=second.json['session_id']
        store=ProcedureStore(self.root,'dext')
        store._write('results/one.json',{'session':one,'platform':'dext','result':'SYNTHETIC PRIVATE ONE'},exclusive=True)
        store._write('results/two.json',{'session':two,'platform':'dext','result':'SYNTHETIC PRIVATE TWO'},exclusive=True)
        store._write('results/foreign.json',{'session':one,'platform':'foreign','result':'FOREIGN'},exclusive=True)
        url='/api/operator/results?session_id='+one
        self.assertEqual(self.client.get(url,base_url=self.base_url).status_code,403)
        self.assertEqual(self.client.get(url,headers={**self.headers,'Origin':'https://foreign.test'},base_url=self.base_url).status_code,403)
        response=self.client.get(url,headers=self.headers,base_url=self.base_url)
        self.assertEqual(response.status_code,200,response.json)
        self.assertEqual(response.headers['Cache-Control'],'no-store')
        self.assertEqual(response.json,[{'receipt':'one','result':'SYNTHETIC PRIVATE ONE'}])
        other=self.client.get('/api/operator/results?session_id='+two,headers=self.headers,base_url=self.base_url)
        self.assertEqual(other.json,[{'receipt':'two','result':'SYNTHETIC PRIVATE TWO'}])

    def test_shell_start_cannot_steal_the_stop_channel_of_an_active_web_run(self):
        self.release.clear()
        first = self.post(platform_id="dext")
        self.assertEqual(first.status_code, 200, first.json)
        self.assertTrue(self.started.wait(5))
        stop_event = self.service.active_agent_stop_event
        run_id = self.service.active_agent_session_id
        response = self.client.post("/api/start-shell", json={
            "provider": "openai", "model": "synthetic", "task": "Synthetic shell request",
        }, headers=self.headers, base_url=self.base_url)
        self.assertEqual(response.status_code, 409, response.json)
        self.assertIs(self.service.active_agent_stop_event, stop_event)
        self.assertEqual(self.service.active_agent_session_id, run_id)


if __name__ == "__main__":
    unittest.main()
