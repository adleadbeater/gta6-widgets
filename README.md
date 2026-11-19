# GTA 6 widgets for MovieWeb

## 1. Contents

- `widgets/` — CMS-ready embeds, three fields each (`html.html`, `css.html`, `js.html`)
  - `00-mega/` — all three widgets in one embed
  - `01-sales-tracker/` — live sales tracker
  - `02-copies-chart/` — GTA 6 vs. best-selling games (copies), Launch / All time
  - `03-revenue-chart/` — GTA 6 vs. biggest entertainment releases (revenue), Launch / All time
- `preview/` — open `preview/index.html` in a browser; runs offline on bundled seed data; `?theme=light` for light mode
- `data/` — `tracker.json` (Sensor Tower readings + daily history), `comparisons.json` (chart data, hand-edited), `links.json` (related articles, hand-edited)
- `src/` — the shared JS and CSS the fields are built from
- `tools/build.py` — rebuilds `widgets/` and `preview/` from `src/` and `data/`: run `python3 tools/build.py` after any change to `src/`
- `scraper/` + `.github/workflows/update-data.yml` — data pipeline
- Mockup: https://claude.ai/artifact/DeAKyPU5KpqVKpYdYa6Wg2

## 2. Installing an embed

- Paste each widget's three files into the CMS's HTML, CSS and JS fields
- CSS and JS are identical across all four widgets
  - Several widgets on one page: pasting the same CSS/JS more than once is harmless (mount guard + one global)
  - Mega and separate widgets can sit on the same page
- `data-src` in `html.html` is the data URL (must be `https://`, ending in `/data/`)
- While data loads, the widget holds its space with an empty panel, so the article doesn't jump when it appears
  - Result: no layout shift (Core Web Vitals) on pages where the widget sits near the top
- If data fails to load or validate, the widget hides itself and logs a console warning
  - Result: a failed fetch or bad JSON never shows a broken box; the held space closes
  - If the script never runs at all, the held space closes after 12 seconds
- Embeds pasted before v1.1 (with `hidden` on the div) still work; they just don't hold space while loading

## 3. Behaviour

- Live counter = latest reading + (rate between the last two readings × time since the latest reading)
  - Re-fetches data every 5 minutes; a new reading snaps the counter to it
  - Ticks only while the widget is on screen and the tab is visible
  - "Pause live count" button stops it; readers with reduced motion switched on get one update a minute
- Stale data: 36 hours after the latest reading the widget stops projecting
  - Shows the latest real reading, badge "Latest reading", "Awaiting next update"; charts label GTA 6 "Latest reading"
  - Result: a stalled feed never leaves an inflated number on screen
- Official figure: shown beside the estimate in an "Official vs. estimate" block; it never replaces the estimate (section 8)
- History chart: Sensor Tower's daily cumulative copies, following the platform buttons; hover or arrow keys read out each day
- Comparison charts: top 10, sorted on render; GTA 6 pinned below with its rank if it falls outside
  - Copies all-time uses a fixed `pinRank` of "50+"
  - Line under each chart: what GTA 6 last passed and what's next, with the gap and an estimate at the current pace
    - Hidden in the next-target part when GTA 6 sits behind a fixed `pinRank` (the entries in between aren't listed)
    - No pace estimate when data is stale or the target is more than 14 days away
- Launch view: GTA 6 shows "Pre-orders + sales to date" until Sensor Tower's history reaches the end of its first 3 days
  - Then it switches to a fixed "First 3 days" figure, comparable with the other first-3-day entries (section 7)
- Share button on every panel: native share sheet on phones, otherwise copies a link to the panel
  - Links end `#gta6-sales-tracker`, `#gta6-copies-chart` or `#gta6-revenue-chart` (`-2` etc. for repeats, in page order)
  - Opening a shared link scrolls to that panel once it has loaded
- "More on GTA 6" related links at the bottom of the tracker (or the mega's last panel), from `data/links.json`
- Theme follows `prefers-color-scheme`; force with `data-theme="light"` or `data-theme="dark"` on the root div
- Narrow layout via container query at 600px, so it adapts to the column, not the window
  - Readings table fits a 320px column; its date column stays pinned if a column is narrower still
- Exception to the design system's "freeze what an article shows" rule: these widgets are intentionally live

## 4. Tracking

- `window.websiteSentinel.sendEvent(category, action, label)`, retried 20 × 250ms, then dropped
- Categories: `GTA 6 Sales Tracker`, `GTA 6 Copies Chart`, `GTA 6 Revenue Chart` (mega sends each panel under its own category)
- Actions: `Impression` (once, 50% visible), `Platform Switch`, `Toggle`, `Link Click`
  - `Pause` (label `pause` / `resume`), `Share` (label `native` / `copy`)
  - `Related Click` (always under `GTA 6 Sales Tracker`, label = article title)

## 5. Data hosting

- Put this folder in a GitHub repo (e.g. `gta6-widgets`), enable GitHub Pages from the main branch root
- Data URL becomes `https://<org>.github.io/gta6-widgets/data/`
- Seed `tracker.json` uses midnight UTC for each reading's `at`
  - Result: today's live figure runs ahead of the published 19.05M; real readings from the scraper carry their capture time

## 6. Scraper

- `scraper/discover.py` — run once locally; saves every JSON response the Sensor Tower page loads to `discover-output/`
- `scraper/update.py` — scheduled job (Python 3.12; Playwright 1.47 does not build on 3.15)
- Source: Sensor Tower's tracker is an Infogram embed, `https://e.infogram.com/_/yi1PZCdFCmfv0cv5KQmG`
  - No JSON request; the data is inlined as `window.infographicData`, read from the iframe whose URL contains `infogram.com`
  - Path: `elements.content.content.entities` → two `CHART` entities with header `date | Xbox | Playstation`
    - Units table in millions, revenue table in $ millions (the one with the larger values); last row by date
    - Totals = Xbox + Playstation; precise to 10k units / $10k
  - `date` = the `TEXT` entity "Last updated November 19, 2026", matching what readers see on Sensor Tower
    - The chart's last row is usually ~2 days earlier; it is not used as the date
  - Cross-check: totals must be within 1% of the headline tiles ("19.05M", "$1.84B")
    - Result: if Sensor Tower changes the embed or layout, the run fails and alerts instead of writing bad data
  - Same date as the latest reading = a revision: it replaces that reading (keeping its `at`) instead of adding a second one
- Also saves Sensor Tower's daily chart as `series` in `tracker.json` (one row per day: date, PS5/Xbox units, PS5/Xbox revenue)
  - Checked separately: a bad series is skipped and the previous one kept; it never blocks a reading
- Validates before writing: positive integers, $60–$120 per copy, PS5 + Xbox within 1% of total, never lower than the previous reading
  - Jump limit: no more than +50% since the previous reading, raised to +200% from 3 days before to 14 days after the release date in `comparisons.json`
  - Result: day-one sales on top of pre-orders aren't rejected as a glitch
  - Result: on failure nothing is written and the last good file stays live
- Workflow runs every 30 minutes, commits `data/` only when it changes

## 7. Updating comparison data

- Edit `data/comparisons.json` directly; no rebuild needed
- `"gta6": {"release": "YYYY-MM-DD", "launchDays": 3}` — GTA 6's release date and launch window
  - Drives the Launch view's like-for-like figure, the history chart's Launch marker and the scraper's launch jump limit
  - Set to 2026-11-19; correct it here if the date changes
- GTA 6 rows use `"live": true` instead of `amt`; their `sub` label is set by the widget (pre-orders, first 3 days, est. to date, latest reading)
  - Don't mention GTA 6's state in a Launch view's `note`: the widget adds that sentence
- `film: true` = grey bar; `plus: true` = value shown with "+"
- Check weekly: Spider-Man: Brand New Day (still in release), Minecraft and GTA 5 lifetime units
- GTA 5 lifetime revenue is a 2018 analyst estimate ($6B); replace when a current figure is available

## 8. Official figures and related links

- Official figure: add `official` to `data/tracker.json` (the scraper keeps it)
  - `{"date": "YYYY-MM-DD", "units": 25000000, "source": "Take-Two", "note": "Sell-in, all formats.", "url": "https://..."}`
  - `revenue` is optional; Take-Two usually reports units only
  - Shown beside the Sensor Tower reading on or before that date; the live estimate keeps running
  - Edit right after a scraper commit, or pull first: the bot commits to the same file
- Related links: `data/links.json`
  - `{"title": "More on GTA 6", "items": [{"title": "...", "url": "https://movieweb.com/..."}]}`
  - Only `https://movieweb.com/` URLs are shown, at most 3, and never a link to the page the widget is on
  - Empty `items` = no links block
