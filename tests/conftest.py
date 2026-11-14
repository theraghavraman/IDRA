import shutil
import time
import pytest
from idra.app.controller import SessionController
from idra.capture.fixtures import SyntheticSource
from idra.events.models import Payload, Settings
from idra.storage.repository import Repository

@pytest.fixture(scope="session")
def recording_template(tmp_path_factory):
    root = tmp_path_factory.mktemp("recording-template")
    settings = Settings(storage_root=str(root), min_free_mb=1, batch_size=16, flush_interval_s=0.05)
    settings.capture.capture_mouse = False
    settings.capture.fps = 10
    settings.capture.output_width = 320
    settings.capture.screenshot_interval_s = 0.1
    c = SessionController(settings)
    m = c.start("SYNTHETIC evaluation session", "Click a generated rectangle", consent=True,
                source=SyntheticSource(), synthetic=True)
    c.annotate("Synthetic task", boundary="start")
    c.emit("mouse_button_down", Payload(x=100, y=150, button="left", coordinate_space="desktop"), "synthetic")
    c.emit("mouse_button_up", Payload(x=100, y=150, button="left", coordinate_space="desktop"), "synthetic")
    c.emit("key_press", Payload(key_category="protected"), "synthetic")
    time.sleep(0.15)
    c.emit("scroll", Payload(x=100, y=150, dx=0, dy=-1, coordinate_space="desktop"), "synthetic")
    c.pause()
    time.sleep(0.1)
    c.resume()
    c.emit("mouse_button_down", Payload(x=120, y=170, button="left"), "synthetic")
    time.sleep(0.25)
    c.annotate("Fixture complete", boundary="end")
    m = c.stop()
    assert m.state.value == "COMPLETED", m.failure_codes
    return root, str(m.session_id)

@pytest.fixture
def recorded(recording_template, tmp_path):
    original, sid = recording_template
    root = tmp_path / "recordings"
    shutil.copytree(original, root)
    repo = Repository(root)
    return repo, sid

@pytest.fixture
def settings(tmp_path):
    s = Settings(storage_root=str(tmp_path / "sessions-root"), min_free_mb=1, batch_size=8, flush_interval_s=0.05)
    s.capture.capture_mouse = False
    s.capture.fps = 10
    s.capture.output_width = 320
    return s
