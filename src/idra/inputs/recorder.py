"""Visible, consent-gated input telemetry. Printable key identities never leave callbacks."""
from __future__ import annotations
import platform
import threading
from idra.events.models import Payload

def _keyboard_permission_missing() -> bool:
    if platform.system() != "Darwin":
        return False
    from idra.diagnostics.checks import mac_permissions
    status = mac_permissions()
    # Unknown (None) is not treated as denied; the listener start check below still applies.
    return status.get("accessibility") is False and status.get("input_monitoring") is not True

_MODIFIERS = {"shift", "ctrl", "alt", "cmd"}
_NAVIGATION = {"up", "down", "left", "right", "home", "end", "page_up", "page_down", "tab", "esc"}
_EDITING = {"enter", "space", "backspace", "delete", "caps_lock"}

def key_metadata(key) -> tuple[str, str | None]:
    # Do not inspect .char, vk, scan codes, or repr(key).
    name = getattr(key, "name", None)
    if not isinstance(name, str):
        return "protected", None
    if name.endswith(("_l", "_r")):
        name = name[:-2]
    if name in _MODIFIERS:
        return "modifier", name
    if name in _NAVIGATION:
        return "navigation", name
    if name in _EDITING:
        return "editing", name
    if name in {f"f{i}" for i in range(1, 13)}:
        return "function", name
    return "protected", None

class InputRecorder:
    def __init__(self, config, clock, emit, request_stop, on_failure):
        self.config, self.clock, self.emit = config, clock, emit
        self.request_stop, self.on_failure = request_stop, on_failure
        self.listeners = []
        self.modifiers = set()
        self.lock = threading.Lock()
        self.last_move = -10**30
        self.running = False
        self.global_stop_available = False
        self.startup_warning = None
        self.shutdown_warning = None
    def _launch(self, listener):
        try:
            listener.start()
            ready = threading.Thread(target=listener.wait, daemon=True)
            ready.start()
            ready.join(5)
            if ready.is_alive() or not listener.is_alive():
                if platform.system() == "Darwin":
                    raise RuntimeError("INPUT_LISTENER_START_FAILED: macOS refused the input event tap; "
                                       "grant Accessibility/Input Monitoring to IDRA")
                raise RuntimeError("INPUT_LISTENER_START_FAILED")
            self.listeners.append(listener)
        except BaseException:
            try:
                listener.stop()
            except Exception:
                pass
            raise

    def start(self):
        self.global_stop_available = False
        self.startup_warning = None
        try:
            from pynput import keyboard, mouse
        except ImportError as exc:
            raise RuntimeError("INPUT_BACKEND_UNAVAILABLE: install pynput and check the graphical session") from exc
        try:
            if self.config.capture_mouse:
                self._launch(mouse.Listener(on_move=self._move, on_click=self._click,
                                            on_scroll=self._scroll))
            # Always attempt the dedicated emergency listener, including when the user
            # has disabled keyboard telemetry. It only inspects modifier/F8 categories.
            # Failure is non-fatal when key-category recording has not been requested;
            # the user is warned to use the visible Stop control or terminal Ctrl+C.
            if _keyboard_permission_missing():
                if self.config.capture_keyboard:
                    raise PermissionError("INPUT_PERMISSION_REQUIRED: grant Accessibility and "
                                          "Input Monitoring to IDRA and restart")
                self.startup_warning = "GLOBAL_STOP_HOTKEY_UNAVAILABLE"
            else:
                try:
                    self._launch(keyboard.Listener(on_press=self._press,
                                                   on_release=self._release))
                    self.global_stop_available = True
                except Exception:
                    if self.config.capture_keyboard:
                        raise
                    self.startup_warning = "GLOBAL_STOP_HOTKEY_UNAVAILABLE"
            self.running = True
        except BaseException:
            self.stop()
            raise
    def _send(self, kind, t_ns, **data):
        try:
            with self.lock:
                modifiers = sorted(self.modifiers) if self.config.capture_keyboard else []
            self.emit(kind, Payload(modifiers=modifiers, **data), "pynput", t_ns=t_ns)
        except Exception:
            self.on_failure("INPUT_NORMALIZATION_FAILED")
    def _move(self, x, y):
        stamp = self.clock.now_ns()
        if stamp - self.last_move < self.config.mouse_move_interval_ms * 1_000_000:
            return
        self.last_move = stamp
        self._send("mouse_move", stamp, x=x, y=y, coordinate_space="desktop")
    def _click(self, x, y, button, pressed):
        stamp = self.clock.now_ns()
        name = getattr(button, "name", "other")
        self._send("mouse_button_down" if pressed else "mouse_button_up", stamp,
                   x=x, y=y, button=name if name in {"left", "right", "middle"} else "other",
                   coordinate_space="desktop")
    def _scroll(self, x, y, dx, dy):
        stamp = self.clock.now_ns()
        self._send("scroll", stamp, x=x, y=y, dx=dx, dy=dy, coordinate_space="desktop")
    def _press(self, key):
        stamp = self.clock.now_ns()
        category, name = key_metadata(key)
        with self.lock:
            if category == "modifier":
                self.modifiers.add(name)
            emergency = name == "f8" and {"ctrl", "alt", "shift"}.issubset(self.modifiers)
        if emergency:
            self.request_stop()
        if self.config.capture_keyboard:
            self._send("key_press", stamp, key_category=category, key_name=name)
    def _release(self, key):
        stamp = self.clock.now_ns()
        category, name = key_metadata(key)
        if self.config.capture_keyboard:
            self._send("key_release", stamp, key_category=category, key_name=name)
        if category == "modifier":
            with self.lock:
                self.modifiers.discard(name)
    def healthy(self):
        return self.running and all(listener.is_alive() for listener in self.listeners)
    def _wake_x11_listeners(self):
        """pynput's X11 record loop only exits after one more input event; send a 1 px round trip."""
        try:
            from pynput import mouse
            controller = mouse.Controller()
            controller.move(1, 0)
            controller.move(-1, 0)
        except Exception:
            pass
    def stop(self):
        """Stop listeners. A listener that is slow to exit is reported, not treated as data loss:
        events stop being accepted as soon as the session leaves RECORDING, and threads are daemons."""
        self.running = False
        self.global_stop_available = False
        self.shutdown_warning = None
        for listener in self.listeners:
            listener.stop()
        started = [listener for listener in self.listeners if listener.ident is not None]
        for listener in started:
            listener.join(0.5)
        if platform.system() == "Linux" and any(listener.is_alive() for listener in started):
            self._wake_x11_listeners()
        for listener in started:
            listener.join(3)
            if listener.is_alive():
                self.shutdown_warning = "INPUT_LISTENER_SHUTDOWN_SLOW"
