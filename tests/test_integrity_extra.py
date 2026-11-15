import json
from uuid import uuid4

import pytest

from idra.datasets.export import ExportError, export_dataset
from idra.datasets.quality import validate_session
from idra.storage.files import atomic_json
from idra.storage.repository import connect_index


def test_manifest_identity_must_match_directory(recorded):
    repo, sid = recorded
    path = repo.path(sid) / "manifest.json"
    data = json.loads(path.read_text())
    data["session_id"] = str(uuid4())
    atomic_json(path, data)
    with pytest.raises(ValueError, match="identity"):
        repo.load(sid)


def test_missing_indexed_event_blocks_export(recorded, tmp_path):
    repo, sid = recorded
    with connect_index(repo.path(sid)) as c:
        c.execute("DELETE FROM events WHERE sequence=(SELECT MIN(sequence) FROM events)")
    result = validate_session(repo, sid)
    assert result["issue_counts"]["EVENT_INDEX_MISMATCH"] > 0
    assert result["issue_counts"]["INDEX_COUNT_MISMATCH"] > 0
    with pytest.raises(ExportError):
        export_dataset(repo, [sid], tmp_path / "unsafe")


def test_modified_index_payload_detected(recorded):
    repo, sid = recorded
    with connect_index(repo.path(sid)) as c:
        row = c.execute("SELECT event_id,data FROM events LIMIT 1").fetchone()
        data = json.loads(row[1])
        data["t_ns"] += 1
        c.execute("UPDATE events SET data=? WHERE event_id=?", (json.dumps(data), row[0]))
    result = validate_session(repo, sid)
    assert result["issue_counts"]["EVENT_INDEX_MISMATCH"] > 0


def test_missing_indexed_frame_detected(recorded):
    repo, sid = recorded
    with connect_index(repo.path(sid)) as c:
        c.execute("DELETE FROM frames WHERE frame_index=0")
    result = validate_session(repo, sid)
    assert result["issue_counts"]["FRAME_INDEX_MISMATCH"] > 0
