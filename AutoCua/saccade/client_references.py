"""Three-file client reference contract; never infer accounting semantics."""

from __future__ import annotations

from pathlib import Path

from .business_catalogue import CLIENT_ID
from .business_contract import digest, read_safe, reject

REFERENCE_FILES = ("comptable_achats.md", "comptable_ventes.md", "comptable_banque.md")
MAX_REFERENCE_BYTES = 2 * 1024 * 1024


def client_id(value):
    if type(value) is not str or not CLIENT_ID.fullmatch(value):
        reject("invalid_client_id")
    # This name is reserved for the existing private procedure store.
    if value == "navigation":
        reject("reserved_client_id")
    return value


def safe_directory(project, path, *, create=False):
    project, path = Path(project), Path(path)
    try:
        parts = path.relative_to(project).parts
        if any(part in (".", "..") for part in parts):
            reject("unsafe_path")
        current = project
        for part in (None, *parts):
            if part is not None:
                current = current / part
                if create:
                    current.mkdir(exist_ok=True)
            info = current.lstat()
            if current.is_symlink() or getattr(info, "st_file_attributes", 0) & 0x400 or not current.is_dir():
                reject("unsafe_path")
        if not path.resolve().is_relative_to(project.resolve()):
            reject("unsafe_path")
    except OSError:
        reject("required_file_unavailable")
    return path


def read_reference(data_root, client, name):
    client_id(client)
    if name not in REFERENCE_FILES:
        reject("unapproved_reference_file")
    root = Path(data_root)
    path = root / client / name
    content = read_safe(root, path, MAX_REFERENCE_BYTES)
    # Canonical paths alone do not detect cross-client hard links.
    if path.stat().st_nlink != 1:
        reject("unsafe_reference_link")
    try:
        text = content.decode("utf-8-sig")
    except UnicodeError:
        reject("invalid_reference_encoding")
    if not text.strip():
        reject("empty_reference")
    if text.startswith(("%PDF-", "PK\x03\x04")) or any(ord(c) < 32 and c not in "\n\r\t" or ord(c) == 127 for c in text):
        reject("invalid_reference_content")
    return text, digest(["reference-present", digest(content)])


def require_reference_bundle(data_root, client):
    """Read full current files, returning revisions only, with no persistence."""
    client_id(client)
    directory = safe_directory(Path(data_root), Path(data_root) / client)
    if any(path.suffix.lower() == ".md" and path.name not in REFERENCE_FILES for path in directory.iterdir()):
        reject("unexpected_reference_file")
    return {name: read_reference(data_root, client, name)[1] for name in REFERENCE_FILES}
