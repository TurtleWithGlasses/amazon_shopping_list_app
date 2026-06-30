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

### Phase 35 — "Search on Google" (find it elsewhere)
Per-product **"Search on Google…"** (right-click) opens a Google web search for
the product name in the browser, so the user can find it **in stock / cheaper**
on other sites. Chosen over scraping a comparison site (Akakçe/Cimri) or a paid
search API: it's **instant** (no Selenium), **robust** (no anti-bot/ToS issues —
we just open a URL), and broad (any site Google indexes, and it tends to rank
in-stock retailer pages). Human-in-the-loop. *(An in-app, pre-matched seller
list was prototyped against Akakçe but dropped: its per-seller store names are
obfuscated / JS-rendered / lazy-loaded and too fragile to scrape reliably.)*

### Phase 36 — Complementary product suggestions ("you might also track…")
Right-click a product → **"You might also need"** lists complementary items for
its category; clicking one opens a Google search (Phase 35). **Free &
deterministic** — a curated category→complement map (`services/suggestions.py`)
with Turkish-aware keyword detection (`İşlemci → işlemci`); no scraping (would be
as fragile as the dropped Akakçe seller list), no ML, no API. Extensible by
adding a row to the rule table. *(Optional Ollama upgrade and a persistent
suggestions strip left as future enhancements.)*

### Phase 37 — Price trend indicator (rising / falling / stable)
A **Trend column** marks each product's tendency over a 7-day window: ▼ green
(falling), ▲ red (rising), → gray (stable), blank (too few points), with a
`% change` tooltip; distinct from Phase 32 (last-scan move). `services/trend.py`
uses a least-squares slope (robust to a single blip); a `_trend_cache` is filled
by one **batched** `recent_history` query at startup and after each refresh —
never per-row on reload — and the column is **sortable** by % change. The cloud
query is **paginated** (Supabase caps a response at 1000 rows, which a week of
snapshots exceeds — otherwise most trends came back empty).

---

### Phase 39 — Theme-aware graphs
The price-history graph and the group comparison graph hardcoded a **white
background** and fixed axis/grid/line colors, so they clashed on the dark /
Stitch / Material themes (a white chart in a dark window). They now pull their
styling from the active theme via a shared helper
([ui/graph_style.py](../ui/graph_style.py) `style_plot()` + a new
`theme.active_theme()` accessor): background = surface (`base`), tick labels =
`subtext`, axis/grid = `border`, the single-product line + hover dots = the
theme `accent` (dot halo = `base`), and the group view's per-line palette + the
legend/hover use theme-legible colors. Applied in `ui/graph_dialog.py` and
`ui/group_view_dialog.py`; re-applied each time a graph opens, so switching the
theme and reopening picks up the new look. UI-only; no schema; no new deps.

### Phase 38 — Virtual shopping cart
A single cart the user builds from tracked products, with a **live total cost**.
New `cart_items` table (both backends; RLS on Supabase) referencing a product +
a quantity (a product appears at most once). Right-click a product → **Add to /
Remove from cart**; a **Cart** menu opens the cart (label shows the item count)
or clears it. The cart view ([ui/cart_dialog.py](../ui/cart_dialog.py)) lists
each item with logo, clickable name link, site, unit price, an inline **Qty**
spinbox, and a **line total**, with a pinned **grand total**. Because items
reference tracked products, prices flow through automatically: editing a quantity
updates the line + grand total instantly (and persists), and a refresh while the
cart is open **reloads it live** (`reload_prices()` hooked into
`_finalize_refresh` / `_on_one_refreshed`). The total is summed **per currency**
and shows a **▲/▼ delta** from the most recent refresh; products scraped without
a currency label are folded into the cart's single known currency so there's one
combined total (only genuinely different currencies split). *(Single cart for
now; cart-level target alerts via Phase 33 left as a future enhancement.)*

---

## Upcoming

Self-contained: **40** (notifications center).

### Phase 40 — In-app notifications center
A **notifications button** (bell) in the toolbar with an **unread badge**, so the
user sees recent changes in the app — not only via Telegram/tray.
- After each refresh, append the detected changes to an in-app **notifications
  history** (same content as the Telegram message: per product `site · name`,
  `prev → new` price with ▲/▼, stock change, 🎯 target reached).
- Clicking the bell opens a **notifications window** listing recent changes,
  newest first; the unread badge clears on open. Each entry could deep-link to
  the product / open its graph.
- Reuses the existing change-collection pipeline (`_refresh_events` /
  `_changes_message`) and the `StartupChangesDialog` table pattern.
- Persistence: in-memory per session for the MVP; optionally persist (a small
  log table / JSON) so history survives restarts. No new deps.

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
- **Amazon currency sometimes blank**: some amazon.com.tr listings are stored
  with an empty `currency`, so prices show without a "TL" suffix. The cart works
  around it (folds blank into the single known currency), but the Amazon adapter
  should capture the currency reliably so the value is correct at the source.
- **Code signing**: unsigned exe/installer triggers SmartScreen. Needs an
  Authenticode certificate (see `BUILD.md`).
- The `.exe` must be rebuilt (`build.bat`) after dependency or asset changes.
- Target machines need **Google Chrome** installed (Selenium Manager fetches the
  driver on first run).
