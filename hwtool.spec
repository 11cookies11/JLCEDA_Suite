# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for hwtool.exe — hardware toolchain CLI entrypoint."""

import sys
from pathlib import Path

import os
_root = Path(os.getcwd())

a = Analysis(
    [str(_root / "hwtool_entry.py")],
    pathex=[str(_root / "src"), str(_root)],
    binaries=[],
    datas=[
        (str(_root / "schemas"), "schemas"),
        (str(_root / "config"), "config"),
        (str(_root / "resources"), "resources"),
        (str(_root / "packs"), "packs"),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
)

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    name="hwtool",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    runtime_tmpdir=None,
    icon=None,
)

# Single-directory bundle
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="hwtool",
)
