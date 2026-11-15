"""Streaming quality checks with disk-backed duplicate detection and bounded reports."""
from __future__ import annotations

import html
import sqlite3
import subprocess
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from idra.events.models import Event, Frame, QualityThresholds, State
from idra.media.ffmpeg import inspect_video
from idra.privacy.policy import sanitize_payload
from idra.storage.files import SessionLock, atomic_json, contained, iter_jsonl, private_open, sha256
from idra.storage.repository import connect_index


class QualityReport:
    def __init__(self, session_id):
        self.session_id = str(session_id)
        self.metrics = Counter()
        self.codes = Counter()
        self.issues = []
        self.errors = self.warnings = 0
    def add(self, severity, code, message, line=None):
        self.codes[code] += 1
        if severity == "error":
            self.errors += 1
        else:
            self.warnings += 1
        if len(self.issues) < 200:
            self.issues.append({"severity":severity, "code":code, "message":message, "line":line})
    def as_dict(self):
        return {"schema_version":"1.0", "session_id":self.session_id,
                "generated_at":datetime.now(timezone.utc).isoformat(),
                "status":"failed" if self.errors else "passed_with_warnings" if self.warnings else "passed",
                "errors":self.errors, "warnings":self.warnings,
                "metrics":dict(self.metrics), "issue_counts":dict(self.codes), "issues":self.issues,
                "issues_truncated":sum(self.codes.values()) > len(self.issues),
                "limitations":["Passing checks does not establish training suitability or consent for downstream use.",
                    "Visual secrets and free-text secrets cannot be comprehensively detected.",
                    "Browser/input correlation is temporal evidence, not ground truth.",
                    "Blur is a Laplacian-variance heuristic; a static or blank screen may be intentional."]}

def validate_session(repository, session_id, thresholds=None, *, verify_media=True,
                     full_decode=False, write_report=True, _locked=False) -> dict:
    directory = repository.path(session_id)
    if not (directory / "manifest.json").is_file():
        raise FileNotFoundError("Session manifest does not exist")
    if not _locked:
        with SessionLock(directory):
            return validate_session(repository, session_id, thresholds, verify_media=verify_media,
                                    full_decode=full_decode, write_report=write_report, _locked=True)
    threshold = thresholds or QualityThresholds()
    report = QualityReport(session_id)
    try:
        m = repository.load(session_id)
    except (ValueError, OSError):
        report.add("error", "MANIFEST_SCHEMA", "Manifest is missing, unreadable or violates the schema")
        result = report.as_dict()
        if write_report:
            atomic_json(directory / "reports/quality.json", result)
        return result
    if m.state != State.COMPLETED:
        report.add("warning", "INCOMPLETE_SESSION", f"Session state is {m.state.value}; do not infer task success")
    if m.failure_codes:
        report.add("error", "RECORDING_FAILURE", "Recording has recorded failure codes")
    if not m.task_description:
        report.add("warning", "NO_TASK_DESCRIPTION", "No user-provided task description is present")
    if m.counts.get("dropped_events", 0) > threshold.max_dropped_events:
        report.add("error", "DROPPED_EVENTS", "Dropped input events exceed the configured threshold")
    for name in ("dropped_frames", "missed_capture_deadlines", "browser_rejected", "browser_rate_limited"):
        report.metrics[name] = m.counts.get(name, 0)
        if m.counts.get(name, 0):
            report.add("warning", name.upper(), "Capture recorded missing, rejected or delayed observations")
    for warning in m.warnings:
        report.add("warning", "CAPABILITY_LIMITATION", warning)
    with tempfile.TemporaryDirectory(prefix=".quality-", dir=directory / "reports") as tmp:
        conn = sqlite3.connect(Path(tmp) / "checks.sqlite3")
        conn.executescript("""CREATE TABLE ids(id TEXT PRIMARY KEY, sequence INTEGER UNIQUE);
          CREATE TABLE clicks(t INTEGER); CREATE INDEX click_time ON clicks(t);
          CREATE TABLE browser_clicks(t INTEGER); CREATE TABLE pauses(start INTEGER, end INTEGER);""")
        index = None
        try:
            index = connect_index(directory, readonly=True)
            for table in ("events", "frames"):
                report.metrics["indexed_" + table] = index.execute("SELECT COUNT(*) FROM " + table).fetchone()[0]
        except sqlite3.DatabaseError:
            report.add("error", "INDEX_UNREADABLE", "Rebuild the local index from canonical journals using recovery")
            if index is not None:
                index.close()
            index = None
        previous_t = previous_received = previous_sequence = -1
        pause_start = None
        try:
            for line, raw in enumerate(iter_jsonl(directory / "events.jsonl"), 1):
                report.metrics["event_records"] += 1
                try:
                    event = Event.model_validate(raw)
                    if index is not None:
                        indexed = index.execute("SELECT sequence,t_ns,received_t_ns,type,data FROM events WHERE event_id=?", (str(event.event_id),)).fetchone()
                        expected = (event.sequence, event.t_ns, event.received_t_ns, event.type, event.model_dump_json())
                        if indexed is None or tuple(indexed) != expected:
                            report.add("error", "EVENT_INDEX_MISMATCH", "Rebuild the event index from its canonical journal", line)
                    if event.session_id != m.session_id:
                        report.add("error", "EVENT_SESSION_MISMATCH", "Event belongs to another session", line)
                    try:
                        conn.execute("INSERT INTO ids VALUES (?,?)", (str(event.event_id), event.sequence))
                    except sqlite3.IntegrityError:
                        report.add("error", "DUPLICATE_EVENT", "Repeated event ID or sequence number", line)
                    if event.sequence <= previous_sequence:
                        report.add("error", "SEQUENCE_ORDER", "Event sequence numbers must increase in the journal", line)
                    elif previous_sequence >= 0 and event.sequence > previous_sequence + 1:
                        report.add("warning", "SEQUENCE_GAP", "One or more event sequence numbers are absent", line)
                    if event.t_ns < previous_t:
                        report.add("warning", "OCCURRENCE_ORDER", "Occurrence order differs from ingestion order; export sorts by occurrence time", line)
                    if event.received_t_ns < previous_received:
                        report.add("warning", "DELIVERY_ORDER", "Callbacks were delivered out of order", line)
                    if event.t_ns > m.duration_ns + (event.uncertainty_ns or 0):
                        report.add("error", "EVENT_OUTSIDE_SESSION", "Event time exceeds the recorded session duration", line)
                    if sanitize_payload(event.payload, m.settings.privacy) != event.payload:
                        report.add("error", "REDACTION_POLICY", "Event violates the configured telemetry minimization policy", line)
                    if event.payload.text is not None and event.type not in {"annotation", "task_boundary"}:
                        report.add("error", "UNEXPECTED_TEXT", "Only explicit user annotations may contain text", line)
                    if event.type in {"key_press", "key_release"} and event.payload.key_category is None:
                        report.add("error", "KEY_CATEGORY_MISSING", "Keyboard event has no normalized category", line)
                    p = event.payload
                    if p.in_capture:
                        w, h = m.geometry.get("output_width", 0), m.geometry.get("output_height", 0)
                        if p.x_px is None or p.y_px is None or not (0 <= p.x_px < w and 0 <= p.y_px < h):
                            report.add("error", "INVALID_COORDINATES", "In-capture coordinates lie outside the captured image", line)
                    if event.type == "mouse_button_down":
                        conn.execute("INSERT INTO clicks VALUES (?)", (event.t_ns,))
                    if event.type == "browser_action" and p.action == "click":
                        conn.execute("INSERT INTO browser_clicks VALUES (?)", (event.t_ns,))
                    if event.type == "state_change":
                        if p.state == State.PAUSED:
                            pause_start = event.t_ns
                        elif p.state in {State.RECORDING, State.STOPPING} and pause_start is not None:
                            conn.execute("INSERT INTO pauses VALUES (?,?)", (pause_start, event.t_ns))
                            pause_start = None
                    if event.timestamp_kind == "received":
                        report.metrics["receive_timed_events"] += 1
                    previous_t, previous_received, previous_sequence = event.t_ns, event.received_t_ns, event.sequence
                except ValueError:
                    report.add("error", "EVENT_SCHEMA", "Event violates the versioned schema", line)
        except (OSError, RuntimeError, ValueError):
            report.add("error", "EVENT_JOURNAL", "Event journal is missing, malformed or contains a partial write")
        if pause_start is not None:
            conn.execute("INSERT INTO pauses VALUES (?,?)", (pause_start, m.duration_ns))
        previous_frame_time = previous_pts = -1
        expected_index = 0
        try:
            for line, raw in enumerate(iter_jsonl(directory / "frames.jsonl"), 1):
                report.metrics["frame_records"] += 1
                try:
                    frame = Frame.model_validate(raw)
                    if index is not None:
                        indexed = index.execute("SELECT t_ns,pts_ns,data FROM frames WHERE frame_index=?", (frame.index,)).fetchone()
                        if indexed is None or tuple(indexed) != (frame.t_ns, frame.pts_ns, frame.model_dump_json()):
                            report.add("error", "FRAME_INDEX_MISMATCH", "Rebuild the frame index from its canonical journal", line)
                    if frame.session_id != m.session_id:
                        report.add("error", "FRAME_SESSION_MISMATCH", "Frame belongs to another session", line)
                    if frame.index != expected_index:
                        report.add("error", "FRAME_INDEX_GAP", "Frame index is missing, duplicated or out of order", line)
                    expected_index = frame.index + 1
                    if frame.t_ns < previous_frame_time or frame.pts_ns <= previous_pts:
                        report.add("error", "FRAME_TIME_ORDER", "Frame capture/PTS order is inconsistent", line)
                    if frame.t_ns > m.duration_ns:
                        report.add("error", "FRAME_OUTSIDE_SESSION", "Frame occurs outside session duration", line)
                    if previous_frame_time >= 0:
                        paused = conn.execute("SELECT COALESCE(SUM(MIN(end,?)-MAX(start,?)),0) FROM pauses WHERE start<? AND end>?",
                            (frame.t_ns, previous_frame_time, frame.t_ns, previous_frame_time)).fetchone()[0]
                        gap = frame.t_ns - previous_frame_time - paused
                        if gap > threshold.max_gap_s * 1e9:
                            report.add("warning", "CAPTURE_GAP", "A capture gap exceeds the threshold after subtracting pauses", line)
                    if frame.screenshot:
                        try:
                            shot = contained(directory, frame.screenshot)
                            if not shot.is_file():
                                report.add("error", "MISSING_SCREENSHOT", "Referenced screenshot is missing", line)
                            elif frame.sha256 and sha256(shot) != frame.sha256:
                                report.add("error", "SCREENSHOT_CHECKSUM", "Screenshot checksum differs", line)
                        except RuntimeError:
                            report.add("error", "UNSAFE_MEDIA_REFERENCE", "Screenshot reference is unsafe", line)
                    if frame.blur_score < threshold.blur_warning_score:
                        report.metrics["low_detail_frames"] += 1
                    if frame.timestamp_kind == "received":
                        report.metrics["receive_timed_frames"] += 1
                    previous_frame_time, previous_pts = frame.t_ns, frame.pts_ns
                except ValueError:
                    report.add("error", "FRAME_SCHEMA", "Frame violates the versioned schema", line)
        except (OSError, RuntimeError, ValueError):
            report.add("error", "FRAME_JOURNAL", "Frame journal is missing, malformed or incomplete")
        report.metrics["browser_clicks"] = conn.execute("SELECT COUNT(*) FROM browser_clicks").fetchone()[0]
        report.metrics["temporally_correlated_browser_clicks"] = conn.execute("""SELECT COUNT(*) FROM browser_clicks b
           WHERE EXISTS (SELECT 1 FROM clicks c WHERE c.t BETWEEN b.t-250000000 AND b.t+250000000)""").fetchone()[0]
        conn.close()
        if index is not None:
            for table, metric in (("events", "event_records"), ("frames", "frame_records")):
                if report.metrics["indexed_" + table] != report.metrics[metric]:
                    report.add("error", "INDEX_COUNT_MISMATCH", "Index count disagrees with canonical journal")
            index.close()
    if report.metrics["frame_records"] < threshold.min_frames:
        report.add("error", "INSUFFICIENT_FRAMES", "Frame count is below the quality threshold")
    for key, metric in (("events", "event_records"), ("frames", "frame_records")):
        if m.counts.get(key, 0) != report.metrics[metric]:
            report.add("error", "MANIFEST_COUNT_MISMATCH", f"Manifest {key} count disagrees with its journal")
    if report.metrics["low_detail_frames"]:
        report.add("warning", "LOW_DETAIL_FRAMES", "Some frames have low Laplacian variance; inspect rather than assuming blur")
    if report.metrics["receive_timed_frames"] or report.metrics["receive_timed_events"]:
        report.add("error" if threshold.strict_received_timing else "warning", "TIMING_UNCERTAINTY",
                   "Some records use receive time rather than native acquisition time")
    if m.media:
        try:
            media = contained(directory, m.media)
            if not media.is_file():
                report.add("error", "MISSING_VIDEO", "Canonical video is missing")
            elif verify_media:
                info = inspect_video(media, m.settings.ffprobe, count_frames=full_decode)
                if info["frame_count"] is not None and info["frame_count"] != report.metrics["frame_records"]:
                    report.add("error", "VIDEO_FRAME_COUNT", "Video frame count differs from the frame journal")
                report.metrics["media_bytes"] = info["size_bytes"]
                if not full_decode:
                    report.add("warning", "FULL_DECODE_NOT_RUN", "Metadata inspection is not a full video corruption scan")
        except (OSError, RuntimeError, ValueError, subprocess.SubprocessError):
            report.add("error", "VIDEO_INTEGRITY", "Video is unreadable or its reference is unsafe")
    else:
        report.add("error", "NO_VIDEO", "No canonical video is registered")
    for relative, expected in m.checksums.items():
        try:
            path = contained(directory, relative)
            if not path.is_file() or sha256(path) != expected:
                report.add("error", "FILE_CHECKSUM", "A registered artifact is missing or has changed")
        except (OSError, RuntimeError):
            report.add("error", "UNSAFE_CHECKSUM_REFERENCE", "Checksum reference is unsafe or unreadable")
    result = report.as_dict()
    result["thresholds"] = threshold.model_dump()
    if write_report:
        atomic_json(directory / "reports/quality.json", result)
        rows = "".join(
            f"<tr><td>{html.escape(i['severity'])}</td><td>{html.escape(i['code'])}</td>"
            f"<td>{'' if i.get('line') is None else int(i['line'])}</td><td>{html.escape(i['message'])}</td></tr>"
            for i in report.issues
        )
        with private_open(directory / "reports/quality.html", "w") as f:
            f.write(
                f"<!doctype html><meta charset='utf-8'><title>IDRA quality report</title>"
                f"<style>body{{font-family:system-ui,-apple-system,sans-serif;margin:24px;color:#0f172a;background:#f8fafc}}"
                f"table{{border-collapse:collapse;width:100%;background:#fff;border:1px solid #cbd5e1}}"
                f"th,td{{padding:8px 12px;border:1px solid #e2e8f0;text-align:left;font-size:13px}}"
                f"th{{background:#f1f5f9;font-weight:600}}</style>"
                f"<h1>Dataset quality: {html.escape(result['status'])}</h1><p>Session {m.session_id}</p>"
                f"<p>{report.errors} errors, {report.warnings} warnings. Passing does not establish training suitability.</p>"
                f"<table><tr><th>Severity</th><th>Code</th><th>Line</th><th>Finding</th></tr>{rows}</table>"
            )
    return result
