from __future__ import annotations
import hashlib
import os
import threading
from pathlib import Path
from uuid import uuid4
import cv2
from idra.media.ffmpeg import Cancelled, MediaError
from idra.storage.files import atomic_json, private_dir, private_open

def blur_score(image) -> float:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())

def save_png(path: Path, image) -> str:
    ok, encoded = cv2.imencode(".png", image, [cv2.IMWRITE_PNG_COMPRESSION, 3])
    if not ok:
        raise MediaError("PNG_ENCODING_FAILED")
    data = encoded.tobytes()
    temp = path.with_name(f".{uuid4().hex}.png")
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, path)
        return hashlib.sha256(data).hexdigest()
    finally:
        temp.unlink(missing_ok=True)

def read_frame(path: Path, index: int):
    if index < 0:
        raise ValueError("Negative frame index")
    cap = cv2.VideoCapture(str(path))
    try:
        if not cap.isOpened():
            raise MediaError("OpenCV could not open this video")
        cap.set(cv2.CAP_PROP_POS_FRAMES, index)
        ok, image = cap.read()
        if not ok:
            raise MediaError("Requested frame could not be decoded")
        return image
    finally:
        cap.release()

def extract_frames(source: Path, target: Path, *, every_n=1, width=None,
                   deduplicate=False, cancel: threading.Event | None = None,
                   progress=None, min_free_mb=256) -> dict:
    import json
    import shutil
    if every_n < 1 or (width is not None and width < 64):
        raise ValueError("Invalid frame extraction settings")
    if target.exists():
        raise FileExistsError("Extraction destination already exists")
    private_dir(target)
    cap = cv2.VideoCapture(str(source))
    result = {"source": source.name, "every_n": every_n, "decoded": 0, "saved": 0,
              "consecutive_duplicates_skipped": 0, "status": "processing",
              "timestamp_semantics": "source frame index; join with source frames.jsonl for session time"}
    try:
        if not cap.isOpened():
            raise MediaError("OpenCV could not open the source")
        total = max(1, int(cap.get(cv2.CAP_PROP_FRAME_COUNT)))
        last_hash = None
        with private_open(target / "frames.jsonl", "w") as out:
            while True:
                if cancel and cancel.is_set():
                    raise Cancelled("Frame extraction cancelled")
                ok, image = cap.read()
                if not ok:
                    break
                index = result["decoded"]
                result["decoded"] += 1
                if index % every_n:
                    continue
                if shutil.disk_usage(target).free < min_free_mb * 1024 * 1024:
                    raise MediaError("INSUFFICIENT_STORAGE")
                if width:
                    height = max(1, round(image.shape[0] * width / image.shape[1]))
                    image = cv2.resize(image, (width, height), interpolation=cv2.INTER_AREA)
                digest = hashlib.sha256(image.tobytes()).hexdigest()
                if deduplicate and digest == last_hash:
                    result["consecutive_duplicates_skipped"] += 1
                    continue
                last_hash = digest
                name = f"frame_{index:08d}.png"
                checksum = save_png(target / name, image)
                out.write(json.dumps({"source_frame_index": index, "file": name,
                    "sha256": checksum, "blur_score": blur_score(image)}) + "\n")
                result["saved"] += 1
                if progress:
                    progress(min(0.99, result["decoded"] / total))
        if result["decoded"] == 0:
            raise MediaError("No frames could be decoded")
        if result["decoded"] < total:
            raise MediaError("DECODE_ENDED_BEFORE_REPORTED_FRAME_COUNT")
        result["status"] = "completed"
        if progress:
            progress(1.0)
        return result
    except Exception as exc:
        result["status"] = "cancelled" if isinstance(exc, Cancelled) else "failed"
        result["error_code"] = type(exc).__name__
        raise
    finally:
        cap.release()
        atomic_json(target / "manifest.json", result)
