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

# Bundle the cart icon + any custom fonts so they ship with the app.
datas += [("assets/icons/cart.svg", "assets/icons")]
if os.path.isdir("assets/fonts"):
    for _f in os.listdir("assets/fonts"):
        if _f.lower().endswith((".ttf", ".otf")):
            datas += [(os.path.join("assets/fonts", _f), "assets/fonts")]

# Bundle the Supabase config (URL + anon key) so the installed app is cloud-
# enabled on any machine. The anon key is safe to ship — row-level security
# protects the data; never put the service_role key here.
if os.path.exists("config.local.json"):
    datas += [("config.local.json", ".")]

# Selenium Manager (locates chromedriver at runtime) must be bundled.
datas += collect_data_files("selenium")
_sel_root = os.path.dirname(selenium.__file__)
_sel_manager = os.path.join(_sel_root, "webdriver", "common", "windows", "selenium-manager.exe")
if os.path.exists(_sel_manager):
    datas += [(_sel_manager, "selenium/webdriver/common/windows")]

# pyqtgraph ships templates/icons and uses dynamic imports.
datas += collect_data_files("pyqtgraph")
hiddenimports += collect_submodules("pyqtgraph")

# Supabase stack + keyring use dynamic/optional imports PyInstaller can miss.
for _pkg in ("supabase", "gotrue", "postgrest", "realtime", "storage3", "supafunc", "keyring"):
    hiddenimports += collect_submodules(_pkg)
hiddenimports += ["keyring.backends.Windows", "win32ctypes.pywin32", "win32timezone"]

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
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
    upx=False,                       # UPX packing is a common antivirus false-positive trigger
    console=False,                   # GUI app — no console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="assets/icons/cart.ico",
    version="version_info.txt",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="PriceTracker",
)
