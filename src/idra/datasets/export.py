"""Portable, atomic datasets, explicit media review, stable leakage-aware split assignment."""
from __future__ import annotations
import csv
import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
from contextlib import ExitStack
from pathlib import Path
from uuid import UUID, uuid4
from idra.datasets.quality import validate_session
from idra.events.models import Event, Frame, SegmentationConfig, State, Trajectory
from idra.media.ffmpeg import Cancelled
from idra.privacy.policy import safe_csv, sanitize_payload
from idra.segmentation.trajectories import trajectories
from idra.storage.files import SessionLock, atomic_json, contained, iter_jsonl, private_dir, private_open, sha256
from idra.storage.repository import iter_events, iter_frames

class ExportFrame(Frame):
    media_available: bool = False

class ExportError(RuntimeError):
    pass

def assign_split(key: str, ratios=(0.8, 0.1, 0.1), seed="idra-v1") -> str:
    if len(ratios) != 3 or any(r < 0 for r in ratios) or abs(sum(ratios) - 1) > 1e-9:
        raise ValueError("Train/validation/test ratios must be nonnegative and sum to 1")
    fraction = int.from_bytes(hashlib.sha256(f"{seed}:{key}".encode()).digest()[:8], "big") / 2**64
    return "train" if fraction < ratios[0] else "validation" if fraction < ratios[0] + ratios[1] else "test"

def _copy(source: Path, target: Path, cancel) -> str:
    private_dir(target.parent)
    h = hashlib.sha256()
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with source.open("rb") as src, os.fdopen(fd, "wb") as dst:
        for chunk in iter(lambda: src.read(1024 * 1024), b""):
            if cancel and cancel.is_set():
                raise Cancelled("Dataset export cancelled")
            dst.write(chunk)
            h.update(chunk)
        dst.flush()
        os.fsync(dst.fileno())
    return h.hexdigest()

def export_dataset(repository, session_ids, target: Path, *, config=None, include_media=False,
                   media_reviewed=False, allow_incomplete=False, ratios=(0.8, 0.1, 0.1),
                   split_unit="session", seed="idra-v1", cancel=None, progress=None) -> dict:
    config = config or SegmentationConfig()
    ids = sorted({str(UUID(str(i))) for i in session_ids})
    if not ids:
        raise ValueError("Select at least one session")
    if split_unit not in {"session", "task"}:
        raise ValueError("Split unit must be session or task")
    assign_split("validation", ratios, seed)
    if include_media and not media_reviewed:
        raise PermissionError("Review the visible media and explicitly authorize its inclusion before exporting it")
    target = Path(target).expanduser().absolute()
    if target.exists():
        raise FileExistsError("Export target already exists")
    private_dir(target.parent)
    staging = private_dir(target.parent / f".{target.name}.{uuid4().hex}.partial")
    counts = {"sessions":len(ids), "events":0, "frames":0, "trajectories":0, "assets":0}
    splits = {"train":0, "validation":0, "test":0}
    sessions = []
    source_manifests = []
    try:
        with ExitStack() as stack:
            for sid in ids:
                directory = repository.path(sid)
                if not (directory / "manifest.json").is_file():
                    raise FileNotFoundError("Selected session is missing")
                stack.enter_context(SessionLock(directory))
            outputs = {name: stack.enter_context(private_open(staging / name, "w")) for name in
                       ("events.jsonl", "frames.jsonl", "trajectories.jsonl", "splits.jsonl", "assets.jsonl", "events.csv")}
            csv_out = csv.writer(outputs["events.csv"], lineterminator="\n")
            csv_out.writerow(["session_id", "event_id", "sequence", "t_ns", "utc", "type", "source", "payload_json"])
            for session_number, sid in enumerate(ids):
                if cancel and cancel.is_set():
                    raise Cancelled("Dataset export cancelled")
                m = repository.load(sid)
                directory = repository.path(sid)
                if m.state != State.COMPLETED and not allow_incomplete:
                    raise ExportError("Incomplete sessions require explicit allow_incomplete authorization")
                quality = validate_session(repository, sid, _locked=True)
                if quality["errors"]:
                    raise ExportError(f"Session {sid} failed quality validation; inspect reports/quality.json")
                source_manifests.append(m)
                relative_media = f"sessions/{sid}/{m.media}" if include_media and m.media else None
                sessions.append({"session_id":sid, "label":m.label, "task_description":m.task_description,
                    "created_at":m.created_at.isoformat(), "duration_ns":m.duration_ns,
                    "synthetic":m.synthetic, "source_state":m.state.value, "geometry":m.geometry,
                    "media":relative_media, "source_manifest_sha256":sha256(directory / "manifest.json"),
                    "privacy":m.settings.privacy.model_dump(mode="json"), "quality_status":quality["status"]})
                for event in iter_events(directory):
                    if cancel and cancel.is_set():
                        raise Cancelled("Dataset export cancelled")
                    event.payload = sanitize_payload(event.payload, m.settings.privacy)
                    outputs["events.jsonl"].write(event.model_dump_json() + "\n")
                    csv_out.writerow([safe_csv(v) for v in [sid, str(event.event_id), event.sequence, event.t_ns,
                        event.utc.isoformat(), event.type, event.source, event.payload.model_dump_json(exclude_none=True)]])
                    counts["events"] += 1
                for frame in iter_frames(directory):
                    if cancel and cancel.is_set():
                        raise Cancelled("Dataset export cancelled")
                    data = frame.model_dump()
                    data["media_available"] = include_media
                    if frame.screenshot and include_media:
                        relative = f"sessions/{sid}/{frame.screenshot}"
                        source = contained(directory, frame.screenshot)
                        checksum = _copy(source, contained(staging, relative), cancel)
                        outputs["assets.jsonl"].write(json.dumps({"path":relative, "sha256":checksum, "size_bytes":source.stat().st_size}) + "\n")
                        counts["assets"] += 1
                        data["screenshot"] = relative
                    else:
                        data["screenshot"] = None
                    outputs["frames.jsonl"].write(ExportFrame.model_validate(data).model_dump_json() + "\n")
                    counts["frames"] += 1
                if relative_media:
                    source = contained(directory, m.media)
                    checksum = _copy(source, contained(staging, relative_media), cancel)
                    outputs["assets.jsonl"].write(json.dumps({"path":relative_media, "sha256":checksum, "size_bytes":source.stat().st_size}) + "\n")
                    counts["assets"] += 1
                for trajectory in trajectories(directory, m, config, media_available=include_media):
                    if cancel and cancel.is_set():
                        raise Cancelled("Dataset export cancelled")
                    key = sid if split_unit == "session" else f"{sid}:{trajectory.quality['task_group_id']}"
                    split = assign_split(key, ratios, seed)
                    outputs["trajectories.jsonl"].write(trajectory.model_dump_json() + "\n")
                    outputs["splits.jsonl"].write(json.dumps({"trajectory_id":str(trajectory.trajectory_id),
                        "session_id":sid, "task_group_id":trajectory.quality["task_group_id"], "split":split}) + "\n")
                    counts["trajectories"] += 1
                    splits[split] += 1
                atomic_json(staging / f"sessions/{sid}/quality.json", quality)
                if progress:
                    progress(0.85 * (session_number + 1) / len(ids))
            for handle in outputs.values():
                handle.flush()
                os.fsync(handle.fileno())
            # Close streams before verification/rename, also on Windows.
            for handle in outputs.values():
                handle.close()
            names = list(outputs) + [f"sessions/{sid}/quality.json" for sid in ids]
            manifest = {"schema_version":"1.0", "format":"idra-portable-dataset", "application_version":"0.9.3",
                "media_included":include_media, "media_review_attested":bool(include_media and media_reviewed),
                "counts":counts, "sessions":sessions, "segmentation":config.model_dump(),
                "splitting":{"unit":split_unit, "ratios":list(ratios), "seed":seed, "counts":splits,
                             "same_session_across_splits_possible":split_unit == "task"},
                "checksums":{name:sha256(contained(staging, name)) for name in names},
                "timestamp_semantics":"t_ns is elapsed monotonic session time; pts_ns is nominal CFR playback time; frame index is authoritative",
                "limitations":["Media review is a user attestation, not automatic visual-secret detection.",
                                "Schema/quality checks do not establish training suitability.",
                                "Deterministic hashing may leave small datasets with an empty split."]}
            atomic_json(staging / "manifest.json", manifest)
            result = verify_export(staging)
            if cancel and cancel.is_set():
                raise Cancelled("Dataset export cancelled")
            os.replace(staging, target)
            for m in source_manifests:
                repository.add_operation(m.session_id, "dataset_export",
                    {"export_name":target.name, "media_included":include_media,
                     "dataset_manifest_sha256":sha256(target / "manifest.json")})
            if progress:
                progress(1.0)
            return {"path":str(target), "manifest":manifest, "verification":result}
    except BaseException:
        if staging.exists():
            shutil.rmtree(staging)
        raise

def verify_export(directory: Path) -> dict:
    m = json.loads(contained(directory, "manifest.json").read_text())
    if m.get("schema_version") != "1.0" or m.get("format") != "idra-portable-dataset":
        raise ExportError("Unknown dataset schema or format")
    ids = {s["session_id"] for s in m["sessions"]}
    for relative, expected in m["checksums"].items():
        path = contained(directory, relative)
        if not path.is_file() or sha256(path) != expected:
            raise ExportError("Dataset checksum validation failed")
    actual = {"events":0, "frames":0, "trajectories":0, "assets":0}
    with tempfile.TemporaryDirectory(prefix="idra-verify-") as tmp:
        c = sqlite3.connect(Path(tmp) / "verify.sqlite3")
        c.executescript("CREATE TABLE e(id TEXT PRIMARY KEY,sid TEXT,t INTEGER,type TEXT); CREATE TABLE f(sid TEXT,i INTEGER,PRIMARY KEY(sid,i)); CREATE TABLE t(id TEXT PRIMARY KEY,sid TEXT); CREATE TABLE splits(id TEXT PRIMARY KEY);")
        try:
            for raw in iter_jsonl(directory / "events.jsonl"):
                e = Event.model_validate(raw)
                if str(e.session_id) not in ids:
                    raise ExportError("Unknown event session")
                c.execute("INSERT INTO e VALUES (?,?,?,?)", (str(e.event_id), str(e.session_id), e.t_ns, e.type))
                actual["events"] += 1
            for raw in iter_jsonl(directory / "frames.jsonl"):
                f = ExportFrame.model_validate(raw)
                if str(f.session_id) not in ids or f.media_available != m["media_included"]:
                    raise ExportError("Frame provenance/media policy mismatch")
                if f.screenshot and not contained(directory, f.screenshot).is_file():
                    raise ExportError("Export references missing screenshot")
                c.execute("INSERT INTO f VALUES (?,?)", (str(f.session_id), f.index))
                actual["frames"] += 1
            for raw in iter_jsonl(directory / "trajectories.jsonl"):
                t = Trajectory.model_validate(raw)
                if str(t.session_id) not in ids:
                    raise ExportError("Unknown trajectory session")
                c.execute("INSERT INTO t VALUES (?,?)", (str(t.trajectory_id), str(t.session_id)))
                for action in t.actions:
                    ref = c.execute("SELECT sid,t,type FROM e WHERE id=?", (str(action.event_id),)).fetchone()
                    if ref != (str(t.session_id), action.t_ns, action.type):
                        raise ExportError("Trajectory action reference mismatch")
                    for index in (action.before_frame, action.after_frame):
                        if index is not None and not c.execute("SELECT 1 FROM f WHERE sid=? AND i=?", (str(t.session_id), index)).fetchone():
                            raise ExportError("Trajectory references missing frame metadata")
                actual["trajectories"] += 1
            for split in iter_jsonl(directory / "splits.jsonl"):
                if split["split"] not in {"train", "validation", "test"}:
                    raise ExportError("Invalid split name")
                ref = c.execute("SELECT sid FROM t WHERE id=?", (split["trajectory_id"],)).fetchone()
                if ref != (split["session_id"],):
                    raise ExportError("Split references an unknown trajectory")
                c.execute("INSERT INTO splits VALUES (?)", (split["trajectory_id"],))
            if c.execute("SELECT COUNT(*) FROM splits").fetchone()[0] != actual["trajectories"]:
                raise ExportError("Missing split assignments")
        except sqlite3.IntegrityError as exc:
            raise ExportError("Duplicate dataset record") from exc
        finally:
            c.close()
    for asset in iter_jsonl(directory / "assets.jsonl"):
        path = contained(directory, asset["path"])
        if not path.is_file() or path.stat().st_size != asset["size_bytes"] or sha256(path) != asset["sha256"]:
            raise ExportError("Media integrity check failed")
        actual["assets"] += 1
    for name, value in actual.items():
        if value != m["counts"][name]:
            raise ExportError("Dataset manifest count mismatch")
    return {"status":"passed", "counts":actual, "checks":["checksums", "schemas", "action/frame references", "split references", "media integrity"]}
