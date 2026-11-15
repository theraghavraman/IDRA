import importlib.util
import json

import pytest

from idra.app.cli import main
from idra.app.settings import load_settings, save_settings
from idra.diagnostics.checks import diagnose
from idra.events.models import Settings


def test_settings_round_trip_minimizes_persisted_start_url(tmp_path):
    settings = Settings(storage_root=str(tmp_path / "root"))
    settings.browser.start_url = "https://example.com/private?secret=NO_STORE#frag"
    target = tmp_path / "settings.json"
    save_settings(settings, target)
    result = load_settings(target)
    assert result.browser.start_url == "https://example.com"
    assert "NO_STORE" not in target.read_text()


def test_cli_refuses_capture_without_consent(tmp_path, capsys):
    assert main(["--storage", str(tmp_path / "r"), "record", "--label", "must refuse"]) == 2
    assert "consent" in capsys.readouterr().err.lower()


def test_cli_screen_probe_requires_consent(tmp_path, capsys):
    assert main(["--storage", str(tmp_path / "r"), "diagnostics", "--probe-screen"]) == 2
    assert "consent" in capsys.readouterr().err.lower()


def test_cli_inspects_and_validates_real_session(recorded, capsys):
    repo, sid = recorded
    assert main(["--storage", str(repo.root), "inspect", sid]) == 0
    assert json.loads(capsys.readouterr().out)["session_id"] == sid
    assert main(["--storage", str(repo.root), "validate", sid, "--full-decode"]) == 0
    assert json.loads(capsys.readouterr().out)["errors"] == 0


def test_cli_delete_requires_confirmation(recorded, capsys):
    repo, sid = recorded
    assert main(["--storage", str(repo.root), "delete", sid]) == 2
    assert repo.path(sid).exists()


def test_cli_real_synthetic_demo_and_export(tmp_path, capsys):
    root = tmp_path / "demo"
    out = tmp_path / "dataset"
    assert main(["--storage", str(root), "demo", "--seconds", "0.4", "--export", str(out)]) == 0
    text = capsys.readouterr().out
    assert "SYNTHETIC FIXTURE" in text
    assert (out / "manifest.json").exists()
    assert main(["verify-export", str(out)]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "passed"


def test_diagnostics_do_not_invent_success(settings):
    report = diagnose(settings)
    assert report["checks"]
    assert any(c["status"] == "NOT_RUN" for c in report["checks"])
    for c in report["checks"]:
        assert c["status"] in {"PASS", "FAIL", "WARN", "UNKNOWN", "NOT_RUN"}


@pytest.mark.skipif(
    importlib.util.find_spec("PyQt6") is not None,
    reason="Missing-Qt failure test only applies when Qt is absent",
)
def test_gui_missing_dependency_is_actionable(tmp_path, capsys):
    assert main(["--storage", str(tmp_path), "gui"]) == 2
    assert "PyQt6" in capsys.readouterr().err


def test_cli_summary_and_state_filter(recorded, capsys):
    repo, sid = recorded
    assert main(["--storage", str(repo.root), "summary"]) == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["total_sessions"] >= 1
    assert summary["by_state"].get("COMPLETED", 0) >= 1
    assert main(["--storage", str(repo.root), "list", "--state", "COMPLETED"]) == 0
    rows = json.loads(capsys.readouterr().out)
    assert any(r["id"] == sid for r in rows)
    assert main(["--storage", str(repo.root), "list", "--state", "FAILED"]) == 0
    assert json.loads(capsys.readouterr().out) == []
