#!/usr/bin/env python3
"""Creates only watermarked synthetic media; never reads the desktop."""

import json
import shutil
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from idra.app.controller import SessionController
from idra.capture.fixtures import SyntheticSource
from idra.datasets.export import export_dataset
from idra.datasets.quality import validate_session
from idra.events.models import Event, Frame, Manifest, Payload, Settings, Trajectory
from idra.storage.files import atomic_json, iter_jsonl
from idra.storage.repository import Repository

root = Path(__file__).resolve().parents[1]
examples = root / "examples"
examples.mkdir(exist_ok=True)
for name, model in [
    ("event", Event),
    ("frame", Frame),
    ("session-manifest", Manifest),
    ("trajectory", Trajectory),
    ("settings", Settings),
]:
    atomic_json(root / "docs/schemas" / f"{name}.schema.json", model.model_json_schema())
config = Settings(storage_root="./local-recordings", min_free_mb=1024)
atomic_json(root / "config.example.json", config.model_dump(mode="json"))
with tempfile.TemporaryDirectory(prefix="idra-release-fixture-") as temp:
    settings = Settings(storage_root=str(Path(temp) / "clean"), min_free_mb=1)
    settings.capture.capture_mouse = False
    settings.capture.fps = 8
    settings.capture.output_width = 480
    settings.capture.screenshot_interval_s = 0.2
    c = SessionController(settings)
    m = c.start(
        "SYNTHETIC release fixture",
        "Click the generated rectangle",
        consent=True,
        source=SyntheticSource(),
        synthetic=True,
    )
    c.annotate("Generated rectangle task", boundary="start")
    for i in range(5):
        c.emit(
            "mouse_button_down",
            Payload(x=100 + i * 10, y=160, button="left", coordinate_space="desktop"),
            "synthetic",
        )
        time.sleep(0.15)
    c.annotate("Synthetic fixture complete", boundary="end")
    m = c.stop()
    assert m.state.value == "COMPLETED", m.failure_codes
    repo = c.repository
    sid = str(m.session_id)
    out = examples / "synthetic_dataset"
    if out.exists():
        raise FileExistsError("Do not overwrite examples without explicit removal")
    result = export_dataset(repo, [sid], out, include_media=True, media_reviewed=True)
    atomic_json(examples / "sample-quality.json", validate_session(repo, sid, full_decode=True))
    atomic_json(examples / "verification.json", result["verification"])
    broken_root = Path(temp) / "defective"
    broken = Repository(broken_root)
    shutil.copytree(repo.path(sid), broken.path(sid))
    broken.scan()
    rows = list(iter_jsonl(broken.path(sid) / "events.jsonl"))
    rows[1]["payload"].update(in_capture=True, x_px=99999, y_px=99999)
    rows.append(rows[0])
    rows.append({"deliberate_defect": "invalid schema"})
    (broken.path(sid) / "events.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    frames = list(iter_jsonl(broken.path(sid) / "frames.jsonl"))
    shot = next(f["screenshot"] for f in frames if f["screenshot"])
    (broken.path(sid) / shot).unlink()
    bad = validate_session(broken, sid)
    expected = {"DUPLICATE_EVENT", "INVALID_COORDINATES", "EVENT_SCHEMA", "MISSING_SCREENSHOT"}
    assert expected <= bad["issue_counts"].keys(), bad
    atomic_json(examples / "defective-quality.json", bad)
    defect = examples / "deliberately_defective_fixture"
    defect.mkdir()
    # Keep an inspectable malformed journal plus recipe, not a misleading valid dataset.
    shutil.copy2(broken.path(sid) / "events.jsonl", defect / "events.jsonl")
    atomic_json(
        defect / "expected-defects.json",
        {
            "synthetic": True,
            "valid_dataset": False,
            "expected_issue_codes": sorted(expected),
            "reproduce": "python scripts/make_examples.py in a clean source copy",
            "notes": "The builder also removes a screenshot from a temporary copied session before validating; raw broken journal is included for inspection.",
        },
    )
print(
    json.dumps(
        {
            "synthetic_session_id": sid,
            "dataset": str(out),
            "verification": result["verification"],
            "defects_detected": sorted(expected),
        },
        indent=2,
    )
)
