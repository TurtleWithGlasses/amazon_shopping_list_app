# Price Tracker — Roadmap

A desktop app that tracks price and stock of products (Amazon first, more stores
later), with per-user cloud accounts, price-history graphs, exports, and
notifications.

## Architecture

- **`core/`** — data + scraping (framework-agnostic)
  - `models.py`, `db.py`, `repository.py` — SQLAlchemy models + local SQLite repo
  - `datastore.py` — backend switch (local SQLite ↔ Supabase) used by UI/services
  - `cloud/` — Supabase config, client, auth, session store, cloud repository
  - `scraping/` — `RetailerAdapter` interface + `AmazonAdapter` + registry
- **`services/`** — scrape worker (threaded), refresh, export (CSV/Excel),
  timescales, stock classifier
- **`ui/`** — PySide6 windows/dialogs (`main_window`, `login_dialog`,
  `settings_dialog`, `graph_dialog`, `edit_dialog`), theming, icons
- **`main.py`** — entry point (login ↔ window loop, theme, app icon)
- Packaging: `PriceTracker.spec` (PyInstaller), `installer/PriceTracker.iss`
  (Inno Setup), `version_info.txt`

**Stack:** PySide6 · pyqtgraph · SQLAlchemy · Selenium + BeautifulSoup · Supabase
(Postgres + Auth) · keyring · pandas/openpyxl · PyInstaller + Inno Setup.

---

## Completed

### Phase 1 — Data layer
SQLAlchemy `Product` + `PriceHistory`, SQLite in `%LOCALAPPDATA%\PriceTracker`,
repository CRUD + change detection + hourly snapshots. Nullable `user_id` from
day one for the later accounts phase.

### Phase 2 — Pluggable scraper
`RetailerAdapter` interface + `ProductData`; `AmazonAdapter` (selectors, URL
normalization, parsing); registry dispatches by URL domain. Selenium-primary
fetch with a requests fallback and startup retries.

### Phase 3 — Desktop UI (PySide6)
Product table, add/edit/delete, clickable title links, orange change
highlighting; pyqtgraph price-history dialog with timescale selector; CSV/Excel
export.

### Phase 4 — Background updates
`QTimer` 5-minute auto-refresh (updates + tray notifications) and hourly history
snapshot; system tray keeps the app running when minimized.

### Phase 5 — Packaging
One-folder PyInstaller build (`.exe`) + Inno Setup installer.

### Phase 6 — Accounts & cloud sync
Supabase Auth (register + email confirmation, login) and cloud Postgres data
with row-level security; the app requires login and uses the cloud backend.

### Phase 7 — Click-to-sort headers
Product / Price / Stock / Last-checked cycle ascending → descending → manual
(position) order, with the native sort arrow; choice persisted.

### Phase 8 — Remember me / auto-login
"Remember me" stores the Supabase refresh token (never the password) in the OS
keyring; startup auto-login with fallback to the login dialog.

### Phase 9 — Stock graph
Price | Stock toggle in the graph window; a stock classifier maps free-text
availability (TR + EN) to a step chart (Out / Limited / In stock).

### Phase 10 — Settings page + logout
Change name / password / email and export data from Settings; Log out clears the
saved session and returns to the login screen.

### Phase 11 — Theming, font, icon, packaging hardening
Material (default) / Light / Dark themes, live-switchable; bundled Orbitron font
+ a "choose any font" picker; shopping-cart app icon (window/taskbar/tray);
manual row ordering with up/down arrows; layout persistence; "Close to tray"
switch. Hardened build: embedded version info, no UPX, per-user install,
bundled cloud config so the installed app is account-enabled on any machine.

### Phase 12 — Center-aligned columns
Price / Stock / Last-checked columns center-aligned; Product stays left-aligned.

### Phase 13 — Product image in each row
Adapters extract the main image URL (`ProductData.image_url`); `image_url`
column added (local model + Supabase migration). An async loader
([ui/image_cache.py](../ui/image_cache.py)) downloads each thumbnail once,
caches it under `%LOCALAPPDATA%\PriceTracker\images\`, and shows it in a new
image column (56px thumbnails in 70px rows).

---

## Upcoming

### Phase 14 — "What changed while you were away" + back-in-stock
*(Covers shutdown→startup price comparison and out-of-stock→in-stock detection.
Builds on existing change flags, making them session-aware and explicit.)*
- A `NotificationService` abstraction (tray now; Telegram in Phase 15).
- Startup background refresh → diff vs persisted `last_price`/`last_stock` →
  summary notification.
- Back-in-stock detection via the stock classifier levels (`OUT → IN_STOCK`).
- No deps/schema. Gotcha: startup refresh is slow (Selenium) → run in background.

### Phase 15 — Telegram bot notifications
- `TelegramNotifier` plugged into the Phase 14 NotificationService (Bot API).
- Settings: bot token + chat ID (token in keyring), "Send test message", toggle.
- Deps: `requests`. The user creates a bot via BotFather; opt-in; respect rate
  limits; never log the token.

### Phase 16 — More e-commerce sites
One `RetailerAdapter` per site, registered in the registry. Candidates (TR):
Trendyol, Hepsiburada, n11, MediaMarkt, Vatan; plus eBay. Feasibility is
per-site (differing layouts, bot detection) — validate and ship one at a time.

### Phase 17 — Updater & version engine
- Single `__version__` source shared with `version_info.txt` + installer.
- Startup check against the GitHub Releases "latest" API; notify with a
  download/install link. Later: assisted auto-download of the new setup.
- Deps: `requests` (+ maybe `packaging`). Ties to code signing (unsigned
  downloads hit SmartScreen); replacing a running exe is hard, so v1 =
  "notify + open release", v2 = assisted download/run.

**Suggested order:** 14 → 15 → 16 → 17 (14 before 15: Telegram plugs into the
notification service).

---

## Known follow-ups / tech debt
- **Code signing**: unsigned exe/installer triggers SmartScreen. Needs an
  Authenticode certificate (see `BUILD.md`).
- The `.exe` must be rebuilt (`build.bat`) after dependency or asset changes.
- Target machines need **Google Chrome** installed (Selenium Manager fetches the
  driver on first run).
