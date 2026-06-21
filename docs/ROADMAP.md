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

### Phase 9 — Stock graph *(later removed)*
Originally a Price | Stock toggle in the graph window. **Removed:** stock isn't
reported reliably across all sites, so the graph is **price-only** now. (The
stock classifier is still used for back-in-stock change detection.)

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
**Later change:** the on-launch auto-refresh was removed (it froze the app
launching many scrapes at once), so refresh now runs only on the periodic timer
or manually — the startup "while you were away" diff/report no longer auto-runs.

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
- **İtopya** ([core/scraping/itopya.py](../core/scraping/itopya.py)) — clean
  class names: title, visible DOM price (`.product-details__sidebar_newprice`),
  `img[data-id=imgMain]` image, best-effort stock. Deliberately ignores the
  JSON-LD price (it's stale/different from the displayed price here).
- **Sinerji** ([core/scraping/sinerji.py](../core/scraping/sinerji.py)) — clean
  class names: title (`.pageTitle h1`), price (`.priceWrapper .price` /
  `.defaultPrice`), carousel image (`data-img`), best-effort stock.
- **İncehesap** ([core/scraping/incehesap.py](../core/scraping/incehesap.py)) —
  microdata hooks (`itemprop` name/price/image) that survive the Tailwind utility
  classes; price from machine-readable `[itemprop=price]`, relative image URL
  made absolute. Also fixed the shared price parser to read Turkish thousands
  without decimals (`5.009` → 5009).
- **Trendyol** — *parked.* It actively blocks headless automation (serves an
  obfuscated anti-bot page); undetected-chromedriver also failed here. Would need
  a paid scraping API / residential proxy, so it's deferred.

### Phase 17 — Updater & version engine
Single `__version__` source ([core/version.py](../core/version.py)), shown in the
window title and a **File → About** dialog. On startup (and via **File → Check
for updates…**), a background check queries the GitHub Releases "latest" API
([services/updater.py](../services/updater.py)). If a newer release exists, the
app **downloads the attached installer (.exe) in the background and runs it**,
then closes so the install can finish (falls back to opening the release page if
the release has no installer asset). The downloaded installer is unsigned, so
SmartScreen may warn ("More info → Run anyway") until code signing is added.

### Phase 18 — Startup changes report window
After the launch "while you were away" refresh, if any price/stock changes were
detected, a report window ([ui/changes_dialog.py](../ui/changes_dialog.py)) lists
them in a table — product, old → new price, and stock / back-in-stock — alongside
the tray notification. Scope is **this startup only** (changes between last
shutdown and this launch); it doesn't show history and doesn't appear when
nothing changed. The 5-minute refresh still only notifies (no window).

### Phase 19 — Configurable refresh interval
A dropdown in the toolbar (5 / 15 / 30 minutes / 1 hour) for the auto-refresh
interval. Changing it takes effect **immediately** (restarts the refresh
`QTimer`), is persisted in `QSettings`, and is restored on launch.

### Phase 20 — Directional change colors
Price/Stock cells are colored by direction: **increase → yellow, decrease →
green** (orange when changed but direction is indeterminate). Price compares
`last_price` vs `prev_price`; stock compares the classifier level (out→in =
increase), then quantity as a tiebreaker.

### Phase 22 — Row numbers
A `#` column at the far left showing each row's 1-based **display position**
(muted gray), set in `_append_row` from the append order so it re-sequences
automatically on sort/reorder. (Done before Phase 21.)

### Phase 23 — Site logo per row
Retailer logo column **between the move arrows and the product image**, mapped
via the scraper registry (`get_adapter(url).name`) to a bundled PNG in
`assets/logos/`, with `generic.png` as the fallback. `ui/logos.py` caches scaled
pixmaps; `scripts/normalize_logos.py` trims + uniform-scales the raw originals.

### Phase 24 — Per-row refresh + status indicator
A **Refresh** button on each row (`_refresh_one`) re-scrapes just that product
and updates only its row, plus a **Status** column indicator: `⟳` refreshing →
`✓` done / `✗` error (tooltip shows the reason). Works for "Refresh All" too —
rows flip to ✓/✗ live as each async task finishes. Batch and single refresh
share `_persist_scrape`; single-row refresh is gated while a batch runs.

---

## Upcoming

### Phase 21 — Scraping performance
The bottleneck is launching Chrome + rendering JS (~10–30s/product); the DB,
parsing, and data structures are negligible (so Redis/caching layers wouldn't
help). Target the actual cost:
- **`requests`-first / embedded-data fast path:** try a plain HTTP fetch and
  read the data from the initial HTML (JSON-LD, Open Graph, or embedded JSON
  like n11's `priceFloat`); only fall back to Chrome when the data isn't there.
  ~100× faster for sites that allow it.
- **Persistent browser reuse:** keep one headless Chrome alive and navigate it
  through a whole "Refresh All" batch instead of starting/stopping Chrome per
  product (saves ~2–5s startup each).
- **Block images/CSS/fonts** during scraping (Chrome flags / CDP) so pages load
  faster — extend the Linux-only image blocking to Windows.
- **Cap concurrency** to a small fixed limit (e.g. 2–3) — faster *and* avoids
  the resource exhaustion / Chrome crashes from unbounded parallel launches.
- Keep Chrome as the reliable fallback; no new deps.

**Next:** Phase 21.

---

## Known follow-ups / tech debt
- **Code signing**: unsigned exe/installer triggers SmartScreen. Needs an
  Authenticode certificate (see `BUILD.md`).
- The `.exe` must be rebuilt (`build.bat`) after dependency or asset changes.
- Target machines need **Google Chrome** installed (Selenium Manager fetches the
  driver on first run).
