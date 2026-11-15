#!/usr/bin/env python3
"""Offline, non-invasive IDRA 0.9.3-rc2 acceptance smoke runner.

Run on EACH target operating system. Does not access the live desktop, run a GUI,
record real users or sign executables. Native/manual and license gates remain open.

Examples:
  python scripts/native_acceptance_runner.py --source-root /path/to/intelligent_data_recording_agent --out /path/to/evidence --zip-file /path/to/source.zip --pytest
  python scripts/native_acceptance_runner.py --source-root C:/idra/intelligent_data_recording_agent --out C:/idra-acceptance --pytest
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from zipfile import ZipFile


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for part in iter(lambda: f.read(1024 * 1024), b""):
            h.update(part)
    return h.hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source-root", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--zip-file", type=Path)
    p.add_argument("--pytest", action="store_true")
    args = p.parse_args()
    root = args.source_root.resolve()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env["PYTHONPATH"] = str(root / "src") + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    summary = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "classification": "source-only automated smoke; NOT production/native-hardware acceptance",
        "platform": {"os": platform.system(), "os_version": platform.platform(), "arch": platform.machine(), "python": platform.python_version()},
        "python_dependencies": {}, "checks": [], "manual_gates_not_tested": [
            "packaged application and clean installer", "native PyQt6 graphical interface",
            "real OS permissions and global keyboard stop hook", "real input hooks and multi-monitor DPI",
            "Developer ID/Authenticator signing, macOS notarization, Windows Authenticode",
            "full transitive and binary SBOM, legal and vulnerability approval",
            "physical hardware/long-running screen capture, sleep/wake, disk exhaustion",
        ],
    }

    def check(name, status, **details):
        summary["checks"].append({"check": name, "status": status, **details})
        print(f"{status:7} {name}", flush=True)

    def run(name, argv, timeout=120, expected=0):
        try:
            child_env = dict(env)
            if name == "pytest" and platform.system() == "Linux" and not child_env.get("DISPLAY") and not child_env.get("WAYLAND_DISPLAY"):
                child_env["QT_QPA_PLATFORM"] = "offscreen"
            if name == "pytest":
                with (out / f"{name}.stdout.txt").open("w", encoding="utf-8") as stdout_file, (out / f"{name}.stderr.txt").open("w", encoding="utf-8") as stderr_file:
                    result = subprocess.run([str(x) for x in argv], cwd=root, env=child_env,
                                            stdout=stdout_file, stderr=stderr_file, timeout=timeout)
                return subprocess.CompletedProcess(argv, result.returncode,
                        (out / f"{name}.stdout.txt").read_text(encoding="utf-8"),
                        (out / f"{name}.stderr.txt").read_text(encoding="utf-8"))
            result = subprocess.run([str(x) for x in argv], cwd=root, env=child_env, capture_output=True,
                                    text=True, timeout=timeout, errors="replace")
            (out / f"{name}.stdout.txt").write_text(result.stdout, encoding="utf-8")
            (out / f"{name}.stderr.txt").write_text(result.stderr, encoding="utf-8")
            return result
        except Exception as exc:
            (out / f"{name}.stderr.txt").write_text(str(exc), encoding="utf-8")
            return None

    if args.zip_file:
        z = args.zip_file.resolve()
        with ZipFile(z) as archive:
            err = archive.testzip()
        check("source_zip_crc", "PASS" if err is None else "FAIL", zip_sha256=digest(z), corrupted_member=err)

    inventory_file = root / "RELEASE_CONTENTS.json"
    inventory = json.loads(inventory_file.read_text(encoding="utf-8"))["sha256"]
    mismatched = [k for k, want in inventory.items() if not (root / k).is_file() or digest(root / k) != want]
    check("source_inventory", "PASS" if not mismatched else "FAIL", matched=len(inventory)-len(mismatched),
          total=len(inventory), mismatches=mismatched[:20])

    for pkg in ("PyQt6", "PyQt6-Qt6", "pynput", "mss", "PyInstaller", "playwright"):
        try:
            summary["python_dependencies"][pkg] = importlib.metadata.version(pkg)
        except importlib.metadata.PackageNotFoundError:
            summary["python_dependencies"][pkg] = "NOT_INSTALLED"

    cli = [sys.executable, "-m", "idra"]
    recordings = out / "synthetic-recordings"
    dataset = out / "synthetic-dataset"
    check("python_compile", "PASS" if (r := run("compile", [sys.executable, "-m", "compileall", "-q", str(root / "src")], 60)) and r.returncode == 0 else "FAIL")
    diag = run("diagnostics", cli + ["--storage", recordings, "diagnostics"], 90)
    if diag and diag.stdout.strip():
        try:
            summary["runtime_diagnostics"] = json.loads(diag.stdout)
        except ValueError:
            summary["runtime_diagnostics_raw"] = diag.stdout[-2000:]
    check("diagnostics_execution", "PASS" if diag is not None and diag.stdout.strip().startswith("{") else "FAIL",
          exit_code=diag.returncode if diag else None)

    demo = run("demo", cli + ["--storage", recordings, "demo", "--seconds", "2", "--export", dataset], 120)
    check("synthetic_capture_export", "PASS" if demo and demo.returncode == 0 else "FAIL",
          exit_code=demo.returncode if demo else None)
    if demo and demo.returncode == 0:
        vr = run("verify_export", cli + ["verify-export", dataset], 120)
        passed = bool(vr and vr.returncode == 0 and json.loads(vr.stdout).get("status") == "passed")
        check("export_reimport", "PASS" if passed else "FAIL")
    else:
        check("export_reimport", "SKIP")

    no_consent = run("no_consent", cli + ["--storage", recordings, "record", "--label", "no consent check", "--seconds", "0.2"], 30)
    check("record_without_consent_rejected", "PASS" if no_consent and no_consent.returncode != 0 else "FAIL")

    sessions = list((recordings / "sessions").glob("*/manifest.json")) if recordings.exists() else []
    if sessions:
        session_id = sessions[0].parent.name
        no_review = run("no_media_review", cli + ["--storage", recordings, "export", session_id,
                                                "--out", out / "must-not-export", "--include-media"], 60)
        check("unreviewed_media_export_rejected", "PASS" if no_review and no_review.returncode != 0 else "FAIL")
    else:
        check("unreviewed_media_export_rejected", "SKIP")

    if dataset.is_dir() and (dataset / "events.jsonl").is_file():
        corrupt = out / "tamper-sandbox"
        shutil.copytree(dataset, corrupt, dirs_exist_ok=True)
        with (corrupt / "events.jsonl").open("a", encoding="utf-8") as f:
            f.write("\n")
        tamper = run("tampered_dataset", cli + ["verify-export", corrupt], 60)
        check("tampered_export_rejected", "PASS" if tamper and tamper.returncode != 0 else "FAIL")
        shutil.rmtree(corrupt)
    else:
        check("tampered_export_rejected", "SKIP")

    if args.pytest:
        tests = run("pytest", [sys.executable, "-m", "pytest", "-q", "-ra", "--tb=short", "-p", "no:cacheprovider"], 240)
        tail = (tests.stdout or "")[-1600:] if tests else ""
        check("automated_tests", "PASS" if tests and tests.returncode == 0 else "FAIL", log_tail=tail)

    summary["result"] = "SOURCE_CORE_PASS_NOT_PRODUCTION_ACCEPTED" if all(x["status"] not in ("FAIL",) for x in summary["checks"]) else "FAILED_OR_INCOMPLETE"
    (out / "acceptance_results.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print("RESULT:", summary["result"])
    return 0 if summary["result"] == "SOURCE_CORE_PASS_NOT_PRODUCTION_ACCEPTED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
