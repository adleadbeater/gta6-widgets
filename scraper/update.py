"""Scheduled update. Loads Sensor Tower's tracker page, extracts the latest
reading plus the daily history series, validates them and writes
data/tracker.json. Run by .github/workflows/update-data.yml every 30 minutes.

Exit codes: 0 = no change or updated, 1 = failure (nothing is written and the
last good data file stays in place).
"""
import json
import os
import re
import sys
from datetime import date as Date, datetime, timedelta, timezone

from playwright.sync_api import sync_playwright

URL = "https://sensortower.com/grand-theft-auto-VI/sales-tracker"
HERE = os.path.dirname(__file__)
DATA = os.path.join(HERE, "..", "data", "tracker.json")
COMPARISONS = os.path.join(HERE, "..", "data", "comparisons.json")
MAX_READINGS = 30
SERIES_FIELDS = ["date", "ps5Units", "xboxUnits", "ps5Revenue", "xboxRevenue"]

# Readings may not jump more than this since the previous one...
MAX_JUMP = 1.5
# ...except around release, when day-one sales can more than double the
# pre-order total (README section 6).
LAUNCH_MAX_JUMP = 3.0
LAUNCH_WINDOW = (-3, 14)  # days relative to the release date in comparisons.json


def extract(page, responses):
    """Return the latest reading as:
    {
      "date": "YYYY-MM-DD",            # Sensor Tower's "Last updated" date
      "units": int, "revenue": int,     # totals, revenue in USD
      "platforms": {
        "ps5": {"units": int, "revenue": int},
        "xbox": {"units": int, "revenue": int}
      },
      "series": [[date, ps5Units, xboxUnits, ps5Revenue, xboxRevenue], ...]
    }
    `series` is Sensor Tower's daily cumulative chart, oldest first. Its dates
    are data dates, which run about two days behind "Last updated".

    Source: the tracker is an Infogram embed (iframe on e.infogram.com). It
    makes no JSON request; its data is inlined as `window.infographicData`,
    which we read from the iframe. See README section 6.
    """
    frame = next((f for f in page.frames if "infogram.com" in f.url), None)
    if frame is None:
        raise RuntimeError("Infogram iframe not found on the tracker page")
    data = frame.evaluate("() => window.infographicData || null")
    if not data:
        raise RuntimeError("window.infographicData missing in the Infogram iframe")
    entities = list(data["elements"]["content"]["content"]["entities"].values())

    # Two CHART entities with header [date, Xbox, Playstation]: units (millions) and revenue ($ millions)
    tables = []
    for e in entities:
        if e.get("type") != "CHART":
            continue
        rows = [[c.get("value", "") for c in r] for r in e["props"]["chartData"]["data"][0]]
        head = [h.lower() for h in rows[0]]
        if head[0] != "date" or not any("xbox" in h for h in head) or not any("playstation" in h for h in head):
            continue
        xi = next(i for i, h in enumerate(head) if "xbox" in h)
        pi = next(i for i, h in enumerate(head) if "playstation" in h)
        by_date = {}
        for r in rows[1:]:
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(r[0]).strip()):
                continue
            by_date[r[0].strip()] = (round(_num(r[pi]) * 1e6), round(_num(r[xi]) * 1e6))
        if not by_date:
            continue
        tables.append(by_date)
    if len(tables) != 2:
        raise RuntimeError(f"expected 2 Xbox/Playstation chart tables, found {len(tables)}")
    last = [max(t) for t in tables]
    if last[0] != last[1]:
        raise RuntimeError("units and revenue charts end on different dates")
    # Revenue per copy is ~$100, so the revenue table is the one with the larger values
    units_t, rev_t = sorted(tables, key=lambda t: sum(t[last[0]]))

    texts = [" ".join(b.get("text", "") for b in e.get("props", {}).get("content", {}).get("blocks", []))
             .strip() for e in entities if e.get("type") == "TEXT"]
    m = re.search(r"Last updated\s+([A-Z][a-z]+ \d{1,2}, \d{4})", " ".join(texts))
    if not m:
        raise RuntimeError('"Last updated <date>" text not found')
    date = datetime.strptime(m.group(1), "%B %d, %Y").strftime("%Y-%m-%d")

    ps_u, xb_u = units_t[last[0]]
    ps_r, xb_r = rev_t[last[0]]
    units, revenue = ps_u + xb_u, ps_r + xb_r

    # Cross-check against the headline tiles (largest "N.NNM" and largest "$N.NNB/M")
    tile_units, tile_rev = [], []
    for t in texts:
        tm = re.fullmatch(r"(\$?)([\d.,]+)\s*([MB])", t)
        if tm:
            v = _num(tm.group(2)) * (1e9 if tm.group(3) == "B" else 1e6)
            (tile_rev if tm.group(1) else tile_units).append(v)
    if not tile_units or not tile_rev:
        raise RuntimeError("headline units/revenue tiles not found")
    for name, chart_v, tile_v in (("units", units, max(tile_units)), ("revenue", revenue, max(tile_rev))):
        if abs(chart_v - tile_v) > tile_v * 0.01:
            raise RuntimeError(f"{name}: chart total {chart_v} disagrees with headline tile {tile_v:.0f}")

    series = [[d, *units_t[d], *rev_t[d]] for d in sorted(set(units_t) & set(rev_t))]
    return {
        "date": date,
        "units": units,
        "revenue": revenue,
        "platforms": {
            "ps5": {"units": ps_u, "revenue": ps_r},
            "xbox": {"units": xb_u, "revenue": xb_r},
        },
        "series": series,
    }


def _num(s):
    return float(str(s).replace(",", "").replace("$", "").strip() or "nan")


def release_date():
    """GTA VI release date from data/comparisons.json ("gta6": {"release": "YYYY-MM-DD"}), or None."""
    try:
        with open(COMPARISONS, encoding="utf-8") as f:
            return Date.fromisoformat(json.load(f)["gta6"]["release"])
    except Exception:
        return None


def max_jump(reading_date):
    rel = release_date()
    if rel:
        d = Date.fromisoformat(reading_date)
        if rel + timedelta(days=LAUNCH_WINDOW[0]) <= d <= rel + timedelta(days=LAUNCH_WINDOW[1]):
            return LAUNCH_MAX_JUMP
    return MAX_JUMP


def validate(new, prev):
    errors = []
    for k in ("units", "revenue"):
        if not isinstance(new.get(k), int) or new[k] <= 0:
            errors.append(f"{k} missing or not a positive integer")
    if errors:
        return errors
    try:
        datetime.strptime(new["date"], "%Y-%m-%d")
    except Exception:
        return ["date is not YYYY-MM-DD"]
    per_copy = new["revenue"] / new["units"]
    if not 60 <= per_copy <= 120:
        errors.append(f"revenue per copy ${per_copy:.2f} outside $60-$120")
    p = new.get("platforms")
    if p:
        try:
            s = p["ps5"]["units"] + p["xbox"]["units"]
            if abs(s - new["units"]) > new["units"] * 0.01:
                errors.append("PS5 + Xbox units differ from total by more than 1%")
        except Exception:
            errors.append("platforms block malformed")
    if prev:
        if new["units"] < prev["units"] or new["revenue"] < prev["revenue"]:
            errors.append("new reading is lower than the previous reading")
        limit = max_jump(new["date"])
        if new["units"] > prev["units"] * limit:
            errors.append(f"units jumped more than {round((limit - 1) * 100)}% since the previous reading")
    return errors


def validate_series(rows, latest):
    """The history must be dated, ascending, non-negative and end on the reading's totals."""
    if not isinstance(rows, list) or len(rows) < 2:
        return ["series has fewer than 2 rows"]
    prev_d = ""
    for r in rows:
        if len(r) != 5 or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(r[0])) or r[0] <= prev_d:
            return [f"series row malformed or out of order: {r!r}"]
        if not all(isinstance(v, int) and v >= 0 for v in r[1:]):
            return [f"series row has a negative or non-integer value: {r!r}"]
        prev_d = r[0]
    end = rows[-1]
    if end[1] + end[2] != latest["units"] or end[3] + end[4] != latest["revenue"]:
        return ["series does not end on the reading's totals"]
    return []


def main():
    with open(DATA, encoding="utf-8") as f:
        data = json.load(f)
    before = json.dumps(data, sort_keys=True)
    readings = data.get("readings", [])
    prev = readings[0] if readings else None

    responses = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(user_agent="Mozilla/5.0 (compatible; MW-GTA6-Tracker/1.0)")

        def on_response(resp):
            if "json" in resp.headers.get("content-type", ""):
                try:
                    responses.append({"url": resp.url, "status": resp.status, "json": resp.json()})
                except Exception:
                    pass

        page.on("response", on_response)
        page.goto(URL, wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(3000)
        new = extract(page, responses)
        browser.close()

    series = new.pop("series", None)
    unchanged = prev and new["units"] == prev["units"] and new["revenue"] == prev["revenue"]

    if not unchanged:
        # Same date as the latest reading = Sensor Tower revised that day's figure:
        # replace it (keeping its original capture time) and validate against the
        # reading before it, rather than stacking two readings for one date.
        same_day = bool(prev) and new["date"] == prev["date"]
        baseline = (readings[1] if len(readings) > 1 else None) if same_day else prev
        errors = validate(new, baseline)
        if errors:
            print("Validation failed, nothing written:", "; ".join(errors), file=sys.stderr)
            return 1
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        at = (prev.get("at") or now) if same_day else now
        new = {"date": new["date"], "at": at, **{k: v for k, v in new.items() if k != "date"}}
        rest = readings[1:MAX_READINGS] if same_day else readings[: MAX_READINGS - 1]
        data["readings"] = [new] + rest
        print("Revised:" if same_day else "Updated:", new["date"], new["units"], new["revenue"])

    # The history series is optional for the widgets: a bad one is skipped, never blocks the reading
    s_errors = validate_series(series, data["readings"][0])
    if s_errors:
        print("Series skipped, keeping the previous one:", "; ".join(s_errors), file=sys.stderr)
    else:
        data["series"] = {"fields": SERIES_FIELDS, "rows": series}

    if json.dumps(data, sort_keys=True) == before:
        print("No change since", prev["date"] if prev else "-")
        return 0

    text = json.dumps(data, indent=2, ensure_ascii=False)
    # One line per series row keeps the daily commit diffs readable
    text = re.sub(r'\[\s+("\d{4}-\d{2}-\d{2}",[\d,\s]+?)\s+\]',
                  lambda m: "[" + re.sub(r",\s+", ", ", m.group(1)) + "]", text)
    tmp = DATA + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text + "\n")
    os.replace(tmp, DATA)
    if unchanged:
        print("Series updated; latest reading unchanged since", prev["date"])
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print("Update failed:", e, file=sys.stderr)
        sys.exit(1)
