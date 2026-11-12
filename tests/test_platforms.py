"""Platform v1 and native domain-skill integration contracts.

All fixtures are synthetic and isolated from local customer data and Chrome.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path

from AutoCua.saccade.platform_config import (
    MAX_CONFIG_SIZE,
    MAX_PROCEDURE_SIZE,
    load_platform,
)
from AutoCua.saccade.platform_registry import list_platforms


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DOMAIN_DIRECTORY = Path("AutoCua/default_skills/web/domain_skill")


class PlatformContracts(unittest.TestCase):
    """Exercise the loader through files rather than private validators."""

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.domain_dir = self.root / DOMAIN_DIRECTORY
        self.domain_dir.mkdir(parents=True)
        self.manifest_path = self.domain_dir / "skills.json"
        self.manifest = {
            "docs.google.com/spreadsheets": "google_sheets.md",
            "app.dext.com": "dext.md",
        }
        (self.domain_dir / "google_sheets.md").write_text(
            "Synthetic Google Sheets procedure.\n", encoding="utf-8"
        )
        (self.domain_dir / "dext.md").write_bytes(b"")
        self.config = {
            "schema_version": 1,
            "id": "dext",
            "name": "Dext",
            "engine": "web",
            "start_url": "https://app.dext.com/login",
            "allowed_hosts": ["app.dext.com"],
            "browser": "chrome",
            "max_steps": 45,
        }
        self.platform_dir = self.root / "platforms/dext"
        self.platform_dir.mkdir(parents=True)
        self.config_path = self.platform_dir / "platform.json"
        self.write_config()
        self.write_manifest()

    def write_config(self) -> None:
        self.config_path.write_text(json.dumps(self.config), encoding="utf-8")

    def write_manifest(self) -> None:
        self.manifest_path.write_text(json.dumps(self.manifest), encoding="utf-8")

    def load(self):
        return load_platform("dext", root=self.root)

    def create_symlink(self, path: Path, target: Path) -> None:
        """Skip only when the host genuinely lacks symlink privileges."""
        try:
            path.symlink_to(target, target_is_directory=target.is_dir())
        except OSError as error:
            if getattr(error, "winerror", None) == 1314:
                self.skipTest("Windows symlink privilege is unavailable.")
            raise

    def create_junction(self, path: Path, target: Path) -> None:
        """Create and clean up a junction only inside this synthetic fixture."""
        for candidate in (path, target):
            candidate.relative_to(self.root)
            if any(character in str(candidate) for character in '&|<>^%!"'):
                self.fail("The temporary junction path contains shell metacharacters.")
        subprocess.run(
            ["cmd.exe", "/d", "/c", "mklink", "/J", str(path), str(target)],
            check=True,
            capture_output=True,
            text=True,
        )
        # Remove only the junction, before TemporaryDirectory cleans the fixture.
        self.addCleanup(path.rmdir)

    def test_empty_native_procedure_is_valid_without_legacy_agent_file(self):
        platform = self.load()
        self.assertEqual(platform.id, "dext")
        self.assertEqual(platform.schema_version, 1)
        self.assertEqual(platform.allowed_hosts, ("app.dext.com",))
        self.assertEqual(platform.start_url, self.config["start_url"])
        self.assertTrue(platform.procedure_path.samefile(self.domain_dir / "dext.md"))
        self.assertEqual(platform.procedure_path.read_text(encoding="utf-8"), "")
        self.assertFalse(hasattr(platform, "agent_md"))
        self.assertFalse((self.platform_dir / "agent.md").exists())
        with self.assertRaises(FrozenInstanceError):
            platform.id = "changed"

    def test_populated_procedure_is_referenced_without_copying_its_content(self):
        procedure_path = self.domain_dir / "dext.md"
        procedure_path.write_text("Synthetic procedure.\n", encoding="utf-8")
        platform = self.load()
        procedure_path.write_text("Updated synthetic procedure.\n", encoding="utf-8")
        self.assertEqual(
            platform.procedure_path.read_text(encoding="utf-8"),
            "Updated synthetic procedure.\n",
        )

    def test_missing_native_procedure_does_not_fall_back_to_legacy_file(self):
        (self.domain_dir / "dext.md").unlink()
        (self.platform_dir / "agent.md").write_text(
            "Legacy synthetic procedure.\n", encoding="utf-8"
        )
        with self.assertRaises(FileNotFoundError):
            self.load()

    def test_missing_configuration_is_rejected(self):
        self.config_path.unlink()
        with self.assertRaises(FileNotFoundError):
            self.load()

    def test_missing_manifest_is_rejected(self):
        self.manifest_path.unlink()
        with self.assertRaises(FileNotFoundError):
            self.load()

    def test_unknown_configuration_properties_are_rejected(self):
        for key in ("agent_md", "procedure", "client_rules", "unexpected"):
            with self.subTest(key=key):
                self.config[key] = "Synthetic untrusted instructions."
                self.write_config()
                with self.assertRaises(ValueError):
                    self.load()
                del self.config[key]

    def test_every_v1_configuration_property_is_required(self):
        for key in tuple(self.config):
            with self.subTest(key=key):
                value = self.config.pop(key)
                self.write_config()
                with self.assertRaises(ValueError):
                    self.load()
                self.config[key] = value

    def test_invalid_schema_versions_are_rejected(self):
        for version in (None, True, False, 0, 2, 1.0, "1"):
            with self.subTest(version=version):
                self.config["schema_version"] = version
                self.write_config()
                with self.assertRaises(ValueError):
                    self.load()

    def test_invalid_platform_identifiers_are_rejected_before_lookup(self):
        for platform_id in (
            "", "../dext", "dext/../dext", "dext\\other", "/dext", "Dext",
            "dext.md", "dext\x00", "x" * 65, None, 1,
        ):
            with self.subTest(platform_id=platform_id):
                with self.assertRaises(ValueError):
                    load_platform(platform_id, root=self.root)

    def test_configuration_identity_must_match_directory(self):
        for platform_id in ("other", "../dext", None, True):
            with self.subTest(platform_id=platform_id):
                self.config["id"] = platform_id
                self.write_config()
                with self.assertRaises(ValueError):
                    self.load()

    def test_invalid_names_engine_browser_and_step_limits_are_rejected(self):
        cases = {
            "name": ("", " \t", None, 1),
            "engine": ("windows", "WEB", None),
            "browser": ("firefox", "Chrome", None),
            "max_steps": (0, 1001, True, 45.0, "45", None),
        }
        for key, values in cases.items():
            original = self.config[key]
            for value in values:
                with self.subTest(key=key, value=value):
                    self.config[key] = value
                    self.write_config()
                    with self.assertRaises(ValueError):
                        self.load()
            self.config[key] = original

    def test_unsafe_and_out_of_scope_start_urls_are_rejected(self):
        for url in (
            "http://app.dext.com/login",
            "https://app.dext.com.evil.test/login",
            "https://evilapp.dext.com/login",
            "https://sub.app.dext.com/login",
            "https://app.dext.com@evil.test/login",
            "https://operator:secret@app.dext.com/login",
            "https://@app.dext.com/login",
            "https://app.dext.com:8443/login",
            "https://app.dext.com:invalid/login",
            "https://app.dext.com./login",
            "https://app.dext.com\\@evil.test/login",
            " https://app.dext.com/login",
            "https://app.dext.com/lo\ngin",
            "javascript:alert(1)",
            "file:///app.dext.com/login",
            "//app.dext.com/login",
            "", None, 1,
        ):
            with self.subTest(url=url):
                self.config["start_url"] = url
                self.write_config()
                with self.assertRaises(ValueError):
                    self.load()

    def test_invalid_allowed_hosts_are_rejected(self):
        for hosts in (
            [], None, "app.dext.com", [None], [1], [""],
            ["app.dext.com", "app.dext.com"],
            ["APP.dext.com"], ["*.dext.com"], [".dext.com"],
            ["app.dext.com."], ["app..dext.com"], ["-app.dext.com"],
            ["app-.dext.com"], ["app.dext.com/login"],
            ["https://app.dext.com"], ["app.dext.com:443"],
            ["app.dext.com@evil.test"], ["app.dext.com\n"],
            ["äpp.dext.com"], ["a" * 64 + ".dext.com"],
            [".".join(["a" * 63] * 4)],
            ["app.dext.com.evil.test"],
        ):
            with self.subTest(hosts=hosts):
                self.config["allowed_hosts"] = hosts
                self.write_config()
                with self.assertRaises(ValueError):
                    self.load()

    def test_duplicate_configuration_keys_are_rejected(self):
        raw = json.dumps(self.config)
        self.config_path.write_text(
            raw[:-1] + ', "max_steps": 46}', encoding="utf-8"
        )
        with self.assertRaises(ValueError):
            self.load()

    def test_configuration_must_be_a_json_object(self):
        for raw in ("[]", "null", '"config"', "{invalid}"):
            with self.subTest(raw=raw):
                self.config_path.write_text(raw, encoding="utf-8")
                with self.assertRaises(ValueError):
                    self.load()

    def test_oversized_configuration_is_rejected(self):
        self.config_path.write_bytes(b" " * (MAX_CONFIG_SIZE + 1))
        with self.assertRaises(ValueError):
            self.load()

    def test_oversized_manifest_is_rejected(self):
        self.manifest_path.write_bytes(b" " * (MAX_CONFIG_SIZE + 1))
        with self.assertRaises(ValueError):
            self.load()

    def test_oversized_procedure_is_rejected(self):
        (self.domain_dir / "dext.md").write_bytes(b"x" * (MAX_PROCEDURE_SIZE + 1))
        with self.assertRaises(ValueError):
            self.load()

    def test_non_utf8_files_are_rejected(self):
        for path in (self.config_path, self.manifest_path, self.domain_dir / "dext.md"):
            with self.subTest(path=path.name):
                original = path.read_bytes()
                path.write_bytes(b"\xff")
                with self.assertRaises(ValueError):
                    self.load()
                path.write_bytes(original)

    def test_missing_platform_mapping_is_rejected(self):
        del self.manifest["app.dext.com"]
        self.write_manifest()
        with self.assertRaises(ValueError):
            self.load()

    def test_mapping_cannot_silently_change_the_platform_procedure(self):
        self.manifest["app.dext.com"] = "google_sheets.md"
        self.write_manifest()
        with self.assertRaises(ValueError):
            self.load()

    def test_unconfigured_mapping_host_is_rejected(self):
        self.manifest["login.dext.com"] = "dext.md"
        self.write_manifest()
        with self.assertRaises(ValueError):
            self.load()

    def test_configured_host_without_mapping_is_rejected(self):
        self.config["allowed_hosts"].append("login.dext.com")
        self.write_config()
        with self.assertRaises(ValueError):
            self.load()

    def test_path_only_mapping_does_not_cover_all_platform_pages(self):
        del self.manifest["app.dext.com"]
        self.manifest["app.dext.com/login"] = "dext.md"
        self.write_manifest()
        with self.assertRaises(ValueError):
            self.load()

    def test_explicit_additional_host_requires_both_configuration_and_mapping(self):
        self.config["allowed_hosts"].append("login.example.test")
        self.manifest["login.example.test"] = "dext.md"
        self.write_config()
        self.write_manifest()
        self.assertEqual(
            self.load().allowed_hosts, ("app.dext.com", "login.example.test")
        )

    def test_duplicate_manifest_keys_are_rejected(self):
        self.manifest_path.write_text(
            '{"app.dext.com":"dext.md","app.dext.com":"google_sheets.md"}',
            encoding="utf-8",
        )
        with self.assertRaises(ValueError):
            self.load()

    def test_equivalent_manifest_scope_aliases_are_rejected(self):
        for first, second in (
            ("example.test", "example.test/"),
            ("example.test/path", "example.test/path/"),
        ):
            with self.subTest(first=first, second=second):
                self.manifest[first] = "google_sheets.md"
                self.manifest[second] = "google_sheets.md"
                self.write_manifest()
                with self.assertRaises(ValueError):
                    self.load()
                del self.manifest[first]
                del self.manifest[second]

    def test_manifest_paths_allow_explicit_url_path_characters(self):
        self.manifest["example.test/area/@account:record"] = "google_sheets.md"
        self.manifest["example.test/area-_.~!$&'()+,;=:@/document"] = "google_sheets.md"
        self.write_manifest()
        self.assertEqual(self.load().id, "dext")

    def test_invalid_manifest_keys_fail_closed_even_when_unrelated_to_dext(self):
        invalid_sites = (
            "", "https://example.test", "http://example.test", "*.example.test",
            "Example.test", "example.test.", "example..test", "-example.test",
            "example.test:443", "user@example.test", "example.test?query=1",
            "example.test/#fragment", "example.test/path?query=1",
            "example.test\\path", " example.test", "example.test/white space",
            "example.test/%2e%2e/path", "example.test//path",
            "example.test/./path", "example.test/../path", "example.test/path/..",
            "example.test/*", "example.test/<path", "example.test/>path",
            'example.test/"path', "example.test/`path",
        )
        for site in invalid_sites:
            with self.subTest(site=site):
                self.manifest[site] = "google_sheets.md"
                self.write_manifest()
                with self.assertRaises(ValueError):
                    self.load()
                del self.manifest[site]

    def test_invalid_manifest_filenames_are_rejected(self):
        for filename in (
            "../dext.md", "sub/dext.md", "sub\\dext.md", "/dext.md",
            "C:\\dext.md", ".md", ".hidden.md", "dext.txt", "dext.md ",
            "dext.md:stream", "déxt.md", "", None, 1,
        ):
            with self.subTest(filename=filename):
                self.manifest["app.dext.com"] = filename
                self.write_manifest()
                with self.assertRaises(ValueError):
                    self.load()

    def test_missing_unrelated_manifest_target_is_rejected(self):
        (self.domain_dir / "google_sheets.md").unlink()
        with self.assertRaises(FileNotFoundError):
            self.load()

    def test_manifest_must_be_a_json_object(self):
        for raw in ("[]", "null", '"manifest"', "{invalid}"):
            with self.subTest(raw=raw):
                self.manifest_path.write_text(raw, encoding="utf-8")
                with self.assertRaises(ValueError):
                    self.load()

    def test_symbolic_configuration_file_is_rejected(self):
        target = self.root / "config-copy.json"
        target.write_bytes(self.config_path.read_bytes())
        self.config_path.unlink()
        self.create_symlink(self.config_path, target)
        with self.assertRaises(ValueError):
            self.load()

    def test_symbolic_procedure_file_is_rejected(self):
        target = self.root / "procedure-copy.md"
        target.write_bytes(b"")
        path = self.domain_dir / "dext.md"
        path.unlink()
        self.create_symlink(path, target)
        with self.assertRaises(ValueError):
            self.load()

    def test_symbolic_manifest_file_is_rejected(self):
        target = self.root / "manifest-copy.json"
        target.write_bytes(self.manifest_path.read_bytes())
        self.manifest_path.unlink()
        self.create_symlink(self.manifest_path, target)
        with self.assertRaises(ValueError):
            self.load()

    def test_symbolic_platform_directory_is_rejected(self):
        target = self.root / "platform-copy"
        self.platform_dir.rename(target)
        self.create_symlink(self.platform_dir, target)
        with self.assertRaises(ValueError):
            self.load()
        with self.assertRaises(ValueError):
            list_platforms(root=self.root)

    def test_symbolic_platforms_root_is_rejected(self):
        platforms_path = self.root / "platforms"
        target = self.root / "platforms-copy"
        platforms_path.rename(target)
        self.create_symlink(platforms_path, target)
        with self.assertRaises(ValueError):
            self.load()
        with self.assertRaises(ValueError):
            list_platforms(root=self.root)

    def test_symbolic_native_skill_ancestor_is_rejected(self):
        target = self.root / "domain-copy"
        self.domain_dir.rename(target)
        self.create_symlink(self.domain_dir, target)
        with self.assertRaises(ValueError):
            self.load()

    def test_symbolic_default_skills_ancestor_is_rejected(self):
        defaults_path = self.root / "AutoCua/default_skills"
        target = self.root / "default-skills-copy"
        defaults_path.rename(target)
        self.create_symlink(defaults_path, target)
        with self.assertRaises(ValueError):
            self.load()

    @unittest.skipUnless(os.name == "nt", "Junctions are a Windows filesystem feature.")
    def test_platforms_root_junction_is_rejected(self):
        platforms_path = self.root / "platforms"
        target = self.root / "platforms-copy"
        platforms_path.rename(target)
        self.create_junction(platforms_path, target)
        with self.assertRaises(ValueError):
            self.load()
        with self.assertRaises(ValueError):
            list_platforms(root=self.root)

    @unittest.skipUnless(os.name == "nt", "Junctions are a Windows filesystem feature.")
    def test_native_skill_ancestor_junction_is_rejected(self):
        defaults_path = self.root / "AutoCua/default_skills"
        target = self.root / "default-skills-copy"
        defaults_path.rename(target)
        self.create_junction(defaults_path, target)
        with self.assertRaises(ValueError):
            self.load()

    def test_registry_returns_only_validated_platforms_in_stable_order(self):
        other_dir = self.root / "platforms/alpha"
        other_dir.mkdir()
        other = dict(self.config, id="alpha", name="Synthetic Alpha")
        other["allowed_hosts"] = ["alpha.example.test"]
        other["start_url"] = "https://alpha.example.test/"
        (other_dir / "platform.json").write_text(json.dumps(other), encoding="utf-8")
        (self.domain_dir / "alpha.md").write_bytes(b"")
        self.manifest["alpha.example.test"] = "alpha.md"
        self.write_manifest()
        (self.root / "platforms/no-config").mkdir()
        (self.root / "platforms/not-a-platform.txt").write_text("Synthetic", encoding="utf-8")
        platforms = list_platforms(root=self.root)
        self.assertIsInstance(platforms, tuple)
        self.assertEqual(tuple(platform.id for platform in platforms), ("alpha", "dext"))

    def test_registry_does_not_silently_accept_invalid_configuration(self):
        self.config["engine"] = "windows"
        self.write_config()
        with self.assertRaises(ValueError):
            list_platforms(root=self.root)

    def test_registry_is_empty_when_platforms_directory_is_missing(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(list_platforms(root=Path(directory)), ())

    def test_registry_rejects_platforms_path_that_is_a_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "platforms").write_text("Synthetic", encoding="utf-8")
            with self.assertRaises(NotADirectoryError):
                list_platforms(root=root)


class RepositoryPlatformIntegration(unittest.TestCase):
    """Verify the shipped platform and upstream manifest stay consistent."""

    def test_dext_uses_the_single_native_procedure(self):
        platform = load_platform("dext")
        self.assertEqual(platform.procedure_path, REPOSITORY_ROOT / DOMAIN_DIRECTORY / "dext.md")
        self.assertTrue(platform.procedure_path.is_file())
        # Validate UTF-8 without fixing the contents of an operator-taught procedure.
        platform.procedure_path.read_text(encoding="utf-8")
        self.assertEqual(platform.allowed_hosts, ("app.dext.com",))
        self.assertEqual(platform.start_url, "https://app.dext.com/login")
        self.assertFalse((REPOSITORY_ROOT / "platforms/dext/agent.md").exists())

    def test_upstream_google_sheets_mapping_is_preserved(self):
        path = REPOSITORY_ROOT / DOMAIN_DIRECTORY / "skills.json"
        manifest = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(manifest["docs.google.com/spreadsheets"], "google_sheets.md")
        self.assertEqual(manifest["app.dext.com"], "dext.md")
        self.assertTrue((path.parent / "google_sheets.md").is_file())


if __name__ == "__main__":
    unittest.main()
