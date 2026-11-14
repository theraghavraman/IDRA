"""A single monotonic timebase; pauses never rewrite historical timestamps."""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
from time import perf_counter_ns
from typing import Callable

class SessionClock:
    def __init__(self, monotonic: Callable[[], int] = perf_counter_ns,
                 utc_start: datetime | None = None):
        self._now = monotonic
        self.origin_ns = monotonic()
        self.utc_start = utc_start or datetime.now(timezone.utc)
        if self.utc_start.tzinfo is None:
            raise ValueError("An aware UTC origin is required")
    def now_ns(self) -> int:
        value = self._now() - self.origin_ns
        if value < 0:
            raise RuntimeError("Monotonic clock moved backwards")
        return value
    def utc_at(self, t_ns: int) -> datetime:
        if t_ns < 0:
            raise ValueError("Negative session time")
        return self.utc_start + timedelta(microseconds=t_ns // 1000)
    @staticmethod
    def media_pts_ns(frame_index: int, fps: int) -> int:
        if frame_index < 0 or fps <= 0:
            raise ValueError("Invalid video timebase")
        return frame_index * 1_000_000_000 // fps
