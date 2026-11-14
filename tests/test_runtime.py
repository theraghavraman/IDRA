"""Start-up hardening and macOS runtime guards (exercised without macOS via controlled fakes)."""
import contextlib
import os
import stat
import sys
import threading
import types
import pytest
from idra.app import runtime


def _fake_exe(directory, name):
    path = directory / name
    path.write_text("#!/bin/sh\nexit 0\n")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


def test_find_executable_searches_package_manager_dirs_when_path_is_minimal(tmp_path, monkeypatch):
    # Finder-launched macOS apps get PATH=/usr/bin:/bin:/usr/sbin:/sbin; Homebrew lives elsewhere.
    tool = _fake_exe(tmp_path, "idra-test-tool")
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    monkeypatch.setattr(runtime, "EXTRA_BIN_DIRS", (str(tmp_path),))
    assert runtime.find_executable("idra-test-tool") == str(tool)


def test_find_executable_explicit_path_and_missing(tmp_path):
    tool = _fake_exe(tmp_path, "explicit")
    assert runtime.find_executable(str(tool)) == str(tool)
    assert runtime.find_executable(str(tmp_path / "absent")) is None
    assert runtime.find_executable("definitely-not-a-real-idra-tool") is None
    assert runtime.find_executable("") is None


def test_media_executable_uses_fallback_dirs(tmp_path, monkeypatch):
    from idra.media.ffmpeg import MediaError, executable
    tool = _fake_exe(tmp_path, "idra-fake-ffmpeg")
    monkeypatch.setenv("PATH", "/nonexistent")
    monkeypatch.setattr(runtime, "EXTRA_BIN_DIRS", (str(tmp_path),))
    assert executable("idra-fake-ffmpeg") == str(tool)
    with pytest.raises(MediaError, match="brew install ffmpeg"):
        executable("idra-missing-ffmpeg")


def test_extend_path_adds_existing_dirs_once(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", "/usr/bin")
    monkeypatch.setattr(runtime, "EXTRA_BIN_DIRS", (str(tmp_path), str(tmp_path / "missing")))
    runtime.extend_path()
    runtime.extend_path()
    parts = os.environ["PATH"].split(os.pathsep)
    assert parts.count(str(tmp_path)) == 1 and str(tmp_path / "missing") not in parts


def test_pynput_guard_computes_context_once_on_calling_thread(monkeypatch):
    calls = []
    @contextlib.contextmanager
    def original():
        calls.append(threading.current_thread().name)
        yield ("kbd", b"layout")
    fake = types.ModuleType("pynput.keyboard._darwin")
    fake.keycode_context = original
    monkeypatch.setitem(sys.modules, "pynput.keyboard._darwin", fake)
    pkg = sys.modules.get("pynput.keyboard") or types.ModuleType("pynput.keyboard")
    monkeypatch.setitem(sys.modules, "pynput.keyboard", pkg)
    monkeypatch.setattr(pkg, "_darwin", fake, raising=False)
    monkeypatch.setattr(runtime, "is_macos", lambda: True)
    monkeypatch.setattr(runtime, "_KEYBOARD_PATCHED", False)
    assert runtime.install_pynput_main_thread_guard() is True
    seen = []
    def listener_thread():
        with fake.keycode_context() as context:
            seen.append(context)
    t = threading.Thread(target=listener_thread, name="listener")
    t.start(); t.join()
    assert seen == [("kbd", b"layout")]
    assert calls == [threading.main_thread().name]  # never re-entered from the listener thread


def test_pynput_guard_is_noop_off_macos(monkeypatch):
    monkeypatch.setattr(runtime, "is_macos", lambda: False)
    monkeypatch.setattr(runtime, "_KEYBOARD_PATCHED", False)
    assert runtime.install_pynput_main_thread_guard() is False


def test_permission_requests_are_safe_off_macos(monkeypatch):
    monkeypatch.setattr(runtime, "is_macos", lambda: False)
    assert runtime.request_screen_recording() is None
    assert runtime.request_input_monitoring() is None
    assert runtime.request_accessibility() is None


def test_corrupt_settings_never_block_launch(tmp_path):
    from idra.app.settings import load_settings_safe
    path = tmp_path / "settings.json"
    path.write_text("{not json")
    settings, warning = load_settings_safe(path)
    assert settings.capture.fps > 0 and "defaults are in use" in warning
    assert not path.exists()
    assert len(list(tmp_path.glob("settings.json.unreadable-*"))) == 1
    ok, none = load_settings_safe(tmp_path / "absent.json")
    assert none is None and ok.storage_root


def test_keyboard_permission_check_uses_os_status(monkeypatch):
    from idra.inputs import recorder
    import idra.diagnostics.checks as checks
    monkeypatch.setattr(recorder.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(checks, "mac_permissions", lambda: {"accessibility": False, "input_monitoring": False})
    assert recorder._keyboard_permission_missing() is True
    monkeypatch.setattr(checks, "mac_permissions", lambda: {"accessibility": True, "input_monitoring": None})
    assert recorder._keyboard_permission_missing() is False
    monkeypatch.setattr(checks, "mac_permissions", lambda: {"accessibility": False, "input_monitoring": True})
    assert recorder._keyboard_permission_missing() is False
    monkeypatch.setattr(recorder.platform, "system", lambda: "Linux")
    assert recorder._keyboard_permission_missing() is False


def test_app_main_discards_finder_psn_argument(monkeypatch):
    from idra.app import cli
    received = []
    monkeypatch.setattr(cli, "main", lambda argv: received.append(argv) or 0)
    monkeypatch.setattr(sys, "argv", ["IDRA", "-psn_0_12345"])
    assert cli.app_main() == 0 and received[-1] == ["gui"]
    monkeypatch.setattr(sys, "argv", ["IDRA", "diagnostics"])
    cli.app_main()
    assert received[-1] == ["diagnostics"]


def test_slow_input_listener_shutdown_is_a_warning_not_a_failure(monkeypatch):
    """A listener that exits late must not turn a complete recording into FAILED."""
    from idra.inputs.recorder import InputRecorder
    class StuckListener:
        ident = 1
        def stop(self): pass
        def join(self, timeout=None): pass
        def is_alive(self): return True
    recorder = InputRecorder(config=None, clock=None, emit=None, request_stop=None, on_failure=None)
    recorder.listeners = [StuckListener()]
    woke = []
    monkeypatch.setattr(recorder, "_wake_x11_listeners", lambda: woke.append(True))
    monkeypatch.setattr("idra.inputs.recorder.platform.system", lambda: "Linux")
    recorder.stop()  # must not raise
    assert recorder.shutdown_warning == "INPUT_LISTENER_SHUTDOWN_SLOW" and woke == [True]


def test_windows_lookup_finds_exe_suffix(tmp_path, monkeypatch):
    tool = _fake_exe(tmp_path, "ffmpeg.exe")
    monkeypatch.setattr(runtime, "is_windows", lambda: True)
    monkeypatch.setenv("PATH", "")
    monkeypatch.setattr(runtime, "EXTRA_BIN_DIRS", (str(tmp_path),))
    assert runtime.find_executable("ffmpeg") == str(tool)
    assert runtime.find_executable(str(tmp_path / "ffmpeg")) == str(tool)  # configured path without .exe


def test_no_window_flag_only_on_windows(monkeypatch):
    monkeypatch.setattr(runtime, "is_windows", lambda: False)
    assert runtime.no_window() == {}
    monkeypatch.setattr(runtime, "is_windows", lambda: True)
    assert runtime.no_window() == {"creationflags": 0x08000000}


def test_wayland_detection(monkeypatch):
    monkeypatch.setattr(runtime.platform, "system", lambda: "Linux")
    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    assert runtime.is_wayland_session() is True
    monkeypatch.setenv("XDG_SESSION_TYPE", "x11")
    monkeypatch.setenv("DISPLAY", ":0")
    assert runtime.is_wayland_session() is False
    monkeypatch.setattr(runtime.platform, "system", lambda: "Darwin")
    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    assert runtime.is_wayland_session() is False


def test_readonly_index_uri_handles_spaces(tmp_path):
    from idra.storage.repository import connect_index
    folder = tmp_path / "folder with spaces"
    folder.mkdir()
    with connect_index(folder) as conn:
        conn.execute("SELECT count(*) FROM events").fetchone()
    with connect_index(folder, readonly=True) as conn:
        assert conn.execute("SELECT count(*) FROM frames").fetchone()[0] == 0
