"""Private, immutable navigation guidance. Publication never grants authority."""

from __future__ import annotations

import contextlib
import difflib
import os
import secrets
import threading
from datetime import datetime, timezone
from pathlib import Path

from .business_contract import digest, dumps, loads, read_safe, reject

ROUTES = {
    "invoices": "Ask the operator to identify the invoices navigation control.",
    "bank": "Ask the operator to identify the bank transactions navigation control.",
    "workspace": "Confirm the active workspace with the operator before proceeding.",
    "record": "Confirm the exact record with the operator; a URL is insufficient.",
    "review": "Stop for operator review if target identity or the transition is uncertain.",
}
MAX_PROCEDURE = 16_384
_THREAD_LOCK = threading.RLock()


def utc():
    return datetime.now(timezone.utc).isoformat()


def identifier(value):
    if type(value) is not str or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        reject("invalid_revision")
    return value


class ProcedureStore:
    """Cross-process CAS with immutable snapshots and one atomic active pointer.

    File fsync precedes replace. Recovery reads only the pointer's complete,
    hash-checked snapshot; orphan snapshots never become active. Directory fsync
    is available on POSIX; Windows power-loss durability depends on the volume.
    Host filesystem integrity is trusted, as with the installed Python bundle.
    """

    def __init__(self, project_root):
        self.project = Path(project_root)
        self.root = self.project / "platforms/dext/data/navigation"
        self.baseline_path = self.project / "AutoCua/default_skills/web/domain_skill/dext.md"
        self.baseline = read_safe(self.project, self.baseline_path, MAX_PROCEDURE).decode("utf-8")
        self.baseline_digest = digest(self.baseline)
        self._directories(self.root / "snapshots")
        self._directories(self.root / "proposals")
        self._directories(self.root / "decisions")
        self._directories(self.root / "pins")
        with self.lock():
            if not (self.root / "active.json").exists() and any((self.root / "snapshots").glob("*.json")):
                # Never treat a deleted pointer or interrupted initialization
                # as a new installation and silently adopt another procedure.
                reject("procedure_corrupt")
            initial = {"schema_version": 1, "source": "baseline", "content": self.baseline,
                       "baseline_digest": self.baseline_digest, "routes": []}
            revision = self._snapshot(initial)
            if not (self.root / "active.json").exists():
                self._write("active.json", {"schema_version": 1, "current": revision,
                                           "previous": None, "generation": 0}, exclusive=True)
            self.active()

    def _directories(self, path):
        current = self.project
        if current.is_symlink() or getattr(current.lstat(), "st_file_attributes", 0) & 0x400:
            reject("unsafe_path")
        for component in path.relative_to(self.project).parts:
            current = current / component
            current.mkdir(exist_ok=True)
            if current.is_symlink() or getattr(current.lstat(), "st_file_attributes", 0) & 0x400 or not current.is_dir():
                reject("unsafe_path")

    @contextlib.contextmanager
    def lock(self):
        # Advisory OS locks release on process death; no stale lock-file removal.
        with _THREAD_LOCK:
            path = self.root / "store.lock"
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
                        reject("procedure_store_busy")
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

    def _read(self, name):
        return loads(read_safe(self.project, self.root / name, 65_536), 65_536)

    def _write(self, name, value, *, exclusive=False):
        path = self.root / name
        self._directories(path.parent)
        if path.exists() or path.is_symlink():
            read_safe(self.project, path, 65_536)
        content = dumps(value, 65_536).encode()
        # Temporary files are inert; never adopted by startup or globbing.
        temporary = path.parent / ("pending-" + secrets.token_hex(24))
        with temporary.open("xb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        if exclusive:
            # Hard-link publication is create-if-absent, with no overwrite race.
            os.link(temporary, path)
        else:
            os.replace(temporary, path)
        if os.name != "nt":
            fd = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
        # Keep crash remnants inert; never delete user or runtime evidence here.

    def _snapshot(self, snapshot):
        revision = digest(snapshot)
        path = "snapshots/" + revision + ".json"
        if (self.root / path).exists():
            if self._read(path) != snapshot:
                reject("procedure_corrupt")
        else:
            self._write(path, snapshot, exclusive=True)
        return revision

    def snapshot(self, revision):
        if digest(read_safe(self.project, self.baseline_path, MAX_PROCEDURE).decode("utf-8")) != self.baseline_digest:
            reject("procedure_corrupt")
        value = self._read("snapshots/" + identifier(revision) + ".json")
        if type(value) is not dict or digest(value) != revision or value.get("baseline_digest") != self.baseline_digest:
            reject("procedure_corrupt")
        if value.get("source") == "operator":
            if value.get("content") != self.render(value.get("routes")):
                reject("procedure_corrupt")
        elif value.get("source") != "baseline" or value.get("content") != self.baseline:
            reject("procedure_corrupt")
        return value

    def active(self):
        pointer = self._read("active.json")
        if type(pointer) is not dict or set(pointer) != {"schema_version", "current", "previous", "generation"} or type(pointer["schema_version"]) is not int or pointer["schema_version"] != 1 or type(pointer["generation"]) is not int or pointer["generation"] < 0:
            reject("procedure_corrupt")
        self.snapshot(pointer["current"])
        if pointer["previous"] is not None:
            self.snapshot(pointer["previous"])
        return pointer

    @staticmethod
    def render(routes):
        if type(routes) is not list or not 1 <= len(routes) <= 8 or any(type(route) is not str or route not in ROUTES for route in routes):
            reject("invalid_procedure_routes")
        # Closed grammar prevents private values, page injection and instructions
        # for secrets, scripts, URLs, selectors or enlarged permissions.
        return "# Dext navigation guidance\n\n" + "\n".join(f"{n}. {ROUTES[route]}" for n, route in enumerate(routes, 1)) + "\n"

    def propose(self, routes, run_id):
        content = self.render(routes)
        with self.lock():
            base = self.active()
            candidate = {"schema_version": 1, "source": "operator", "content": content,
                         "baseline_digest": self.baseline_digest, "routes": list(routes),
                         "base": base, "run_digest": digest(run_id), "utc": utc(),
                         "proposal_id": secrets.token_hex(32)}
            revision = digest(candidate)
            self._write("proposals/" + candidate["proposal_id"] + ".json", candidate, exclusive=True)
            old = self.snapshot(base["current"])["content"]
            return {"proposal_id": candidate["proposal_id"], "base_revision": base["current"],
                    "candidate_revision": revision, "base_generation": base["generation"],
                    "old": old, "new": content, "diff": "".join(difflib.unified_diff(
                        old.splitlines(True), content.splitlines(True), fromfile="approved", tofile="proposed")),
                    "evidence": "Operator-selected generic route; no live target semantics verified.",
                    "rationale": "Explicit operator teaching; guidance grants no action permission."}

    def review(self, proposal_id, base_revision, candidate_revision, approve):
        identifier(proposal_id)
        identifier(base_revision)
        identifier(candidate_revision)
        if type(approve) is not bool:
            reject("invalid_operator_decision")
        with self.lock():
            candidate = self._read("proposals/" + proposal_id + ".json")
            if digest(candidate) != candidate_revision or candidate["base"]["current"] != base_revision:
                reject("proposal_identity_mismatch")
            decision = "decisions/" + proposal_id + ".json"
            if (self.root / decision).exists():
                reject("proposal_already_reviewed")
            current = self.active()
            if current != candidate["base"] and approve:
                reject("stale_procedure_proposal")
            if candidate["content"] != self.render(candidate["routes"]):
                reject("procedure_corrupt")
            if approve:
                self._snapshot(candidate)
            self._write(decision, {"approved": approve, "candidate_revision": candidate_revision,
                                   "base": current, "utc": utc()}, exclusive=True)
            if approve:
                self._write("active.json", {"schema_version": 1, "current": candidate_revision,
                                            "previous": current["current"], "generation": current["generation"] + 1})
            return self.active()

    def rollback(self, expected, target, run_id):
        # A rollback is a new explicitly reviewed revision, not snapshot mutation.
        with self.lock():
            current = self.active()
            if current["current"] != identifier(expected) or current["previous"] != identifier(target):
                reject("stale_procedure_proposal")
            snapshot = self.snapshot(target)
            candidate = {**snapshot, "rollback_from": current, "utc": utc(), "run_digest": digest(run_id)}
            revision = self._snapshot(candidate)
            self._write("active.json", {"schema_version": 1, "current": revision,
                                        "previous": current["current"], "generation": current["generation"] + 1})
            return self.active()

    def pin(self, session_id, *, adopt=False):
        name = "pins/" + digest(session_id) + ".json"
        marker = "pins/" + digest(session_id) + ".bound"
        with self.lock():
            present, bound = (self.root / name).exists(), (self.root / marker).exists()
            if present != bound:
                reject("procedure_corrupt")
            if not bound:
                self._write(marker, {"baseline_digest": self.baseline_digest}, exclusive=True)
                self._write(name, {"revision": self.active()["current"], "baseline_digest": self.baseline_digest}, exclusive=True)
            pin = self._read(name)
            if self._read(marker) != {"baseline_digest": self.baseline_digest}:
                reject("procedure_corrupt")
            if set(pin) != {"revision", "baseline_digest"} or pin["baseline_digest"] != self.baseline_digest:
                reject("procedure_corrupt")
            self.snapshot(pin["revision"])
            if adopt:
                pin = {"revision": self.active()["current"], "baseline_digest": self.baseline_digest}
                self._write(name, pin)
            return pin["revision"]
