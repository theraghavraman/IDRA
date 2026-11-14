"""No green status without a completed check. No automatic permission bypass."""
from __future__ import annotations
import ctypes
import importlib
import importlib.metadata
import os
import platform
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from idra.events.models import Settings
from idra.app.runtime import find_executable, no_window

PINS = {"pydantic":"2.13.5", "numpy":"2.3.5", "opencv-python-headless":"4.13.0.92",
        "PyQt6":"6.10.0", "PyQt6-Qt6":"6.10.0", "playwright":"1.57.0", "pynput":"1.8.1", "mss":"10.1.0"}

def mac_permissions() -> dict[str, bool | None]:
    if platform.system() != "Darwin":
        return {}
    results = {"screen_recording": None, "accessibility": None, "input_monitoring": None}
    try:
        cg = ctypes.CDLL("/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics")
        for key, name in (("screen_recording", "CGPreflightScreenCaptureAccess"),
                          ("input_monitoring", "CGPreflightListenEventAccess")):
            func = getattr(cg, name, None)
            if func:
                func.restype = ctypes.c_bool
                func.argtypes = []
                results[key] = bool(func())
        services = ctypes.CDLL("/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices")
        services.AXIsProcessTrusted.restype = ctypes.c_bool
        services.AXIsProcessTrusted.argtypes = []
        results["accessibility"] = bool(services.AXIsProcessTrusted())
    except (OSError, AttributeError):
        pass
    return results

def diagnose(settings: Settings, *, probe_screen=False) -> dict:
    checks = []
    def add(name, status, detail):
        checks.append({"name":name, "status":status, "detail":detail})
    supported = (3, 11) <= sys.version_info[:2] < (3, 15)
    add("Python", "PASS" if supported else "FAIL", platform.python_version())
    for name, version in PINS.items():
        try:
            actual = importlib.metadata.version(name)
            add(name, "PASS" if actual == version else "WARN", f"Installed {actual}; declared pin {version}")
        except importlib.metadata.PackageNotFoundError:
            module = {"opencv-python-headless":"cv2", "PyQt6-Qt6":"PyQt6.QtCore"}.get(name, name)
            try:
                imported = importlib.import_module(module)
                version = getattr(imported, "__version__", None) or getattr(imported, "QT_VERSION_STR", None) or "bundled"
                add(name, "PASS", f"Module present ({version}); package metadata not bundled; declared pin {PINS[name]}")
            except Exception:
                add(name, "FAIL", "Not installed; run the documented requirements installation")
    for key, value in (("FFmpeg", settings.ffmpeg), ("FFprobe", settings.ffprobe)):
        found = find_executable(value)
        if not found:
            add(key, "FAIL", "Executable not found. Install FFmpeg separately from Python packages.")
            continue
        try:
            p = subprocess.run([found, "-version"], capture_output=True, text=True, timeout=10, **no_window())
            add(key, "PASS" if p.returncode == 0 else "FAIL", p.stdout.splitlines()[0] if p.stdout else "Version check failed")
            if key == "FFmpeg":
                enc = subprocess.run([found, "-hide_banner", "-encoders"], capture_output=True, text=True, timeout=10, **no_window())
                good = enc.returncode == 0 and "libx264" in enc.stdout
                add("H.264 encoder", "PASS" if good else "FAIL", "libx264 available" if good else "FFmpeg build must include libx264")
        except (OSError, subprocess.TimeoutExpired):
            add(key, "FAIL", "Executable could not be run")
    permissions = mac_permissions()
    for name, permitted in permissions.items():
        status = "PASS" if permitted is True else "FAIL" if permitted is False else "UNKNOWN"
        add(name, status, "Granted to this process" if permitted else
            "Grant it in System Settings > Privacy & Security to "
            + ("IDRA" if getattr(sys, "frozen", False) else "the app that launched Python (Terminal/IDE)")
            + ", then quit and reopen it")
    if platform.system() == "Darwin":
        mac_version = platform.mac_ver()[0]
        major = int(mac_version.split(".")[0]) if mac_version else 0
        add("Qt macOS baseline", "PASS" if major >= 13 else "FAIL", "Pinned Qt 6.10 requires macOS 13 or newer")
    if platform.system() == "Linux":
        wayland = os.getenv("XDG_SESSION_TYPE", "").lower() == "wayland"
        add("Desktop backend", "FAIL" if wayland else "UNKNOWN",
            "Full Wayland capture/input is unsupported" if wayland else "X11 availability requires an explicit capture probe")
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = Path(settings.browser.executable or p.chromium.executable_path)
            good = browser.is_file() and os.access(browser, os.X_OK)
            add("Chromium executable", "PASS" if good else "FAIL",
                "Executable exists; launch is not verified by this check" if good else "Run python -m playwright install chromium, or configure an executable")
    except Exception:
        add("Chromium executable", "FAIL", "Playwright runtime could not be inspected")
    root = Path(settings.storage_root).expanduser()
    parent = root if root.exists() else next((p for p in root.parents if p.exists()), Path.home())
    try:
        free = shutil.disk_usage(parent).free
        add("Storage capacity", "PASS" if free >= settings.min_free_mb * 1024**2 else "FAIL",
            f"{free / 1024**3:.2f} GiB free; warning/stop reserve {settings.min_free_mb} MiB")
    except OSError:
        add("Storage capacity", "FAIL", "Storage path could not be inspected")
    if probe_screen:
        from idra.capture.sources import source_for
        source = source_for(settings.capture, settings.ffmpeg)
        try:
            source.open()
            image = source.grab()
            add("Screen capture probe", "PASS", f"Captured and discarded {image.shape[1]}x{image.shape[0]} pixels")
        except Exception as exc:
            add("Screen capture probe", "FAIL", f"Capture failed: {type(exc).__name__}; check permissions/backend/monitor")
        finally:
            source.close()
    else:
        add("Screen capture probe", "NOT_RUN", "Requires explicit consent; no screen image was acquired by this diagnostics run")
    return {"generated_at":datetime.now(timezone.utc).isoformat(), "platform":platform.system(),
            "architecture":platform.machine(), "checks":checks,
            "note":"Package presence and permission checks do not prove end-to-end recording compatibility."}
