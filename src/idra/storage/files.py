"""Restrictive files, atomic replacement, safe relative paths, streaming JSONL."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Iterator

MAX_JSONL_LINE = 8 * 1024 * 1024

class StorageError(RuntimeError):
    pass

class SessionBusy(StorageError):
    pass

def private_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.is_symlink():
        raise StorageError("Refusing a symlinked storage directory")
    if os.name == "posix":
        path.chmod(0o700)
    return path

def contained(root: Path, relative: str) -> Path:
    p = Path(relative)
    if p.is_absolute() or ".." in p.parts or "\\" in relative or ":" in relative:
        raise StorageError("Unsafe relative path")
    base = root.resolve()
    candidate = root / p
    cursor = root
    for part in p.parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise StorageError("Symlinks are not accepted in session artifacts")
    resolved = candidate.resolve()
    if not resolved.is_relative_to(base):
        raise StorageError("Path escapes the session")
    return candidate

def sync_dir(path: Path):
    if os.name == "posix":
        fd = os.open(path, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)

def atomic_json(path: Path, data):
    private_dir(path.parent)
    fd, name = tempfile.mkstemp(prefix=".atomic-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2, allow_nan=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(name, path)
        sync_dir(path.parent)
    except BaseException:
        Path(name).unlink(missing_ok=True)
        raise

def private_open(path: Path, mode="a"):
    private_dir(path.parent)
    if path.is_symlink():
        raise StorageError("Refusing symlinked file")
    flags = os.O_CREAT | os.O_WRONLY | (os.O_APPEND if mode == "a" else os.O_TRUNC)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags, 0o600)
    return os.fdopen(fd, mode, encoding="utf-8", newline="\n")

def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def iter_jsonl(path: Path) -> Iterator[dict]:
    with path.open("rb") as handle:
        line_no = 0
        while True:
            line = handle.readline(MAX_JSONL_LINE + 1)
            if not line:
                break
            line_no += 1
            if len(line) > MAX_JSONL_LINE or not line.endswith(b"\n"):
                raise StorageError(f"Oversized or incomplete JSONL line {line_no}")
            try:
                value = json.loads(line)
            except (ValueError, UnicodeError) as exc:
                raise StorageError(f"Invalid JSONL line {line_no}") from exc
            if not isinstance(value, dict):
                raise StorageError(f"Expected a JSON object at line {line_no}")
            yield value

class SessionLock:
    """Cross-process advisory lock; process death releases the OS lock."""
    def __init__(self, directory: Path):
        self.directory = directory
        self.handle = None
    def acquire(self):
        private_dir(self.directory)
        path = contained(self.directory, ".session.lock")
        fd = os.open(path, os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
        self.handle = os.fdopen(fd, "r+b", buffering=0)
        try:
            if os.name == "nt":
                import msvcrt
                if path.stat().st_size == 0:
                    self.handle.write(b"0")
                self.handle.seek(0)
                msvcrt.locking(self.handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            self.handle.close()
            self.handle = None
            raise SessionBusy("Session is currently in use") from exc
        return self
    def release(self):
        if self.handle is not None:
            try:
                if os.name == "nt":
                    import msvcrt
                    self.handle.seek(0)
                    msvcrt.locking(self.handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
            finally:
                self.handle.close()
                self.handle = None
    def __enter__(self):
        return self.acquire()
    def __exit__(self, *args):
        self.release()
