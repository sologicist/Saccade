"""Small local Downloads lookup; no browser interception or receipt manager."""
import ctypes
import os
from pathlib import Path

from .business_contract import read_safe, reject


def downloads_folder():
    configured = os.getenv('SACCADE_DOWNLOADS_DIR')
    if configured:
        path = Path(configured)
        if not path.is_absolute():
            reject('downloads_configuration_invalid')
        return path
    if os.name == 'nt':
        # FOLDERID_Downloads, resolved by Windows (including redirected folders).
        import uuid
        identifier = (ctypes.c_byte * 16).from_buffer_copy(uuid.UUID('374DE290-123F-4565-9164-39C4925E467B').bytes_le)
        value = ctypes.c_void_p()
        shell = ctypes.WinDLL('shell32')
        shell.SHGetKnownFolderPath.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)]
        shell.SHGetKnownFolderPath.restype = ctypes.c_long
        if shell.SHGetKnownFolderPath(ctypes.byref(identifier), 0, None, ctypes.byref(value)):
            reject('downloads_folder_unavailable')
        try:
            return Path(ctypes.wstring_at(value))
        finally:
            ctypes.windll.ole32.CoTaskMemFree.argtypes = [ctypes.c_void_p]
            ctypes.windll.ole32.CoTaskMemFree(value)
    return Path.home() / 'Downloads'


def resolve_download(pdf, *, folder=None, since_ns=None):
    """Resolve an exact name or absolute path inside the trusted Downloads root.

    A reported name is only a lookup key. A fresh, stable, completed local PDF
    must exist; no directory search, guessed collision suffix or old-file fallback.
    """
    root = Path(folder) if folder is not None else downloads_folder()
    if not root.is_absolute() or not isinstance(pdf, str) or not pdf:
        reject('invalid_download_path')
    supplied = Path(pdf)
    name = supplied.name
    if not supplied.is_absolute():
        name = pdf
    if not name or any(char in name for char in '/\\:') or name in ('.', '..') or name.endswith((' ', '.')) or any(ord(c) < 32 for c in name):
        reject('invalid_download_filename')
    path = root / name
    if supplied.is_absolute() and supplied != path:
        reject('download_outside_folder')
    if path.suffix.casefold() != '.pdf':
        reject('invalid_download_pdf')
    if path.with_name(name + '.crdownload').exists() or path.with_name(name + '.part').exists():
        reject('download_incomplete')
    try:
        before = path.stat()
    except OSError:
        reject('download_file_missing')
    if since_ns is not None and max(before.st_ctime_ns, before.st_mtime_ns) < since_ns:
        reject('download_stale')
    content = read_safe(root, path, 8 * 1024 * 1024)
    try:
        after = path.stat()
    except OSError:
        reject('download_file_changed')
    if (before.st_size,before.st_mtime_ns,before.st_ctime_ns,before.st_ino) != (after.st_size,after.st_mtime_ns,after.st_ctime_ns,after.st_ino):
        reject('download_file_changed')
    if not content.startswith(b'%PDF-') or b'%%EOF' not in content[-4096:]:
        reject('invalid_download_pdf')
    return str(path.absolute()), content
