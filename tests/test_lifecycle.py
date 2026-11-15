import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from idra.app.controller import SessionController
from idra.capture.fixtures import SyntheticSource
from idra.events.models import Payload, State
from idra.storage.files import iter_jsonl
from idra.storage.recovery import recover
from idra.storage.repository import Repository


def test_recording_requires_explicit_consent(settings):
    c = SessionController(settings)
    with pytest.raises(PermissionError):
        c.start("Not authorized", source=SyntheticSource(), synthetic=True)
    assert c.state == State.IDLE

def test_synthetic_source_requires_synthetic_label(settings):
    c = SessionController(settings)
    with pytest.raises(RuntimeError):
        c.start("Incorrect labeling", consent=True, source=SyntheticSource(), synthetic=False)
    assert c.state == State.FAILED

def test_pause_drops_capture_and_events_and_resume_finalizes(settings):
    c = SessionController(settings)
    m = c.start("SYNTHETIC pause test", consent=True, source=SyntheticSource(), synthetic=True)
    time.sleep(.12)
    c.pause()
    paused_at = c.clock.now_ns()
    assert not c.emit("key_press", Payload(key_category="protected"), "synthetic")
    time.sleep(.22)
    resume_at = c.clock.now_ns()
    c.resume()
    time.sleep(.2)
    m = c.stop()
    assert m.state == State.COMPLETED
    frames = list(iter_jsonl(c.repository.path(m.session_id) / "frames.jsonl"))
    assert not any(paused_at < f["t_ns"] < resume_at for f in frames)
    assert any(f["t_ns"] > resume_at for f in frames)
    assert c.stop().session_id == m.session_id

def test_new_session_does_not_overwrite_previous(settings):
    c = SessionController(settings)
    first = c.start("First fixture", consent=True, source=SyntheticSource(), synthetic=True).session_id
    c.stop()
    second = c.start("Second fixture", consent=True, source=SyntheticSource(), synthetic=True).session_id
    c.stop()
    assert first != second
    assert len(c.repository.list()) == 2
    assert c.repository.load(first).state == State.COMPLETED

def test_missing_ffmpeg_has_actionable_failure(settings):
    settings.ffmpeg = "idra-missing-ffmpeg-command"
    c = SessionController(settings)
    with pytest.raises(RuntimeError, match="Executable unavailable"):
        c.start("Missing dependency", consent=True, source=SyntheticSource(), synthetic=True)
    assert c.state == State.FAILED

def test_capture_failure_is_preserved_as_failed(settings):
    class Broken(SyntheticSource):
        def grab(self):
            if self.index >= 2:
                raise OSError("Injected capture failure")
            return super().grab()
    c = SessionController(settings)
    c.start("Injected failure", consent=True, source=Broken(), synthetic=True)
    assert c.stop_requested.wait(3)
    m = c.stop()
    assert m.state == State.FAILED
    assert any("CAPTURE_FAILED" in code for code in m.failure_codes)

def test_disk_reserve_failure_is_not_completed(settings, monkeypatch):
    from collections import namedtuple
    c = SessionController(settings)
    c.start("Disk reserve injection", consent=True, source=SyntheticSource(), synthetic=True)
    usage = namedtuple("usage", "total used free")
    monkeypatch.setattr("idra.capture.pipeline.shutil.disk_usage", lambda _:usage(100,100,0))
    assert c.stop_requested.wait(3)
    m = c.stop()
    assert m.state == State.FAILED
    assert "INSUFFICIENT_STORAGE" in m.failure_codes

def test_browser_failure_cleans_up_capture(settings):
    class FailingBrowser:
        def __init__(self, *args):
            self.error, self.status = "INJECTED_BROWSER_FAILURE", "failed"
        def start(self):
            raise RuntimeError(self.error)
        def stop(self):
            pass
        def stats(self):
            return {}
    settings.browser.enabled = True
    c = SessionController(settings, browser_factory=FailingBrowser)
    with pytest.raises(RuntimeError):
        c.start("Browser failure fixture", consent=True, source=SyntheticSource(), synthetic=True)
    assert c.manifest.state == State.FAILED
    assert not c.pipeline.capture_thread.is_alive()
    assert not c.pipeline.encode_thread.is_alive()

def test_raw_browser_text_is_rejected_before_journaling(settings):
    c = SessionController(settings)
    c.start("Payload guard", consent=True, source=SyntheticSource(), synthetic=True)
    try:
        with pytest.raises(ValueError):
            c.emit("browser_action", Payload(action="input", text="must not persist"), "browser")
    finally:
        m = c.stop()
    assert "must not persist" not in (c.repository.path(m.session_id) / "events.jsonl").read_text()

def test_actual_process_interruption_can_be_recovered(tmp_path):
    root = tmp_path / "crash-fixture"
    code = """
import os,time
from pathlib import Path
from idra.app.controller import SessionController
from idra.capture.fixtures import SyntheticSource
from idra.events.models import Settings,Payload
s=Settings(storage_root=os.environ['FIXTURE_ROOT'],min_free_mb=1,flush_interval_s=.05,batch_size=8)
s.capture.capture_mouse=False
s.capture.output_width=320
c=SessionController(s)
m=c.start('SYNTHETIC crash fixture',consent=True,source=SyntheticSource(),synthetic=True)
c.emit('mouse_button_down',Payload(button='left'), 'synthetic')
Path(os.environ['FIXTURE_ROOT'],'sid.txt').write_text(str(m.session_id))
time.sleep(.6)
os._exit(17)
"""
    env = os.environ.copy()
    env["FIXTURE_ROOT"] = str(root)
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
    p = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, timeout=30)
    assert p.returncode == 17, p.stderr.decode()
    sid = (root / "sid.txt").read_text()
    time.sleep(.3)
    repository = Repository(root)
    report = recover(repository, sid)
    assert report["events"] >= 1 and report["frames"] >= 1
    assert repository.load(sid).state == State.INTERRUPTED
