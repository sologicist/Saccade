"""Explicit operator CLI for private local onboarding; never imports archives."""

from __future__ import annotations

import argparse
import contextlib
import os
import secrets
import threading
from pathlib import Path

from .business_catalogue import read_registration
from .business_contract import BusinessError, digest, dumps, loads, read_safe, reject
from .client_references import REFERENCE_FILES, client_id, read_reference, safe_directory
from .platform_config import PROJECT_ROOT, load_platform

_REGISTRY_LOCK = threading.RLock()


class ReferenceManager:
    def __init__(self, project_root=PROJECT_ROOT):
        self.project = Path(project_root)
        load_platform("dext", root=self.project)
        self.data = self.project / "platforms/dext/data"

    def initialize(self, client):
        """Create directories only; no files, imports, registry edits or overwrite."""
        client_id(client)
        safe_directory(self.project, self.data / client, create=True)
        return {"client_id": client, "initialized": True, "reference_files_created": 0,
                "registration_changed": False, "required_files": list(REFERENCE_FILES)}

    def validate(self, client):
        client_id(client)
        rows = []
        try:
            directory = safe_directory(self.project, self.data / client)
        except BusinessError as error:
            return {"client_id": client, "valid": False, "directory_error": str(error), "files": []}
        extra = sum(path.suffix.lower() == ".md" and path.name not in REFERENCE_FILES for path in directory.iterdir())
        for name in REFERENCE_FILES:
            try:
                try:
                    (directory / name).lstat()
                except FileNotFoundError:
                    rows.append({"name": name, "status": "missing_reference"})
                    continue
                text, revision = read_reference(self.data, client, name)
                rows.append({"name": name, "status": "valid", "revision": revision,
                             "utf8_bytes": len(text.encode("utf-8"))})
            except BusinessError as error:
                rows.append({"name": name, "status": str(error)})
        return {"client_id": client, "valid": not extra and all(row["status"] == "valid" for row in rows),
                "files": rows, "unexpected_markdown_files": extra}

    def registry_status(self):
        value, revision = read_registration(self.data)
        return {"revision": revision, "active_client": value["active_client"] if value else None,
                "clients": sorted(value["clients"]) if value else [], "real_analysis_authorized": False}

    @contextlib.contextmanager
    def _lock(self):
        safe_directory(self.project, self.data, create=True)
        with _REGISTRY_LOCK:
            path = self.data / ".registration.lock"
            if path.exists() or path.is_symlink():
                read_safe(self.project, path, 1)
            with path.open("a+b") as stream:
                if stream.tell() == 0:
                    stream.write(b"0")
                    stream.flush()
                read_safe(self.project, path, 1)
                stream.seek(0)
                if os.name == "nt":
                    import msvcrt
                    try:
                        msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                    except OSError:
                        reject("client_registry_busy")
                else:
                    import fcntl
                    fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
                try:
                    yield
                finally:
                    stream.seek(0)
                    if os.name == "nt":
                        msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
                    else:
                        fcntl.flock(stream, fcntl.LOCK_UN)

    def register_real(self, client, expected_revision, *, activate=False, existing=False):
        """Metadata only. This is never record binding or disclosure consent."""
        client_id(client)
        with self._lock():
            value, revision = read_registration(self.data)
            if expected_revision != revision:
                reject("client_registration_changed")
            report = self.validate(client)
            if not report["valid"]:
                reject("client_references_invalid")
            value = loads(dumps(value)) if value else {"schema_version": 1, "active_client": None, "clients": {}}
            if existing:
                if client not in value["clients"]:
                    reject("unauthorized_client")
            else:
                if client in value["clients"]:
                    reject("client_already_registered")
                value["clients"][client] = {"synthetic": False, "bank_labels": [], "bank_responses": {}}
            if len(value["clients"]) > 32:
                reject("invalid_client_registration")
            if activate:
                value["active_client"] = client
            if value["active_client"] is None:
                reject("explicit_active_client_required")
            staged = self.data / (".registration-" + secrets.token_hex(24) + ".pending")
            try:
                with staged.open("xb") as stream:
                    stream.write(dumps(value, 32_768).encode())
                    stream.flush()
                    os.fsync(stream.fileno())
                if read_registration(self.data)[1] != revision:
                    reject("client_registration_changed")
                path = self.data / "registration.json"
                if value and revision == digest(b"unconfigured"):
                    os.link(staged, path)  # Create-if-absent, never clobber a race.
                else:
                    os.replace(staged, path)
            finally:
                # Only our uniquely created staging file; never a reference.
                staged.unlink(missing_ok=True)
            return self.registry_status()


def main(argv=None):
    parser = argparse.ArgumentParser(description="Local-only Dext reference onboarding; no archive import or network.")
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("initialize", "validate", "register-real", "activate"):
        item = sub.add_parser(command)
        item.add_argument("--client", required=True)
        if command in ("register-real", "activate"):
            item.add_argument("--expected-revision", required=True)
        if command == "register-real":
            item.add_argument("--activate", action="store_true")
    sub.add_parser("registry-status")
    args = parser.parse_args(argv)
    try:
        manager = ReferenceManager(args.project_root)
        if args.command == "initialize":
            result = manager.initialize(args.client)
        elif args.command == "validate":
            result = manager.validate(args.client)
        elif args.command == "registry-status":
            result = manager.registry_status()
        else:
            result = manager.register_real(args.client, args.expected_revision,
                activate=args.command == "activate" or args.activate, existing=args.command == "activate")
        print(dumps(result))
        return 2 if result.get("valid") is False else 0
    except BusinessError as error:
        print(dumps({"error": str(error)}))
        return 2
    except (OSError, ValueError):
        print(dumps({"error": "local_onboarding_unavailable"}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
