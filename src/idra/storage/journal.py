"""One bounded writer. Journals are fsynced before committing rebuildable indexes."""
from __future__ import annotations
import queue
import threading
import time
from collections import Counter
from pathlib import Path
from idra.events.models import Event, Frame
from idra.storage.files import StorageError, private_open
from idra.storage.repository import connect_index

class Journal:
    def __init__(self, directory: Path, queue_size=8192, batch_size=128, flush_interval=0.5):
        self.directory = directory
        self.queue: queue.Queue[Event | Frame] = queue.Queue(maxsize=queue_size)
        self.batch_size = batch_size
        self.flush_interval = flush_interval
        self._closing = threading.Event()
        self._ready = threading.Event()
        self._stats_lock = threading.Lock()
        self._stats = Counter()
        self.error: str | None = None
        self.thread = threading.Thread(target=self._run, name="idra-journal", daemon=True)
    def start(self):
        self.thread.start()
        if not self._ready.wait(10):
            raise StorageError("Journal initialization timed out")
        if self.error:
            raise StorageError(self.error)
    def submit(self, record: Event | Frame, *, essential=False) -> bool:
        if self._closing.is_set() or self.error:
            return False
        try:
            self.queue.put(record, timeout=2 if essential else 0)
            return True
        except queue.Full:
            with self._stats_lock:
                self._stats["dropped_frames_metadata" if isinstance(record, Frame) else "dropped_events"] += 1
            return False
    def stats(self) -> dict[str, int]:
        with self._stats_lock:
            return dict(self._stats) | {"pending_records": self.queue.qsize()}
    def close(self, timeout=30):
        self._closing.set()
        self.thread.join(timeout)
        if self.thread.is_alive():
            raise StorageError("Journal shutdown timed out; recording remains incomplete")
        if self.error:
            raise StorageError(self.error)
    def _run(self):
        conn = None
        handles = {}
        try:
            conn = connect_index(self.directory)
            handles = {Event: private_open(self.directory / "events.jsonl"),
                       Frame: private_open(self.directory / "frames.jsonl")}
            self._ready.set()
            while not self._closing.is_set() or not self.queue.empty():
                batch = []
                deadline = time.monotonic() + self.flush_interval
                while len(batch) < self.batch_size:
                    if self._closing.is_set() and self.queue.empty():
                        break
                    try:
                        record = self.queue.get(timeout=max(0.01, deadline - time.monotonic()))
                        batch.append(record)
                    except queue.Empty:
                        break
                    if time.monotonic() >= deadline:
                        break
                if not batch:
                    continue
                counts = Counter()
                for record in batch:
                    data = record.model_dump_json()
                    if isinstance(record, Event):
                        cursor = conn.execute("INSERT OR IGNORE INTO events VALUES (?,?,?,?,?,?)",
                            (str(record.event_id), record.sequence, record.t_ns, record.received_t_ns, record.type, data))
                        key = "events"
                    else:
                        cursor = conn.execute("INSERT OR IGNORE INTO frames VALUES (?,?,?,?)",
                            (record.index, record.t_ns, record.pts_ns, data))
                        key = "frames"
                    if cursor.rowcount:
                        handles[type(record)].write(data + "\n")
                        counts[key] += 1
                        if isinstance(record, Event):
                            counts[record.type] += 1
                    else:
                        counts["duplicates_ignored"] += 1
                for handle in handles.values():
                    handle.flush()
                    import os
                    os.fsync(handle.fileno())
                conn.commit()
                with self._stats_lock:
                    self._stats.update(counts)
                for _ in batch:
                    self.queue.task_done()
        except Exception as exc:
            self.error = f"JOURNAL_WRITE_FAILED:{type(exc).__name__}"
            self._ready.set()
        finally:
            for handle in handles.values():
                try:
                    handle.close()
                except OSError:
                    self.error = self.error or "JOURNAL_CLOSE_FAILED"
            if conn is not None:
                conn.close()
