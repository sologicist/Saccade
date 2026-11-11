"""Cross-process ownership of a Chrome profile for one existing Web run."""

from __future__ import annotations

import hashlib
import os
import stat
import threading

from AutoCua import browser_profile_dir, data_root, normalize_profile_name


_GUARD = threading.RLock()
_HELD: dict[str, "ProfileLease"] = {}


class ProfileBusyError(RuntimeError):
    """Another active run owns the requested Chrome profile."""

    status_code = 409


def _profile_identity(browser_profile: str | None) -> tuple[str | None, str]:
    if browser_profile is None:
        return None, "personal-visible-chrome"
    if not isinstance(browser_profile, str) or not browser_profile:
        raise ValueError("browser_profile must be a non-empty profile name or null.")
    name = normalize_profile_name(browser_profile)
    directory = browser_profile_dir(name).resolve()
    return name, os.path.normcase(str(directory))


def _safe_regular(path) -> None:
    metadata = path.lstat()
    if (
        not stat.S_ISREG(metadata.st_mode)
        or stat.S_ISLNK(metadata.st_mode)
        or getattr(metadata, "st_file_attributes", 0)
        & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    ):
        raise ValueError("The profile lease must be an ordinary local file.")


class ProfileLease:
    """Own an OS-held descriptor lock; release is explicit and idempotent.

    The lock file remains on disk. A stale PID or clock expiry never grants
    ownership; only the OS releasing the descriptor allows a later run.
    """

    def __init__(self, browser_profile: str | None):
        self.browser_profile, self._identity = _profile_identity(browser_profile)
        directory = data_root().resolve() / "web_profile_locks"
        directory.mkdir(parents=True, exist_ok=True)
        metadata = directory.lstat()
        if stat.S_ISLNK(metadata.st_mode) or (
            getattr(metadata, "st_file_attributes", 0)
            & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
        ):
            raise ValueError("The profile lock directory cannot be symbolic.")
        self._path = directory / (hashlib.sha256(self._identity.encode()).hexdigest() + ".lock")
        self._file = None

    def ensure_held(self) -> "ProfileLease":
        """Keep or reacquire this exact lease without stealing another owner."""
        with _GUARD:
            other = _HELD.get(self._identity)
            if other is self and self._file is not None:
                return self
            if other is not None:
                raise ProfileBusyError("Chrome profile is busy with another active agent run.")
            if self._path.exists() or self._path.is_symlink():
                _safe_regular(self._path)
            handle = self._path.open("a+b")
            try:
                _safe_regular(self._path)
                handle.seek(0, os.SEEK_END)
                if handle.tell() == 0:
                    handle.write(b"\0")
                    handle.flush()
                handle.seek(0)
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as error:
                handle.close()
                raise ProfileBusyError("Chrome profile is busy or its lock is unavailable.") from error
            except BaseException:
                handle.close()
                raise
            self._file = handle
            _HELD[self._identity] = self
            return self

    def release(self) -> None:
        """Release ownership after the run has stopped, including error teardown."""
        with _GUARD:
            handle, self._file = self._file, None
            if _HELD.get(self._identity) is self:
                del _HELD[self._identity]
            if handle is not None:
                try:
                    handle.seek(0)
                    if os.name == "nt":
                        import msvcrt
                        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                    else:
                        import fcntl
                        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
                finally:
                    handle.close()

    def __enter__(self) -> "ProfileLease":
        return self.ensure_held()

    def __exit__(self, *_args) -> None:
        self.release()


def acquire_web_profile(browser_profile: str | None) -> ProfileLease:
    """Reserve the actual profile before run startup or return a busy conflict."""
    return ProfileLease(browser_profile).ensure_held()


def validate_web_profile_lease(lease: object, browser_profile: str | None) -> ProfileLease:
    """Accept only a live, registered ownership object for this exact profile."""
    if type(lease) is not ProfileLease:
        raise ValueError("Invalid Chrome profile lease.")
    name, identity = _profile_identity(browser_profile)
    with _GUARD:
        if (
            lease.browser_profile != name
            or lease._identity != identity
            or lease._file is None
            or _HELD.get(identity) is not lease
        ):
            raise ValueError("The Chrome profile lease is not active for this profile.")
    return lease
