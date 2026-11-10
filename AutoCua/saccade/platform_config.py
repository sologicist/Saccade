"""Load and validate Saccade web platform configurations."""

from __future__ import annotations

import json
import re
import stat
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit


PROJECT_ROOT = Path(__file__).resolve().parents[2]

PLATFORM_ID_PATTERN = re.compile(r"[a-z][a-z0-9_-]{0,63}")
HOST_PATTERN = re.compile(
    r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)"
    r"(?:\.(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?))*"
)

MAX_CONFIG_SIZE = 65_536
MAX_PROCEDURE_SIZE = 262_144
SKILL_NAME_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*\.md")
MAPPING_PATH_PATTERN = re.compile(r"/[A-Za-z0-9/._~!$&'()+,;=:@-]*")
DOMAIN_SKILLS = Path("AutoCua/default_skills/web/domain_skill")


@dataclass(frozen=True)
class PlatformConfig:
    """Validated configuration for a Saccade web platform."""

    schema_version: int
    id: str
    name: str
    engine: str
    start_url: str
    allowed_hosts: tuple[str, ...]
    browser: str
    max_steps: int
    procedure_path: Path


def _check_path(path: Path, root: Path) -> None:
    """Reject symbolic links and Windows reparse points within the trusted root."""
    relative = path.relative_to(root)
    current = root
    for part in relative.parts:
        current = current / part
        metadata = current.lstat()
        if stat.S_ISLNK(metadata.st_mode) or (
            getattr(metadata, "st_file_attributes", 0)
            & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
        ):
            raise ValueError("Symbolic links and reparse points are not allowed.")


def _read_text(path: Path, root: Path, limit: int) -> str:
    _check_path(path, root)
    if not path.is_file():
        raise ValueError(f"Required file is not a regular file: {path.name}")
    # Bound the read as well as the stat, including files changed during loading.
    with path.open("rb") as source:
        content = source.read(limit + 1)
    if len(content) > limit:
        raise ValueError(f"{path.name} exceeds the maximum file size.")
    return content.decode("utf-8")


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON properties are not allowed.")
        result[key] = value
    return result


def _valid_host(host: object) -> bool:
    return (
        isinstance(host, str)
        and len(host) <= 253
        and HOST_PATTERN.fullmatch(host) is not None
    )


def _mapping_scope(site: str) -> tuple[str, str]:
    """Parse a canonical exact hostname and optional path with segment boundaries."""
    host, separator, suffix = site.partition("/")
    path = "/" + suffix if separator else ""
    if (
        not _valid_host(host)
        or path and not MAPPING_PATH_PATTERN.fullmatch(path)
        or "//" in path
        or any(segment in (".", "..") for segment in path.split("/"))
    ):
        raise ValueError("Invalid domain skill mapping scope.")
    return host, path.rstrip("/")


def _load_manifest(root: Path) -> dict[str, str]:
    directory = root / DOMAIN_SKILLS
    manifest = json.loads(
        _read_text(directory / "skills.json", root, MAX_CONFIG_SIZE),
        object_pairs_hook=_unique_object,
    )
    if not isinstance(manifest, dict):
        raise ValueError("skills.json must contain a JSON object.")
    scopes = set()
    for site, filename in manifest.items():
        scope = _mapping_scope(site)
        if scope in scopes:
            raise ValueError("Duplicate domain skill scopes are not allowed.")
        scopes.add(scope)
        if not isinstance(filename, str) or not SKILL_NAME_PATTERN.fullmatch(filename):
            raise ValueError("Invalid domain skill filename.")
        _read_text(directory / filename, root, MAX_PROCEDURE_SIZE)
    return manifest


def load_platform(
    platform_id: str,
    root: Path | None = None,
) -> PlatformConfig:
    """Validate a v1 platform and reference its sole native Web procedure.

    Args:
        platform_id: Unique identifier of the platform.
        root: Project root directory. Defaults to the Saccade root.

    Returns:
        A validated and immutable platform configuration.

    Raises:
        ValueError: If the platform configuration is invalid.
        FileNotFoundError: If a required platform file is missing.
        json.JSONDecodeError: If platform.json contains invalid JSON.
    """

    # Validate the platform identifier before resolving any paths.
    if (
        not isinstance(platform_id, str)
        or not PLATFORM_ID_PATTERN.fullmatch(platform_id)
    ):
        raise ValueError("Invalid platform identifier.")

    project_root = (root or PROJECT_ROOT).resolve()
    config_path = project_root / "platforms" / platform_id / "platform.json"
    procedure_path = project_root / DOMAIN_SKILLS / f"{platform_id}.md"
    data = json.loads(
        _read_text(config_path, project_root, MAX_CONFIG_SIZE),
        object_pairs_hook=_unique_object,
    )

    if not isinstance(data, dict):
        raise ValueError("platform.json must contain a JSON object.")

    allowed_keys = {
        "schema_version",
        "id",
        "name",
        "engine",
        "start_url",
        "allowed_hosts",
        "browser",
        "max_steps",
    }

    unknown_keys = set(data) - allowed_keys

    if unknown_keys:
        raise ValueError(
            f"Unknown configuration properties: {sorted(unknown_keys)}"
        )

    missing_keys = allowed_keys - set(data)
    if missing_keys:
        raise ValueError(f"Missing configuration properties: {sorted(missing_keys)}")

    # Validate the schema version.
    schema_version = data.get("schema_version")

    if type(schema_version) is not int or schema_version != 1:
        raise ValueError("Unsupported platform schema version.")

    # Validate the platform identity.
    if data.get("id") != platform_id:
        raise ValueError("Platform identifier mismatch.")

    name = data.get("name")

    if not isinstance(name, str) or not name.strip():
        raise ValueError("Platform name must be a non-empty string.")

    # Saccade V1 only supports web platforms.
    if data.get("engine") != "web":
        raise ValueError(
            "Saccade V1 only supports the web engine."
        )

    # Validate the initial URL.
    start_url = data.get("start_url")

    if not isinstance(start_url, str):
        raise ValueError("A platform start URL is required.")

    parsed_url = urlsplit(start_url)

    if (
        parsed_url.scheme != "https"
        or not parsed_url.hostname
        or "@" in parsed_url.netloc
        or "\\" in start_url
        or any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in start_url)
        or not _valid_host(parsed_url.hostname)
        or parsed_url.netloc not in (
            parsed_url.hostname, f"{parsed_url.hostname}:443"
        )
        or parsed_url.port not in (None, 443)
        or not parsed_url.netloc
    ):
        raise ValueError("A valid HTTPS start URL is required.")

    # Validate the list of explicitly allowed hosts.
    hosts = data.get("allowed_hosts")

    if (
        not isinstance(hosts, list)
        or not hosts
        or any(
            not _valid_host(host)
            for host in hosts
        )
    ):
        raise ValueError("Invalid allowed_hosts configuration.")

    if len(hosts) != len(set(hosts)):
        raise ValueError("Duplicate allowed hosts are not allowed.")

    if parsed_url.hostname.lower() not in hosts:
        raise ValueError(
            "The start URL is outside the allowed platform hosts."
        )

    # Chrome is the only supported browser in Saccade V1.
    browser = data["browser"]

    if browser != "chrome":
        raise ValueError(
            "Saccade V1 only supports Google Chrome."
        )

    # Validate the maximum number of agent steps.
    max_steps = data["max_steps"]

    if (
        type(max_steps) is not int
        or not 1 <= max_steps <= 1000
    ):
        raise ValueError(
            "max_steps must be an integer between 1 and 1000."
        )

    # Validate UTF-8 and size, but leave live content in the native skill file.
    _read_text(procedure_path, project_root, MAX_PROCEDURE_SIZE)
    manifest = _load_manifest(project_root)
    scopes = {
        _mapping_scope(site)
        for site, filename in manifest.items()
        if filename == procedure_path.name
    }
    if scopes != {(host, "") for host in hosts}:
        raise ValueError("Platform hosts and native domain skill mappings differ.")

    # Return an immutable, validated configuration.
    return PlatformConfig(
        schema_version=schema_version,
        id=platform_id,
        name=name.strip(),
        engine="web",
        start_url=start_url,
        allowed_hosts=tuple(hosts),
        browser=browser,
        max_steps=max_steps,
        procedure_path=procedure_path,
    )
