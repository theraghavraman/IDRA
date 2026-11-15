"""Real FFmpeg regression tests: recovery may discard unjournaled tail, never invent frames."""
from __future__ import annotations

import pytest

from idra.datasets.quality import validate_session
from idra.events.models import State
from idra.media.ffmpeg import inspect_video
from idra.storage.recovery import recover


def test_recovery_reconciles_video_tail_without_inventing_metadata(recorded):
    repo, sid = recorded
    directory = repo.path(sid)
    video = directory / "media/screen.mkv"
    original = inspect_video(video, count_frames=True)["frame_count"]
    if not original or original < 3:
        pytest.skip("Fixture has insufficient frames for tail-loss test")
    journal = directory / "frames.jsonl"
    lines = journal.read_bytes().splitlines(keepends=True)
    journal.write_bytes(b"".join(lines[:-2]))
    manifest = repo.load(sid)
    manifest.state = State.RECORDING
    repo.save(manifest)

    result = recover(repo, sid)
    assert result["video_reconciled"] is True, result
    assert result["video_frames_before"] == original
    assert result["video_frames_after"] == original - 2
    original_backup = directory / result["original_media"]
    assert original_backup.is_file()
    assert inspect_video(original_backup, count_frames=True)["frame_count"] == original
    assert inspect_video(video, count_frames=True)["frame_count"] == original - 2
    assert repo.load(sid).state == State.INTERRUPTED
    assert "RECOVERY_VIDEO_TAIL_TRIMMED" in repo.load(sid).warnings
    quality = validate_session(repo, sid, full_decode=True)
    assert "VIDEO_FRAME_COUNT" not in quality["issue_counts"], quality
    assert quality["status"] != "passed"  # Interruption must be visible
    second = recover(repo, sid)
    assert second["video_reconciled"] is False
    assert len(list((directory / "reports").glob("recovered-video-original-*"))) == 1


def test_recovery_never_invents_frames_when_video_shorter(recorded, monkeypatch):
    repo, sid = recorded
    directory = repo.path(sid)
    count = repo.load(sid).counts["frames"]
    import idra.media.ffmpeg as media
    original_inspect = media.inspect_video
    def fewer_frames(path, ffprobe="ffprobe", *, count_frames=False):
        info = original_inspect(path, ffprobe, count_frames=count_frames)
        if count_frames:
            info["frame_count"] = max(0, count - 1)
        return info
    monkeypatch.setattr(media, "inspect_video", fewer_frames)
    manifest = repo.load(sid)
    manifest.state = State.RECORDING
    repo.save(manifest)
    report = recover(repo, sid)
    assert report["video_reconciled"] is False
    assert report["media_reconciliation"] == "REVIEW_REQUIRED_FRAME_DEFICIT_OR_UNKNOWN"
    assert (directory / "media/screen.mkv").is_file()
    assert "RECOVERY_MEDIA_REQUIRES_REVIEW" in repo.load(sid).warnings
