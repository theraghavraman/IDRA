import json
import threading

import numpy as np
import pytest

from idra.media.ffmpeg import (
    Cancelled,
    MediaError,
    VideoEncoder,
    encoder_command,
    inspect_video,
    transcode,
)
from idra.media.images import blur_score, extract_frames, read_frame, save_png
from idra.storage.files import sha256


def video(recorded):
    repo, sid = recorded
    m = repo.load(sid)
    return repo.path(sid) / m.media, m


def test_real_ffprobe_count_matches_journal(recorded):
    source, m = video(recorded)
    info = inspect_video(source, count_frames=True)
    assert info["frame_count"] == m.counts["frames"]
    assert info["width"] == 320
    assert info["duration_s"] > 0
    assert info["codec"] == "h264"


def test_real_transcode_preserves_original(recorded, tmp_path):
    source, _ = video(recorded)
    original = sha256(source)
    output = tmp_path / "output name ; not-a-command.mp4"
    progress = []
    result = transcode(source, output, width=160, progress=progress.append)
    assert sha256(source) == original
    assert result["output_sha256"] == sha256(output)
    assert result["metadata"]["width"] == 160
    assert result["metadata"]["frame_count"] > 0
    assert progress[-1] == 1


def test_real_clip_reports_playback_time_mapping(recorded, tmp_path):
    source, _ = video(recorded)
    result = transcode(source, tmp_path / "clip.mp4", start_s=0.1, duration_s=0.2)
    assert result["operation"] == "clip"
    assert result["source_start_pts_ns"] == 100_000_000
    assert 0 < result["metadata"]["duration_s"] <= 0.4


@pytest.mark.parametrize(
    "kwargs",
    [{"width": 10}, {"codec": "shell;bad"}, {"crf": -1}, {"start_s": -1}, {"duration_s": 0}],
)
def test_invalid_media_options(recorded, tmp_path, kwargs):
    source, _ = video(recorded)
    with pytest.raises(ValueError):
        transcode(source, tmp_path / "invalid.mp4", **kwargs)


def test_never_overwrite_source_or_existing_output(recorded, tmp_path):
    source, _ = video(recorded)
    with pytest.raises(FileExistsError):
        transcode(source, source)
    target = tmp_path / "existing.mp4"
    target.write_bytes(b"keep")
    with pytest.raises(FileExistsError):
        transcode(source, target)
    assert target.read_bytes() == b"keep"


def test_pre_cancelled_transcode_leaves_no_output(recorded, tmp_path):
    source, _ = video(recorded)
    flag = threading.Event()
    flag.set()
    target = tmp_path / "cancelled.mp4"
    with pytest.raises(Cancelled):
        transcode(source, target, cancel=flag)
    assert not target.exists()
    assert not list(tmp_path.glob("*.partial.mp4"))


def test_corrupt_or_empty_media_rejected(tmp_path):
    target = tmp_path / "bad.mp4"
    with pytest.raises(MediaError):
        inspect_video(target)
    target.write_bytes(b"not a media file\x00")
    with pytest.raises(MediaError):
        inspect_video(target)


def test_encoder_arguments_are_distinct_no_shell(tmp_path):
    target = tmp_path / "a;touch never.mkv"
    cmd = encoder_command("ffmpeg", 320, 240, 5, target)
    assert cmd[-1] == str(target.resolve())
    assert "-f" in cmd and "rawvideo" in cmd
    with pytest.raises(ValueError):
        encoder_command("ffmpeg", 321, 240, 5, target)


def test_actual_streaming_extraction(recorded, tmp_path):
    source, m = video(recorded)
    target = tmp_path / "frames"
    report = extract_frames(source, target, every_n=2, width=160, min_free_mb=1)
    assert report["status"] == "completed"
    assert report["decoded"] == m.counts["frames"]
    rows = [json.loads(s) for s in (target / "frames.jsonl").read_text().splitlines()]
    assert len(rows) == report["saved"]
    assert all(row["source_frame_index"] % 2 == 0 for row in rows)
    assert all(sha256(target / row["file"]) == row["sha256"] for row in rows)
    assert read_frame(source, 0).shape[1] == 320


def test_exact_consecutive_dedup(tmp_path):
    source = tmp_path / "constant.mkv"
    encoder = VideoEncoder(source, 128, 96, 5)
    frame = np.full((96, 128, 3), 100, dtype=np.uint8)
    for _ in range(4):
        encoder.write(frame)
    encoder.finish()
    result = extract_frames(source, tmp_path / "dedup", deduplicate=True, min_free_mb=1)
    assert result["decoded"] == 4
    assert result["saved"] == 1
    assert result["consecutive_duplicates_skipped"] == 3


def test_cancelled_extraction_marks_partial_output(recorded, tmp_path):
    source, _ = video(recorded)
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(Cancelled):
        extract_frames(source, tmp_path / "partial", cancel=cancel, min_free_mb=1)
    report = json.loads((tmp_path / "partial/manifest.json").read_text())
    assert report["status"] == "cancelled"


def test_png_hash_blur_and_invalid_frame_index(recorded, tmp_path):
    source, _ = video(recorded)
    frame = read_frame(source, 0)
    target = tmp_path / "frame.png"
    assert save_png(target, frame) == sha256(target)
    assert blur_score(np.zeros((20, 20, 3), dtype=np.uint8)) == 0
    assert blur_score(frame) >= 0
    with pytest.raises(ValueError):
        read_frame(source, -1)
