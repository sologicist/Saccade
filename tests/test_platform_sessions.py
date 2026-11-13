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
        with patch.dict(sys.modules, {"webview": types.ModuleType("webview")}):
            self.service = importlib.import_module("AutoCua.ui.service")
        self.release = threading.Event()
        self.release.set()
        self.started = threading.Event()
        self.created = []
        test = self

        class FakeWebAgent:
            def __init__(self, **kwargs):
                self.kwargs = kwargs
                self.assistant_messages = ["Synthetic step"]
                self.tool_responses = ["Synthetic result"]
                test.created.append(self)

            def process_request(self, task):
                test.started.set()
                if not test.release.wait(10):
                    raise RuntimeError("Synthetic test release timed out.")
                return {"status": "success", "message": "Synthetic completion"}

        original_import = importlib.import_module

        def import_agent(name, *args, **kwargs):
            if name == "AutoCua.web.agent":
                return types.SimpleNamespace(AgentService=FakeWebAgent)
            return original_import(name, *args, **kwargs)

        from AutoCua.saccade import platform_registry
        patches = (
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
        response = self.post(platform_id="dext")
        self.finish_run()
        sid = response.json['session_id']
        self.addCleanup(lambda: operator_requests.pending.pop(sid, None))
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

    def test_generic_chat_has_no_dext_operator_control(self):
        response = self.post()
        self.finish_run()
        self.assertIsNone(self.created[0].kwargs["dext_control"])
        url = "/api/dext/control?session_id=" + response.json["session_id"]
        self.assertEqual(self.client.get(url, headers=self.headers, base_url=self.base_url).status_code, 409)

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
