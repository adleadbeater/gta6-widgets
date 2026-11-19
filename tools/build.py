"""Rebuild widgets/ and preview/ from src/ and data/.

    python3 tools/build.py

- widgets/*/css.html and js.html: src/mw-gta6.css and src/mw-gta6.js wrapped in
  <style> / <script>, identical across all four widgets
- widgets/*/html.html: the root div pointing at DATA_SRC
- preview/*.html: the same CSS and JS inlined, with data/*.json as the offline seed
"""
import json
import os
import re

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DATA_SRC = "https://adleadbeater.github.io/gta6-widgets/data/"
WIDGETS = {"00-mega": "mega", "01-sales-tracker": "tracker", "02-copies-chart": "copies", "03-revenue-chart": "revenue"}
# Previews only: example related links so the "More on GTA 6" block can be seen offline
PREVIEW_LINKS = [
    {"title": "Example related article (edit data/links.json)", "url": "https://movieweb.com/"},
    {"title": "Another example article", "url": "https://movieweb.com/"},
]


def read(*p):
    with open(os.path.join(ROOT, *p), encoding="utf-8") as f:
        return f.read()


def write(text, *p):
    path = os.path.join(ROOT, *p)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return os.path.relpath(path, ROOT)


def main():
    css, js = read("src", "mw-gta6.css"), read("src", "mw-gta6.js")
    css_field, js_field = "<style>\n" + css + "</style>\n", "<script>\n" + js + "</script>\n"
    out = []
    for folder, kind in WIDGETS.items():
        out.append(write(css_field, "widgets", folder, "css.html"))
        out.append(write(js_field, "widgets", folder, "js.html"))
        out.append(write(f'<div class="mw-gta6" data-widget="{kind}" data-src="{DATA_SRC}"></div>\n',
                         "widgets", folder, "html.html"))

    links = json.loads(read("data", "links.json"))
    if not links.get("items"):
        links = dict(links, items=PREVIEW_LINKS)
    seed = {
        "tracker": json.loads(read("data", "tracker.json")),
        "comparisons": json.loads(read("data", "comparisons.json")),
        "links": links,
    }
    seed_js = "<script>window.MWGTA6_SEED = " + json.dumps(seed, ensure_ascii=True).replace("</", "<\\/") + ";</script>"

    for name in sorted(os.listdir(os.path.join(ROOT, "preview"))):
        if not name.endswith(".html") or name == "index.html":
            continue
        page = read("preview", name)
        n_seed = n_css = n_js = 0
        page, n_seed = re.subn(r"<script>window\.MWGTA6_SEED = .*?;</script>", lambda m: seed_js, page, flags=re.S)
        page, n_css = re.subn(r"<style>\n\.mw-gta6 \{.*?</style>\n", lambda m: css_field, page, count=1, flags=re.S)
        page, n_js = re.subn(r"<script>\n\(function \(\) \{\n  'use strict';.*?</script>\n", lambda m: js_field, page, count=1, flags=re.S)
        page = re.sub(r'(<div class="mw-gta6" data-widget="[a-z]+" data-src="")\s+hidden>', r"\1>", page)
        if (n_seed, n_css, n_js) != (1, 1, 1):
            raise SystemExit(f"preview/{name}: expected one seed, CSS and JS block, found {n_seed}, {n_css}, {n_js}")
        out.append(write(page, "preview", name))
    print("Built:\n  " + "\n  ".join(out))


if __name__ == "__main__":
    main()
