"""Optional frontmost-application metadata. Window titles are never collected."""
from __future__ import annotations
import os
import platform
import re
import shutil
import subprocess
import threading
from pathlib import Path
from idra.events.models import Payload

def active_application() -> tuple[str, int] | None:
    system = platform.system()
    if system == "Darwin":
        try:
            from AppKit import NSWorkspace
        except ImportError:
            return None
        app = NSWorkspace.sharedWorkspace().frontmostApplication()
        return (str(app.localizedName()), int(app.processIdentifier())) if app else None
    if system == "Windows":
        import ctypes
        from ctypes import wintypes
        hwnd = ctypes.windll.user32.GetForegroundWindow()
        pid = wintypes.DWORD()
        ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
        handle = kernel.OpenProcess(0x1000, False, pid.value)
        if not handle:
            return None
        try:
            buf = ctypes.create_unicode_buffer(32768)
            size = wintypes.DWORD(len(buf))
            if kernel.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
                return Path(buf.value).name, int(pid.value)
        finally:
            kernel.CloseHandle(handle)
        return None
    if system == "Linux" and shutil.which("xprop") and os.getenv("DISPLAY"):
        first = subprocess.run(["xprop", "-root", "_NET_ACTIVE_WINDOW"], capture_output=True, text=True, timeout=2)
        match = re.search(r"0x[0-9a-fA-F]+", first.stdout)
        if not match or match.group() == "0x0":
            return None
        second = subprocess.run(["xprop", "-id", match.group(), "_NET_WM_PID"], capture_output=True, text=True, timeout=2)
        pid_match = re.search(r"=\s*(\d+)", second.stdout)
        if pid_match:
            pid = int(pid_match.group(1))
            try:
                return Path(f"/proc/{pid}/comm").read_text().strip()[:256], pid
            except OSError:
                return None
    return None

class ContextWatcher:
    def __init__(self, clock, emit, is_active):
        self.clock, self.emit, self.is_active = clock, emit, is_active
        self.stopping = threading.Event()
        self.status = "not_started"
        self.thread = threading.Thread(target=self._run, daemon=True, name="idra-window-context")
    def start(self):
        self.thread.start()
    def _run(self):
        previous = None
        while not self.stopping.is_set():
            if self.is_active():
                stamp = self.clock.now_ns()
                try:
                    current = active_application()
                    self.status = "available" if current else "unavailable"
                    if current and current != previous:
                        self.emit("window_context", Payload(app=current[0], pid=current[1]),
                                  "window_context", t_ns=stamp)
                        previous = current
                except Exception:
                    self.status = "unavailable"
            self.stopping.wait(0.5)
    def stop(self):
        self.stopping.set()
        self.thread.join(6)
        if self.thread.is_alive():
            raise RuntimeError("WINDOW_CONTEXT_SHUTDOWN_TIMEOUT")
