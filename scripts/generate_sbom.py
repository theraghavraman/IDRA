#!/usr/bin/env python3
"""Provisional CycloneDX Python-environment inventory; NOT a final binary SBOM."""
from __future__ import annotations

import argparse
import importlib.metadata as md
import json
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def canonical(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def declared_dependencies():
    deps = {}
    for source in (ROOT / "requirements.txt", ROOT / "packaging/requirements-build.txt"):
        for raw in source.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if "==" not in line:
                raise ValueError(f"Unpinned or unsupported requirement in {source.name}: {line}")
            name, version = line.split("==", 1)
            deps[canonical(name)] = {"version": version, "source": str(source.relative_to(ROOT))}
    return deps


def create_sbom():
    expected = declared_dependencies()
    found = {}
    for dist in md.distributions():
        name = dist.metadata.get("Name")
        if not name:
            continue
        key = canonical(name)
        # Distribution metadata can contain duplicate names in overlapping editable installs.
        if key in found:
            continue
        found[key] = dist
    missing = [{"name": n, **spec} for n, spec in expected.items() if n not in found]
    mismatches = [{"name": n, "expected": spec["version"], "installed": found[n].version}
                  for n, spec in expected.items() if n in found and found[n].version != spec["version"]]
    components = []
    for key, dist in sorted(found.items()):
        metadata = dist.metadata
        properties = [{"name": "idra:environment_inventory_only", "value": "true"}]
        if key in expected:
            properties += [{"name": "idra:direct_requirement", "value": "true"},
                           {"name": "idra:required_version", "value": expected[key]["version"]}]
        component = {"type": "library", "name": metadata.get("Name", key),
                     "version": dist.version,
                     "purl": f"pkg:pypi/{key}@{dist.version}",
                     "properties": properties}
        license_value = metadata.get("License-Expression") or metadata.get("License")
        if license_value and license_value not in {"UNKNOWN", "None"}:
            component["properties"].append({"name": "idra:unverified_upstream_license_metadata",
                                            "value": license_value[:400]})
        components.append(component)
    data = {
        "bomFormat": "CycloneDX", "specVersion": "1.6", "serialNumber": None, "version": 1,
        "metadata": {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "component": {"type": "application", "name": "IDRA", "version": "0.9.3-rc2"},
            "properties": [
                {"name": "idra:scope", "value": "PROVISIONAL_BUILD_ENVIRONMENT_NOT_DISTRIBUTED_BINARY"},
                {"name": "idra:binary_and_native_components_included", "value": "false"},
                {"name": "idra:commercial_license_review_complete", "value": "false"},
            ],
        },
        "components": components,
    }
    # Null serialNumber is not a valid CycloneDX UUID. Omit when no stable serial is available.
    data.pop("serialNumber", None)
    evidence = {
        "classification": "provisional_environment_inventory",
        "component_count": len(components),
        "declared_required_count": len(expected),
        "missing_required": missing,
        "version_mismatches": mismatches,
        "needs_separate_verification": ["actual PyInstaller bundled content",
                                        "FFmpeg executable/DLLs and libx264 licensing",
                                        "Playwright Chromium/Node", "Qt native binaries and plugins",
                                        "native operating-system frameworks", "wheel hashes",
                                        "transitive dependencies and CVE review", "legal approval"],
        "production_approved": False,
    }
    return data, evidence


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("reports/provisional-python-sbom.cdx.json"))
    parser.add_argument("--evidence", type=Path, default=Path("reports/sbom-limitations.json"))
    args = parser.parse_args()
    sbom, evidence = create_sbom()
    for path, data in ((args.out, sbom), (args.evidence, evidence)):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(json.dumps(evidence, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
