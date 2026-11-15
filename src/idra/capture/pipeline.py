"""Two bounded workers: capture/mask and encode/journal. No GUI-thread I/O."""
from __future__ import annotations

import hashlib
import os
import queue
import shutil
import threading
import time
from collections import Counter
from pathlib import Path

import cv2
import numpy as np

from idra.events.models import Frame, Settings
from idra.media.ffmpeg import MediaError, VideoEncoder
from idra.media.images import blur_score, save_png
from idra.privacy.policy import apply_masks


class CapturePipeline:
    def __init__(self, session_id, directory: Path, clock, settings: Settings, journal,
                 source, is_active, on_failure):
        self.session_id, self.directory, self.clock = session_id, directory, clock
        self.settings, self.journal, self.source = settings, journal, source
        self.is_active, self.on_failure = is_active, on_failure
        self.frames = queue.Queue(maxsize=settings.capture.queue_frames)
        self.stopping = threading.Event()
        self.capture_done = threading.Event()
        self.ready = threading.Event()
        self.stats_lock = threading.Lock()
        self.counters = Counter()
        self.error = None
        self.encoder = None
        self.geometry = {}
        self.media_info = None
        self.capture_thread = threading.Thread(target=self._capture, name="idra-capture", daemon=True)
        self.encode_thread = threading.Thread(target=self._encode, name="idra-encoder", daemon=True)
    def start(self):
        self.encode_thread.start()
        self.capture_thread.start()
        if not self.ready.wait(20):
            self.stopping.set()
            self.source.interrupt()
            raise MediaError("CAPTURE_START_TIMEOUT")
        if self.error:
            raise MediaError(self.error)
    def stats(self):
        with self.stats_lock:
            return dict(self.counters) | {"pending_frames": self.frames.qsize()}
    def _count(self, key, amount=1):
        with self.stats_lock:
            self.counters[key] += amount
    def _fail(self, code):
        self.error = self.error or code
        self.stopping.set()
        self.ready.set()
        self.on_failure(code)
    def _capture(self):
        opened = False
        shape = None
        next_tick = time.monotonic()
        interval = 1 / self.settings.capture.fps
        next_disk_check = 0.0
        try:
            while not self.stopping.is_set():
                if not self.is_active():
                    if opened:
                        self.source.close()
                        opened = False
                    self.stopping.wait(0.05)
                    next_tick = time.monotonic()
                    continue
                if not opened:
                    new_geometry = self.source.open()
                    if self.geometry and any(self.geometry.get(k) != v for k, v in new_geometry.items()):
                        raise MediaError("DISPLAY_GEOMETRY_CHANGED")
                    self.geometry = new_geometry
                    opened = True
                if time.monotonic() >= next_disk_check:
                    if shutil.disk_usage(self.directory).free < self.settings.min_free_mb * 1024 * 1024:
                        raise MediaError("INSUFFICIENT_STORAGE")
                    next_disk_check = time.monotonic() + 1
                started = self.clock.now_ns()
                image = self.source.grab()
                captured = self.clock.now_ns()
                if not self.is_active() or self.stopping.is_set():
                    continue
                if shape is not None and image.shape != shape:
                    raise MediaError("DISPLAY_RESOLUTION_CHANGED")
                shape = image.shape
                width = min(self.settings.capture.output_width, image.shape[1]) // 2 * 2
                height = max(2, round(image.shape[0] * width / image.shape[1]) // 2 * 2)
                if image.shape[1] != width or image.shape[0] != height:
                    image = cv2.resize(image, (width, height), interpolation=cv2.INTER_AREA)
                image = np.ascontiguousarray(apply_masks(image, self.settings.privacy))
                self.geometry.update({"output_width": width, "output_height": height})
                self._count("captured_frames")
                try:
                    self.frames.put_nowait((image, started, captured))
                except queue.Full:
                    self._count("dropped_frames")
                next_tick += interval
                delay = next_tick - time.monotonic()
                if delay < -interval:
                    self._count("missed_capture_deadlines", int(-delay / interval))
                    next_tick = time.monotonic()
                else:
                    self.stopping.wait(max(0, delay))
        except Exception as exc:
            if not self.stopping.is_set():
                code = str(exc) if isinstance(exc, MediaError) else f"CAPTURE_FAILED:{type(exc).__name__}"
                self._fail(code)
        finally:
            try:
                self.source.close()
            finally:
                self.capture_done.set()
    def _encode(self):
        last_screenshot = -10**30
        index = 0
        target = self.directory / "media/screen.partial.mkv"
        try:
            while not self.capture_done.is_set() or not self.frames.empty():
                try:
                    image, started, captured = self.frames.get(timeout=0.1)
                except queue.Empty:
                    continue
                if self.encoder is None:
                    self.encoder = VideoEncoder(target, image.shape[1], image.shape[0],
                        self.settings.capture.fps, self.settings.ffmpeg, self.settings.ffprobe)
                self.encoder.write(image)
                screenshot = None
                checksum = None
                if captured - last_screenshot >= self.settings.capture.screenshot_interval_s * 1e9:
                    screenshot = f"media/frames/frame_{index:08d}.png"
                    checksum = save_png(self.directory / screenshot, image)
                    last_screenshot = captured
                    self._count("screenshots")
                metadata = Frame(session_id=self.session_id, index=index, t_ns=captured,
                    capture_started_t_ns=started, pts_ns=self.clock.media_pts_ns(index, self.settings.capture.fps),
                    width=image.shape[1], height=image.shape[0], screenshot=screenshot, sha256=checksum,
                    timestamp_kind=self.source.timestamp_kind, synthetic=self.source.synthetic,
                    content_sha256=hashlib.sha256(image.tobytes()).hexdigest(), blur_score=blur_score(image))
                if not self.journal.submit(metadata, essential=True):
                    raise MediaError("FRAME_METADATA_COULD_NOT_BE_PERSISTED")
                index += 1
                self._count("encoded_frames")
                self.frames.task_done()
                self.ready.set()
            if self.encoder:
                self.media_info = self.encoder.finish()
                os.replace(target, self.directory / "media/screen.mkv")
            elif not self.error:
                raise MediaError("NO_FRAMES_CAPTURED")
        except Exception as exc:
            self._fail(str(exc) if isinstance(exc, MediaError) else f"ENCODING_FAILED:{type(exc).__name__}")
            if self.encoder:
                self.encoder.abort()
        finally:
            self.ready.set()
    def stop(self):
        self.stopping.set()
        self.source.interrupt()
        self.capture_thread.join(timeout=10)
        if self.capture_thread.is_alive():
            self._fail("CAPTURE_SHUTDOWN_TIMEOUT")
        self.encode_thread.join(timeout=40)
        if self.encode_thread.is_alive():
            if self.encoder:
                self.encoder.abort()
            self.encode_thread.join(timeout=5)
            self._fail("ENCODER_SHUTDOWN_TIMEOUT")
        if self.error:
            raise MediaError(self.error)
