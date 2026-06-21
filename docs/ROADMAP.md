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

### Phase 14 — Away-changes + back-in-stock notifications
Channel-agnostic `NotificationService` ([services/notifications.py](../services/notifications.py))
with a tray channel. On launch, a one-shot background refresh diffs current
price/stock against the values persisted from the last session and notifies
("While you were away"). Back-in-stock is detected via the stock classifier's
`OUT → available` transition and surfaced separately, in both startup and the
5-minute refresh. Notifications are categorized (back in stock / price / stock).

### Phase 15 — Telegram notifications
`TelegramNotifier` ([services/telegram.py](../services/telegram.py)) plugs into
the NotificationService: self-gating, async (never blocks the UI). Settings →
Telegram: bot token (stored in keyring), chat ID + enabled (QSettings), a
"Send test" button, and an in-app step-by-step setup guide with clickable
@BotFather / @userinfobot links. The Settings dialog is scrollable so it never
squeezes as sections grow. Token is never logged.

### Phase 16 — Beyond Amazon (generic structured-data adapter)
A `GenericAdapter` ([core/scraping/generic.py](../core/scraping/generic.py))
handles any non-Amazon site by reading standardized structured data —
schema.org JSON-LD `Product` first, then Open Graph / product meta tags — for
name, price, currency, availability, and image. Registered as the catch-all
after Amazon. This covers many stores (Trendyol, Hepsiburada, …) without
per-site selectors; sites exposing neither return a clear error, and we can add
a bespoke adapter for those later. Robust price parsing handles US/EU formats.
Dedicated adapters so far:
- **n11** ([core/scraping/n11.py](../core/scraping/n11.py)) — title, image, and
  price read from the embedded JS state (`"priceFloat"`), since the visible
  price is a bot-gated XHR; no reliable stock, so it's skipped.
- **Hepsiburada** ([core/scraping/hepsiburada.py](../core/scraping/hepsiburada.py))
  — uses stable `data-test-id` hooks (classes are hashed) for title/price, with
  the `data-hbus` JSON price as fallback; best-effort stock.
- **AliExpress** ([core/scraping/aliexpress.py](../core/scraping/aliexpress.py))
  — title (`h1[data-pl=product-title]`) + current price via stable class prefix
  (`[class*="price-default--current"]`) and `og:image`; stock skipped. Has
  anti-bot (baxia) that may occasionally serve a challenge instead of the page.
- **Trendyol** — *parked.* It actively blocks headless automation (serves an
  obfuscated anti-bot page); undetected-chromedriver also failed here. Would need
  a paid scraping API / residential proxy, so it's deferred.

---

## Upcoming

### Phase 17 — Updater & version engine
- Single `__version__` source shared with `version_info.txt` + installer.
- Startup check against the GitHub Releases "latest" API; notify with a
  download/install link. Later: assisted auto-download of the new setup.
- Deps: `requests` (+ maybe `packaging`). Ties to code signing (unsigned
  downloads hit SmartScreen); replacing a running exe is hard, so v1 =
  "notify + open release", v2 = assisted download/run.

### Phase 18 — Startup changes report window
After the launch "while you were away" refresh (Phase 14) finishes, if any
price/stock changes were detected, show them in a dedicated **report window**
(a dialog with a small table), in addition to the tray notification. Scope is
**this startup only** — just the changes between the last shutdown and this
startup; it does not show historical changes, and it doesn't appear when nothing
changed. Each row: product, old → new price, and stock change / back-in-stock.
- Builds on Phase 14: extend the startup batch to collect old→new values (not
  just names), and open the dialog when that batch finalizes with changes.
- No deps/schema.

### Phase 19 — Configurable refresh interval
A dropdown (5 min / 15 min / 30 min / 1 hour) for the auto-refresh interval.
Changing it takes effect **immediately** — restart the refresh `QTimer` with the
new interval (`setInterval`/restart), no app restart. Persisted in `QSettings`
and restored on launch; replaces the hard-coded `REFRESH_INTERVAL_MS`. Lives in
the toolbar (or Settings → Appearance/General). No deps/schema.

### Phase 20 — Directional change colors
Replace the single orange "changed" color with direction-aware colors in the
Price and Stock cells: **increase → yellow, decrease → green** (a price drop is
"good", so green). Price direction = compare `last_price` vs `prev_price`; stock
direction = compare classifier levels/quantity (`prev_stock` vs `last_stock`,
e.g. out→in = increase). No deps/schema.

**Next:** Phase 17 → 18 → 19 → 20.

---

## Known follow-ups / tech debt
- **Code signing**: unsigned exe/installer triggers SmartScreen. Needs an
  Authenticode certificate (see `BUILD.md`).
- The `.exe` must be rebuilt (`build.bat`) after dependency or asset changes.
- Target machines need **Google Chrome** installed (Selenium Manager fetches the
  driver on first run).
