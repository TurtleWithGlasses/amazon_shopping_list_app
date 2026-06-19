# Building Price Tracker

## Prerequisites

- The project's `venv` with runtime deps installed (`pip install -r requirements.txt`).
- Build tools: `pip install -r requirements-dev.txt` (adds PyInstaller).
- **Google Chrome must be installed on the target machine** — the app drives a
  headless Chrome via Selenium. Selenium Manager downloads the matching
  chromedriver automatically on first run (needs internet once).

## 1. Build the app folder

From the project root:

```
build.bat
```

This runs PyInstaller against `PriceTracker.spec` and produces a one-folder
build at:

```
dist\PriceTracker\PriceTracker.exe
```

You can zip and share that folder as-is, or build an installer (below).

## 2. (Optional) Build a Windows installer

Install [Inno Setup](https://jrsoftware.org/isdl.php), then:

```
"C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer\PriceTracker.iss
```

This produces `installer\Output\PriceTracker-Setup.exe` — a standard installer
with Start-Menu and optional desktop shortcuts. It installs **per-user** (no
admin prompt) under the user's Program Files.

## Windows security

What's implemented in the build:
- **Embedded version info** (`version_info.txt`) — CompanyName/ProductName/
  version, so the exe isn't an anonymous binary (reduces AV suspicion).
- **No UPX packing** — UPX-compressed exes are a common antivirus false-positive
  trigger, so it's disabled in the spec.
- **Per-user install** (`PrivilegesRequired=lowest`) — no UAC elevation; the app
  never needs admin.
- **Cart app icon** embedded in the exe + installer.
- DEP/ASLR are on by default in the PyInstaller bootloader.

Not implemented (needs a paid certificate):
- **Code signing.** Without an Authenticode signature, Windows SmartScreen may
  warn on first run of the installer/exe ("Windows protected your PC" →
  *More info* → *Run anyway*). To remove this, sign `PriceTracker.exe` and the
  setup with `signtool` using a code-signing certificate (e.g. from a CA), or a
  self-signed cert for internal use. Signing reputation also builds over time.

## Notes

- **User data** (the SQLite database) lives in
  `%LOCALAPPDATA%\PriceTracker\app.db`, *not* inside the install folder, so it
  survives reinstalls and upgrades.
- The build is one-folder (not one-file) for faster startup and more reliable
  Selenium/Qt loading. `build/` and `dist/` are git-ignored.
- The target machine needs **Google Chrome** installed; Selenium Manager fetches
  the matching chromedriver on first run. If a scrape fails with a Chrome
  startup error, confirm Chrome is installed and up to date.
