"""Real Qt tests; never counted as passed when Qt or pytest-qt are absent."""
import importlib.util
import os
import time
import pytest
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
missing=importlib.util.find_spec('PyQt6') is None or importlib.util.find_spec('pytestqt') is None
pytestmark=[pytest.mark.gui,pytest.mark.skipif(missing,reason='PyQt6/pytest-qt unavailable; GUI execution NOT VERIFIED')]

@pytest.fixture
def window(qtbot,settings):
    from idra.ui.window import MainWindow
    w=MainWindow(settings);qtbot.addWidget(w);w.show()
    qtbot.waitUntil(lambda:not w.jobs,timeout=5000)
    yield w
    w.timer.stop()
    if w.tray:w.tray.hide()


def test_six_screens_and_visible_status(window):
    assert window.pages.count()==6
    assert window.navigation.count()==6
    assert window.status.text()=='IDLE'
    assert window.global_stop.text()=='STOP AND FINALIZE'


def test_consent_requires_both_checks(qtbot,settings):
    from PyQt6.QtWidgets import QDialogButtonBox
    from idra.ui.window import ConsentDialog
    dialog=ConsentDialog(settings);qtbot.addWidget(dialog)
    ok=dialog.buttons.button(QDialogButtonBox.StandardButton.Ok)
    assert not ok.isEnabled()
    dialog.authorized.setChecked(True);assert not ok.isEnabled()
    dialog.visual_risk.setChecked(True);assert ok.isEnabled()


def test_navigation_connects_actual_screens(window):
    for i in range(6):
        window.show_page(i)
        assert window.pages.currentIndex()==i


def test_gui_workers_keep_event_loop_responsive(window,qtbot):
    from PyQt6.QtCore import QTimer
    ticks=[];results=[]
    timer=QTimer();timer.setInterval(10);timer.timeout.connect(lambda:ticks.append(1));timer.start()
    window.run_job('Controlled fixture work',lambda c,p:(time.sleep(.25),'done')[1],results.append)
    qtbot.waitUntil(lambda:bool(results),timeout=5000)
    qtbot.waitUntil(lambda:not window.jobs,timeout=5000)
    timer.stop()
    assert results==['done'] and len(ticks)>=5


def test_gui_cancellation_reaches_worker(window,qtbot):
    flags=[]
    def work(cancel,progress):
        assert cancel.wait(3)
        flags.append(True)
        return 'cancelled'
    window.run_job('Cancellable fixture',work)
    window.cancel_operations()
    qtbot.waitUntil(lambda:not window.jobs,timeout=5000)
    assert flags==[True]


def test_gui_real_fixture_pause_resume_stop(window,qtbot):
    from idra.capture.fixtures import SyntheticSource
    window.run_job('Start controlled fixture',lambda c,p:window.controller.start(
        'GUI synthetic fixture','Test recording controls',consent=True,source=SyntheticSource(),synthetic=True))
    qtbot.waitUntil(lambda:window.controller.state.value=='RECORDING' and not window.jobs,timeout=10000)
    window.pause_recording()
    qtbot.waitUntil(lambda:window.controller.state.value=='PAUSED' and not window.jobs,timeout=5000)
    window.resume_recording()
    qtbot.waitUntil(lambda:window.controller.state.value=='RECORDING' and not window.jobs,timeout=5000)
    window.stop_recording()
    qtbot.waitUntil(lambda:window.controller.state.value=='COMPLETED' and not window.jobs,timeout=10000)
    assert window.controller.manifest.counts['frames']>0


def test_unhandled_exceptions_become_dialogs_not_aborts(window, qtbot, monkeypatch):
    import sys as _sys
    import threading as _threading
    from PyQt6.QtWidgets import QApplication
    from idra.ui.window import _install_exception_hooks
    shown = []
    monkeypatch.setattr(window, "error", shown.append)
    old_hook, old_thread_hook = _sys.excepthook, _threading.excepthook
    try:
        bridge = _install_exception_hooks(QApplication.instance(), lambda: window)
        try:
            raise ValueError("boom")
        except ValueError:
            _sys.excepthook(*_sys.exc_info())
        t = _threading.Thread(target=lambda: (_ for _ in ()).throw(RuntimeError("worker boom")))
        t.start(); t.join()
        qtbot.waitUntil(lambda: len(shown) == 2, timeout=3000)
        assert all("IDRA kept running" in m for m in shown)
        assert bridge is not None
    finally:
        _sys.excepthook, _threading.excepthook = old_hook, old_thread_hook


def test_unavailable_storage_falls_back_instead_of_crashing(tmp_path, monkeypatch, settings):
    from idra.ui import window as win
    monkeypatch.setenv("HOME", str(tmp_path))
    blocker = tmp_path / "not-a-dir"
    blocker.write_text("x")
    settings.storage_root = str(blocker / "recordings")
    repository, problem = win._usable_repository(settings)
    assert problem and "is unavailable" in problem
    assert repository.root == (tmp_path / "IDRA-recordings").resolve()


def test_settings_and_studio_validation_edge_cases(window):
    window.settings_page.masks.setPlainText("   \n  ")
    built = window.build_settings()
    assert built.privacy.masks == []
    window.settings_page.region.setText("0,0,1280")
    with pytest.raises(ValueError, match="four comma-separated integers"):
        window.build_settings()
    window.settings_page.region.setText("0,0,1280,720")
    window.studio.monitor.clear()
    built_fallback = window.build_settings()
    assert built_fallback.capture.monitor == 1


def test_library_empty_selection_clears_inspector(window):
    window.library.metadata.setPlainText('{"stale": true}')
    window.library.preview.setText("Stale preview")
    window.library.populate([])
    assert window.library.metadata.toPlainText() == ""
    assert "Select a session" in window.library.preview.text()
