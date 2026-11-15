#!/usr/bin/env python3
"""Verify inventory and tests after extraction. Existing dependencies are reused, not installed."""

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

p = argparse.ArgumentParser()
p.add_argument("archive", type=Path)
p.add_argument("--report", type=Path, default=Path("clean-extraction-report.json"))
a = p.parse_args()
result = {
    "archive": a.archive.name,
    "archive_sha256": hashlib.sha256(a.archive.read_bytes()).hexdigest(),
    "fresh_extraction": False,
    "fresh_dependency_install": "NOT_VERIFIED_EXISTING_RUNTIME_REUSED",
    "checks": [],
}
with tempfile.TemporaryDirectory(prefix="idra-release-check-") as temp:
    dest = Path(temp)
    with zipfile.ZipFile(a.archive) as z:
        for info in z.infolist():
            rel = PurePosixPath(info.filename)
            if (
                rel.is_absolute()
                or ".." in rel.parts
                or "\\" in info.filename
                or ":" in info.filename
            ):
                raise ValueError("Unsafe ZIP member")
            if (info.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError("Symlink ZIP member refused")
        bad = z.testzip()
        if bad:
            raise ValueError("ZIP CRC failed")
        z.extractall(dest)
    root = dest / "intelligent_data_recording_agent"
    result["fresh_extraction"] = True
    inventory = json.loads((root / "RELEASE_CONTENTS.json").read_text())
    for rel, expected in inventory["sha256"].items():
        if hashlib.sha256((root / rel).read_bytes()).hexdigest() != expected:
            raise ValueError("Source inventory mismatch")
    result["checks"].append(
        {"name": "inventory", "status": "passed", "files": len(inventory["sha256"])}
    )
    env = dict(os.environ)
    env["PYTHONPATH"] = str(root / "src")
    env["QT_QPA_PLATFORM"] = "offscreen"
    calls = [
        ("compileall", [sys.executable, "-m", "compileall", "-q", "src", "tests", "scripts"]),
        ("pytest", [sys.executable, "-m", "pytest", "-q", "--tb=short"]),
        (
            "synthetic_demo",
            [
                sys.executable,
                "-m",
                "idra",
                "--storage",
                str(dest / "recordings"),
                "demo",
                "--seconds",
                "0.5",
                "--export",
                str(dest / "dataset"),
            ],
        ),
        ("export_reimport", [sys.executable, "-m", "idra", "verify-export", str(dest / "dataset")]),
    ]
    for name, cmd in calls:
        r = subprocess.run(cmd, cwd=root, env=env, capture_output=True, text=True, timeout=240)
        result["checks"].append(
            {
                "name": name,
                "status": "passed" if r.returncode == 0 else "failed",
                "returncode": r.returncode,
                "stdout_tail": r.stdout[-15000:],
                "stderr_tail": r.stderr[-4000:],
            }
        )
result["status"] = "passed" if all(c["status"] == "passed" for c in result["checks"]) else "failed"
a.report.parent.mkdir(parents=True, exist_ok=True)
a.report.write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps(result, indent=2))
sys.exit(result["status"] != "passed")
