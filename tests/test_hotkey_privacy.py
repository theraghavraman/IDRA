"""Privacy-preserving global stop works independently of category telemetry."""
from types import SimpleNamespace
from unittest.mock import Mock

from idra.events.models import CaptureConfig
from idra.inputs.recorder import InputRecorder


def test_hotkey_without_keyboard_categories_does_not_emit_events():
    emitted = []
    stopped = []
    config = CaptureConfig(capture_mouse=False, capture_keyboard=False)
    recorder = InputRecorder(config, SimpleNamespace(now_ns=lambda:42),
                             lambda *a, **kw:emitted.append(a),
                             lambda:stopped.append(True), lambda code:None)
    for modifier in ("ctrl", "alt", "shift"):
        recorder._press(SimpleNamespace(name=modifier))
    recorder._press(SimpleNamespace(name="f8"))
    recorder._release(SimpleNamespace(name="f8"))
    assert stopped == [True]
    assert emitted == []


def test_hotkey_without_telemetry_starts_real_keyboard_listener(monkeypatch):
    import sys
    import types
    instances = []
    class FakeListener:
        ident = 1
        def __init__(self, **callbacks):
            self.callbacks = callbacks
            self.alive = False
            instances.append(self)
        def start(self): self.alive = True
        def wait(self): return None
        def is_alive(self): return self.alive
        def stop(self): self.alive = False
        def join(self, timeout=None): return None
    pynput = types.ModuleType("pynput")
    pynput.keyboard = SimpleNamespace(Listener=FakeListener)
    pynput.mouse = SimpleNamespace(Listener=FakeListener)
    monkeypatch.setitem(sys.modules, "pynput", pynput)
    monkeypatch.setattr("idra.inputs.recorder._keyboard_permission_missing", lambda: False)
    config = CaptureConfig(capture_mouse=False, capture_keyboard=False)
    emitted, stopped = [], []
    recorder = InputRecorder(config, SimpleNamespace(now_ns=lambda:3),
                             lambda *a, **kw:emitted.append(a), lambda:stopped.append(True), lambda c:None)
    recorder.start()
    assert recorder.global_stop_available
    assert len(instances) == 1 and "on_press" in instances[0].callbacks
    for mod in ("ctrl", "alt", "shift"):
        instances[0].callbacks["on_press"](SimpleNamespace(name=mod))
    instances[0].callbacks["on_press"](SimpleNamespace(name="f8"))
    assert stopped == [True] and emitted == []
    recorder.stop()
    assert not recorder.global_stop_available


def test_denied_hotkey_permission_warns_without_telemetry(monkeypatch):
    import sys
    import types
    pynput = types.ModuleType("pynput")
    pynput.keyboard = SimpleNamespace()
    pynput.mouse = SimpleNamespace()
    monkeypatch.setitem(sys.modules, "pynput", pynput)
    monkeypatch.setattr("idra.inputs.recorder._keyboard_permission_missing", lambda: True)
    config = CaptureConfig(capture_mouse=False, capture_keyboard=False)
    recorder = InputRecorder(config, SimpleNamespace(now_ns=lambda:0),
                             Mock(), Mock(), Mock())
    recorder.start()
    assert recorder.startup_warning == "GLOBAL_STOP_HOTKEY_UNAVAILABLE"
    assert not recorder.global_stop_available
    recorder.stop()


def test_modifier_state_from_emergency_listener_does_not_leak_into_mouse_events():
    config = CaptureConfig(capture_mouse=True, capture_keyboard=False)
    received = []
    recorder = InputRecorder(config, SimpleNamespace(now_ns=lambda:10),
                             lambda kind, payload, source, **kw:received.append(payload),
                             lambda:None, lambda code:None)
    recorder._press(SimpleNamespace(name="ctrl"))
    recorder._move(22, 40)
    assert len(received) == 1 and received[0].modifiers == []
