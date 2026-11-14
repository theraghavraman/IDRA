#!/usr/bin/env python3
"""Build the IDRA desktop app for the computer this runs on (macOS, Windows or Linux).

Usually started by a launcher in the project folder:
  macOS:   Build IDRA (macOS).command      Windows: Build IDRA (Windows).bat
  Linux:   ./build-idra-linux.sh
Direct use:  python packaging/build_app.py [--skip-tests] [--no-browser] [--no-bundle-ffmpeg]

Steps: check this computer -> find FFmpeg -> private build environment -> optional Chromium ->
automated tests -> PyInstaller -> signature check (macOS) -> smoke test of the finished app ->
installer package in dist/. Uses only the Python standard library.
"""
from __future__ import annotations
import argparse
import glob
import json
import os
import platform
import shutil
import struct
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path

VERSION = "0.9.3"
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DIST = ROOT / "dist"
BUILD = ROOT / "build"
SYSTEM = platform.system()
ARCH = {"x86_64": "x86_64", "amd64": "x86_64", "arm64": "arm64", "aarch64": "arm64"}.get(
    platform.machine().lower(), platform.machine().lower())
IS_MAC, IS_WIN, IS_LINUX = SYSTEM == "Darwin", SYSTEM == "Windows", SYSTEM == "Linux"
PLATFORM_TAG = {"Darwin": f"macos-{ARCH}", "Windows": "windows-x64", "Linux": f"linux-{ARCH}"}.get(SYSTEM, SYSTEM.lower())

if IS_WIN:
    os.system("")  # enable ANSI colours in the Windows console

sys.path.insert(0, str(ROOT / "src"))
from idra.app.runtime import find_executable  # noqa: E402  (standard-library only module)


class BuildStopped(Exception):
    pass


def say(text):
    print(f"\n\033[1;32m==> {text}\033[0m", flush=True)


def note(text):
    print(f"    {text}", flush=True)


def warn(text):
    print(f"\033[1;33mWARNING: {text}\033[0m", flush=True)


def run(cmd, *, check=True, env=None, capture=False, cwd=None):
    result = subprocess.run([str(c) for c in cmd], env=env, cwd=cwd, text=True,
                            capture_output=capture)
    if check and result.returncode:
        raise subprocess.CalledProcessError(result.returncode, cmd, result.stdout, result.stderr)
    return result


def output(cmd) -> str:
    try:
        r = subprocess.run([str(c) for c in cmd], capture_output=True, text=True, timeout=60)
        return (r.stdout or "") + (r.stderr or "")
    except (OSError, subprocess.SubprocessError):
        return ""


# ------------------------------------------------------------------ 1. this computer
def check_computer():
    say("Checking this computer")
    if not (3, 11) <= sys.version_info[:2] < (3, 15):
        raise BuildStopped(f"Python 3.11-3.14 is required; this is {platform.python_version()}.")
    if struct.calcsize("P") != 8:
        raise BuildStopped("A 64-bit Python is required.")
    if IS_MAC:
        if output(["sysctl", "-n", "sysctl.proc_translated"]).strip() == "1":
            raise BuildStopped("This Terminal runs in Intel (Rosetta) mode on an Apple Silicon Mac. "
                               "Turn off 'Open using Rosetta' for Terminal and run again.")
        major = int((platform.mac_ver()[0] or "0").split(".")[0])
        if major < 13:
            raise BuildStopped(f"macOS 13 Ventura or newer is required (this Mac runs {platform.mac_ver()[0]}).")
        if not output(["xcode-select", "-p"]).strip():
            warn("Xcode Command Line Tools not found. If a later step fails, run: xcode-select --install")
    elif IS_WIN:
        if sys.getwindowsversion().major < 10:
            raise BuildStopped("Windows 10 or 11 is required.")
        if ARCH != "x86_64":
            warn("This is not an x64 Python. Windows-on-ARM builds are untested; use x64 Python if the build fails.")
    elif IS_LINUX:
        libs = output(["/sbin/ldconfig", "-p"])
        if libs and "libxcb-cursor.so.0" not in libs:
            warn("libxcb-cursor0 is not installed. The app may not open on other Linux machines. "
                 "Install it first: sudo apt install libxcb-cursor0  (Fedora: sudo dnf install xcb-util-cursor)")
    else:
        raise BuildStopped(f"Unsupported system: {SYSTEM}")
    note(f"{SYSTEM} {platform.release()} on {ARCH}; Python {platform.python_version()} ({sys.executable})")


# ------------------------------------------------------------------ 2. FFmpeg
def _winget_ffmpeg() -> tuple[str | None, str | None]:
    base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "Microsoft" / "WinGet"
    for pattern in (str(base / "Links" / "ffmpeg.exe"),
                    str(base / "Packages" / "Gyan.FFmpeg*" / "**" / "bin" / "ffmpeg.exe")):
        for match in glob.glob(pattern, recursive=True):
            probe = Path(match).with_name("ffprobe.exe")
            if probe.is_file():
                return match, str(probe)
    return None, None


def find_ffmpeg() -> tuple[str, str]:
    say("Checking FFmpeg (records and encodes the screen video)")
    ffmpeg, ffprobe = find_executable("ffmpeg"), find_executable("ffprobe")
    if IS_WIN and not (ffmpeg and ffprobe):
        ffmpeg, ffprobe = _winget_ffmpeg()
    if not (ffmpeg and ffprobe):
        if IS_MAC and find_executable("brew"):
            note("Installing FFmpeg with Homebrew (one-time)...")
            run([find_executable("brew"), "install", "ffmpeg"])
        elif IS_WIN and find_executable("winget"):
            note("Installing FFmpeg with winget (one-time)...")
            run(["winget", "install", "--id", "Gyan.FFmpeg", "-e", "--accept-source-agreements",
                 "--accept-package-agreements"], check=False)
            ffmpeg, ffprobe = _winget_ffmpeg()
        elif IS_LINUX:
            raise BuildStopped("FFmpeg is missing. Install it, then run this again:\n"
                               "  Ubuntu/Debian: sudo apt install ffmpeg\n"
                               "  Fedora:        sudo dnf install ffmpeg   (enable RPM Fusion first)\n"
                               "  Arch:          sudo pacman -S ffmpeg")
        ffmpeg = ffmpeg or find_executable("ffmpeg")
        ffprobe = ffprobe or find_executable("ffprobe")
    if not (ffmpeg and ffprobe):
        hint = {"Darwin": "Install Homebrew (https://brew.sh), then: brew install ffmpeg",
                "Windows": "Run: winget install Gyan.FFmpeg   (or download the 'essentials' build from "
                           "https://www.gyan.dev/ffmpeg/builds/ and unzip it to C:\\ffmpeg)"}.get(SYSTEM, "")
        raise BuildStopped("FFmpeg and ffprobe were not found. " + hint)
    if "libx264" not in output([ffmpeg, "-hide_banner", "-encoders"]):
        raise BuildStopped(f"{ffmpeg} has no libx264 (H.264) encoder. Install a full FFmpeg build "
                           "(Homebrew, Gyan.FFmpeg, or your distribution's ffmpeg package).")
    note(f"ffmpeg:  {ffmpeg}")
    note(f"ffprobe: {ffprobe}")
    return ffmpeg, ffprobe


def stage_ffmpeg(ffmpeg: str, ffprobe: str, enabled: bool) -> bool:
    """Copy FFmpeg into the app when it is self-contained, so the app needs no separate install."""
    target = HERE / "bin"
    shutil.rmtree(target, ignore_errors=True)
    if not enabled:
        note("FFmpeg will not be bundled (--no-bundle-ffmpeg); the app uses the installed copy.")
        return False
    sources = [Path(ffmpeg).resolve(), Path(ffprobe).resolve()]
    if IS_WIN:
        dlls = sorted(sources[0].parent.glob("*.dll"))  # shared builds keep their DLLs beside the exe
        files = sources + dlls
    elif IS_MAC:
        def self_contained(p):
            libs = output(["otool", "-L", p]).splitlines()[1:]
            return all(line.strip().startswith(("/usr/lib/", "/System/")) for line in libs if line.strip())
        files = sources if all(self_contained(p) for p in sources) else []
    else:
        def static(p):
            text = output(["ldd", p])
            return "not a dynamic executable" in text or "statically linked" in text
        files = sources if all(static(p) for p in sources) else []
    if not files:
        note("This FFmpeg depends on system libraries, so it is not bundled; the app will use the "
             "installed copy (the installer checks for it).")
        return False
    target.mkdir(parents=True)
    for f in files:
        shutil.copy2(f, target / f.name)
    note(f"Bundling FFmpeg inside the app ({len(files)} files)")
    return True


# ------------------------------------------------------------------ 3. environment
def venv_python() -> Path:
    venv = BUILD / f"venv-{PLATFORM_TAG}"
    py = venv / ("Scripts/python.exe" if IS_WIN else "bin/python")
    if py.exists() and not output([py, "-c", "import sys; print(sys.version_info[:2] >= (3, 11))"]).strip() == "True":
        shutil.rmtree(venv, ignore_errors=True)
    if not py.exists():
        say("Creating the private build environment")
        try:
            run([sys.executable, "-m", "venv", venv])
        except subprocess.CalledProcessError as exc:
            raise BuildStopped("Python could not create a virtual environment. On Ubuntu/Debian run: "
                               "sudo apt install python3-venv") from exc
    return py


def install_packages(py: Path, with_tests: bool):
    check_mods = "import pydantic, numpy, cv2, PyQt6, playwright, pynput, mss, PyInstaller"
    if with_tests:
        check_mods += ", pytest, pytestqt"
    if run([py, "-c", check_mods], check=False, capture=True).returncode == 0:
        note("Python packages already installed in build environment")
        return
    say("Installing Python packages (first run downloads about 300 MB)")
    cmd = [py, "-m", "pip", "install", "--quiet", "--disable-pip-version-check",
           "-r", ROOT / "requirements.txt", "-r", HERE / "requirements-build.txt"]
    if with_tests:
        cmd += ["pytest==9.0.2", "pytest-qt==4.5.0"]
    try:
        run(cmd)
    except subprocess.CalledProcessError as exc:
        raise BuildStopped("Package installation failed. Check the internet connection and run again.") from exc
    note("Packages installed")


def install_browser(py: Path):
    note("Installing Chromium for the optional managed-browser capture...")
    if run([py, "-m", "playwright", "install", "chromium"], check=False).returncode:
        warn("Chromium download failed. Recording works; only managed-browser capture is unavailable. "
             "Run this build again later to retry.")
    elif IS_LINUX:
        note("If the managed browser later fails to start on Linux, run once: "
             f"sudo {py} -m playwright install-deps chromium")


def run_tests(py: Path):
    say("Running the automated tests (about a minute)")
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    if run([py, "-m", "pytest", "-q", "-p", "no:cacheprovider"], check=False, env=env, cwd=ROOT).returncode:
        raise BuildStopped("Tests failed on this computer (details above). Nothing was packaged. "
                           "Send the output above for diagnosis, or use --skip-tests to build anyway.")


# ------------------------------------------------------------------ 4. build + verify
def pyinstaller(py: Path) -> Path:
    say("Building the app with PyInstaller")
    shutil.rmtree(BUILD / "pyinstaller", ignore_errors=True)
    for old in (DIST / "IDRA.app", DIST / "IDRA"):
        shutil.rmtree(old, ignore_errors=True)
    env = dict(os.environ)
    if IS_MAC:
        env["IDRA_TARGET_ARCH"] = ARCH
    try:
        run([py, "-m", "PyInstaller", "--noconfirm", "--clean", "--log-level", "WARN",
             "--distpath", DIST, "--workpath", BUILD / "pyinstaller", HERE / "IDRA.spec"], env=env)
    except subprocess.CalledProcessError as exc:
        raise BuildStopped("PyInstaller could not build the app (details above).") from exc
    if IS_MAC:
        shutil.rmtree(DIST / "IDRA", ignore_errors=True)
        app = DIST / "IDRA.app"
        if not (app / "Contents" / "MacOS" / "IDRA").exists():
            raise BuildStopped("The app bundle was not created.")
        return app
    app = DIST / "IDRA"
    if not (app / ("IDRA.exe" if IS_WIN else "IDRA")).exists():
        raise BuildStopped("The app executable was not created.")
    return app


def mac_signature(app: Path):
    say("Checking the code signature")
    run(["xattr", "-cr", app], check=False)
    if run(["codesign", "--verify", "--deep", "--strict", app], check=False, capture=True).returncode:
        note("Re-applying a local (ad-hoc) signature...")
        run(["codesign", "--force", "--deep", "--entitlements", HERE / "macos" / "entitlements.plist",
             "--sign", "-", app])
        run(["codesign", "--verify", "--deep", "--strict", app])
    note("Signature valid (local ad-hoc signature; no Apple Developer ID needed for your own Mac)")


def cli_executable(app: Path) -> Path:
    if IS_MAC:
        return app / "Contents" / "MacOS" / "IDRA"
    return app / ("idra-cli.exe" if IS_WIN else "idra-cli")


def smoke_test(app: Path):
    say("Testing the finished app")
    cli = cli_executable(app)
    with tempfile.TemporaryDirectory() as tmp:
        base = [cli, "--settings", Path(tmp) / "settings.json"]
        diag = run(base + ["diagnostics"], check=False, capture=True)
        out = diag.stdout or ""
        try:
            json.JSONDecoder().raw_decode(out[out.index("{"):])
        except ValueError as exc:
            raise BuildStopped("The finished app's diagnostics command did not run:\n"
                               + (out + (diag.stderr or ""))[-2000:]) from exc
        demo = run(base + ["--storage", Path(tmp) / "rec", "demo", "--seconds", "2",
                           "--export", Path(tmp) / "dataset"], check=False, capture=True)
        if demo.returncode:
            raise BuildStopped("The finished app could not complete a synthetic recording:\n"
                               + (demo.stdout + demo.stderr)[-2000:])
        verify = run(base + ["verify-export", Path(tmp) / "dataset"], check=False, capture=True)
        if verify.returncode or '"passed"' not in verify.stdout:
            raise BuildStopped("The finished app's test dataset did not verify:\n" + (verify.stdout + verify.stderr)[-2000:])
    note("Synthetic record -> encode -> export -> verify: passed")


# ------------------------------------------------------------------ 5. installer package
def package(app: Path) -> Path:
    say("Creating the installer package")
    name = f"IDRA-{VERSION}-rc2-{PLATFORM_TAG}"
    if IS_MAC:
        dmg = DIST / f"{name}.dmg"
        with tempfile.TemporaryDirectory() as stage:
            shutil.copytree(app, Path(stage) / "IDRA.app", symlinks=True)
            os.symlink("/Applications", Path(stage) / "Applications")
            dmg.unlink(missing_ok=True)
            if run(["hdiutil", "create", "-quiet", "-volname", f"IDRA {VERSION}", "-srcfolder", stage,
                    "-ov", "-format", "UDZO", dmg], check=False).returncode:
                warn("DMG creation failed; dist/IDRA.app is complete and can be dragged to Applications.")
                return app
        return dmg
    readme = (HERE / ("windows" if IS_WIN else "linux") / "README-FIRST.txt").read_text(encoding="utf-8")
    if IS_WIN:
        archive = DIST / f"{name}.zip"
        archive.unlink(missing_ok=True)
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            for f in sorted(app.rglob("*")):
                if f.is_file():
                    z.write(f, f"{name}/IDRA/{f.relative_to(app).as_posix()}")
            for extra in ("Install IDRA.cmd", "install-idra.ps1", "uninstall-idra.ps1"):
                z.write(HERE / "windows" / extra, f"{name}/{extra}")
            z.writestr(f"{name}/README-FIRST.txt", readme.replace("\n", "\r\n"))
        return archive
    archive = DIST / f"{name}.tar.gz"
    archive.unlink(missing_ok=True)
    def executable(info):
        if info.name.endswith(("install.sh", "uninstall.sh")):
            info.mode = 0o755
        return info
    with tarfile.open(archive, "w:gz", compresslevel=6) as t:
        t.add(app, f"{name}/IDRA")
        t.add(HERE / "icons" / "idra-256.png", f"{name}/idra.png")
        for extra in ("install.sh", "uninstall.sh"):
            t.add(HERE / "linux" / extra, f"{name}/{extra}", filter=executable)
        data = readme.encode("utf-8")
        info = tarfile.TarInfo(f"{name}/README-FIRST.txt")
        info.size, info.mode = len(data), 0o644
        import io
        t.addfile(info, io.BytesIO(data))
    return archive


def main() -> int:
    parser = argparse.ArgumentParser(description=f"Build IDRA {VERSION} for this computer.")
    parser.add_argument("--skip-tests", action="store_true", help="do not run the automated tests first")
    parser.add_argument("--package-only", action="store_true", help="smoke-test and package an existing native build (preserves external signatures)")
    parser.add_argument("--no-browser", action="store_true", help="do not download Chromium")
    parser.add_argument("--no-bundle-ffmpeg", action="store_true", help="never copy FFmpeg into the app")
    parser.add_argument("--no-package", action="store_true", help="build the app only, no installer package")
    args = parser.parse_args()
    try:
        check_computer()
        if args.package_only:
            app = DIST / "IDRA.app" if IS_MAC else DIST / "IDRA"
            if not app.exists():
                raise BuildStopped("There is no existing native application to package.")
            bundled = False  # Package-only does not modify or resolve external FFmpeg dependencies.
            smoke_test(app)
            result = app if args.no_package else package(app)
        else:
            ffmpeg, ffprobe = find_ffmpeg()
            bundled = stage_ffmpeg(ffmpeg, ffprobe, not args.no_bundle_ffmpeg)
            py = venv_python()
            install_packages(py, not args.skip_tests)
            if not args.no_browser:
                install_browser(py)
            if not args.skip_tests:
                run_tests(py)
            app = pyinstaller(py)
            if IS_MAC:
                mac_signature(app)
            smoke_test(app)
            result = app if args.no_package else package(app)
    except BuildStopped as exc:
        print(f"\n\033[1;31mBUILD STOPPED: {exc}\033[0m", file=sys.stderr, flush=True)
        return 1
    except KeyboardInterrupt:
        print("\nBuild cancelled.", file=sys.stderr)
        return 130
    say("Done")
    note(f"App:     {app}")
    note(f"Package: {result}")
    note("FFmpeg:  " + ("inside the app" if bundled else "check existing native package / host"))
    warn("Native packaging alone does not establish production acceptance. Sign and review each artifact.")
    steps = {
        "Darwin": "Open the .dmg and drag IDRA into Applications, then follow DOCUMENTATION.md section 4 "
                  "(macOS permissions).",
        "Windows": "Unzip the package and double-click 'Install IDRA.cmd' (adds Start menu and desktop "
                   "shortcuts), or run IDRA\\IDRA.exe directly.",
        "Linux": "Extract the .tar.gz and run ./install.sh (adds IDRA to your applications menu).",
    }[SYSTEM]
    print(f"\nNext: {steps}\n", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
