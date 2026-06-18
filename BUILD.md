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
with Start-Menu and optional desktop shortcuts, installing to
`C:\Program Files\PriceTracker`.

## Notes

- **User data** (the SQLite database) lives in
  `%LOCALAPPDATA%\PriceTracker\app.db`, *not* inside the install folder, so it
  survives reinstalls and upgrades.
- The build is one-folder (not one-file) for faster startup and more reliable
  Selenium/Qt loading. `build/` and `dist/` are git-ignored.
- If a scrape fails on a fresh machine with a Chrome startup error, confirm
  Chrome is installed and up to date.
