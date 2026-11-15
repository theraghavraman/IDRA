from __future__ import annotations

import os
import shutil
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID, uuid4

from idra.events.models import Event, Frame, Manifest, State
from idra.storage.files import SessionLock, StorageError, atomic_json, contained, private_dir


class ClosingConnection(sqlite3.Connection):
    def __exit__(self, *args):
        try:
            return super().__exit__(*args)
        finally:
            self.close()

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS events (
 event_id TEXT PRIMARY KEY, sequence INTEGER NOT NULL UNIQUE,
 t_ns INTEGER NOT NULL, received_t_ns INTEGER NOT NULL,
 type TEXT NOT NULL, data TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS events_time ON events(t_ns, sequence);
CREATE INDEX IF NOT EXISTS events_type_time ON events(type, t_ns, sequence);
CREATE TABLE IF NOT EXISTS frames (
 frame_index INTEGER PRIMARY KEY, t_ns INTEGER NOT NULL,
 pts_ns INTEGER NOT NULL, data TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS frames_time ON frames(t_ns);
"""

def connect_index(directory: Path, readonly=False) -> sqlite3.Connection:
    target = contained(directory, "index.sqlite3")
    if readonly:
        conn = sqlite3.connect(target.resolve().as_uri() + "?mode=ro", uri=True, timeout=10, factory=ClosingConnection)
    else:
        conn = sqlite3.connect(target, timeout=10, factory=ClosingConnection)
        target.chmod(0o600)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=FULL")
        conn.executescript(SCHEMA_SQL)
    conn.row_factory = sqlite3.Row
    return conn

class Repository:
    def __init__(self, root: Path | str):
        candidate = Path(root).expanduser()
        if candidate.is_symlink():
            raise StorageError("Choose a real directory rather than a symlink")
        self.root = private_dir(candidate.resolve())
        private_dir(self.root / "sessions")
        self.database = self.root / "library.sqlite3"
        with self._connect() as c:
            c.execute("""CREATE TABLE IF NOT EXISTS sessions (
              id TEXT PRIMARY KEY, label TEXT NOT NULL, task TEXT NOT NULL,
              created_at TEXT NOT NULL, state TEXT NOT NULL, duration_ns INTEGER NOT NULL,
              frame_count INTEGER NOT NULL, event_count INTEGER NOT NULL, synthetic INTEGER NOT NULL)""")
            c.execute("CREATE INDEX IF NOT EXISTS sessions_created ON sessions(created_at)")
        self.database.chmod(0o600)
    def _connect(self):
        conn = sqlite3.connect(self.database, timeout=10, factory=ClosingConnection)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn
    def path(self, session_id: UUID | str) -> Path:
        sid = str(UUID(str(session_id)))
        return contained(self.root, f"sessions/{sid}")
    def create(self, manifest: Manifest) -> Path:
        directory = self.path(manifest.session_id)
        directory.mkdir(mode=0o700, exist_ok=False)
        for name in ("media/frames", "reports", "exports", "trajectories", "processed", "logs"):
            private_dir(directory / name)
        self.save(manifest)
        return directory
    def load(self, session_id) -> Manifest:
        path = contained(self.path(session_id), "manifest.json")
        manifest = Manifest.model_validate_json(path.read_text(encoding="utf-8"))
        if str(manifest.session_id) != str(UUID(str(session_id))):
            raise ValueError("Manifest identity disagrees with its session directory")
        return manifest
    def save(self, manifest: Manifest):
        directory = self.path(manifest.session_id)
        atomic_json(directory / "manifest.json", manifest.model_dump(mode="json"))
        self.index_manifest(manifest)
    def index_manifest(self, m: Manifest):
        with self._connect() as c:
            c.execute("""INSERT INTO sessions VALUES (?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET label=excluded.label,task=excluded.task,
            created_at=excluded.created_at,state=excluded.state,duration_ns=excluded.duration_ns,
            frame_count=excluded.frame_count,event_count=excluded.event_count,synthetic=excluded.synthetic""",
            (str(m.session_id), m.label, m.task_description, m.created_at.isoformat(), m.state.value,
             m.duration_ns, m.counts.get("frames", 0), m.counts.get("events", 0), int(m.synthetic)))
    def scan(self) -> dict:
        result = {"indexed": 0, "invalid": []}
        for directory in (self.root / "sessions").iterdir():
            if not directory.is_dir() or directory.is_symlink():
                continue
            try:
                m = self.load(UUID(directory.name))
                self.index_manifest(m)
                result["indexed"] += 1
            except (ValueError, OSError, StorageError):
                result["invalid"].append(directory.name)
        return result
    def list(self, search="", limit=500, offset=0, state: str | None = None) -> list[dict]:
        limit = min(max(int(limit), 1), 10000)
        sql = "SELECT * FROM sessions WHERE (label LIKE ? OR task LIKE ? OR id LIKE ?)"
        params: list = [f"%{search}%", f"%{search}%", f"%{search}%"]
        if state and state != "ALL":
            sql += " AND state = ?"
            params.append(state)
        sql += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, max(0, offset)])
        with self._connect() as c:
            rows = c.execute(sql, tuple(params)).fetchall()
        return [dict(row) for row in rows]
    def summary(self) -> dict:
        with self._connect() as c:
            totals = c.execute(
                "SELECT COUNT(*) AS count, COALESCE(SUM(duration_ns),0) AS duration_ns, "
                "COALESCE(SUM(frame_count),0) AS frames, COALESCE(SUM(event_count),0) AS events FROM sessions"
            ).fetchone()
            states = {r["state"]: r["c"] for r in c.execute("SELECT state, COUNT(*) AS c FROM sessions GROUP BY state")}
        return {
            "total_sessions": int(totals["count"] if totals else 0),
            "by_state": states,
            "total_frames": int(totals["frames"] if totals else 0),
            "total_events": int(totals["events"] if totals else 0),
            "total_duration_s": round(float(totals["duration_ns"] if totals else 0) / 1e9, 2),
        }
    def delete(self, session_id, *, confirmed=False):
        if not confirmed:
            raise PermissionError("Explicit deletion confirmation is required")
        directory = self.path(session_id)
        with SessionLock(directory):
            m = self.load(session_id)
            if m.state in {State.STARTING, State.RECORDING, State.PAUSED, State.STOPPING}:
                raise StorageError("Recover an interrupted session before deleting it")
            trash = private_dir(self.root / "trash") / f"{m.session_id}_{uuid4()}"
            os.replace(directory, trash)
            with self._connect() as c:
                c.execute("DELETE FROM sessions WHERE id=?", (str(m.session_id),))
        # Release the lock before removing files, including on Windows.
        shutil.rmtree(trash)
    def retention_candidates(self, days: int) -> list[dict]:
        if days <= 0:
            return []
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        with self._connect() as c:
            return [dict(r) for r in c.execute(
                "SELECT * FROM sessions WHERE created_at<? AND state IN ('COMPLETED','FAILED','INTERRUPTED') ORDER BY created_at",
                (cutoff,))]
    def add_operation(self, session_id, operation: str, details: dict):
        m = self.load(session_id)
        m.operations.append({"at": datetime.now(timezone.utc).isoformat(), "operation": operation, **details})
        self.save(m)

def query_events(directory: Path, event_type: str | None = None, start_ns=0,
                 end_ns: int | None = None, limit=500, offset=0) -> list[Event]:
    sql = "SELECT data FROM events WHERE t_ns>=?"
    args: list = [start_ns]
    if end_ns is not None:
        sql += " AND t_ns<=?"
        args.append(end_ns)
    if event_type:
        sql += " AND type=?"
        args.append(event_type)
    sql += " ORDER BY t_ns,sequence LIMIT ? OFFSET ?"
    args += [min(max(1, limit), 10000), max(0, offset)]
    with connect_index(directory, readonly=True) as c:
        return [Event.model_validate_json(row[0]) for row in c.execute(sql, args)]

def iter_events(directory: Path):
    c = connect_index(directory, readonly=True)
    try:
        for row in c.execute("SELECT data FROM events ORDER BY t_ns,sequence"):
            yield Event.model_validate_json(row[0])
    finally:
        c.close()

def iter_frames(directory: Path):
    c = connect_index(directory, readonly=True)
    try:
        for row in c.execute("SELECT data FROM frames ORDER BY frame_index"):
            yield Frame.model_validate_json(row[0])
    finally:
        c.close()

def neighboring_frames(connection: sqlite3.Connection, t_ns: int, max_distance_ns=3_000_000_000):
    before = connection.execute("SELECT data FROM frames WHERE t_ns<=? ORDER BY t_ns DESC LIMIT 1", (t_ns,)).fetchone()
    after = connection.execute("SELECT data FROM frames WHERE t_ns>=? ORDER BY t_ns LIMIT 1", (t_ns,)).fetchone()
    def parse(row):
        f = Frame.model_validate_json(row[0]) if row else None
        return f if f and abs(f.t_ns - t_ns) <= max_distance_ns else None
    return parse(before), parse(after)
