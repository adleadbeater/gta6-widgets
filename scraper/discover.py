"""Step 1: find where Sensor Tower's tracker page gets its numbers.

Run locally once:
    pip install -r scraper/requirements.txt
    python -m playwright install chromium
    python scraper/discover.py

Writes discover-output/responses.json (every JSON response the page loads),
discover-output/page.txt (the rendered text) and discover-output/page.png.
Look for the response that holds units, revenue and the PS5/Xbox split, then
fill in extract() in scraper/update.py.
"""
import json
import os

from playwright.sync_api import sync_playwright

URL = "https://sensortower.com/grand-theft-auto-VI/sales-tracker"
OUT = "discover-output"


def main():
    os.makedirs(OUT, exist_ok=True)
    captured = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()

        def on_response(resp):
            ctype = resp.headers.get("content-type", "")
            if "json" not in ctype:
                return
            try:
                body = resp.text()
            except Exception:
                return
            captured.append({"url": resp.url, "status": resp.status, "body": body[:20000]})

        page.on("response", on_response)
        page.goto(URL, wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(3000)
        with open(os.path.join(OUT, "page.txt"), "w", encoding="utf-8") as f:
            f.write(page.inner_text("body"))
        page.screenshot(path=os.path.join(OUT, "page.png"), full_page=True)
        browser.close()

    with open(os.path.join(OUT, "responses.json"), "w", encoding="utf-8") as f:
        json.dump(captured, f, indent=2)

    hints = ("unit", "revenue", "ps5", "playstation", "xbox", "preorder", "pre_order")
    print(f"{len(captured)} JSON responses saved to {OUT}/responses.json")
    for c in captured:
        low = c["body"].lower()
        if any(h in low for h in hints):
            print("Likely data response:", c["status"], c["url"])


if __name__ == "__main__":
    main()
