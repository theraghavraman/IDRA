"""Release gating is deliberately conservative; completeness is not signer authentication."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path


def load_script(name):
    script = Path(__file__).resolve().parents[1] / "scripts" / name
    spec = importlib.util.spec_from_file_location(name.removesuffix(".py"), script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_unapproved_template_is_no_go():
    gate = load_script("release_gate.py")
    path = Path(__file__).resolve().parents[1] / "docs/release_acceptance_template.json"
    evidence = json.loads(path.read_text(encoding="utf-8"))
    missing = gate.check_evidence(evidence)
    assert len(missing) > 25
    assert any("Legal:" in error for error in missing)
    assert all(target in str(missing) for target in gate.REQUIRED_TARGETS)


def test_release_gate_tamper_detection_even_with_flags_accepted(tmp_path):
    gate = load_script("release_gate.py")
    payload = tmp_path / "artifact.zip"
    payload.write_bytes(b"an example artifact")
    evidence_file = tmp_path / "log.txt"
    evidence_file.write_text("synthetic test evidence - NOT REAL APPROVAL")
    sha = hashlib.sha256(payload.read_bytes()).hexdigest()
    p = {"artifact_path": str(payload), "artifact_sha256": sha,
         "test_log": str(evidence_file), "signature_report": str(evidence_file),
         "tested_os_version": "test-only", "tester": "test-only"}
    p.update({flag: True for flag in gate.TARGET_FLAGS})
    legal = {flag: True for flag in gate.LEGAL_FLAGS}
    legal.update(reviewer="test-only", approval_reference="test-only")
    evidence = {"version": "0.9.3-rc2", "platforms": {t: dict(p) for t in gate.REQUIRED_TARGETS},
                "legal": legal}
    assert gate.check_evidence(evidence) == []  # Automated completeness is not authenticity.
    payload.write_bytes(b"tampered!")
    problems = gate.check_evidence(evidence)
    assert len([x for x in problems if "SHA-256 mismatch" in x]) == 4


def test_provisional_sbom_is_not_binary_or_license_approved():
    generator = load_script("generate_sbom.py")
    sbom, evidence = generator.create_sbom()
    assert sbom["bomFormat"] == "CycloneDX"
    assert sbom["specVersion"] == "1.6"
    assert evidence["production_approved"] is False
    assert "actual PyInstaller bundled content" in evidence["needs_separate_verification"]
