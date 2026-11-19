# GTA 6 widgets for MovieWeb

## 1. Contents

- `widgets/` — CMS-ready embeds, three fields each (`html.html`, `css.html`, `js.html`)
  - `00-mega/` — all three widgets in one embed
  - `01-sales-tracker/` — live sales tracker
  - `02-copies-chart/` — GTA 6 vs. best-selling games (copies), Launch / All time
  - `03-revenue-chart/` — GTA 6 vs. biggest entertainment releases (revenue), Launch / All time
- `preview/` — open `preview/index.html` in a browser; runs offline on bundled seed data; `?theme=light` for light mode
- `data/` — `tracker.json` (Sensor Tower readings), `comparisons.json` (chart data, hand-edited)
- `src/` — the shared JS and CSS the fields are built from
- `scraper/` + `.github/workflows/update-data.yml` — data pipeline scaffold
- Mockup: https://claude.ai/artifact/DeAKyPU5KpqVKpYdYa6Wg2

## 2. Installing an embed

- Paste each widget's three files into the CMS's HTML, CSS and JS fields
- CSS and JS are identical across all four widgets
  - Several widgets on one page: pasting the same CSS/JS more than once is harmless (mount guard + one global)
  - Mega and separate widgets can sit on the same page
- Before use, replace `data-src` in `html.html` with the real data URL (must be `https://`, ending in `/data/`)
  - Result: until replaced, the widget stays hidden and logs a console warning
- Widgets start hidden and only appear once data loads and validates
  - Result: a failed fetch or bad JSON never shows a broken box

## 3. Behaviour

- Live counter = latest reading + (rate between the last two readings × time since the latest reading)
  - Capped at 36 hours past the latest reading, then shows "Awaiting next update"
  - Re-fetches data every 5 minutes; a new reading snaps the counter to it
  - Ticks only while the widget is on screen and the tab is visible
- `official` in `tracker.json` (`{"date","units","revenue"}`) overrides the estimate: badge changes to "Official", counter stops ticking
- Comparison charts: top 10, sorted on render; GTA 6 pinned below with its rank if it falls outside
  - Copies all-time uses a fixed `pinRank` of "50+"
- Theme follows `prefers-color-scheme`; force with `data-theme="light"` or `data-theme="dark"` on the root div
- Narrow layout via container query at 600px, so it adapts to the column, not the window
- Exception to the design system's "freeze what an article shows" rule: these widgets are intentionally live

## 4. Tracking

- `window.websiteSentinel.sendEvent(category, action, label)`, retried 20 × 250ms, then dropped
- Categories: `GTA 6 Sales Tracker`, `GTA 6 Copies Chart`, `GTA 6 Revenue Chart` (mega sends each panel under its own category)
- Actions: `Impression` (once, 50% visible), `Platform Switch`, `Toggle`, `Link Click`

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
- Validates before writing: positive integers, $60–$120 per copy, PS5 + Xbox within 1% of total, never lower than the previous reading, no jump over 50%
  - Result: on failure nothing is written and the last good file stays live
- Workflow runs every 30 minutes, commits `data/` only when it changes
- Optional Slack alert on failure: add repo secret `SLACK_WEBHOOK_URL`

## 7. Updating comparison data

- Edit `data/comparisons.json` directly; no rebuild needed
- GTA 6 rows use `"live": true` instead of `amt`
- `film: true` = grey bar; `plus: true` = value shown with "+"
- Check weekly: Spider-Man: Brand New Day (still in release), Minecraft and GTA 5 lifetime units
- GTA 5 lifetime revenue is a 2018 analyst estimate ($6B); replace when a current figure is available
