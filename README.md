# GTA VI widgets for MovieWeb

Built to the MovieWeb Vignette Style guide (`../index.html`). Exceptions are listed in section 9.

## 1. Contents

- `widgets/` — CMS-ready embeds, three fields each (`html.html`, `css.html`, `js.html`)
  - `00-mega/` — all three in one box: each part on its own shaded panel, one Copy link and More link at the bottom
  - `01-sales-tracker/` — live sales tracker
  - `02-copies-chart/` — GTA VI vs. best-selling games (copies), Launch / All time
  - `03-revenue-chart/` — GTA VI vs. biggest entertainment releases (revenue), Launch / All time
- `preview/` — open `preview/index.html` in a browser; runs offline on bundled seed data; `?theme=light` for light mode
  - `preview/showcase.html` — one self-contained file to click through all four (theme and phone-width switches); live data online, snapshot offline
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
  - A widget inserted later (e.g. infinite scroll) mounts by itself
- `data-src` in `html.html` is the data URL (must be `https://`, ending in `/data/`)
- The HTML field holds a static frame: each panel's heading plus a skeleton at the finished height
  - Shows before the script runs and in CMS previews; nothing on the page moves when data arrives
  - Measured on a live MovieWeb article (site fonts): matches the finished widget to 0px on desktop (760px column) and phone (358px)
  - Heights are tuned to the current content; see `tools/build.py` to re-measure after changes
- If data fails to load or validate, the widget hides itself and logs a console warning
  - Add `?gta6debug=1` to the page URL: a one-line note instead of hiding, and the build stamp on working widgets
- Embeds pasted before v1.2 still work, without the static frame

## 3. Behaviour

- Live counter = latest reading + (rate between the last two readings × time since the latest reading)
  - Re-fetches data every 5 minutes; a new reading snaps the counter to it
  - Ticks only while the widget is on screen and the tab is visible
  - "Pause live count" button stops it; readers with reduced motion switched on get one update a minute
- Stale data: 36 hours after the latest reading the widget stops projecting
  - Shows the latest real reading, badge "Latest reading", "Awaiting next update"; charts label GTA VI "Latest reading"
  - Result: a stalled feed never leaves an inflated number on screen
- Official figure: shown beside the estimate in an "Official vs. estimate" block; it never replaces the estimate (section 8)
- Tracker order: platform buttons, revenue/copies, platform split, then "Show sales by day"
- "Show sales by day": full-width outline button; opens Day · Copies · Revenue · Change (up to 14 days, newest first)
  - Copies and revenue added that day; Change = that day's copies against the day before (green ▲, red ▼, = for no change)
  - Only days with a one-day step in the history (daily from Nov 9; earlier history is in two-day steps)
  - Follows the platform buttons; the release day carries a Launch tag
- Comparison charts: top 10, sorted on render; GTA VI pinned below with its rank if it falls outside
  - Copies all-time uses a fixed `pinRank` of "50+"
  - Line under each chart: what GTA VI last passed and what's next, with the gap and an estimate at the current pace
    - Hidden in the next-target part when GTA VI sits behind a fixed `pinRank` (the entries in between aren't listed)
    - No pace estimate when data is stale or the target is more than 14 days away
- Launch view: GTA VI shows "Pre-orders + sales to date" until the history reaches the end of its first 3 days
  - Then it switches to a fixed "First 3 days" figure, comparable with the other first-3-day entries (section 7)
- "Copy link" button on every widget (once in the mega, linking to its top): copies a link straight to it (no share sheet)
  - Links end `#gta6-sales-tracker`, `#gta6-copies-chart` or `#gta6-revenue-chart` (`-2` etc. for repeats, in page order)
  - Opening a shared link scrolls to that panel once it has loaded
- "More on GTA VI" link at the bottom of the tracker (or the mega's last panel): the `title` text from `data/links.json`, linking to the first item's URL, in a new tab
- No source credit lines are shown; the `sources` lists in `comparisons.json` are kept for the record only
- Site styles can't reach inside: the CSS resets article styles, and `tools/build.py` doubles the root class on every rule
  (`.mw-gta6.mw-gta6 …`) so it outranks rules such as `.article-body table th` without `!important`
- Theme follows `prefers-color-scheme`; force with `data-theme="light"` or `data-theme="dark"` on the root div
- Narrow layout via container query at 600px, so it adapts to the column, not the window
  - Tables fit a 320px column; the date column stays pinned and gets a soft edge if a table has to scroll

## 4. Tracking

- `window.websiteSentinel.sendEvent(category, action, label)`, retried 20 × 250ms, then dropped; at most 50 events per page
- Categories: `GTA VI Sales Tracker Vignette`, `GTA VI Copies Chart Vignette`, `GTA VI Revenue Chart Vignette` (mega sends each panel under its own)
- Actions (snake_case) and labels (slugs, never reader data or URLs):
  - `load`, `view` (once, 50% visible): label = panel (`tracker`, `copies`, `revenue`)
  - `tab_switch`: `all`, `ps5`, `xbox` · `period_switch`: `launch`, `all-time`
  - `pause` / `resume`: `live-count` · `by_day_open` / `by_day_close`: `sales-by-day`
  - `share`: `native` / `copy` · `link_click`: link text as a slug (related links always under the Sales Tracker category)

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
- Workflow runs at :17 and :47 past each hour (GitHub runs schedules best-effort; :00 and :30 are often delayed), commits `data/` only when it changes

## 7. Updating comparison data

- Edit `data/comparisons.json` directly; no rebuild needed
- `"gta6": {"release": "YYYY-MM-DD", "launchDays": 3}` — GTA VI's release date and launch window
  - Drives the Launch view's like-for-like figure, the history chart's Launch marker and the scraper's launch jump limit
  - Set to 2026-11-19; correct it here if the date changes
- GTA VI rows use `"live": true` instead of `amt`; their `sub` label is set by the widget (pre-orders, first 3 days, est. to date, latest reading)
  - Don't mention GTA VI's state in a Launch view's `note`: the widget adds that sentence
- `film: true` = grey bar; `plus: true` = value shown with "+"
- Check weekly: Spider-Man: Brand New Day (still in release), Minecraft and GTA 5 lifetime units
- `est: true` = an outside estimate, not a publisher figure: the value gets an asterisk and the view's `note` must explain it
  - Revenue all-time: GTA 5 ($9.5B+, as of May 2025), Minecraft ($4.2B, game sales), Red Dead Redemption 2 ($3.3B+, from unit sales)
  - Replace with publisher figures if any are ever disclosed

## 8. Official figures and related links

- Official figure: add `official` to `data/tracker.json` (the scraper keeps it)
  - `{"date": "YYYY-MM-DD", "units": 25000000, "source": "Take-Two", "note": "Sell-in, all formats."}`
  - `source` is shown as a plain-text credit (no link)
  - `revenue` is optional; Take-Two usually reports units only
  - Shown beside the estimate reading on or before that date; the live estimate keeps running
  - Edit right after a scraper commit, or pull first: the bot commits to the same file
- Related links: `data/links.json`
  - `{"title": "More on GTA VI", "items": [{"title": "...", "url": "https://movieweb.com/..."}]}`
  - Only `https://movieweb.com/` URLs count, never a link to the page the widget is on; the first valid one is used
  - Empty `items` = no links block

## 9. Style guide exceptions

- Live, exact counter: the guide prefers abbreviated estimates and freezing what an article shows; the tracker
  intentionally counts live in full figures (decided Nov 19, 2026)
- Launch / All time is a plain switch, not the guide's flip card
- One namespaced global (`window.MWGTA6`) so repeated pastes don't run twice; everything else is inside the IIFE
- Highlighted-row rank in light mode is #b81a21, a shade darker than the guide's #c81e25, which only reaches 4.46:1 on the pink row
- Highlighted-row dates use the heading grey (#555555) in light mode: muted grey fails contrast there (4.15:1)
- Table cells are 17px (15px at 600px and below), larger than the guide's 15px body, at the editor's request
