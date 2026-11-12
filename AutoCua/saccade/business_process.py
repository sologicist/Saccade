"""Bounded single-call child process. Resource limits are not a Python sandbox."""

from __future__ import annotations

import ctypes
import os
import signal
import subprocess
import sys
import threading
import time

from .business_contract import MAX_OUTPUT, dumps, loads, reject


WORKER_BOOTSTRAP = """
import sys, importlib.abc, importlib.machinery, importlib.util
from pathlib import Path
root = Path(sys.argv[1])
sys.path.insert(0, str(root))
class SourceOnlyLoader(importlib.machinery.SourceFileLoader):
    def get_code(self, fullname):
        source = self.get_filename(fullname)
        return self.source_to_code(self.get_data(source), source)
class SourceOnlyFinder(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname != 'AutoCua' and fullname != 'AutoCua.saccade' and not fullname.startswith('AutoCua.saccade.'):
            return None
        candidate = root.joinpath(*fullname.split('.'))
        package = candidate / '__init__.py'
        source = package if package.is_file() else candidate.with_suffix('.py')
        if not source.is_file():
            raise ModuleNotFoundError('Required installed business source is unavailable')
        return importlib.util.spec_from_file_location(fullname, source,
            loader=SourceOnlyLoader(fullname, str(source)),
            submodule_search_locations=[str(candidate)] if source == package else None)
sys.meta_path.insert(0, SourceOnlyFinder())
from AutoCua.saccade.business_worker import main
main()
"""


class WindowsJob:
    """Kill-on-close job, assigned before the child receives any request."""

    def __init__(self, process):
        from ctypes import wintypes as w
        class Basic(ctypes.Structure):
            _fields_ = [("ProcessTime", ctypes.c_int64), ("JobTime", ctypes.c_int64),
                        ("Flags", w.DWORD), ("MinWorkingSet", ctypes.c_size_t),
                        ("MaxWorkingSet", ctypes.c_size_t), ("ActiveProcesses", w.DWORD),
                        ("Affinity", ctypes.c_size_t), ("Priority", w.DWORD), ("Scheduling", w.DWORD)]
        class IO(ctypes.Structure):
            _fields_ = [(name, ctypes.c_uint64) for name in ("ReadOps", "WriteOps", "OtherOps", "ReadBytes", "WriteBytes", "OtherBytes")]
        class Extended(ctypes.Structure):
            _fields_ = [("Basic", Basic), ("IO", IO), ("ProcessMemory", ctypes.c_size_t),
                        ("JobMemory", ctypes.c_size_t), ("PeakProcessMemory", ctypes.c_size_t), ("PeakJobMemory", ctypes.c_size_t)]
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self.kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, w.LPCWSTR]
        self.kernel.CreateJobObjectW.restype = w.HANDLE
        self.kernel.SetInformationJobObject.argtypes = [w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD]
        self.kernel.AssignProcessToJobObject.argtypes = [w.HANDLE, w.HANDLE]
        self.kernel.CloseHandle.argtypes = [w.HANDLE]
        self.handle = self.kernel.CreateJobObjectW(None, None)
        info = Extended()
        info.Basic.Flags = 0x2000 | 0x8  # KILL_ON_JOB_CLOSE and ACTIVE_PROCESS.
        info.Basic.ActiveProcesses = 1  # Approved pure functions have no children.
        if not self.handle or not self.kernel.SetInformationJobObject(self.handle, 9, ctypes.byref(info), ctypes.sizeof(info)) or not self.kernel.AssignProcessToJobObject(self.handle, int(process._handle)):
            self.close()
            reject("worker_job_unavailable")

    def close(self):
        if getattr(self, "handle", None):
            self.kernel.CloseHandle(self.handle)
            self.handle = None


def run_worker(request, *, package_root, stop_event=None, timeout=10.0, output_limit=MAX_OUTPUT):
    deadline = time.monotonic() + timeout
    from AutoCua import IS_COMPILED
    if IS_COMPILED:
        reject("worker_python_runtime_required")
    payload = dumps(request, 131_072).encode()
    if stop_event is not None and stop_event.is_set():
        reject("worker_cancelled")
    # -I excludes cwd/PYTHONPATH/user-site. Only the verified installed package
    # root is added; no model argument can choose it. No credentials are inherited.
    environment = {key: os.environ[key] for key in ("SYSTEMROOT", "WINDIR", "TEMP", "TMP") if key in os.environ}
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    process = subprocess.Popen([sys.executable, "-I", "-B", "-c", WORKER_BOOTSTRAP, str(package_root.parent)],
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               cwd=str(package_root.parent), env=environment, close_fds=True,
                               creationflags=0x08000000 if os.name == "nt" else 0,
                               start_new_session=os.name != "nt")
    job = None
    overflow = threading.Event()
    output = bytearray()
    write_failed = threading.Event()

    def write_request():
        try:
            process.stdin.write(payload)
            process.stdin.close()
        except (OSError, ValueError):
            write_failed.set()

    def drain(stream, destination):
        count = 0
        while True:
            block = stream.read(4096)
            if not block:
                return
            count += len(block)
            if count > output_limit:
                overflow.set()
                return
            if destination is not None:
                destination.extend(block)

    readers = [threading.Thread(target=drain, args=(process.stdout, output), daemon=True),
               threading.Thread(target=drain, args=(process.stderr, None), daemon=True)]
    writer = threading.Thread(target=write_request, daemon=True)
    try:
        if os.name == "nt":
            job = WindowsJob(process)
        for reader in readers:
            reader.start()
        writer.start()
        while process.poll() is None:
            if stop_event is not None and stop_event.is_set():
                reject("worker_cancelled")
            if overflow.is_set():
                reject("worker_output_limit")
            if time.monotonic() >= deadline:
                reject("worker_timeout")
            time.sleep(0.02)  # Releases the GIL; UI stop remains responsive.
        for reader in readers:
            reader.join(timeout=1)
        if overflow.is_set():
            reject("worker_output_limit")
        if process.returncode or write_failed.is_set() or any(reader.is_alive() for reader in readers):
            reject("worker_failed")
        return loads(bytes(output), output_limit)
    finally:
        if job is not None:
            job.close()
        if os.name != "nt":
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        elif process.poll() is None:
            process.kill()
        process.wait(timeout=5)
        if writer.ident is not None:
            writer.join(timeout=1)
        for stream in (process.stdin, process.stdout, process.stderr):
            stream.close()
        for reader in readers:
            if reader.ident is not None:
                reader.join(timeout=1)
