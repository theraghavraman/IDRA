"""Real FFmpeg operations with bounded I/O, cancellation and output verification."""
from __future__ import annotations

import json
import os
import queue
import subprocess
import threading
import time
from pathlib import Path
from typing import Callable
from uuid import uuid4

from idra.app.runtime import no_window
from idra.storage.files import private_dir, sha256


class MediaError(RuntimeError):
    pass

class Cancelled(MediaError):
    pass

def executable(name: str) -> str:
    from idra.app.runtime import find_executable
    value = find_executable(name)
    if not value:
        raise MediaError(f"Executable unavailable: {Path(name).name}. Install FFmpeg (for example "
                         f"'brew install ffmpeg' on macOS) or configure its full path in Settings.")
    return value

def inspect_video(path: Path, ffprobe="ffprobe", *, count_frames=False) -> dict:
    if not path.is_file() or path.stat().st_size == 0:
        raise MediaError("Media is missing or empty")
    cmd = [executable(ffprobe), "-v", "error", "-protocol_whitelist", "file,pipe",
           "-select_streams", "v:0", "-show_streams", "-show_format", "-of", "json"]
    if count_frames:
        cmd += ["-count_frames"]
    cmd += [str(path.resolve())]
    result = subprocess.run(cmd, capture_output=True, timeout=300 if count_frames else 30, **no_window())
    if result.returncode:
        raise MediaError("FFPROBE_FAILED: media could not be inspected")
    try:
        data = json.loads(result.stdout)
        stream = data["streams"][0]
        width, height = int(stream["width"]), int(stream["height"])
        if width <= 0 or height <= 0:
            raise ValueError
        raw_duration = stream.get("duration", data.get("format", {}).get("duration", 0))
        duration = float(raw_duration) if raw_duration not in (None, "N/A") else 0.0
        result = {"width": width, "height": height, "duration_s": duration,
                  "codec": stream.get("codec_name"), "pixel_format": stream.get("pix_fmt"),
                  "frame_rate": stream.get("avg_frame_rate"), "size_bytes": path.stat().st_size}
        count = stream.get("nb_read_frames", stream.get("nb_frames"))
        result["frame_count"] = int(count) if count not in (None, "N/A") else None
        return result
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise MediaError("Invalid video metadata") from exc

def encoder_command(ffmpeg: str, width: int, height: int, fps: int, target: Path) -> list[str]:
    if width <= 0 or height <= 0 or width % 2 or height % 2 or fps <= 0:
        raise ValueError("Encoder requires positive even dimensions and a positive frame rate")
    return [executable(ffmpeg), "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
            "-f", "rawvideo", "-pixel_format", "bgr24", "-video_size", f"{width}x{height}",
            "-framerate", str(fps), "-i", "pipe:0", "-an", "-c:v", "libx264",
            "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", "-threads", "2",
            "-f", "matroska", str(target.resolve())]

class VideoEncoder:
    def __init__(self, target: Path, width: int, height: int, fps: int, ffmpeg="ffmpeg", ffprobe="ffprobe"):
        self.target, self.width, self.height, self.fps = target, width, height, fps
        self.ffprobe = ffprobe
        private_dir(target.parent)
        self.error_log = target.with_suffix(".stderr.log")
        fd = os.open(self.error_log, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        self._stderr = os.fdopen(fd, "wb")
        try:
            self.process = subprocess.Popen(encoder_command(ffmpeg, width, height, fps, target),
                stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=self._stderr, bufsize=0, **no_window())
        except BaseException:
            self._stderr.close()
            raise
        self.frames_written = 0
        self._finished = False
    def write(self, image):
        if image.shape != (self.height, self.width, 3) or str(image.dtype) != "uint8":
            raise ValueError("Frame shape or dtype changed")
        if self.process.poll() is not None:
            raise MediaError("ENCODER_EXITED")
        data = memoryview(image.tobytes())
        assert self.process.stdin is not None
        while data:
            n = self.process.stdin.write(data)
            if not n:
                raise MediaError("ENCODER_PIPE_CLOSED")
            data = data[n:]
        self.frames_written += 1
    def finish(self) -> dict:
        if self._finished:
            raise MediaError("Encoder already finalized")
        try:
            if self.process.stdin:
                self.process.stdin.close()
            try:
                code = self.process.wait(timeout=30)
            except subprocess.TimeoutExpired as exc:
                self.abort()
                raise MediaError("ENCODER_FINALIZATION_TIMEOUT") from exc
            if code:
                raise MediaError("ENCODER_FINALIZATION_FAILED")
            self.target.chmod(0o600)
            info = inspect_video(self.target, self.ffprobe, count_frames=True)
            if info["frame_count"] != self.frames_written:
                raise MediaError("ENCODED_FRAME_COUNT_MISMATCH")
            return info
        finally:
            self._finished = True
            self._stderr.close()
    def abort(self):
        if self.process.poll() is None:
            self.process.kill()
        self.process.wait(timeout=10)
        if self.process.stdin and not self.process.stdin.closed:
            self.process.stdin.close()
        if not self._stderr.closed:
            self._stderr.close()

def run_processing(command: list[str], target: Path, *, duration_s=0.0,
                   cancel: threading.Event | None = None,
                   progress: Callable[[float], None] | None = None) -> None:
    cancel = cancel or threading.Event()
    if cancel.is_set():
        raise Cancelled("Media processing cancelled before starting")
    private_dir(target.parent)
    logfile = target.parent / (target.name + ".stderr.log")
    fd = os.open(logfile, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    output: queue.Queue[str] = queue.Queue(maxsize=128)
    with os.fdopen(fd, "wb") as err:
        proc = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=err, text=True, bufsize=1, **no_window())
        def read_progress():
            assert proc.stdout is not None
            for line in proc.stdout:
                try:
                    output.put_nowait(line.strip())
                except queue.Full:
                    pass
        reader = threading.Thread(target=read_progress, daemon=True)
        reader.start()
        try:
            last_progress = time.monotonic()
            while proc.poll() is None:
                if cancel.is_set():
                    raise Cancelled("Media processing cancelled; original media was retained")
                try:
                    line = output.get(timeout=0.1)
                    if line.startswith("out_time_us="):
                        last_progress = time.monotonic()
                        if duration_s > 0 and progress:
                            try:
                                progress(min(0.99, int(line.split("=", 1)[1]) / 1e6 / duration_s))
                            except ValueError:
                                pass
                except queue.Empty:
                    pass
                if time.monotonic() - last_progress > 300:
                    raise MediaError("PROCESSING_STALLED")
            if proc.returncode:
                raise MediaError("FFMPEG_PROCESSING_FAILED")
            if not target.is_file() or target.stat().st_size == 0:
                raise MediaError("No media output was produced")
            target.chmod(0o600)
        except BaseException:
            if proc.poll() is None:
                proc.kill()
            proc.wait(timeout=10)
            target.unlink(missing_ok=True)
            raise
        finally:
            reader.join(timeout=5)
            if proc.stdout:
                proc.stdout.close()

def transcode(source: Path, destination: Path, *, ffmpeg="ffmpeg", ffprobe="ffprobe",
              width: int | None = None, codec="libx264", crf=20,
              start_s: float | None = None, duration_s: float | None = None,
              cancel=None, progress=None) -> dict:
    if codec not in {"libx264", "libx265", "mpeg4"}:
        raise ValueError("Unsupported configured codec")
    if not 0 <= crf <= 51 or (width is not None and width < 64):
        raise ValueError("Invalid media quality or dimensions")
    if destination.exists() or source.resolve() == destination.resolve():
        raise FileExistsError("Choose a new output path; recordings are never overwritten")
    info = inspect_video(source, ffprobe)
    if start_s is not None and (start_s < 0 or start_s >= info["duration_s"]):
        raise ValueError("Clip start must be inside the video playback timeline")
    if duration_s is not None and duration_s <= 0:
        raise ValueError("Clip duration must be positive")
    private_dir(destination.parent)
    temp = destination.with_name(f".{uuid4().hex}.partial.mp4")
    cmd = [executable(ffmpeg), "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
           "-protocol_whitelist", "file,pipe", "-i", str(source.resolve())]
    if start_s is not None:
        cmd += ["-ss", str(start_s)]
    if duration_s is not None:
        cmd += ["-t", str(duration_s)]
    if width:
        cmd += ["-vf", f"scale={width // 2 * 2}:-2"]
    cmd += ["-map", "0:v:0", "-an", "-c:v", codec]
    cmd += ["-q:v", "5"] if codec == "mpeg4" else ["-crf", str(crf), "-preset", "fast"]
    cmd += ["-pix_fmt", "yuv420p", "-threads", "2", "-movflags", "+faststart",
            "-progress", "pipe:1", "-nostats", str(temp.resolve())]
    try:
        run_processing(cmd, temp, duration_s=duration_s or info["duration_s"], cancel=cancel, progress=progress)
        verified = inspect_video(temp, ffprobe, count_frames=True)
        if not verified["frame_count"]:
            raise MediaError("Processed output contains no readable frames")
        os.replace(temp, destination)
        if progress:
            progress(1.0)
        return {"operation": "clip" if start_s is not None else "transcode",
                "source_sha256": sha256(source), "output_sha256": sha256(destination),
                "source_start_pts_ns": int((start_s or 0) * 1e9),
                "timestamp_mapping": "output playback PTS; use source frame index for session time",
                "output": destination.name, "metadata": verified}
    finally:
        temp.unlink(missing_ok=True)
