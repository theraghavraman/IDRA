import json
import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4
import pytest
from idra.events.models import Event, Payload, State
from idra.storage.files import SessionBusy, SessionLock, StorageError, atomic_json, contained, iter_jsonl
from idra.storage.journal import Journal
from idra.storage.recovery import recover
from idra.storage.repository import connect_index, query_events

def event(sid=None, sequence=0):
    return Event(session_id=sid or uuid4(), sequence=sequence, t_ns=sequence,
                 received_t_ns=sequence, utc=datetime.now(timezone.utc), type="annotation",
                 source="synthetic", synthetic=True, payload=Payload(text="Synthetic test"))

@pytest.mark.parametrize("relative", ["../secret", "/tmp/secret", "sub/../../x", "C:\\secret", "a\\b"])
def test_paths_cannot_escape(tmp_path, relative):
    with pytest.raises(StorageError):
        contained(tmp_path, relative)

def test_symlink_references_refused(tmp_path):
    if not hasattr(os, "symlink"):
        pytest.skip("Platform lacks symlink support")
    target = tmp_path / "outside"
    target.mkdir()
    (tmp_path / "alias").symlink_to(target, target_is_directory=True)
    with pytest.raises(StorageError):
        contained(tmp_path, "alias/file.txt")

def test_atomic_manifest_and_private_permissions(tmp_path):
    target = tmp_path / "private" / "manifest.json"
    atomic_json(target, {"version":1})
    atomic_json(target, {"version":2})
    assert json.loads(target.read_text()) == {"version":2}
    assert not list(target.parent.glob(".atomic-*"))
    if os.name == "posix":
        assert target.stat().st_mode & 0o777 == 0o600
        assert target.parent.stat().st_mode & 0o777 == 0o700

def test_exclusive_lock(tmp_path):
    with SessionLock(tmp_path):
        with pytest.raises(SessionBusy):
            SessionLock(tmp_path).acquire()
    with SessionLock(tmp_path):
        pass

def test_journal_persists_and_prevents_duplicate_ids(tmp_path):
    j = Journal(tmp_path, batch_size=4, flush_interval=.05)
    j.start()
    e = event()
    assert j.submit(e)
    assert j.submit(e)
    j.close()
    assert len(list(iter_jsonl(tmp_path / "events.jsonl"))) == 1
    assert j.stats()["duplicates_ignored"] == 1
    with connect_index(tmp_path, readonly=True) as c:
        assert c.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 1

def test_queue_is_bounded_and_counts_drops(tmp_path):
    j = Journal(tmp_path, queue_size=1)
    assert j.submit(event())
    assert not j.submit(event(sequence=1))
    assert j.stats()["dropped_events"] == 1

def test_writer_failure_is_not_success(tmp_path, monkeypatch):
    import idra.storage.journal as module
    def fail(_):
        raise OSError("Controlled write failure")
    monkeypatch.setattr(module, "connect_index", fail)
    j = Journal(tmp_path)
    with pytest.raises(StorageError, match="JOURNAL_WRITE_FAILED"):
        j.start()
    assert j.error is not None

def test_recovery_preserves_partial_tail_and_is_idempotent(recorded):
    repo, sid = recorded
    directory = repo.path(sid)
    count = repo.load(sid).counts["events"]
    partial = b'{"partial":'
    with (directory / "events.jsonl").open("ab") as f:
        f.write(partial)
    m = repo.load(sid)
    m.state = State.RECORDING
    repo.save(m)
    first = recover(repo, sid)
    second = recover(repo, sid)
    assert first["repaired_tail_bytes"] == len(partial)
    assert second["repaired_tail_bytes"] == 0
    assert first["events"] == second["events"] == count
    assert repo.load(sid).state == State.INTERRUPTED
    quarantined = list((directory / "reports").glob("partial_*.bin"))
    assert quarantined and quarantined[0].read_bytes() == partial

def test_recovery_refuses_an_active_session(recorded):
    repo, sid = recorded
    with SessionLock(repo.path(sid)):
        with pytest.raises(SessionBusy):
            recover(repo, sid)

def test_deletion_requires_confirmation(recorded):
    repo, sid = recorded
    with pytest.raises(PermissionError):
        repo.delete(sid)
    assert repo.path(sid).exists()
    repo.delete(sid, confirmed=True)
    assert not repo.path(sid).exists()
    assert repo.list() == []

def test_retention_only_previews_eligible_sessions(recorded):
    repo, sid = recorded
    m = repo.load(sid)
    m.created_at = datetime.now(timezone.utc) - timedelta(days=40)
    repo.save(m)
    assert [r["id"] for r in repo.retention_candidates(30)] == [sid]
    assert repo.path(sid).exists()
    assert repo.retention_candidates(0) == []

def test_index_filters_and_pagination(recorded):
    repo, sid = recorded
    rows = query_events(repo.path(sid), "mouse_button_down", limit=1)
    assert len(rows) == 1 and rows[0].type == "mouse_button_down"
    following = query_events(repo.path(sid), "mouse_button_down", limit=1, offset=1)
    assert following and following[0].event_id != rows[0].event_id
