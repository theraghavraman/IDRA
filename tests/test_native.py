"""Uses only a newly created isolated Xvfb display, never the user's desktop."""

import importlib.util
import platform
import shutil
import subprocess
import time
from pathlib import Path

import pytest

from idra.app.controller import SessionController
from idra.capture.sources import FFmpegX11Source, MSSSource
from idra.media.images import read_frame
from idra.storage.files import iter_jsonl

pytestmark = pytest.mark.native


@pytest.fixture
def isolated_x11(monkeypatch):
    if platform.system() != "Linux" or not shutil.which("Xvfb") or not shutil.which("xmessage"):
        pytest.skip("Isolated X11 integration requires Linux, Xvfb and xmessage")
    display = None
    for n in range(190, 240):
        if not Path(f"/tmp/.X11-unix/X{n}").exists() and not Path(f"/tmp/.X{n}-lock").exists():
            display = f":{n}"
            break
    if display is None:
        pytest.skip("No free isolated test display")
    xvfb = subprocess.Popen(
        ["Xvfb", display, "-screen", "0", "640x360x24", "-nolisten", "tcp"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    message = None
    try:
        for _ in range(100):
            if Path("/tmp/.X11-unix/X" + display[1:]).exists():
                break
            if xvfb.poll() is not None:
                pytest.fail("Isolated Xvfb failed")
            time.sleep(0.03)
        message = subprocess.Popen(
            [
                "xmessage",
                "-display",
                display,
                "-geometry",
                "580x250+10+10",
                "-buttons",
                "OK:0",
                "SYNTHETIC ISOLATED CAPTURE FIXTURE - NO PRIVATE DESKTOP",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        time.sleep(0.15)
        monkeypatch.setenv("XDG_SESSION_TYPE", "x11")
        yield display
    finally:
        for p in (message, xvfb):
            if p:
                if p.poll() is None:
                    p.terminate()
                try:
                    p.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    p.kill()
                    p.wait(timeout=5)


def test_actual_ffmpeg_x11_capture_and_recording(settings, isolated_x11):
    settings.capture.backend = "ffmpeg_x11"
    settings.capture.x11_display = isolated_x11
    settings.capture.region_width = 640
    settings.capture.region_height = 360

    class IsolatedFixtureSource(FFmpegX11Source):
        synthetic = True

    c = SessionController(settings)
    m = c.start(
        "Synthetic isolated Xvfb capture",
        "Read generated test window",
        consent=True,
        source=IsolatedFixtureSource(settings.capture),
        synthetic=True,
    )
    time.sleep(0.3)
    m = c.stop()
    assert m.state.value == "COMPLETED", m.failure_codes
    assert m.counts["frames"] >= 2
    image = read_frame(c.repository.path(m.session_id) / m.media, 0)
    assert image.std() > 10
    frames = list(iter_jsonl(c.repository.path(m.session_id) / "frames.jsonl"))
    assert all(f["timestamp_kind"] == "received" and f["synthetic"] for f in frames)
    assert any("receive" in w.lower() for w in m.warnings)


@pytest.mark.skipif(
    importlib.util.find_spec("mss") is None,
    reason="MSS package unavailable; native MSS behavior NOT VERIFIED",
)
def test_actual_mss_on_isolated_x11(settings, isolated_x11, monkeypatch):
    monkeypatch.setenv("DISPLAY", isolated_x11)
    source = MSSSource(settings.capture)
    try:
        geometry = source.open()
        image = source.grab()
        assert geometry["width"] == 640
        assert image.shape == (360, 640, 3)
        assert image.std() > 10
    finally:
        source.close()


@pytest.mark.skipif(
    importlib.util.find_spec("pynput") is None,
    reason="Pynput package unavailable; native input-hook behavior NOT VERIFIED",
)
def test_actual_pynput_on_isolated_x11(isolated_x11, monkeypatch):
    monkeypatch.setenv("DISPLAY", isolated_x11)
    from pynput import mouse

    moves = []
    with mouse.Listener(on_move=lambda x, y: moves.append((x, y))) as listener:
        listener.wait()
        controller = mouse.Controller()
        controller.position = (123, 77)
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline and (123, 77) not in moves:
            time.sleep(0.02)
    assert (123, 77) in moves
