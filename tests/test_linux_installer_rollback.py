"""Integration tests for the Linux transactional installer using harmless fake app files."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="Linux installer")
def test_linux_installer_rollback_and_upgrade(tmp_path):
    original = Path(__file__).resolve().parents[1] / "packaging/linux"
    package = tmp_path / "release"
    package.mkdir()
    shutil.copy2(original / "install.sh", package / "install.sh")
    shutil.copy2(original / "uninstall.sh", package / "uninstall.sh")
    (package / "idra.png").write_bytes(b"placeholder icon")
    binary = package / "IDRA"
    binary.mkdir()
    home = tmp_path / "home"
    home.mkdir()
    env = dict(os.environ, HOME=str(home), XDG_DATA_HOME=str(home / "share"), PATH=os.environ["PATH"])
    destination = home / "share/IDRA"

    def stage(version, cli_ok=True, icon_ok=True):
        (binary / "IDRA").write_text("#!/bin/sh\nexit 0\n")
        (binary / "idra-cli").write_text(
            "#!/bin/sh\n" + (f"echo '{version}'\nexit 0\n" if cli_ok else "exit 13\n")
        )
        for name in ("IDRA", "idra-cli"):
            (binary / name).chmod(0o755)
        (binary / "VERSION").write_text(version)
        if icon_ok:
            (package / "idra.png").write_bytes(b"placeholder icon")
        else:
            (package / "idra.png").unlink(missing_ok=True)

    def install():
        return subprocess.run(["bash", str(package / "install.sh")], env=env, text=True,
                              capture_output=True, timeout=20)

    stage("v1")
    first = install()
    assert first.returncode == 0, first.stderr
    assert (destination / "VERSION").read_text() == "v1"
    stage("v2")
    second = install()
    assert second.returncode == 0, second.stderr
    assert (destination / "VERSION").read_text() == "v2"
    assert not list((home / "share").glob(".IDRA.backup.*"))

    # If the staged executable cannot start, the prior installation stays intact.
    stage("v3", cli_ok=False)
    rejected = install()
    assert rejected.returncode != 0
    assert (destination / "VERSION").read_text() == "v2"
    assert not list((home / "share").glob(".IDRA.stage.*"))

    # If a post-activation launcher/icon step fails, the original app is restored.
    stage("v4", cli_ok=True, icon_ok=False)
    rollback = install()
    assert rollback.returncode != 0
    assert (destination / "VERSION").read_text() == "v2"
    assert not list((home / "share").glob(".IDRA.backup.*"))
