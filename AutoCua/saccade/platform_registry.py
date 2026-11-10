"""Discover and load registered Saccade web platforms."""

from __future__ import annotations

from pathlib import Path

from .platform_config import (
    PLATFORM_ID_PATTERN,
    PROJECT_ROOT,
    PlatformConfig,
    _check_path,
    load_platform,
)


def list_platforms(
    root: Path | None = None,
) -> tuple[PlatformConfig, ...]:
    """Discover and validate all registered web platforms.

    Platforms are discovered from subdirectories containing
    a platform.json file.

    Invalid configurations raise an exception instead of
    being silently ignored.

    Args:
        root: Project root directory.

    Returns:
        An immutable tuple of validated platform configurations.
    """

    project_root = (root or PROJECT_ROOT).resolve()
    platforms_dir = project_root / "platforms"

    if not platforms_dir.exists() and not platforms_dir.is_symlink():
        return ()

    _check_path(platforms_dir, project_root)

    if not platforms_dir.is_dir():
        raise NotADirectoryError(
            "The platforms path must be a directory."
        )

    platforms: list[PlatformConfig] = []

    for folder in sorted(
        platforms_dir.iterdir(),
        key=lambda path: path.name,
    ):
        _check_path(folder, project_root)

        if not folder.is_dir():
            continue

        if not PLATFORM_ID_PATTERN.fullmatch(folder.name):
            continue

        if not (folder / "platform.json").exists():
            continue

        platform = load_platform(
            platform_id=folder.name,
            root=project_root,
        )

        platforms.append(platform)

    return tuple(platforms)
