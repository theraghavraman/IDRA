#!/usr/bin/env python3
"""Fail-closed release evidence completeness gate. Does NOT replace native signature/legal review."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

REQUIRED_TARGETS = ("windows-x64", "macos-arm64", "macos-x86_64", "linux-x86_64")
TARGET_FLAGS = ("native_tests_passed", "real_gui_passed", "global_stop_passed",
                "installer_rollback_passed", "signature_verified", "long_run_passed",
                "browser_provenance_reviewed")
LEGAL_FLAGS = ("commercial_pyqt_approved", "qt_obligations_approved",
               "ffmpeg_libx264_approved", "chromium_redistribution_approved",
               "complete_binary_sbom_reviewed", "vulnerability_reviewed",
               "release_publisher_identity_approved")


def sha256_file(path: Path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def check_evidence(data: dict) -> list[str]:
    failures = []
    if data.get("version") != "0.9.3-rc2":
        failures.append("Release version must be 0.9.3-rc2")
    for target in REQUIRED_TARGETS:
        evidence = data.get("platforms", {}).get(target) or {}
        for flag in TARGET_FLAGS:
            if evidence.get(flag) is not True:
                failures.append(f"{target}: {flag} is not accepted")
        for path_field in ("test_log", "signature_report"):
            path_str = evidence.get(path_field)
            if not path_str or not Path(path_str).is_file():
                failures.append(f"{target}: {path_field} evidence file is missing")
        artifact_name = evidence.get("artifact_path")
        digest = evidence.get("artifact_sha256", "")
        if not artifact_name or not Path(artifact_name).is_file():
            failures.append(f"{target}: native artifact is missing")
        elif not digest or sha256_file(Path(artifact_name)).lower() != str(digest).lower():
            failures.append(f"{target}: artifact SHA-256 mismatch or absent")
        if not evidence.get("tested_os_version") or not evidence.get("tester"):
            failures.append(f"{target}: native OS version and responsible tester required")
    legal = data.get("legal", {})
    for flag in LEGAL_FLAGS:
        if legal.get(flag) is not True:
            failures.append(f"Legal: {flag} is not accepted")
    if not legal.get("reviewer") or not legal.get("approval_reference"):
        failures.append("Legal: named reviewer and approval reference required")
    return failures


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--report", type=Path, default=Path("release_gate_result.json"))
    args = parser.parse_args()
    try:
        data = json.loads(args.evidence.read_text(encoding="utf-8"))
        failures = check_evidence(data)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        failures = [f"Evidence file could not be read: {type(exc).__name__}"]
    result = {
        "version": "0.9.3-rc2", "generated_at": datetime.now(timezone.utc).isoformat(),
        "decision": "GO_REQUIRES_HUMAN_AUTHENTICITY_REVIEW" if not failures else "NO_GO",
        "checks": {"targets": list(REQUIRED_TARGETS), "legal_flags": list(LEGAL_FLAGS)},
        "failed_checks": failures,
        "important": "This is an evidence-completeness/hash gate, not independent validation of signer identity or legal advice.",
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0 if not failures else 2


if __name__ == "__main__":
    raise SystemExit(main())
