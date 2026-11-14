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

from .dext_learning import ROUTES, ROUTE_LABELS  # Legacy public contracts.
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

    def __init__(self, project_root, platform_id="dext"):
        self.project = Path(project_root)
        from .learning_adapter import load_adapter
        from .platform_config import load_platform
        try:
            platform = load_platform(platform_id, root=self.project)
        except (OSError, ValueError):
            reject("invalid_learning_platform")
        self.platform_id = platform.id
        self.adapter = load_adapter(self.project, platform.id)
        self.root = self.project / "platforms" / platform.id / "data/navigation"
        self.baseline_path = platform.procedure_path
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
            if self.platform_id != "dext":
                initial.update(self._identity(), steps=[])
            revision = self._snapshot(initial)
            if not (self.root / "active.json").exists():
                self._write("active.json", {"schema_version": 1, "current": revision,
                                           "previous": None, "generation": 0}, exclusive=True)
            self._active_locked()

    def _identity(self):
        return {"schema_version": 2, "platform_id": self.platform_id, "adapter_revision": self.adapter.revision}

    def _validate_identity(self, value):
        if value.get("schema_version") == 2:
            if any(value.get(k) != v for k, v in self._identity().items()):
                reject("procedure_platform_mismatch")
        elif value.get("schema_version") != 1 or self.platform_id != "dext":
            reject("procedure_platform_mismatch")

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
            self._active_locked()
            snapshot = self.snapshot(revision)
            path = self._export_markdown(revision, snapshot['content'])
            return read_safe(self.project, path, MAX_PROCEDURE).decode('utf-8')

    def snapshot(self, revision):
        if digest(read_safe(self.project, self.baseline_path, MAX_PROCEDURE).decode("utf-8")) != self.baseline_digest:
            reject("procedure_corrupt")
        value = self._read("snapshots/" + identifier(revision) + ".json")
        if type(value) is not dict or digest(value) != revision or value.get("baseline_digest") != self.baseline_digest:
            reject("procedure_corrupt")
        self._validate_identity(value)
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

    def _active_pointer(self):
        from .learning_adapter import load_adapter
        if load_adapter(self.project, self.platform_id) != self.adapter:
            reject("learning_adapter_changed")
        pointer = self._read("active.json")
        if type(pointer) is not dict or set(pointer) != {"schema_version", "current", "previous", "generation"} or type(pointer["schema_version"]) is not int or pointer["schema_version"] != 1 or type(pointer["generation"]) is not int or pointer["generation"] < 0:
            reject("procedure_corrupt")
        self.snapshot(pointer["current"])
        if pointer["previous"] is not None:
            self.snapshot(pointer["previous"])
        return pointer

    def _sync_learning(self, pointer):
        """Verify the stable projection; recover only a recorded publication gap.

        The journal describes projection progress, never procedure authority.
        Only active.json selects a revision. Unknown Markdown is never adopted
        or overwritten, including text copied from another approved revision.
        """
        content = self.snapshot(pointer['current'])['content'].encode('utf-8')
        path = self.root / 'learning.md'
        existing = read_safe(self.project, path, MAX_PROCEDURE) if path.exists() or path.is_symlink() else None
        journal = self.root / 'learning.projection.json'
        if journal.exists() or journal.is_symlink():
            state = self._read('learning.projection.json')
            if type(state) is not dict or set(state) != {'schema_version', 'current', 'next'} or type(state['schema_version']) is not int or state['schema_version'] != 1:
                reject('learning_projection_corrupt')
            old = state['current']
            target = state['next']
            # Compare complete pointer contracts, not just revision strings.
            for value in (old, target):
                if value is not None:
                    if type(value) is not dict or set(value) != {'schema_version', 'current', 'previous', 'generation'} or type(value['generation']) is not int or value['generation'] < 0 or type(value['schema_version']) is not int or value['schema_version'] != 1:
                        reject('learning_projection_corrupt')
                    self.snapshot(value['current'])
                    if value['previous'] is not None:
                        self.snapshot(value['previous'])
            if old is None or target is not None and (target['previous'] != old['current'] or target['generation'] != old['generation'] + 1):
                reject('learning_projection_corrupt')
            if pointer == old:
                if existing is not None and existing != content:
                    reject('learning_markdown_modified')
            elif target is not None and pointer == target:
                previous = self.snapshot(old['current'])['content'].encode('utf-8')
                if existing is not None and existing not in (previous, content):
                    reject('learning_markdown_modified')
            else:
                reject('learning_projection_corrupt')
        else:
            # First installation or migration from JSON/revision-only PR5.
            if existing is not None and existing != content:
                reject('learning_markdown_modified')
            state = None
        if existing != content:
            self._publish('learning.md', content)
        if read_safe(self.project, path, MAX_PROCEDURE) != content:
            reject('learning_markdown_modified')
        settled = {'schema_version': 1, 'current': pointer, 'next': None}
        if state != settled:
            self._write('learning.projection.json', settled)

    def _active_locked(self):
        pointer = self._active_pointer()
        self._sync_learning(pointer)
        return pointer

    def active(self):
        with self.lock():
            return self._active_locked()

    def _activate(self, current, target):
        self._sync_learning(current)
        # Persist intent before the pointer swap. A crash before activation
        # keeps the old procedure; after it, recovery projects only the target.
        self._write('learning.projection.json', {'schema_version': 1, 'current': current, 'next': target})
        self._write('active.json', target)
        self._sync_learning(target)

    @staticmethod
    def render(routes):
        if type(routes) is not list or not 1 <= len(routes) <= 8 or any(type(route) is not str or route not in ROUTES for route in routes):
            reject("invalid_procedure_routes")
        # Closed grammar prevents private values, page injection and instructions
        # for secrets, scripts, URLs, selectors or enlarged permissions.
        return "# Dext navigation guidance\n\n" + "\n".join(f"{n}. {ROUTES[route]}" for n, route in enumerate(routes, 1)) + "\n"

    def _candidate_content(self, candidate):
        if candidate.get("schema_version") == 2:
            self._validate_identity(candidate)
            paths = candidate.get("step_paths")
            if type(paths) is not list or not 1 <= len(paths) <= 8:
                reject("invalid_procedure_steps")
            content = "# Platform navigation guidance\n\nOperator-assisted paths only; no action, disclosure or download authority.\n"
            inherited = candidate.get('legacy_revision')
            if inherited is not None:
                # Preserve previously approved Dext identity/review cautions
                # without pretending they prove manual section transitions.
                if self.platform_id != 'dext':
                    reject('procedure_platform_mismatch')
                legacy = self._read('snapshots/' + identifier(inherited) + '.json')
                if legacy.get('schema_version') != 1:
                    reject('procedure_corrupt')
                content += '\n## Previously approved guidance\n\n' + self.snapshot(inherited)['content']
            for index, steps in enumerate(paths, 1):
                routes = self.adapter.routes(steps)
                content += f"\n## Operator-assisted path {index}\n\n"
                content += "".join(f"{n}. Ask the operator to open {self.adapter.labels[r]} manually, then reobserve and verify the section heading.\n" for n, r in enumerate(routes, 1))
            if candidate.get("steps") != [step for path in paths for step in path] or len(content.encode()) > MAX_PROCEDURE:
                reject("invalid_procedure_steps")
            return content
        if self.platform_id != "dext":
            reject("procedure_platform_mismatch")
        paths = candidate.get('paths')
        if paths is None:
            return self.render(candidate.get('routes'))
        if type(paths) is not list or not 1 <= len(paths) <= 8:
            reject('invalid_procedure_routes')
        content = '# Dext navigation guidance\n\nOperator-assisted paths only; no action, disclosure or download authority.\n'
        for index, path in enumerate(paths, 1):
            self.render(path)
            content += f'\n## Operator-assisted path {index}\n\n' + '\n'.join(f'{n}. {ROUTES[route]}' for n, route in enumerate(path, 1)) + '\n'
        if candidate.get('routes') != [route for path in paths for route in path] or len(content.encode()) > MAX_PROCEDURE:
            reject('invalid_procedure_routes')
        return content

    def propose(self, routes, run_id, *, teaching_source="route_selection", observation_digest=None, incremental=False, neutral=False):
        if teaching_source not in ("route_selection", "operator_chat_correction"):
            reject("invalid_teaching_source")
        if observation_digest is not None:
            identifier(observation_digest)
        if neutral or self.platform_id != "dext":
            return self.propose_steps(self.adapter.steps(routes), run_id, teaching_source=teaching_source, observation_digest=observation_digest, incremental=incremental)
        content = self.render(routes)
        with self.lock():
            base = self._active_locked()
            paths = None
            if incremental:
                prior = self.snapshot(base['current'])
                paths = ([self.adapter.routes(path) for path in prior['step_paths']] if prior.get('step_paths') else prior.get('paths', [prior['routes']] if prior.get('routes') else []))
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

    def propose_steps(self, steps, run_id, *, teaching_source="operator_chat_correction", observation_digest=None, incremental=True):
        routes = self.adapter.routes(steps)
        if teaching_source not in ("route_selection", "operator_chat_correction"):
            reject("invalid_teaching_source")
        if observation_digest is not None:
            identifier(observation_digest)
        with self.lock():
            base = self._active_locked()
            prior = self.snapshot(base['current'])
            paths = []
            inherited = None
            if incremental and prior['source'] != 'baseline':
                paths = prior.get('step_paths')
                inherited = prior.get('legacy_revision')
                if paths is None:
                    # Old Dext snapshots stay immutable. Conversion happens only
                    # inside a new candidate requiring an independent approval.
                    old_paths = prior.get('paths', [prior['routes']])
                    if all(route in self.adapter.labels for path in old_paths for route in path):
                        paths = [self.adapter.steps(path) for path in old_paths]
                    else:
                        paths, inherited = [], base['current']
                paths = [path for path in paths if self.adapter.routes(path)[0] != routes[0]]
            paths = paths + [steps]
            candidate = {**self._identity(), "source": "operator", "baseline_digest": self.baseline_digest,
                         "step_paths": paths, "steps": [s for path in paths for s in path],
                         "base": base, "run_digest": digest(run_id), "utc": utc(),
                         "teaching_source": teaching_source, "observation_digest": observation_digest,
                         "proposal_id": secrets.token_hex(32)}
            if inherited is not None:
                candidate['legacy_revision'] = inherited
            content = candidate['content'] = self._candidate_content(candidate)
            self._write("proposals/" + candidate['proposal_id'] + ".json", candidate, exclusive=True)
            old = prior['content']
            return {"proposal_id": candidate['proposal_id'], "base_revision": base['current'],
                    "candidate_revision": digest(candidate), "base_generation": base['generation'],
                    "platform_id": self.platform_id, "adapter_revision": self.adapter.revision,
                    "summary": '\n'.join(' -> '.join(self.adapter.labels[r] for r in self.adapter.routes(path)) for path in paths),
                    "teaching_source": teaching_source, "observation_digest": observation_digest,
                    "old": old, "new": content, "diff": ''.join(difflib.unified_diff(old.splitlines(True), content.splitlines(True), fromfile='approved', tofile='proposed'))}

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
            current = self._active_locked()
            if current != candidate["base"] and approve:
                reject("stale_procedure_proposal")
            self._validate_identity(candidate)
            if candidate["content"] != self._candidate_content(candidate):
                reject("procedure_corrupt")
            if approve:
                self._snapshot(candidate)
            self._write(decision, {"approved": approve, "candidate_revision": candidate_revision,
                                   "base": current, "utc": utc()}, exclusive=True)
            if approve:
                self._activate(current, {"schema_version": 1, "current": candidate_revision,
                                         "previous": current["current"], "generation": current["generation"] + 1})
            return self._active_locked()

    def rollback(self, expected, target, run_id):
        # A rollback is a new explicitly reviewed revision, not snapshot mutation.
        with self.lock():
            current = self._active_locked()
            if current["current"] != identifier(expected) or current["previous"] != identifier(target):
                reject("stale_procedure_proposal")
            snapshot = self.snapshot(target)
            candidate = {**snapshot, "rollback_from": current, "utc": utc(), "run_digest": digest(run_id)}
            revision = self._snapshot(candidate)
            self._activate(current, {"schema_version": 1, "current": revision,
                                     "previous": current["current"], "generation": current["generation"] + 1})
            return self._active_locked()

    def pin(self, session_id, *, adopt=False):
        name = "pins/" + digest(session_id) + ".json"
        marker = "pins/" + digest(session_id) + ".bound"
        with self.lock():
            active = self._active_locked()
            present, bound = (self.root / name).exists(), (self.root / marker).exists()
            if present != bound:
                reject("procedure_corrupt")
            if not bound:
                self._write(marker, {"baseline_digest": self.baseline_digest}, exclusive=True)
                self._write(name, {"revision": active["current"], "baseline_digest": self.baseline_digest}, exclusive=True)
            pin = self._read(name)
            if self._read(marker) != {"baseline_digest": self.baseline_digest}:
                reject("procedure_corrupt")
            if set(pin) != {"revision", "baseline_digest"} or pin["baseline_digest"] != self.baseline_digest:
                reject("procedure_corrupt")
            self.snapshot(pin["revision"])
            if adopt:
                pin = {"revision": active["current"], "baseline_digest": self.baseline_digest}
                self._write(name, pin)
            return pin["revision"]
