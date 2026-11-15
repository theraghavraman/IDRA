#!/usr/bin/env python3
"""Create a source-only ZIP with a per-file SHA-256 inventory; no credentials/recordings."""

import argparse
import hashlib
import json
import zipfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
p = argparse.ArgumentParser()
p.add_argument(
    "--out", type=Path, default=root.parent / "Intelligent_Data_Recording_Agent_v0.9.3-rc2.zip"
)
a = p.parse_args()
allow_roots = {"src", "tests", "docs", "scripts", "examples", "reports", "packaging"}
allow_files = {
    "README.md",
    "SECURITY.md",
    "LICENSE",
    "NOTICE",
    "THIRD_PARTY_NOTICES.md",
    "CHANGELOG.md",
    "pyproject.toml",
    "requirements.txt",
    "requirements-dev.txt",
    "requirements-core.txt",
    "config.example.json",
    ".gitignore",
    "Build IDRA (macOS).command",
    "Build IDRA (Windows).bat",
    "build-idra-linux.sh",
    "DOCUMENTATION.md",
}
exclude = {
    "bin",
    "build",
    "dist",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".venv",
    "venv",
    "htmlcov",
}
files = []
for f in sorted(root.rglob("*")):
    relative = f.relative_to(root)
    if (
        not f.is_file()
        or f.is_symlink()
        or any(part in exclude or part.endswith(".egg-info") for part in relative.parts)
    ):
        continue
    if relative.parts[0] not in allow_roots and relative.as_posix() not in allow_files:
        continue
    if f.suffix in {".pyc", ".pyo"} or f.name in {".coverage"}:
        continue
    files.append((f, relative.as_posix()))
inventory = {rel: hashlib.sha256(f.read_bytes()).hexdigest() for f, rel in files}
a.out.parent.mkdir(parents=True, exist_ok=True)
with zipfile.ZipFile(a.out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
    for f, rel in files:
        z.write(f, "intelligent_data_recording_agent/" + rel)
    z.writestr(
        "intelligent_data_recording_agent/RELEASE_CONTENTS.json",
        json.dumps({"version": "0.9.3-rc2", "sha256": inventory}, indent=2) + "\n",
    )
checksum = hashlib.sha256(a.out.read_bytes()).hexdigest()
a.out.with_suffix(".sha256").write_text(f"{checksum}  {a.out.name}\n")
print(
    json.dumps(
        {
            "archive": str(a.out),
            "files": len(files) + 1,
            "bytes": a.out.stat().st_size,
            "sha256": checksum,
        },
        indent=2,
    )
)
