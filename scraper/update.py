"""Step 2: scheduled update. Loads the tracker page, extracts the latest
reading, validates it and writes data/tracker.json. Run by
.github/workflows/update-data.yml every 30 minutes.

extract() must be completed after running scraper/discover.py: Sensor
Tower's data endpoint/selectors are not known until then.

Exit codes: 0 = no change or updated, 1 = failure (the workflow alerts Slack
and the last good data file stays in place).
"""
import json
import os
import re
import sys
from datetime import datetime, timezone

from playwright.sync_api import sync_playwright

URL = "https://sensortower.com/grand-theft-auto-VI/sales-tracker"
DATA = os.path.join(os.path.dirname(__file__), "..", "data", "tracker.json")
MAX_READINGS = 30


def extract(page, responses):
    """Return the latest reading as:
    {
      "date": "YYYY-MM-DD",            # the date Sensor Tower shows for the reading
      "units": int, "revenue": int,     # totals, revenue in USD
      "platforms": {                    # optional
        "ps5": {"units": int, "revenue": int},
        "xbox": {"units": int, "revenue": int}
      }
    }
    `responses` is a list of {"url", "status", "json"} for every JSON
    response the page loaded. Prefer parsing the data response over the DOM.

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
    entities = data["elements"]["content"]["content"]["entities"].values()

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
        last = max(rows[1:], key=lambda r: r[0])
        xbox, ps = _num(last[xi]) * 1e6, _num(last[pi]) * 1e6
        tables.append({"date": last[0], "xbox": round(xbox), "ps5": round(ps)})
    if len(tables) != 2:
        raise RuntimeError(f"expected 2 Xbox/Playstation chart tables, found {len(tables)}")
    if tables[0]["date"] != tables[1]["date"]:
        raise RuntimeError("units and revenue charts end on different dates")
    # Revenue per copy is ~$100, so the revenue table is the one with the larger values
    units_t, rev_t = sorted(tables, key=lambda t: t["xbox"] + t["ps5"])

    texts = [" ".join(b.get("text", "") for b in e.get("props", {}).get("content", {}).get("blocks", []))
             .strip() for e in entities if e.get("type") == "TEXT"]
    joined = " ".join(texts)
    m = re.search(r"Last updated\s+([A-Z][a-z]+ \d{1,2}, \d{4})", joined)
    if not m:
        raise RuntimeError('"Last updated <date>" text not found')
    date = datetime.strptime(m.group(1), "%B %d, %Y").strftime("%Y-%m-%d")

    units = units_t["xbox"] + units_t["ps5"]
    revenue = rev_t["xbox"] + rev_t["ps5"]

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

    return {
        "date": date,
        "units": units,
        "revenue": revenue,
        "platforms": {
            "ps5": {"units": units_t["ps5"], "revenue": rev_t["ps5"]},
            "xbox": {"units": units_t["xbox"], "revenue": rev_t["xbox"]},
        },
    }


def _num(s):
    return float(str(s).replace(",", "").replace("$", "").strip())


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
        errors.append("date is not YYYY-MM-DD")
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
        if new["units"] > prev["units"] * 1.5:
            errors.append("units jumped more than 50% since the previous reading")
    return errors


def main():
    with open(DATA, encoding="utf-8") as f:
        data = json.load(f)
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

    if prev and new["units"] == prev["units"] and new["revenue"] == prev["revenue"]:
        print("No change since", prev["date"])
        return 0

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
    tmp = DATA + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, DATA)
    print("Revised:" if same_day else "Updated:", new["date"], new["units"], new["revenue"])
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print("Update failed:", e, file=sys.stderr)
        sys.exit(1)
