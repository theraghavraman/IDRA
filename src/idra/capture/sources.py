"""Capture providers. FFmpeg/X11 is an explicit, receive-timestamped fallback."""
from __future__ import annotations

import os
import platform
import re
import subprocess
from typing import Protocol

import numpy as np

from idra.events.models import CaptureConfig
from idra.media.ffmpeg import MediaError, executable


class ScreenSource(Protocol):
    timestamp_kind: str
    geometry: dict
    synthetic: bool
    def open(self) -> dict: ...
    def grab(self): ...
    def close(self): ...
    def interrupt(self): ...

class MSSSource:
    timestamp_kind = "acquisition_complete"
    synthetic = False
    def __init__(self, config: CaptureConfig):
        self.config = config
        self.sct = None
        self.geometry = {}
    def open(self):
        try:
            import mss
        except ImportError as exc:
            raise MediaError("MSS is missing. Install the pinned requirements.") from exc
        self.sct = mss.mss()
        try:
            if self.config.monitor >= len(self.sct.monitors):
                raise MediaError("Selected monitor is not available")
            self.monitor = dict(self.sct.monitors[self.config.monitor])
            self.geometry = dict(self.monitor) | {"monitor": self.config.monitor, "backend": "mss"}
            return self.geometry
        except BaseException:
            self.close()
            raise
    def grab(self):
        if self.sct is None:
            raise MediaError("Screen source is not open")
        raw = self.sct.grab(self.monitor)
        return np.asarray(raw, dtype=np.uint8)[:, :, :3].copy()
    def interrupt(self):
        # Native grab is synchronous; close it on its owning capture thread.
        return None
    def close(self):
        if self.sct is not None:
            self.sct.close()
            self.sct = None

class FFmpegX11Source:
    timestamp_kind = "received"
    synthetic = False
    def __init__(self, config: CaptureConfig, ffmpeg="ffmpeg"):
        self.config, self.ffmpeg = config, ffmpeg
        self.process = None
        self.geometry = {}
    def open(self):
        if platform.system() != "Linux":
            raise MediaError("The FFmpeg X11 fallback is supported only on Linux/X11")
        if os.getenv("XDG_SESSION_TYPE", "").lower() == "wayland":
            raise MediaError("Full Wayland capture is unsupported. Use a supported X11 session.")
        c = self.config
        display = c.x11_display or os.getenv("DISPLAY", "")
        if not re.fullmatch(r":\d+(?:\.\d+)?", display):
            raise MediaError("A local X11 DISPLAY such as :99 is required")
        self.geometry = {"left": c.region_left, "top": c.region_top,
                         "width": c.region_width, "height": c.region_height,
                         "monitor": c.monitor, "backend": "ffmpeg_x11"}
        cmd = [executable(self.ffmpeg), "-nostdin", "-hide_banner", "-loglevel", "error",
            "-f", "x11grab", "-draw_mouse", "1", "-framerate", str(c.fps),
            "-video_size", f"{c.region_width}x{c.region_height}", "-i",
            f"{display}+{c.region_left},{c.region_top}", "-an", "-pix_fmt", "bgr24",
            "-threads", "1", "-f", "rawvideo", "pipe:1"]
        self.process = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                        stderr=subprocess.DEVNULL, bufsize=0)
        return self.geometry
    def grab(self):
        if self.process is None or self.process.stdout is None:
            raise MediaError("X11 source is not open")
        size = self.config.region_width * self.config.region_height * 3
        data = bytearray(size)
        view = memoryview(data)
        offset = 0
        while offset < size:
            n = self.process.stdout.readinto(view[offset:])
            if not n:
                raise MediaError("X11_CAPTURE_FAILED: check the display, region and FFmpeg x11grab support")
            offset += n
        return np.frombuffer(data, dtype=np.uint8).reshape(self.config.region_height, self.config.region_width, 3)
    def interrupt(self):
        p = self.process
        if p is not None and p.poll() is None:
            p.kill()
    def close(self):
        p = self.process
        self.process = None
        if p is not None:
            try:
                if p.poll() is None:
                    p.kill()
                p.wait(timeout=5)
            finally:
                if p.stdout:
                    p.stdout.close()

def enumerate_monitors() -> list[dict]:
    import mss
    with mss.mss() as sct:
        return [dict(m) | {"monitor": i} for i, m in enumerate(sct.monitors) if i]

def source_for(config: CaptureConfig, ffmpeg="ffmpeg"):
    return MSSSource(config) if config.backend == "mss" else FFmpegX11Source(config, ffmpeg)
