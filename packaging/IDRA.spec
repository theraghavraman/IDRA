# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for the IDRA desktop app. Run through packaging/build_app.py.
#   macOS   -> dist/IDRA.app
#   Windows -> dist/IDRA/IDRA.exe (windowed) + dist/IDRA/idra-cli.exe (console, for commands)
#   Linux   -> dist/IDRA/IDRA + dist/IDRA/idra-cli
import os
import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules, copy_metadata

HERE = Path(SPECPATH).resolve()
ROOT = HERE.parent
SRC = ROOT / "src"
VERSION = "0.9.3"
IS_MAC = sys.platform == "darwin"
IS_WIN = sys.platform.startswith("win")
sys.path.insert(0, str(SRC))

datas = [
    (str(SRC / "idra" / "browser" / "instrumentation.js"), "idra/browser"),
    (str(SRC / "idra" / "resources" / "idra.png"), "idra/resources"),
]
for dist in ("pydantic", "numpy", "opencv-python-headless", "PyQt6", "PyQt6-Qt6",
             "playwright", "pynput", "mss"):
    try:
        datas += copy_metadata(dist)
    except Exception:
        pass

hiddenimports = collect_submodules("idra") + ["pynput.keyboard", "pynput.mouse",
                                             "PyQt6.QtMultimedia", "PyQt6.QtMultimediaWidgets"]
if IS_MAC:
    hiddenimports += ["pynput.keyboard._darwin", "pynput.mouse._darwin", "pynput._util.darwin",
                      "mss.darwin", "Quartz", "AppKit", "HIServices", "ApplicationServices", "CoreFoundation"]
elif IS_WIN:
    hiddenimports += ["pynput.keyboard._win32", "pynput.mouse._win32", "pynput._util.win32", "mss.windows"]
else:
    hiddenimports += ["pynput.keyboard._xorg", "pynput.mouse._xorg", "pynput._util.xorg", "mss.linux"]

# Playwright has no PyInstaller hook: ship its Node driver so the managed browser works.
binaries = []
try:
    import playwright
    pw_root = Path(playwright.__file__).resolve().parent
    for f in (pw_root / "driver").rglob("*"):
        if f.is_file():
            dest = str(f.parent.relative_to(pw_root.parent))
            if f.name in ("node", "node.exe") or f.suffix in (".node", ".dylib", ".so", ".dll"):
                binaries.append((str(f), dest))
            else:
                datas.append((str(f), dest))
except ImportError:
    pass

# Self-contained FFmpeg placed in packaging/bin by build_app.py is shipped inside the app.
bundled_bin = HERE / "bin"
if bundled_bin.is_dir():
    for f in bundled_bin.iterdir():
        if f.is_file():
            binaries.append((str(f), "bin"))

a = Analysis(
    [str(HERE / "idra_app.py")],
    pathex=[str(SRC)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["tkinter", "pytest", "pytestqt", "mypy", "ruff", "IPython",
              "PyQt6.QtWebEngineCore", "PyQt6.QtWebEngineWidgets", "PyQt6.Qt3DCore",
              "PyQt6.QtQuick3D", "PyQt6.QtBluetooth", "PyQt6.QtSql", "PyQt6.QtDesigner"],
    noarchive=False,
)
pyz = PYZ(a.pure)

icon = str(HERE / "icons" / ("IDRA.icns" if IS_MAC else "IDRA.ico"))
gui = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="IDRA",
    debug=False, strip=False, upx=False,
    console=False,
    argv_emulation=False,
    target_arch=(os.environ.get("IDRA_TARGET_ARCH") or None) if IS_MAC else None,
    codesign_identity=(os.environ.get("IDRA_CODESIGN_IDENTITY") or None) if IS_MAC else None,
    entitlements_file=str(HERE / "macos" / "entitlements.plist") if IS_MAC else None,
    icon=icon,
)
executables = [gui]
if not IS_MAC:
    # A console twin: windowed Windows programs cannot print, so commands and the
    # build smoke test use idra-cli. On Linux it is the same program under a CLI name.
    executables.append(EXE(
        pyz, a.scripts, [],
        exclude_binaries=True,
        name="idra-cli",
        debug=False, strip=False, upx=False,
        console=True,
        icon=icon,
    ))
coll = COLLECT(*executables, a.binaries, a.datas, strip=False, upx=False, name="IDRA")

if IS_MAC:
    app = BUNDLE(
        coll,
        name="IDRA.app",
        icon=icon,
        bundle_identifier="com.idra.recorder",
        version=VERSION,
        info_plist={
            "CFBundleName": "IDRA",
            "CFBundleDisplayName": "IDRA",
            "CFBundleShortVersionString": VERSION,
            "CFBundleVersion": VERSION,
            "LSMinimumSystemVersion": "13.0",
            "LSApplicationCategoryType": "public.app-category.productivity",
            "NSHighResolutionCapable": True,
            "NSRequiresAquaSystemAppearance": False,
            "NSHumanReadableCopyright": "MIT License. Local-first recording; no uploads.",
        },
    )
