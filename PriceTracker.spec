# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller build spec for Price Tracker (one-folder Windows build).

Build with:  pyinstaller PriceTracker.spec --noconfirm
Output:      dist\\PriceTracker\\PriceTracker.exe
"""
import os

import selenium
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

datas = []
hiddenimports = []

# Selenium Manager (downloads/locates chromedriver at runtime) must be bundled.
datas += collect_data_files("selenium")
_sel_root = os.path.dirname(selenium.__file__)
_sel_manager = os.path.join(_sel_root, "webdriver", "common", "windows", "selenium-manager.exe")
if os.path.exists(_sel_manager):
    datas += [(_sel_manager, "selenium/webdriver/common/windows")]

# pyqtgraph ships templates/icons and uses dynamic imports.
datas += collect_data_files("pyqtgraph")
hiddenimports += collect_submodules("pyqtgraph")

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # Keep the bundle lean: the old Streamlit stack and unused GUI toolkits.
    excludes=["streamlit", "streamlit_autorefresh", "tkinter", "PyQt5", "PyQt6", "PySide2"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="PriceTracker",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,          # GUI app — no console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="PriceTracker",
)
