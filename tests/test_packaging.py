"""Inspect a built wheel and exercise its installed platform resources.

Set SACCADE_TEST_WHEEL to a wheel built from this tree to run these integration
tests. They use a fresh extraction and isolated interpreter, never the checkout
as an import fallback or local customer reference data.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path, PurePosixPath
from zipfile import ZipFile


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
WHEEL_PATH = os.environ.get("SACCADE_TEST_WHEEL")
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
                    self.assertNotEqual(parts[-1], "agent.md")
                self.assertNotIn("AutoCua_data", parts)

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
            code = """
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


if __name__ == "__main__":
    unittest.main()
