"""Transactional recording lifecycle, with injectable capture/input/browser providers."""
from __future__ import annotations
import logging
import platform
import shutil
import threading
from datetime import datetime, timezone
from uuid import uuid4
from idra.app.state import transition
from idra.browser.managed import ManagedBrowser
from idra.capture.pipeline import CapturePipeline
from idra.capture.sources import source_for
from idra.diagnostics.checks import mac_permissions
from idra.events.models import Consent, Event, Manifest, Payload, Settings, State
from idra.inputs.context import ContextWatcher
from idra.inputs.recorder import InputRecorder
from idra.media.ffmpeg import executable
from idra.privacy.policy import redact_text, sanitize_payload, sanitize_url
from idra.storage.files import SessionLock, sha256
from idra.storage.journal import Journal
from idra.storage.repository import Repository
from idra.synchronization.clock import SessionClock

logger = logging.getLogger("idra.controller")

class SessionController:
    def __init__(self, settings: Settings, repository: Repository | None = None,
                 *, input_factory=InputRecorder, browser_factory=ManagedBrowser):
        self.settings = settings.model_copy(deep=True)
        self.repository = repository or Repository(settings.storage_root)
        self.input_factory, self.browser_factory = input_factory, browser_factory
        self.guard = threading.RLock()
        self.stop_guard = threading.Lock()
        self.stop_requested = threading.Event()
        self.state = State.IDLE
        self.manifest = None
        self.clock = None
        self.journal = self.pipeline = self.inputs = self.browser = self.context = None
        self.session_lock = None
        self.sequence = 0
        self.failures = []
        self.starting = False
        self.start_done = threading.Event()
        self.start_done.set()
        self.start_thread_id = None
    def _transition(self, target):
        with self.guard:
            self.state = transition(self.state, target)
            if self.manifest:
                self.manifest.state = self.state
    def _active(self):
        with self.guard:
            return self.state in {State.STARTING, State.RECORDING}
    def _recording(self):
        with self.guard:
            return self.state == State.RECORDING
    def request_stop(self):
        self.stop_requested.set()
    def _failure(self, code):
        with self.guard:
            if code not in self.failures:
                self.failures.append(code)
        logger.error("recording_failure code=%s", code.split(":", 1)[0])
        self.stop_requested.set()
    def start(self, label: str, task_description="", *, consent=False, source=None, synthetic=False) -> Manifest:
        if not consent:
            raise PermissionError("Explicit recording authorization and visual-risk consent are required")
        with self.guard:
            self._transition(State.STARTING)
            self.manifest = None
            self.starting = True
            self.start_done.clear()
            self.start_thread_id = threading.get_ident()
            self.sequence, self.failures = 0, []
            self.stop_requested.clear()
            self.journal = self.pipeline = self.inputs = self.browser = self.context = None
            self.session_lock = None
        try:
            executable(self.settings.ffmpeg)
            executable(self.settings.ffprobe)
            if shutil.disk_usage(self.repository.root).free < self.settings.min_free_mb * 1024**2:
                raise RuntimeError("INSUFFICIENT_STORAGE")
            if not synthetic and mac_permissions().get("screen_recording") is False:
                raise PermissionError("SCREEN_PERMISSION_REQUIRED: grant Screen Recording to this launcher and restart it")
            capture_source = source or source_for(self.settings.capture, self.settings.ffmpeg)
            if bool(capture_source.synthetic) != bool(synthetic):
                raise ValueError("Synthetic capture must be explicitly and consistently labeled")
            self.clock = SessionClock()
            saved_settings = self.settings.model_copy(deep=True)
            saved_settings.browser.start_url = sanitize_url(saved_settings.browser.start_url)
            self.manifest = Manifest(session_id=uuid4(), label=redact_text(label)[:256],
                task_description=redact_text(task_description), created_at=self.clock.utc_start,
                settings=saved_settings, synthetic=synthetic, platform=platform.system(),
                consent=Consent(granted_at=datetime.now(timezone.utc), authorized_to_record=True,
                                understands_visual_risk=True))
            directory = self.repository.create(self.manifest)
            self.session_lock = SessionLock(directory).acquire()
            self.journal = Journal(directory, self.settings.event_queue_size,
                self.settings.batch_size, self.settings.flush_interval_s)
            self.journal.start()
            self.emit("state_change", Payload(state=State.RECORDING), "controller", force=True)
            self.pipeline = CapturePipeline(self.manifest.session_id, directory, self.clock,
                self.settings, self.journal, capture_source, self._active, self._failure)
            self.pipeline.start()
            if self.stop_requested.is_set():
                raise RuntimeError("START_CANCELLED")
            self._transition(State.RECORDING)
            if not synthetic or self.settings.capture.capture_mouse or self.settings.capture.capture_keyboard:
                self.inputs = self.input_factory(self.settings.capture, self.clock, self.emit,
                                                 self.request_stop, self._failure)
                try:
                    self.inputs.start()
                except (RuntimeError, ImportError) as exc:
                    # If all telemetry channels are disabled, hotkey failure must not
                    # prevent screen-only recording; clearly mark the limitation.
                    if self.settings.capture.capture_mouse or self.settings.capture.capture_keyboard:
                        raise
                    self.manifest.warnings.append("GLOBAL_STOP_HOTKEY_UNAVAILABLE")
                    self.inputs = None
                if self.inputs is not None and getattr(self.inputs, "startup_warning", None):
                    self.manifest.warnings.append(self.inputs.startup_warning)
            if self.settings.capture.capture_window_context:
                self.context = ContextWatcher(self.clock, self.emit, self._recording)
                self.context.start()
            if self.settings.browser.enabled:
                self.browser = self.browser_factory(self.settings.browser, self.settings.privacy,
                    self.clock, self.emit, self._recording)
                self.browser.start()
            if self.stop_requested.is_set():
                raise RuntimeError("START_CANCELLED")
            self.manifest.geometry = dict(self.pipeline.geometry)
            if capture_source.timestamp_kind == "received":
                self.manifest.warnings.append("SCREEN_TIMESTAMPS_ARE_RECEIVE_TIMES_NOT_NATIVE_ACQUISITION_TIMES")
            if platform.system() in {"Darwin", "Windows"}:
                self.manifest.warnings.append("DPI_COORDINATE_MAPPING_REQUIRES_TARGET_MACHINE_CALIBRATION")
            self.repository.save(self.manifest)
            return self.manifest
        except Exception as exc:
            self._failure(str(exc) if isinstance(exc, (RuntimeError, PermissionError)) else f"START_FAILED:{type(exc).__name__}")
            if self.manifest is not None:
                self.stop()
            else:
                self._transition(State.FAILED)
            raise RuntimeError(self.failures[0]) from exc
        finally:
            self.starting = False
            self.start_done.set()
    def emit(self, kind, payload: Payload, source="controller", *, t_ns=None,
             received_t_ns=None, timestamp_kind="callback", uncertainty_ns=None, force=False) -> bool:
        with self.guard:
            if self.clock is None or self.manifest is None or self.journal is None:
                return False
            if not force and self.state != State.RECORDING:
                return False
            if force and self.state not in {State.STARTING, State.RECORDING, State.PAUSED, State.STOPPING}:
                return False
            received = self.clock.now_ns() if received_t_ns is None else received_t_ns
            stamp = received if t_ns is None else t_ns
            if payload.text is not None and kind not in {"annotation", "task_boundary"}:
                raise ValueError("Only explicit user annotations may contain text")
            clean = sanitize_payload(payload, self.settings.privacy)
            if source == "pynput" and clean.x is not None and clean.y is not None and self.pipeline:
                g = self.pipeline.geometry
                if g.get("width") and g.get("height"):
                    clean.x_px = (clean.x - g["left"]) * g["output_width"] / g["width"]
                    clean.y_px = (clean.y - g["top"]) * g["output_height"] / g["height"]
                    clean.in_capture = 0 <= clean.x_px < g["output_width"] and 0 <= clean.y_px < g["output_height"]
            event = Event(session_id=self.manifest.session_id, sequence=self.sequence,
                t_ns=stamp, received_t_ns=received, utc=self.clock.utc_at(stamp), type=kind,
                payload=clean, source=source, synthetic=self.manifest.synthetic,
                timestamp_kind="synthetic" if self.manifest.synthetic else timestamp_kind,
                uncertainty_ns=uncertainty_ns)
            self.sequence += 1
            return self.journal.submit(event)
    def pause(self):
        self._transition(State.PAUSED)
        self.emit("state_change", Payload(state=State.PAUSED), "controller", force=True)
        self.repository.save(self.manifest)
    def resume(self):
        self._transition(State.RECORDING)
        self.emit("state_change", Payload(state=State.RECORDING), "controller", force=True)
        self.repository.save(self.manifest)
    def annotate(self, text: str, boundary: str | None = None):
        if self.state not in {State.RECORDING, State.PAUSED}:
            raise RuntimeError("Annotations require an active recording")
        return self.emit("task_boundary" if boundary else "annotation",
                         Payload(text=text, boundary=boundary), "controller", force=True)
    def stop(self) -> Manifest | None:
        if self.starting and threading.get_ident() != self.start_thread_id:
            self.request_stop()
            if not self.start_done.wait(60):
                raise RuntimeError("START_CANCELLATION_TIMEOUT")
        with self.stop_guard:
            if self.state in {State.IDLE, State.COMPLETED, State.FAILED, State.INTERRUPTED}:
                return self.manifest
            self._transition(State.STOPPING)
            self.emit("state_change", Payload(state=State.STOPPING), "controller", force=True)
            try:
                for name in ("inputs", "context", "browser", "pipeline"):
                    component = getattr(self, name)
                    if component is not None:
                        try:
                            component.stop()
                        except Exception as exc:
                            self._failure(str(exc) if isinstance(exc, RuntimeError) else f"{name.upper()}_STOP_FAILED")
                if self.journal is not None and self.journal.thread.ident is not None:
                    try:
                        self.journal.close()
                    except Exception as exc:
                        self._failure(str(exc) if isinstance(exc, RuntimeError) else "JOURNAL_STOP_FAILED")
                if self.manifest is not None:
                    self.manifest.duration_ns = self.clock.now_ns()
                    self.manifest.counts = self.journal.stats() if self.journal else {}
                    if self.pipeline:
                        self.manifest.counts.update(self.pipeline.stats())
                        self.manifest.geometry = dict(self.pipeline.geometry)
                    if self.browser:
                        self.manifest.counts.update({f"browser_{k}":v for k,v in self.browser.stats().items()})
                        if self.browser.error or self.browser.status == "disconnected":
                            self.manifest.warnings.append("MANAGED_BROWSER_DISCONNECTED")
                    if self.inputs is not None and getattr(self.inputs, "shutdown_warning", None):
                        self.manifest.warnings.append(self.inputs.shutdown_warning)
                    if self.context and self.context.status == "unavailable":
                        self.manifest.warnings.append("WINDOW_CONTEXT_UNAVAILABLE")
                    directory = self.repository.path(self.manifest.session_id)
                    if (directory / "media/screen.mkv").exists():
                        self.manifest.media = "media/screen.mkv"
                    for name in ["events.jsonl", "frames.jsonl"] + ([self.manifest.media] if self.manifest.media else []):
                        path = directory / name
                        if path.is_file():
                            self.manifest.checksums[name] = sha256(path)
                    self.manifest.failure_codes = list(self.failures)
                    self._transition(State.FAILED if self.failures else State.COMPLETED)
                    self.repository.save(self.manifest)
                return self.manifest
            except Exception:
                self.state = State.FAILED
                if self.manifest:
                    self.manifest.state = State.FAILED
                raise
            finally:
                if self.session_lock:
                    self.session_lock.release()
                    self.session_lock = None
    def snapshot(self) -> dict:
        with self.guard:
            state = self.state.value
            duration = self.clock.now_ns() if self.clock and self.state in {State.STARTING, State.RECORDING, State.PAUSED, State.STOPPING} else (self.manifest.duration_ns if self.manifest else 0)
            sid = str(self.manifest.session_id) if self.manifest else None
        counts = self.journal.stats() if self.journal else {}
        if self.pipeline:
            counts.update(self.pipeline.stats())
        if self.inputs and self.state == State.RECORDING and not self.inputs.healthy():
            self._failure("INPUT_LISTENER_STOPPED_UNEXPECTEDLY")
        return {"state":state, "session_id":sid, "duration_ns":duration, "counts":counts,
                "geometry":dict(self.pipeline.geometry) if self.pipeline else {},
                "browser":self.browser.status if self.browser else "disabled",
                "global_stop_available":bool(self.inputs and self.inputs.global_stop_available),
                "failure_codes":list(self.failures), "stop_requested":self.stop_requested.is_set(),
                "disk_free_bytes":shutil.disk_usage(self.repository.root).free}
