"""Inspect a built wheel and exercise its installed platform resources.

Set SACCADE_TEST_WHEEL to a wheel built from this tree to run these integration
tests. They use a fresh extraction and isolated interpreter, never the checkout
as an import fallback or local customer reference data.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path, PurePosixPath
from zipfile import ZipFile


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
WHEEL_PATH = os.environ.get("SACCADE_TEST_WHEEL")
SDIST_PATH = os.environ.get("SACCADE_TEST_SDIST")
DOMAIN_DIRECTORY = "AutoCua/default_skills/web/domain_skill"


@unittest.skipUnless(WHEEL_PATH, "Set SACCADE_TEST_WHEEL to verify a built wheel.")
class BuiltWheelContracts(unittest.TestCase):
    """Catch missing resources at the installed paths used by the real loader."""

    def setUp(self) -> None:
        wheel_path = Path(WHEEL_PATH).resolve()
        self.assertTrue(wheel_path.is_file(), "The specified wheel does not exist.")
        self.wheel = ZipFile(wheel_path)
        self.addCleanup(self.wheel.close)
        self.names = set(self.wheel.namelist())

    def test_platform_and_native_skill_resources_are_packaged(self):
        resources = (
            "platforms/dext/platform.json",
            "AutoCua/saccade/platform_config.py",
            "AutoCua/saccade/platform_registry.py",
            "AutoCua/saccade/business_contract.py",
            "AutoCua/saccade/business_catalogue.py",
            "AutoCua/saccade/business_run.py",
            "AutoCua/saccade/business_process.py",
            "AutoCua/saccade/business_worker.py",
            "AutoCua/saccade/procedure_store.py",
            "AutoCua/saccade/platform_learning.py",
            "AutoCua/saccade/learning_adapter.py",
            "AutoCua/saccade/dext_learning.py",
            "AutoCua/saccade/dext_control.py",
            "AutoCua/saccade/operator_requests.py",
            "AutoCua/saccade/execution.py",
            "AutoCua/saccade/capabilities.py",
            "AutoCua/saccade/scribe_pdf.py",
            "AutoCua/saccade/operator_diagnostics.py",
            "AutoCua/saccade/operator_language.py",
            "AutoCua/ui/platform_session/operator_chat.ts",
            "AutoCua/ui/platform_session/operator_resume.ts",
            "AutoCua/ui/platform_session/operator_review.tsx",
            "AutoCua/ui/container/agent/run_reply.js",
            "AutoCua/ui/script.js",
            "AutoCua/ui/index.js",
            "AutoCua/saccade/client_references.py",
            "AutoCua/saccade/reference_management.py",
            "AutoCua/saccade/navigation_correction.py",
            "AutoCua/saccade/business_functions/__init__.py",
            "AutoCua/saccade/business_functions/platforms/__init__.py",
            "AutoCua/saccade/business_functions/platforms/dext/__init__.py",
            "AutoCua/saccade/business_functions/platforms/dext/functions.py",
            "AutoCua/saccade/business_functions/platforms/dext/runtime.py",
            "AutoCua/saccade/business_functions/platforms/dext/invoice_validation.py",
            "AutoCua/saccade/business_functions/platforms/dext/policy.json",
            f"{DOMAIN_DIRECTORY}/skills.json",
            f"{DOMAIN_DIRECTORY}/dext.md",
            f"{DOMAIN_DIRECTORY}/google_sheets.md",
        )
        for resource in resources:
            with self.subTest(resource=resource):
                self.assertTrue(resource in self.names, f"Missing wheel resource: {resource}")
                self.assertEqual(
                    self.wheel.read(resource),
                    (REPOSITORY_ROOT / resource).read_bytes(),
                )
        manifest = json.loads(self.wheel.read(f"{DOMAIN_DIRECTORY}/skills.json"))
        self.assertEqual(manifest["app.dext.com"], "dext.md")
        for filename in manifest.values():
            self.assertIn(f"{DOMAIN_DIRECTORY}/{filename}", self.names)

    def test_local_platform_data_and_legacy_procedures_are_absent(self):
        for name in self.names:
            parts = PurePosixPath(name).parts
            with self.subTest(name=name):
                if parts and parts[0] == "platforms":
                    self.assertNotIn("data", parts)
                    self.assertNotIn("reports", parts)
                    self.assertNotEqual(parts[-1], "agent.md")
                self.assertNotIn("AutoCua_data", parts)
                self.assertNotIn("legacy_reference", parts)
                self.assertNotIn("Saccade-PR5-handoff", parts)
                self.assertNotIn("navigation", parts if "data" in parts else ())

    def test_extracted_wheel_loads_without_the_source_checkout(self):
        with tempfile.TemporaryDirectory(prefix="saccade-wheel-install-") as temporary:
            install_root = Path(temporary) / "site-packages"
            install_root.mkdir()
            for name in self.names:
                parts = PurePosixPath(name).parts
                self.assertFalse(name.startswith(("/", "\\")))
                self.assertNotIn("..", parts)
                self.assertTrue(all(":" not in part and "\\" not in part for part in parts))
            self.wheel.extractall(install_root)
            # -I removes the source checkout and ambient PYTHONPATH. No runtime
            # dependencies or Chrome session are needed to load configuration.
            code = r"""
import importlib
import json
import sys
from pathlib import Path

installed = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(installed))
from AutoCua.saccade import platform_config
from AutoCua.saccade.platform_registry import list_platforms

assert Path(platform_config.__file__).resolve().is_relative_to(installed)
assert platform_config.PROJECT_ROOT == installed
platform = platform_config.load_platform("dext")
assert platform.procedure_path == installed / "AutoCua/default_skills/web/domain_skill/dext.md"
platform.procedure_path.read_text(encoding="utf-8")
assert platform.allowed_hosts == ("app.dext.com",)
assert "dext" in [item.id for item in list_platforms()]
from AutoCua.saccade.dext_control import DextRunControl
from AutoCua.saccade.session_context import build_platform_context
control = DextRunControl(build_platform_context("dext"), "wheel-synthetic")
assert control.overlay() == ""
assert control.status()["capabilities"]["live_scribe"] == "verified_download_receipt_required"
control.close()
from AutoCua.saccade.business_catalogue import catalogue
catalog = catalogue("dext")
assert set(catalog["functions"]) == {"dext.bank", "dext.scribe"}
from AutoCua.saccade.business_functions.platforms.dext import functions
assert callable(functions.bank) and callable(functions.scribe)
from AutoCua.saccade.session_context import build_platform_context
from AutoCua.saccade.business_run import BusinessRun
data = installed / "platforms/dext/data"
(data / "wheel-synthetic").mkdir(parents=True)
(data / "registration.json").write_text(json.dumps({"schema_version":1,"active_client":"wheel-synthetic",
    "clients":{"wheel-synthetic":{"synthetic":True,"bank_labels":["SYNTHETIC WHEEL LABEL"],
    "bank_responses":{"SYNTHETIC WHEEL LABEL":{"compte":"40100000"}}}}}), encoding="utf-8")
(data / "wheel-synthetic/comptable_banque.md").write_text("Entire synthetic wheel reference.", encoding="utf-8")
for name in ("comptable_achats.md", "comptable_ventes.md"):
    (data / "wheel-synthetic" / name).write_text("Entire synthetic wheel invoice reference.", encoding="utf-8")
run = BusinessRun(build_platform_context("dext"))
run.refresh()
ticket = run.prepare({"type":"call_function","version":1,"name":"dext.bank",
    "arguments":{"client_id":"wheel-synthetic","string":"SYNTHETIC WHEEL LABEL"}})
assert run.execute(ticket)["result"] == {"compte":"40100000"}
from AutoCua.saccade.platform_learning import PlatformLearningControl
functions_dir = installed / "platforms/dext/functions"
functions_dir.mkdir()
(functions_dir / "echo.py").write_text('def echo(text: str) -> str:\n    return "WHEEL:" + text\n', encoding="utf-8")
(installed / "platforms/dext/capabilities.json").write_text(json.dumps({"schema_version":1,"platform_id":"dext","functions":[
    {"id":"dext.wheel_echo","source":"echo.py","symbol":"echo","effect":"compute","destination":"local",
     "description":"Synthetic installed wheel function","output_visibility":"public"}]}), encoding="utf-8")
control = PlatformLearningControl(build_platform_context("dext"), "wheel-capability")
action = {"type":"call_function","version":1,"name":"dext.wheel_echo","arguments":{"text":"SYNTHETIC"}}
stamp = {"platform_id":"dext","profile":"saccade-dext","config_revision":control.context["config_revision"],"session":"synthetic-browser","tab":"1"}
assert "dext.wheel_echo" in str(control.execution_tools())
assert not control.authorize_execution(action,stamp,{})["allowed"]
control.execution.review(control.execution.pending["id"],True)
assert control.authorize_execution(action,stamp,{})["allowed"]
assert control.execute_capability(action)["result"] == "WHEEL:SYNTHETIC"
assert set(catalogue("dext")["functions"]) == {"dext.bank", "dext.scribe"}
control.close()
native = importlib.import_module("AutoCua.web.agent_native")
assert Path(native.__file__).resolve().is_relative_to(installed)
print(json.dumps({"id": platform.id, "native_imported": True}))
"""
            result = subprocess.run(
                [sys.executable, "-I", "-c", code, str(install_root)],
                cwd=temporary,
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(
                json.loads(result.stdout), {"id": "dext", "native_imported": True}
            )


@unittest.skipUnless(SDIST_PATH, "Set SACCADE_TEST_SDIST to inspect a built source distribution.")
class BuiltSourceContracts(unittest.TestCase):
    def test_business_sources_are_present_and_private_data_is_excluded(self):
        with tarfile.open(Path(SDIST_PATH).resolve()) as archive:
            names = archive.getnames()
        for resource in ("AutoCua/saccade/business_run.py", "AutoCua/saccade/business_worker.py",
                         "AutoCua/saccade/business_functions/platforms/dext/functions.py",
                         "AutoCua/saccade/business_functions/platforms/dext/policy.json",
                         "AutoCua/web/tool_registry/business.rs", "AutoCua/web/browser/download_events.rs", "AutoCua/web/Cargo.toml",
                         "platforms/dext/platform.json"):
            self.assertTrue(any(name.endswith("/" + resource) for name in names), resource)
        for name in names:
            parts = PurePosixPath(name).parts
            self.assertNotIn("..", parts)
            self.assertFalse(name.startswith(("/", "\\")))
            self.assertFalse(re.search(r"(^|/)platforms/[^/]+/(data|reports)/", name))
            self.assertNotIn("/browser_profiles/", name)
            self.assertNotIn("/.cache/", name)
            self.assertNotIn("pilot_reference/", name)
            self.assertFalse(name.lower().endswith(".pdf"))


if __name__ == "__main__":
    unittest.main()
