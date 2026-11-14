"""Versioned, bounded schemas. Unknown fields fail closed."""
from __future__ import annotations
from datetime import datetime, timezone
from enum import Enum
from typing import Literal
from uuid import UUID, uuid4
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SCHEMA_VERSION = "1.0"

class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    @field_validator("*", mode="after")
    @classmethod
    def aware_datetimes(cls, value):
        if isinstance(value, datetime):
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError("Datetime fields must be timezone-aware")
            return value.astimezone(timezone.utc)
        return value

class State(str, Enum):
    IDLE = "IDLE"
    STARTING = "STARTING"
    RECORDING = "RECORDING"
    PAUSED = "PAUSED"
    STOPPING = "STOPPING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    INTERRUPTED = "INTERRUPTED"

class Mask(Model):
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    width: float = Field(gt=0, le=1)
    height: float = Field(gt=0, le=1)
    @model_validator(mode="after")
    def inside(self):
        if self.x + self.width > 1.00000001 or self.y + self.height > 1.00000001:
            raise ValueError("A privacy mask must fit within the captured image")
        return self

class PrivacyConfig(Model):
    masks: list[Mask] = Field(default_factory=list, max_length=64)
    browser_labels: bool = False
    browser_titles: bool = False
    url_detail: Literal["origin", "path"] = "origin"
    # Raw typed text, clipboard, full DOM and credentials are deliberately unsupported.

class CaptureConfig(Model):
    backend: Literal["mss", "ffmpeg_x11"] = "mss"
    monitor: int = Field(default=1, ge=1, le=64)
    fps: int = Field(default=5, ge=1, le=60)
    output_width: int = Field(default=1280, ge=64, le=7680)
    screenshot_interval_s: float = Field(default=2.0, ge=0.1, le=3600)
    queue_frames: int = Field(default=8, ge=1, le=64)
    # Explicit X11 fallback region; never assumes DISPLAY=:0.
    x11_display: str | None = Field(default=None, max_length=100)
    region_left: int = 0
    region_top: int = 0
    region_width: int = Field(default=1280, ge=64, le=16384)
    region_height: int = Field(default=720, ge=64, le=16384)
    capture_mouse: bool = True
    capture_keyboard: bool = False
    capture_window_context: bool = False
    mouse_move_interval_ms: int = Field(default=50, ge=5, le=5000)
    @field_validator("x11_display")
    @classmethod
    def local_display(cls, value):
        if value is not None:
            import re
            if not re.fullmatch(r":\d+(?:\.\d+)?", value):
                raise ValueError("Only a local X11 display such as :99 is accepted")
        return value

class BrowserConfig(Model):
    enabled: bool = False
    start_url: str = Field(default="about:blank", max_length=2048)
    executable: str | None = None
    @field_validator("start_url")
    @classmethod
    def safe_url(cls, value):
        from urllib.parse import urlsplit
        if value == "about:blank":
            return value
        u = urlsplit(value)
        if u.scheme not in {"http", "https"} or not u.hostname or u.username or u.password:
            raise ValueError("Use http(s) without embedded credentials, or about:blank")
        return value

class Settings(Model):
    storage_root: str = "~/IDRA-recordings"
    ffmpeg: str = "ffmpeg"
    ffprobe: str = "ffprobe"
    capture: CaptureConfig = Field(default_factory=CaptureConfig)
    browser: BrowserConfig = Field(default_factory=BrowserConfig)
    privacy: PrivacyConfig = Field(default_factory=PrivacyConfig)
    min_free_mb: int = Field(default=1024, ge=1, le=1048576)
    event_queue_size: int = Field(default=8192, ge=32, le=131072)
    batch_size: int = Field(default=128, ge=1, le=8192)
    flush_interval_s: float = Field(default=0.5, ge=0.05, le=5)
    retention_days: int = Field(default=0, ge=0, le=36500)

EventKind = Literal[
    "mouse_move", "mouse_button_down", "mouse_button_up", "scroll", "key_press",
    "key_release", "window_context", "browser_navigation", "browser_action",
    "annotation", "task_boundary", "state_change", "capture_gap"
]
KeyName = Literal[
    "shift", "ctrl", "alt", "cmd", "enter", "tab", "esc", "space", "backspace",
    "delete", "up", "down", "left", "right", "home", "end", "page_up", "page_down",
    "caps_lock", "f1", "f2", "f3", "f4", "f5", "f6", "f7", "f8", "f9", "f10",
    "f11", "f12"
]

class Payload(Model):
    x: float | None = Field(default=None, allow_inf_nan=False)
    y: float | None = Field(default=None, allow_inf_nan=False)
    x_px: float | None = Field(default=None, allow_inf_nan=False)
    y_px: float | None = Field(default=None, allow_inf_nan=False)
    in_capture: bool | None = None
    coordinate_space: Literal["desktop", "viewport", "none"] = "none"
    button: Literal["left", "right", "middle", "other"] | None = None
    dx: float | None = Field(default=None, allow_inf_nan=False)
    dy: float | None = Field(default=None, allow_inf_nan=False)
    key_category: Literal["protected", "modifier", "navigation", "editing", "function"] | None = None
    key_name: KeyName | None = None
    modifiers: list[Literal["shift", "ctrl", "alt", "cmd"]] = Field(default_factory=list, max_length=4)
    redacted: bool = True
    action: Literal["click", "input", "change", "focus", "scroll", "start", "complete", "failed"] | None = None
    url: str | None = Field(default=None, max_length=2048)
    title: str | None = Field(default=None, max_length=256)
    tag: str | None = Field(default=None, max_length=32)
    role: str | None = Field(default=None, max_length=64)
    label: str | None = Field(default=None, max_length=256)
    input_type: str | None = Field(default=None, max_length=32)
    sensitive: bool = False
    viewport_width: int | None = Field(default=None, ge=0, le=100000)
    viewport_height: int | None = Field(default=None, ge=0, le=100000)
    browser_timestamp_ms: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    browser_time_origin_ms: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    is_trusted: bool | None = None
    outcome: Literal["observed_event_only", "navigation_completed", "navigation_failed"] | None = None
    text: str | None = Field(default=None, max_length=4000)
    boundary: Literal["start", "end"] | None = None
    app: str | None = Field(default=None, max_length=256)
    pid: int | None = Field(default=None, ge=0)
    state: State | None = None
    reason: str | None = Field(default=None, max_length=120)
    @model_validator(mode="after")
    def no_printable_key(self):
        if self.key_category == "protected" and self.key_name is not None:
            raise ValueError("Protected keyboard events cannot contain key names")
        if not self.redacted:
            raise ValueError("Unredacted telemetry is not supported")
        return self

class Event(Model):
    schema_version: Literal["1.0"] = SCHEMA_VERSION
    event_id: UUID = Field(default_factory=uuid4)
    session_id: UUID
    sequence: int = Field(ge=0)
    t_ns: int = Field(ge=0)
    received_t_ns: int = Field(ge=0)
    utc: datetime
    type: EventKind
    source: Literal["pynput", "browser", "controller", "window_context", "synthetic"]
    timestamp_kind: Literal["callback", "calibrated", "received", "synthetic"] = "callback"
    uncertainty_ns: int | None = Field(default=None, ge=0)
    synthetic: bool = False
    payload: Payload = Field(default_factory=Payload)
    @field_validator("utc")
    @classmethod
    def aware_utc(cls, value):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("UTC timestamps must be timezone-aware")
        return value.astimezone(timezone.utc)

class Frame(Model):
    schema_version: Literal["1.0"] = SCHEMA_VERSION
    session_id: UUID
    index: int = Field(ge=0)
    t_ns: int = Field(ge=0)
    capture_started_t_ns: int = Field(ge=0)
    pts_ns: int = Field(ge=0)
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    timestamp_kind: Literal["acquisition_complete", "received", "synthetic"]
    screenshot: str | None = None
    sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    blur_score: float = Field(default=0, ge=0, allow_inf_nan=False)
    content_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    synthetic: bool = False
    @model_validator(mode="after")
    def times(self):
        if self.capture_started_t_ns > self.t_ns:
            raise ValueError("Frame acquisition interval is reversed")
        return self

class Consent(Model):
    granted_at: datetime
    authorized_to_record: Literal[True]
    understands_visual_risk: Literal[True]
    telemetry_content: Literal["no_raw_text"] = "no_raw_text"

class Manifest(Model):
    schema_version: Literal["1.0"] = SCHEMA_VERSION
    application_version: str = "0.9.3"
    session_id: UUID
    label: str = Field(max_length=256)
    task_description: str = Field(default="", max_length=4000)
    created_at: datetime
    state: State = State.STARTING
    duration_ns: int = Field(default=0, ge=0)
    synthetic: bool = False
    settings: Settings
    consent: Consent
    platform: str
    geometry: dict[str, int | float | str] = Field(default_factory=dict)
    counts: dict[str, int] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    failure_codes: list[str] = Field(default_factory=list)
    media: str | None = None
    checksums: dict[str, str] = Field(default_factory=dict)
    operations: list[dict] = Field(default_factory=list)
    timebase: str = "monotonic elapsed ns including pauses; video PTS mapped by frames.jsonl"

class QualityThresholds(Model):
    max_gap_s: float = Field(default=3, gt=0)
    max_dropped_events: int = Field(default=0, ge=0)
    min_frames: int = Field(default=1, ge=0)
    blur_warning_score: float = Field(default=10, ge=0)
    strict_received_timing: bool = False

class SegmentationConfig(Model):
    inactivity_s: float = Field(default=30, gt=0, le=86400)
    navigation_boundaries: bool = False
    max_actions: int = Field(default=1000, ge=1, le=10000)
    frame_stride: int = Field(default=1, ge=1, le=10000)

class Action(Model):
    event_id: UUID
    t_ns: int = Field(ge=0)
    type: EventKind
    payload: Payload
    before_frame: int | None = None
    after_frame: int | None = None
    context_status: Literal["available", "missing", "media_excluded"] = "missing"
    outcome: Literal["not_inferred"] = "not_inferred"

class Trajectory(Model):
    schema_version: Literal["1.0"] = SCHEMA_VERSION
    session_id: UUID
    trajectory_id: UUID
    task_description: str
    start_t_ns: int = Field(ge=0)
    end_t_ns: int = Field(ge=0)
    boundary_reason: str
    task_completion: Literal["user_marked_complete", "unconfirmed", "interrupted"]
    synthetic: bool
    actions: list[Action]
    annotations: list[Event] = Field(default_factory=list)
    quality: dict = Field(default_factory=dict)
    @model_validator(mode="after")
    def ordered(self):
        if self.end_t_ns < self.start_t_ns:
            raise ValueError("Trajectory time interval is reversed")
        return self
