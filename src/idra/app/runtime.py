"""Process-level runtime support shared by the CLI, the GUI and the packaged macOS app.

Everything here is defensive: a helper that cannot do its job reports that fact and
returns, it never raises into application start-up.
"""
from __future__ import annotations
import contextlib
import ctypes
import faulthandler
import logging
import os
import platform
import shutil
import sys
from pathlib import Path

logger = logging.getLogger("idra.runtime")

def _extra_bin_dirs() -> tuple[str, ...]:
    """Package-manager locations that a GUI-launched app may not have on PATH."""
    if platform.system() == "Windows":
        local = os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))
        program_data = os.environ.get("ProgramData", r"C:\ProgramData")
        return (str(Path(local) / "Microsoft" / "WinGet" / "Links"),
                str(Path(program_data) / "chocolatey" / "bin"),
                str(Path.home() / "scoop" / "shims"), r"C:\ffmpeg\bin")
    # Finder/Dock-launched macOS apps receive a minimal PATH (/usr/bin:/bin:/usr/sbin:/sbin),
    # so Homebrew/MacPorts executables are invisible unless these locations are searched.
    return ("/opt/homebrew/bin", "/usr/local/bin", "/opt/local/bin", "/snap/bin")


EXTRA_BIN_DIRS = _extra_bin_dirs()
_FAULT_LOG = None


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def is_macos() -> bool:
    return platform.system() == "Darwin"


def is_windows() -> bool:
    return platform.system() == "Windows"


def is_wayland_session() -> bool:
    return platform.system() == "Linux" and (
        os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland"
        or (bool(os.environ.get("WAYLAND_DISPLAY")) and not os.environ.get("DISPLAY")))


def no_window() -> dict:
    """subprocess kwargs that stop Windows from flashing a console for each FFmpeg call."""
    if is_windows():
        return {"creationflags": getattr(__import__("subprocess"), "CREATE_NO_WINDOW", 0x08000000)}
    return {}


def bundle_bin_dirs() -> list[Path]:
    """Directories inside a packaged app that may contain bundled ffmpeg/ffprobe."""
    dirs = []
    base = getattr(sys, "_MEIPASS", None)
    if base:
        dirs.append(Path(base) / "bin")
    if is_frozen():
        exe = Path(sys.executable).resolve()
        # IDRA.app/Contents/MacOS/IDRA -> IDRA.app/Contents/Resources/bin; Windows/Linux: <dir>/bin
        dirs.append(exe.parent.parent / "Resources" / "bin")
        dirs.append(exe.parent / "bin")
        dirs.append(exe.parent / "_internal" / "bin")
    return dirs


def _names(name: str) -> list[str]:
    if is_windows() and not name.lower().endswith(".exe"):
        return [name + ".exe", name]
    return [name]


def _runnable(path: Path) -> bool:
    return path.is_file() and os.access(path, os.X_OK)


def find_executable(name: str) -> str | None:
    """Resolve an executable by explicit path, bundled copy, PATH, then common package-manager dirs."""
    if not name:
        return None
    candidate = Path(name).expanduser()
    if candidate.is_absolute() or "/" in name or "\\" in name:
        for option in [candidate] + ([candidate.with_name(candidate.name + ".exe")] if is_windows() else []):
            if _runnable(option):
                return str(option)
        return None
    for directory in bundle_bin_dirs():
        for item in _names(name):
            if _runnable(directory / item):
                return str(directory / item)
    found = shutil.which(name)
    if found:
        return found
    for directory in EXTRA_BIN_DIRS:
        for item in _names(name):
            if _runnable(Path(directory) / item):
                return str(Path(directory) / item)
    return None


def extend_path():
    """Make bundled and package-manager executables visible to child processes too."""
    current = os.environ.get("PATH", "")
    parts = current.split(os.pathsep) if current else []
    for directory in [str(d) for d in bundle_bin_dirs()] + list(EXTRA_BIN_DIRS):
        if directory not in parts and Path(directory).is_dir():
            parts.append(directory)
    os.environ["PATH"] = os.pathsep.join(parts)


def configure_playwright():
    """Frozen apps must look for Playwright browsers in the normal per-user cache."""
    if os.environ.get("PLAYWRIGHT_BROWSERS_PATH"):
        return
    if is_frozen():
        if is_macos():
            cache = Path.home() / "Library" / "Caches" / "ms-playwright"
        elif platform.system() == "Windows":
            cache = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "ms-playwright"
        else:
            cache = Path.home() / ".cache" / "ms-playwright"
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(cache)


def enable_fault_log(directory: Path):
    """Record native crashes (segfault/abort) in the log directory instead of vanishing silently."""
    global _FAULT_LOG
    with contextlib.suppress(Exception):
        directory.mkdir(parents=True, exist_ok=True)
        if _FAULT_LOG is None:
            _FAULT_LOG = open(directory / "native-crash.log", "a", encoding="utf-8")
            faulthandler.enable(_FAULT_LOG)


# ---------------------------------------------------------------------------
# macOS: pynput keyboard-listener crash guard
# ---------------------------------------------------------------------------
_KEYBOARD_PATCHED = False


def install_pynput_main_thread_guard() -> bool:
    """Prevent the macOS 14+ crash in pynput's keyboard listener.

    pynput 1.8.x calls TISCopyCurrentKeyboardInputSource/TISGetInputSourceProperty from
    the listener thread. Recent macOS versions assert that those Text Input Source calls
    run on the main dispatch queue and terminate the whole process otherwise. IDRA never
    uses translated characters (only key *names*), so the context is computed once here,
    on the main thread, and the listener thread reuses it.
    Must be called from the main thread before any keyboard listener starts.
    """
    global _KEYBOARD_PATCHED
    if _KEYBOARD_PATCHED or not is_macos():
        return _KEYBOARD_PATCHED
    try:
        from pynput.keyboard import _darwin as kb_darwin
        original = kb_darwin.keycode_context
        try:
            with original() as context:
                cached = context
        except Exception:
            cached = (None, None)

        @contextlib.contextmanager
        def cached_keycode_context():
            yield cached

        kb_darwin.keycode_context = cached_keycode_context
        _KEYBOARD_PATCHED = True
    except Exception as exc:
        logger.warning("pynput_guard_unavailable type=%s", type(exc).__name__)
    return _KEYBOARD_PATCHED


# ---------------------------------------------------------------------------
# macOS: permission status and prompts (CoreGraphics / ApplicationServices)
# ---------------------------------------------------------------------------
def _cg():
    return ctypes.CDLL("/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics")


def _bool_call(lib, name) -> bool | None:
    func = getattr(lib, name, None)
    if func is None:
        return None
    func.restype = ctypes.c_bool
    func.argtypes = []
    return bool(func())


def request_screen_recording() -> bool | None:
    """Ask macOS to list this app under Screen Recording and show the system prompt once."""
    if not is_macos():
        return None
    try:
        return _bool_call(_cg(), "CGRequestScreenCaptureAccess")
    except OSError:
        return None


def request_input_monitoring() -> bool | None:
    """Ask macOS to list this app under Input Monitoring (needed for keyboard categories)."""
    if not is_macos():
        return None
    try:
        return _bool_call(_cg(), "CGRequestListenEventAccess")
    except OSError:
        return None


def request_accessibility() -> bool | None:
    """Show the Accessibility prompt (AXIsProcessTrustedWithOptions with kAXTrustedCheckOptionPrompt)."""
    if not is_macos():
        return None
    try:
        from ApplicationServices import AXIsProcessTrustedWithOptions, kAXTrustedCheckOptionPrompt
        return bool(AXIsProcessTrustedWithOptions({kAXTrustedCheckOptionPrompt: True}))
    except Exception:
        try:
            services = ctypes.CDLL("/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices")
            return _bool_call(services, "AXIsProcessTrusted")
        except OSError:
            return None


SETTINGS_PANES = {
    "screen_recording": "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture",
    "accessibility": "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility",
    "input_monitoring": "x-apple.systempreferences:com.apple.preference.security?Privacy_ListenEvent",
}


def prepare_process():
    """Idempotent start-up preparation; safe on every platform."""
    extend_path()
    configure_playwright()
    if is_macos():
        install_pynput_main_thread_guard()
