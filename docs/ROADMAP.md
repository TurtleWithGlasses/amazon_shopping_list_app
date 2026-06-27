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

### Phase 21 — Scraping performance
`requests`-first fast path: each adapter now splits fetch from parse (`_parse`),
so `RetailerAdapter.scrape()` tries a plain HTTP fetch and reads the price from
the initial HTML (embedded JSON like n11's `priceFloat`, microdata, JSON-LD,
server-rendered DOM), only launching headless Chrome when the data isn't there
— ~100x faster for server-rendered sites. Also: image loading disabled on all
platforms (was Linux-only), a shared keep-alive HTTP session, and scraping moved
to a dedicated pool capped at 3 so "Refresh All" can't spawn a swarm of Chrome
instances (the global pool stays free for thumbnails/notifications).
Persistent-browser reuse (Part D) was deferred — see Upcoming.

### Phase 25 — Auth confirmation email + post-confirmation page
Polish the sign-up confirmation experience (Supabase Auth):
- **Confirmation email:** a proper branded HTML template — Price Tracker name +
  cart logo, clear "Confirm your email" CTA button, plain-text fallback, sane
  subject/sender. Configured in the Supabase dashboard (Auth → Email Templates)
  using its template variables (`{{ .ConfirmationURL }}` etc.).
- **After-confirmation page:** the link currently lands on a bare/default page.
  Point Supabase's redirect at a small branded "Email confirmed — you can now
  sign in to Price Tracker" page (or a clear in-app deep-link/message) instead.
- Mostly dashboard config + a static page; no app code beyond the redirect URL.

### Phase 26 — Consistent row selection highlight
Selecting a row highlights the plain text cells blue, but the **widget cells
don't follow** — move arrows, logo, image, status, and the Actions buttons keep
their default background (see screenshot), so a selected row looks patchy.
- Cause: `setCellWidget` cells paint the widget over the cell, so the table's
  selection brush never shows through.
- Fix options: make widget containers transparent and let the row brush show
  (`setAutoFillBackground(False)` + transparent stylesheet), **or** drive the
  selection color via the table's stylesheet / a custom delegate / a
  `selectionChanged` handler that tints each row's widgets to match.
- Goal: the entire row (including widget columns) reads as one consistent
  selection. UI-only; no schema.

### Phase 27 — Preserve scroll position on reload
After scrolling down, adding a URL or refreshing jumps the table back to the
top, because `reload()` clears and rebuilds every row (resetting the scrollbar).
- Fix: capture `table.verticalScrollBar().value()` before the rebuild and
  restore it after (and ideally keep the selected/added product in view). Guard
  against the new content being shorter than the old offset.
- Applies to `reload()` callers: Add Product, single/batch refresh, move,
  edit/delete. UI-only; no schema.

### Phase 28 — Google Stitch / Material 3 visual restyle
Adopt the look of Google Stitch (Google's AI UI-design tool, Material 3
aesthetic). Stitch outputs **web** designs/HTML-CSS, so there's no direct import
into Qt — we emulate the style with a Qt stylesheet (QSS) theme:
- Material-3 color tokens (primary/surface/on-surface), rounded corners, subtle
  elevation/shadows, consistent spacing, and a clean type scale.
- Restyle the high-traffic widgets: toolbar, buttons, inputs, the product
  table (header, rows, selection), status/menu bar.
- Workflow: optionally generate a reference mockup in Stitch, then translate it
  to QSS; build on the app's existing theming/dark-mode so both themes get the
  new look.
- Coordinate with Phase 26 (selection highlight) so the table styling is done
  once. UI-only; no schema; no new runtime deps (pure QSS, optional design-time
  use of Stitch).

*Shipped:* new "Stitch (Material 3)" theme (default) + M3 tokens on every theme;
tonal pill buttons, filled-primary CTAs (`Add Product` / `Refresh All`), filled
rounded inputs, card-like table, refined header/scrollbars; transparent
`#rowcell` wrappers so rows/selection render consistently.

### Post-v0.5.0 fixes & polish (v0.6.x – v0.7.0)
Incremental fixes/features shipped after Phase 28 (not numbered phases):
- **Scraping / build:** bundled Selenium's lazily-imported Chrome submodules so
  browser-fallback scraping works in the packaged app; Sinerji/İtopya now wait
  for the title *text* (JS-rendered SPA) instead of mere element presence.
- **Price graph:** single line with hoverable dots only at price changes, marked
  at **both ends** of each segment; tooltips show price, time, and the +/- delta.
- **Notifications:** manual "Refresh All" now notifies (was auto-refresh only);
  per-product **list** format with directional price arrows (red/up = rose,
  green/down = fell) and the **store name** leading each line.
- **Window state:** maximized/full-screen restored after close-to-tray or restart.
- **Duplicate guard:** adding an already-tracked URL is blocked with a warning
  (canonical URL compare; normalizes Amazon /dp vs /gp).
- **Logos:** lookup falls back to the domain word for adapter-less sites; added
  Teknosa, Vatan Bilgisayar, Akakçe, Media Markt, Trendyol.

### Phase 29 — "Never" auto-refresh option
**Never** added to the auto-refresh dropdown; selecting it stops the refresh
`QTimer` so the app tracks **only on demand** (manual "Refresh All" / per-row).
New `_apply_refresh_interval` guards the `0` case (`QTimer.start(0)` would
otherwise fire continuously); persisted in `QSettings` and restored on launch.

### Phase 30 — Theme-aware link (URL) color
Each theme gained a tuned `link` token, and `link_color()` reads the active
theme — so the product-name link harmonizes per theme instead of a fixed blue.
Changing the theme reloads the table so the new color applies live.

### Phase 31 — Refresh progress counter
The bottom-left status bar shows a live `done/total` counter ("Refreshing
15/100…") that ticks up in `_on_refreshed` as each async fetch finishes.

### Phase 32 — Inline price-change arrow in the Price column
Price cells show **red ▲ up / green ▼ down** next to the price when it changed,
and nothing when a later scan finds no change. Price colors now match the
notification convention (Phase 20's yellow-up replaced by red for price; stock
colors unchanged).

### Phase 33 — Target-price alerts
Per-product **target price** (set in the Edit dialog): the price cell shows a 🎯
badge when the current price is at/below it, and a **"🎯 Target price reached"**
alert (tray + Telegram) fires on the scan that crosses below — not on every scan
after, re-arming if it goes back above. Stored as `products.target_price`,
checked in `_persist_scrape`. (Percent-drop / recent-average variant deferred.)

### Phase 34 — Product groups (manual comparison sets)
User-defined comparison sets. New `groups` + `group_members` tables (both
backends; RLS on Supabase). Right-click a product → add to / remove from groups;
the **Groups** menu lists every group (one click opens it) plus a manager
(create / rename / delete). The **group view** shows members **cheapest-first**
with a color swatch, logo, clickable name link, current price, and 30-day low
(cheapest highlighted), above a **combined price graph** — each line + legend
tagged by store, with hover tooltips (`site · product · price · time`); a
draggable splitter sizes the table vs. graph. Membership is a reference (FK
`on delete cascade`), so deleting/refreshing a product flows through
automatically. Group-level alerts can layer on later via Phase 33.

---

## Upcoming

The remaining "buying tool" set — built to need **no paid APIs** (discovery and
recommendations reuse the existing scraper). Suggested order: 35 → 36, with 37
(trend) and 38 (cart) as self-contained additions.

### Phase 35 — "Find it cheaper elsewhere" (comparison-site discovery)
Suggest the same product on other sites — **free**, by leaning on a price-
comparison site (Akakçe / Cimri) that already solved cross-site matching, rather
than a paid search API.
- Given a product, query its comparison-site page and scrape the **seller +
  price list** (reuses the scraping pipeline; needs an adapter for the section).
- Surface results as "also available on…"; matching is **best-effort** —
  results are **suggestions the user confirms**, then drop into a Phase 34 group.
- Optional precision signal: match on **GTIN/MPN/brand** from structured data
  when present. No paid API; human-in-the-loop to avoid wrong-variant matches.

### Phase 36 — Complementary product suggestions ("you might also track…")
"Tracking shaving blades? You might want shaving gel / after-shave too." Built
**free**, no recommender-model data needed (avoids the cold-start problem):
- **Primary — scrape the retailer's own widget:** parse "Birlikte Alınanlar /
  İlgili Ürünler" on pages already being loaded — real co-purchase data, zero
  cost, items already trackable.
- **Fallback — curated category→complement rules:** a static JSON map
  (`shaving → {gel, after-shave, brush}`) with keyword-based category detection;
  suggested terms run through Phase 35 discovery to become real listings.
- **Optional upgrade — local LLM via Ollama:** if the user runs Ollama
  (`localhost:11434`, no API key, no cost), ask a small model (e.g.
  `llama3.2:3b`) for complementary **Turkish** search terms; fall back to the
  above when absent. Not bundled (would bloat the installer); cached per product.
- A quiet, **dismissible** suggestions strip; everything human-confirmed; results
  feed discovery/groups.

### Phase 37 — Price trend indicator (rising / falling / stable)
Mark each product by its **tendency over a window** (default 7 days) — distinct
from Phase 32, which shows only the last scan's move. No ML; reads the existing
`PriceHistory`.
- Compute from history in the window: a least-squares **slope** (robust to a
  single blip) or net % change start→end, classified with a **stability band** —
  **falling** (green ▼ / 📉), **rising** (red ▲ / 📈), **stable** (→), or
  **unknown** when there are too few points. Colors match Phase 32 (down green,
  up red).
- Show as a **Trend column / badge** with a tooltip giving the % change + window;
  let the user **sort by trend** to spot what's dropping this week. Window could
  reuse the existing timescale options (day / week / month).
- **Perf:** batch the history fetch (one query) or cache the computed trend and
  recompute after each refresh — never per-row on every reload. No new deps.

### Phase 38 — Virtual shopping cart
A cart the user builds from tracked products, showing the **live total cost**.
- Add/remove tracked products to/from a cart (per-product quantity optional);
  the cart lists each item with its current price and a running **total**.
- **Prices flow through live:** since cart items reference tracked products, a
  price change from any refresh updates the cart total automatically (reuse the
  same `last_price`); show the per-item ▲/▼ and a total delta.
- A cart panel/tab (or dialog) with the total pinned; optionally a cart-level
  target alert ("notify when the cart total drops below ₺X") via Phase 33.
- Schema: a `cart_items` table (product_id, quantity) — or reuse Phase 34 groups
  with a "cart" flag, since a cart is essentially a group with a summed total.

*Deferred:* Phase 21 Part D (persistent browser reuse) — keep one headless Chrome
alive across a batch; low value now that the fast path skips Chrome for most
sites, so revisit only if browser-fallback sites come to dominate a refresh.

---

## Known follow-ups / tech debt
- **Offline-DB migration gap**: running **not logged in** can crash on missing
  `image_url` / `position` columns (the local SQLite predates them). Add a tiny
  startup migration / schema check so the offline path doesn't break.
- **No automated tests yet**: add a `pytest` suite — adapter parse-tests against
  saved HTML fixtures, plus price-parsing / dedup / notification-format tests —
  so scrapers and core logic can change safely as the app grows.
- **Dedicated adapters** for Teknosa / Vatan / Media Markt / Trendyol (currently
  scraped via the generic adapter, which may misread price/stock).
- **Code signing**: unsigned exe/installer triggers SmartScreen. Needs an
  Authenticode certificate (see `BUILD.md`).
- The `.exe` must be rebuilt (`build.bat`) after dependency or asset changes.
- Target machines need **Google Chrome** installed (Selenium Manager fetches the
  driver on first run).
