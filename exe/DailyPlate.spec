# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for Daily Plate (Calorie Tracker): windowed app, no console.
# Normally started by exe\build_exe.ps1 (or CI), which sets DAILYPLATE_BUILD_MODE:
#   exe     -> one self-contained DailyPlate.exe (default)
#   folder  -> DailyPlate\ folder (faster start, ship the whole folder)
# Manual build:  python -m PyInstaller exe\DailyPlate.spec --noconfirm --clean

import os
from pathlib import Path

ROOT = Path(SPECPATH).resolve().parent          # project folder (the one containing app.py)
ICON = ROOT / "exe" / "app.ico"                 # the exe icon; must exist at build time

MODE = os.environ.get("DAILYPLATE_BUILD_MODE", "exe").strip().lower()
if MODE not in ("exe", "folder"):
    raise SystemExit(f"DAILYPLATE_BUILD_MODE must be 'exe' or 'folder', not {MODE!r}")

print(f"[DailyPlate.spec] Build mode: {MODE}")
if ICON.is_file():
    print(f"[DailyPlate.spec] Using exe icon: {ICON}")
else:
    print("=" * 78)
    print(f"[DailyPlate.spec] WARNING: icon not found at {ICON}")
    print("                  The exe will be built with the default icon. Add exe/app.ico and rebuild.")
    print("=" * 78)

a = Analysis(
    [str(ROOT / "app.py")],
    pathex=[str(ROOT / "src")],
    binaries=[],
    datas=[
        # Read-only files shipped with the app.
        (str(ROOT / "food_macros_seed.csv"), "."),
        (
            str(ROOT / "src" / "calorie_tracker" / "presentation" / "assets"),
            "calorie_tracker/presentation/assets",
        ),
    ],
    # The chevron arrows are SVGs; this makes sure Qt's SVG image/icon plugins are bundled.
    hiddenimports=["PySide6.QtSvg"],
    excludes=["tkinter"],
    noarchive=False,
)

pyz = PYZ(a.pure)

_common = dict(
    name="DailyPlate",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,                # UPX-packed Qt apps are more often flagged by antivirus
    console=False,            # set True temporarily to see error output when debugging
    icon=str(ICON) if ICON.is_file() else None,
)

if MODE == "folder":
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, **_common)
    coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="DailyPlate")
else:
    exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], runtime_tmpdir=None, **_common)
