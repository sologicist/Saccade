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
    "purchases": "Ask the operator to open Purchases manually, then reobserve and verify the section heading.",
    "inbox": "Ask the operator to open Inbox manually, then reobserve and verify the section heading.",
    "invoices": "Ask the operator to identify the invoices navigation control.",
    "bank": "Ask the operator to identify the bank transactions navigation control.",
    "workspace": "Confirm the active workspace with the operator before proceeding.",
    "record": "Confirm the exact record with the operator; a URL is insufficient.",
    "review": "Stop for operator review if target identity or the transition is uncertain.",
}
ROUTE_LABELS = {'purchases': 'Purchases', 'inbox': 'Inbox', 'invoices': 'Invoices', 'bank': 'Bank transactions',
                'workspace': 'Workspace check', 'record': 'Record check', 'review': 'Operator review'}
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
        return self._publish(name, dumps(value, 65_536).encode(), exclusive=exclusive)

    def _publish(self, name, content, *, exclusive=False):
        path = self.root / name
        self._directories(path.parent)
        if path.exists() or path.is_symlink():
            read_safe(self.project, path, 65_536)
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
        self._export_markdown(revision, snapshot["content"])
        return revision

    def _export_markdown(self, revision, content):
        name = "snapshots/" + identifier(revision) + ".md"
        path = self.root / name
        encoded = content.encode('utf-8')
        if path.exists() or path.is_symlink():
            if read_safe(self.project, path, MAX_PROCEDURE) != encoded:
                reject("procedure_markdown_corrupt")
        else:
            self._publish(name, encoded, exclusive=True)
        return path

    def markdown(self, revision):
        """Export legacy snapshots on demand; JSON remains the canonical source."""
        with self.lock():
            snapshot = self.snapshot(revision)
            path = self._export_markdown(revision, snapshot['content'])
            return read_safe(self.project, path, MAX_PROCEDURE).decode('utf-8')

    def snapshot(self, revision):
        if digest(read_safe(self.project, self.baseline_path, MAX_PROCEDURE).decode("utf-8")) != self.baseline_digest:
            reject("procedure_corrupt")
        value = self._read("snapshots/" + identifier(revision) + ".json")
        if type(value) is not dict or digest(value) != revision or value.get("baseline_digest") != self.baseline_digest:
            reject("procedure_corrupt")
        if value.get("source") == "operator":
            if value.get("content") != self._candidate_content(value):
                reject("procedure_corrupt")
        elif value.get("source") != "baseline" or value.get("content") != self.baseline:
            reject("procedure_corrupt")
        markdown = self.root / ("snapshots/" + revision + ".md")
        if markdown.exists() or markdown.is_symlink():
            if read_safe(self.project, markdown, MAX_PROCEDURE) != value['content'].encode('utf-8'):
                reject("procedure_markdown_corrupt")
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

    @classmethod
    def _candidate_content(cls, candidate):
        paths = candidate.get('paths')
        if paths is None:
            return cls.render(candidate.get('routes'))
        if type(paths) is not list or not 1 <= len(paths) <= 8:
            reject('invalid_procedure_routes')
        content = '# Dext navigation guidance\n\nOperator-assisted paths only; no action, disclosure or download authority.\n'
        for index, path in enumerate(paths, 1):
            cls.render(path)
            content += f'\n## Operator-assisted path {index}\n\n' + '\n'.join(f'{n}. {ROUTES[route]}' for n, route in enumerate(path, 1)) + '\n'
        if candidate.get('routes') != [route for path in paths for route in path] or len(content.encode()) > MAX_PROCEDURE:
            reject('invalid_procedure_routes')
        return content

    def propose(self, routes, run_id, *, teaching_source="route_selection", observation_digest=None, incremental=False):
        if teaching_source not in ("route_selection", "operator_chat_correction"):
            reject("invalid_teaching_source")
        if observation_digest is not None:
            identifier(observation_digest)
        content = self.render(routes)
        with self.lock():
            base = self.active()
            paths = None
            if incremental:
                prior = self.snapshot(base['current'])
                paths = prior.get('paths', [prior['routes']] if prior['routes'] else [])
                # Revise the path with the same entry section, preserve unrelated paths.
                paths = [list(path) for path in paths if path[0] != routes[0]] + [list(routes)]
            candidate = {"schema_version": 1, "source": "operator", "content": content,
                         "baseline_digest": self.baseline_digest, "routes": list(routes),
                         "base": base, "run_digest": digest(run_id), "utc": utc(),
                         "teaching_source": teaching_source, "observation_digest": observation_digest,
                         "proposal_id": secrets.token_hex(32)}
            if paths is not None:
                candidate.update(paths=paths, routes=[route for path in paths for route in path])
                candidate['content'] = self._candidate_content(candidate)
                content = candidate['content']
            revision = digest(candidate)
            self._write("proposals/" + candidate["proposal_id"] + ".json", candidate, exclusive=True)
            old = self.snapshot(base["current"])["content"]
            return {"proposal_id": candidate["proposal_id"], "base_revision": base["current"],
                    "summary": '\n'.join(' → '.join(ROUTE_LABELS[route] for route in path) for path in (paths or [routes])),
                    "observation_digest": observation_digest, "teaching_source": teaching_source,
                    "candidate_revision": revision, "base_generation": base["generation"],
                    "old": old, "new": content, "diff": "".join(difflib.unified_diff(
                        old.splitlines(True), content.splitlines(True), fromfile="approved", tofile="proposed")),
                    "evidence": ("Operator chat correction compiled locally to generic guidance. " if teaching_source == "operator_chat_correction" else "Operator-selected generic route. ") + ("A redacted native scope observation is referenced; record semantics remain unverified." if observation_digest else "No native source observation available; live target semantics unverified."),
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
            if candidate["content"] != self._candidate_content(candidate):
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
