"""Explicit crash recovery. Preserve bad data; never invent a completed session."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path
from uuid import uuid4

from idra.events.models import Event, Frame, State
from idra.storage.files import MAX_JSONL_LINE, SessionLock, atomic_json, contained, sha256
from idra.storage.repository import Repository, connect_index


def repair_partial_tail(path: Path, reports: Path) -> int:
    if not path.exists():
        return 0
    with path.open("rb") as handle:
        good_end = 0
        while True:
            line = handle.readline(MAX_JSONL_LINE + 1)
            if not line:
                return 0
            if len(line) > MAX_JSONL_LINE:
                raise ValueError("An oversized journal line requires manual inspection")
            if not line.endswith(b"\n"):
                quarantine = reports / f"partial_{path.stem}_{uuid4().hex}.bin"
                fd = os.open(quarantine, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(fd, "wb") as q:
                    q.write(line)
                    q.flush()
                    os.fsync(q.fileno())
                with path.open("r+b") as output:
                    output.truncate(good_end)
                    output.flush()
                    os.fsync(output.fileno())
                return len(line)
            good_end = handle.tell()


def _reconcile_trailing_video(directory: Path, candidate: Path, expected_frames: int,
                              ffmpeg: str, ffprobe: str, report: dict) -> Path:
    """Keep original media, and retain only its *proven* journaled prefix in canonical video.

    Never synthesize journal entries. The session remains INTERRUPTED, and the untouched
    video stays in reports for manual inspection. On any failure the original is retained.
    """
    from idra.app.runtime import no_window
    from idra.media.ffmpeg import executable, inspect_video

    info = inspect_video(candidate, ffprobe, count_frames=True)
    actual = info["frame_count"]
    report["video_frames_before"] = actual
    report["journal_frames"] = expected_frames
    report["video_reconciled"] = False
    if actual == expected_frames:
        return candidate
    if actual is None or actual < expected_frames or expected_frames == 0:
        report["media_reconciliation"] = "REVIEW_REQUIRED_FRAME_DEFICIT_OR_UNKNOWN"
        return candidate
    # The decoder can prove the first N frames exist, but we must NOT invent metadata
    # for the surplus encoded tail after the final durable frame-journal write.
    fd, tmp_name = None, directory / "media" / f".reconciled-{uuid4().hex}.mkv"
    try:
        command = [executable(ffmpeg), "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
                   "-protocol_whitelist", "file,pipe", "-i", str(candidate.resolve()),
                   "-map", "0:v:0", "-an", "-frames:v", str(expected_frames),
                   "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                   "-pix_fmt", "yuv420p", "-threads", "2", "-f", "matroska",
                   str(tmp_name.resolve())]
        process = subprocess.run(command, capture_output=True, timeout=180, **no_window())
        if process.returncode:
            raise RuntimeError("FFMPEG_RECOVERY_REENCODE_FAILED")
        tmp_name.chmod(0o600)
        result = inspect_video(tmp_name, ffprobe, count_frames=True)
        if result["frame_count"] != expected_frames or any(
            result[field] != info[field] for field in ("width", "height")
        ):
            raise RuntimeError("RECOVERY_OUTPUT_VERIFICATION_FAILED")
        original_hash = sha256(candidate)
        backup_rel = f"reports/recovered-video-original-{uuid4().hex}.mkv"
        backup = contained(directory, backup_rel)
        canonical = contained(directory, "media/screen.mkv")
        os.replace(candidate, backup)
        try:
            os.replace(tmp_name, canonical)
        except OSError:
            # Never lose the original file if activation of reconciled media fails.
            os.replace(backup, candidate)
            raise
        report["video_reconciled"] = True
        report["media_reconciliation"] = "VIDEO_TAIL_REMOVED_TO_MATCH_DURABLE_JOURNAL"
        report["video_frames_after"] = result["frame_count"]
        report["original_media"] = backup_rel
        report["original_media_sha256"] = original_hash
        report["reconciled_media_sha256"] = sha256(canonical)
        return canonical
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        report["media_reconciliation"] = "REVIEW_REQUIRED_RECONCILIATION_FAILED"
        report["reconciliation_error"] = type(exc).__name__
        return candidate
    finally:
        tmp_name.unlink(missing_ok=True)


def recover(repository: Repository, session_id) -> dict:
    directory = repository.path(session_id)
    with SessionLock(directory):
        manifest = repository.load(session_id)
        report = {"session_id": str(manifest.session_id), "repaired_tail_bytes": 0,
                  "invalid_records": 0, "duplicate_records": 0, "events": 0, "frames": 0,
                  "state": "INTERRUPTED", "media_salvaged": False, "video_reconciled": False}
        for name in ("events.jsonl", "frames.jsonl"):
            report["repaired_tail_bytes"] += repair_partial_tail(directory / name, directory / "reports")
        c = connect_index(directory)
        max_t = 0
        contiguous_frame_prefix = False
        try:
            c.execute("DELETE FROM events")
            c.execute("DELETE FROM frames")
            for name, model in (("events.jsonl", Event), ("frames.jsonl", Frame)):
                path = directory / name
                if not path.exists():
                    continue
                with path.open("rb") as f:
                    for line in f:
                        try:
                            record = model.model_validate_json(line)
                            if record.session_id != manifest.session_id:
                                raise ValueError("Foreign session record")
                            data = record.model_dump_json()
                            if isinstance(record, Event):
                                r = c.execute("INSERT OR IGNORE INTO events VALUES (?,?,?,?,?,?)",
                                    (str(record.event_id), record.sequence, record.t_ns,
                                     record.received_t_ns, record.type, data))
                                key = "events"
                            else:
                                r = c.execute("INSERT OR IGNORE INTO frames VALUES (?,?,?,?)",
                                    (record.index, record.t_ns, record.pts_ns, data))
                                key = "frames"
                            report[key] += int(bool(r.rowcount))
                            report["duplicate_records"] += int(not r.rowcount)
                            max_t = max(max_t, record.t_ns)
                        except (ValueError, TypeError):
                            report["invalid_records"] += 1
            if report["frames"]:
                span = c.execute("SELECT MIN(frame_index),MAX(frame_index) FROM frames").fetchone()
                contiguous_frame_prefix = tuple(span) == (0, report["frames"] - 1)
            c.commit()
        finally:
            c.close()
        from idra.media.ffmpeg import inspect_video
        partial = contained(directory, "media/screen.partial.mkv")
        media = contained(directory, "media/screen.mkv")
        candidate = partial if partial.exists() else media
        report["original_checksums"] = dict(manifest.checksums)
        if candidate.exists():
            try:
                inspect_video(candidate, manifest.settings.ffprobe)
                if contiguous_frame_prefix and report["invalid_records"] == 0 and report["duplicate_records"] == 0:
                    candidate = _reconcile_trailing_video(directory, candidate, report["frames"],
                                                          manifest.settings.ffmpeg,
                                                          manifest.settings.ffprobe, report)
                else:
                    report["media_reconciliation"] = "REVIEW_REQUIRED_INVALID_OR_NONCONTIGUOUS_JOURNAL"
                if candidate == partial:
                    os.replace(partial, media)
                manifest.media = "media/screen.mkv"
                manifest.checksums[manifest.media] = sha256(media)
                report["media_salvaged"] = True
            except (OSError, RuntimeError, ValueError):
                manifest.warnings.append("RECOVERY_MEDIA_NOT_READABLE")
        if report["video_reconciled"] and "RECOVERY_VIDEO_TAIL_TRIMMED" not in manifest.warnings:
            manifest.warnings.append("RECOVERY_VIDEO_TAIL_TRIMMED")
        elif report.get("media_reconciliation", "").startswith("REVIEW_REQUIRED"):
            if "RECOVERY_MEDIA_REQUIRES_REVIEW" not in manifest.warnings:
                manifest.warnings.append("RECOVERY_MEDIA_REQUIRES_REVIEW")
        for name in ("events.jsonl", "frames.jsonl"):
            if (directory / name).exists():
                manifest.checksums[name] = sha256(directory / name)
        manifest.state = State.INTERRUPTED
        manifest.duration_ns = max(manifest.duration_ns, max_t)
        manifest.counts.update({"events": report["events"], "frames": report["frames"]})
        if "RECOVERED_NOT_COMPLETE" not in manifest.warnings:
            manifest.warnings.append("RECOVERED_NOT_COMPLETE")
        manifest.operations.append({"operation": "recovery", **report})
        repository.save(manifest)
        atomic_json(directory / "reports/recovery.json", report)
        return report
