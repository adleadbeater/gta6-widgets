"""Rebuild widgets/ and preview/ from src/ and data/.

    python3 tools/build.py

- widgets/*/css.html and js.html: src/mw-gta6.css and src/mw-gta6.js wrapped in
  <style> / <script>, identical across all four widgets
- widgets/*/html.html: the root div pointing at DATA_SRC, holding the static frame
  (heading + skeleton) that shows before the script runs and in CMS previews
- preview/*.html: the same CSS and JS inlined, with data/*.json as the offline seed

Fails if the JS breaks the Emaki field rules (style guide, "Building for Emaki").

Frame heights (.mw-gta6__skel--* in src/mw-gta6.css) = finished panel height minus 64px
(minus 60px at 600px and below). Re-measure them after a change that alters a panel's
height, e.g. adding related links: each extra link adds 42px to the panel that shows them.
"""
import hashlib
import html
import json
import os
import re
from datetime import datetime, timezone

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DATA_SRC = "https://adleadbeater.github.io/gta6-widgets/data/"
WIDGETS = {"00-mega": "mega", "01-sales-tracker": "tracker", "02-copies-chart": "copies", "03-revenue-chart": "revenue"}
# Previews only: example related links so the "More on GTA VI" block can be seen offline
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


EMAKI_FORBIDDEN = ["[[", "]]", "{{", "{%", "<!--", "</script", "`"]


def emaki_check(js):
    """Emaki drops a JS field containing these, or non-ASCII; comments included."""
    problems = []
    for n, line in enumerate(js.splitlines(), 1):
        for bad in EMAKI_FORBIDDEN:
            if bad in line:
                problems.append(f"line {n}: contains {bad!r}")
        if any(ord(c) > 127 for c in line):
            problems.append(f"line {n}: non-ASCII character (write it as a \\u escape)")
    if problems:
        raise SystemExit("src/mw-gta6.js breaks the Emaki JS rules:\n  " + "\n  ".join(problems))


def harden(css):
    """Prefix every rule with a doubled root class (.mw-gta6.mw-gta6 ...), so the widget's rules
    outrank article styles such as `.article-body table th` without !important."""
    def fix(sel):
        sel = sel.strip()
        if sel.startswith(".mw-gta6__"):
            return ".mw-gta6.mw-gta6 " + sel
        if sel.startswith(".mw-gta6"):
            return ".mw-gta6.mw-gta6" + sel[len(".mw-gta6"):]
        return sel

    def prelude(m):
        lead, sels = m.group(1), m.group(2)
        if sels.lstrip().startswith(("@", "from", "to")) or sels.strip().endswith("%"):
            return m.group(0)
        parts, depth, cur = [], 0, ""
        for ch in sels:  # split on top-level commas only, not those inside :is(...)
            depth += (ch == "(") - (ch == ")")
            if ch == "," and depth == 0:
                parts.append(cur); cur = ""
            else:
                cur += ch
        parts.append(cur)
        return lead + ",\n".join(fix(x) for x in parts) + " {"

    # a comment is matched up to its own first */ only, so it can never swallow the rules after it
    out = re.sub(r"((?:^|[{}])\s*(?:/\*(?:[^*]|\*(?!/))*\*/\s*)*)([^\s{}@/][^{}]*?)\s*\{", prelude, css, flags=re.S)
    check_hardened(out)
    return out


def check_hardened(css):
    """Every selector must carry the doubled root class, or article styles can win again."""
    body = re.sub(r"/\*(?:[^*]|\*(?!/))*\*/", "", css)
    bad = []
    for m in re.finditer(r"([^{};]+)\{", body):
        pre = m.group(1).strip()
        if not pre or pre.startswith("@") or re.fullmatch(r"(from|to|\d+%)(\s*,\s*(from|to|\d+%))*", pre):
            continue
        parts, depth, cur = [], 0, ""
        for ch in pre:
            depth += (ch == "(") - (ch == ")")
            if ch == "," and depth == 0:
                parts.append(cur); cur = ""
            else:
                cur += ch
        parts.append(cur)
        bad += [x.strip() for x in parts if x.strip() and not x.strip().startswith(".mw-gta6.mw-gta6")]
    if bad:
        raise SystemExit("CSS rules not hardened (article styles could override them):\n  " + "\n  ".join(bad))


def frame(kind, titles, src):
    """Static frame: one panel per part, heading + skeleton at the finished height."""
    parts = ["tracker", "copies", "revenue"] if kind == "mega" else [kind]
    inner = "".join(
        f'<section class="mw-gta6__panel"><div class="mw-gta6__head"><h2 class="mw-gta6__h">{html.escape(titles[k])}</h2></div>'
        f'<div class="mw-gta6__skel mw-gta6__skel--{k}"></div></section>' for k in parts)
    return f'<div class="mw-gta6" data-widget="{kind}" data-src="{src}">{inner}</div>'


NAMES = {"00-mega": "Mega (all three)", "01-sales-tracker": "Sales tracker", "02-copies-chart": "Copies chart", "03-revenue-chart": "Revenue chart"}
PREVIEWS = {"00-mega": "mega", "01-sales-tracker": "sales-tracker", "02-copies-chart": "copies-chart", "03-revenue-chart": "revenue-chart"}


def copy_page(stamp):
    """widgets/index.html: every CMS field with a Copy button, for pasting into Emaki."""
    blocks = []
    for folder in WIDGETS:
        fields = []
        for name in ("html", "css", "js"):
            text = read("widgets", folder, f"{name}.html")
            fid = f"{folder}-{name}"
            fields.append(
                f'<div class="f"><div class="fh"><b>{name.upper()} field</b><span>{len(text):,} characters</span>'
                f'<button type="button" data-for="{fid}">Copy</button></div>'
                f'<textarea id="{fid}" readonly spellcheck="false">{html.escape(text)}</textarea></div>')
        view = f"../preview/{PREVIEWS[folder]}.html"
        blocks.append(f'<section><div class="sh"><h2>{NAMES[folder]}</h2><span class="v">View: <a href="{view}" target="_blank">Dark</a>'
                      f' \u00b7 <a href="{view}?theme=light" target="_blank">Light</a></span></div>{"".join(fields)}</section>')
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>GTA VI embed fields</title>
<style>
body{{margin:0;padding:24px 16px;background:#f2f2f2;color:#181818;font:15px/21px Roboto,Arial,sans-serif}}
main{{max-width:900px;margin:0 auto}} h1{{font:600 22px/28px Poppins,Arial,sans-serif;margin:0 0 4px}}
p{{margin:0 0 16px;color:#555}} section{{background:#fff;border-radius:4px;padding:16px;margin:0 0 16px}}
h2{{font:600 17px/22px Poppins,Arial,sans-serif;text-transform:uppercase;margin:0;color:#555}}
.sh{{display:flex;flex-wrap:wrap;align-items:baseline;justify-content:space-between;gap:4px 12px;margin:0 0 12px}} .v{{font-size:13px;color:#6b6b6b}}
a{{color:#c81e25;font-weight:500}} a:hover{{color:#181818}} a:focus-visible{{outline:2px solid #c81e25;outline-offset:2px}}
.links{{display:flex;flex-wrap:wrap;gap:6px 16px;margin:0 0 16px;font-size:15px}}
.f{{margin:0 0 12px}} .fh{{display:flex;align-items:center;gap:12px;margin:0 0 4px}} .fh span{{color:#6b6b6b;font-size:13px;flex:1}}
button{{font:600 11px/13px Poppins,Arial,sans-serif;text-transform:uppercase;padding:8px 14px;border:0;border-radius:2px;background:#de272e;color:#fff;cursor:pointer}}
button.done{{background:#0b5c2b}} button:focus-visible{{outline:2px solid #c81e25;outline-offset:2px}}
textarea{{width:100%;box-sizing:border-box;height:64px;font:12px/16px ui-monospace,Menlo,monospace;border:1px solid #e4e4e4;border-radius:2px;padding:6px;resize:vertical}}
</style></head><body><main>
<h1>GTA VI embed fields</h1>
<p>Build {stamp}. Paste each widget's HTML, CSS and JS into the matching Emaki field. CSS and JS are the same for all four widgets.</p>
<p class="links"><a href="../preview/index.html" target="_blank">All previews</a><a href="../preview/separate-embeds.html" target="_blank">Three separate embeds on one page</a><a href="../preview/mega.html?gta6debug=1" target="_blank">Mega with build stamp</a></p>
<p>Previews use the data bundled at build time, so they work offline; on the live site the widgets load the latest data.</p>
{"".join(blocks)}
</main>
<script>
document.addEventListener('click', function (ev) {{
  var b = ev.target.closest('button[data-for]'); if (!b) return;
  var t = document.getElementById(b.getAttribute('data-for'));
  function done() {{ b.textContent = 'Copied'; b.className = 'done'; setTimeout(function () {{ b.textContent = 'Copy'; b.className = ''; }}, 2000); }}
  if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(t.value).then(done, function () {{ t.select(); document.execCommand('copy'); done(); }});
  else {{ t.select(); document.execCommand('copy'); done(); }}
}});
</script></body></html>
"""


def showcase_page(css_field, js_field, seed_js, titles, stamp):
    """preview/showcase.html: one self-contained file to click through all four widgets.
    Loads live data from DATA_SRC; falls back to the bundled snapshot offline."""
    views = [("mega", "All-in-one"), ("tracker", "Sales tracker"), ("copies", "Copies chart"), ("revenue", "Revenue chart")]
    tabs = "".join(f'<button type="button" data-view="{k}" aria-pressed="{str(i == 0).lower()}">{n}</button>' for i, (k, n) in enumerate(views))
    panes = "".join(f'<div class="sc-pane" data-pane="{k}"{"" if i == 0 else " hidden"}>{frame(k, titles, DATA_SRC)}</div>' for i, (k, _) in enumerate(views))
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>GTA VI Vignettes Showcase</title>
<link href="https://fonts.googleapis.com/css2?family=Poppins:wght@500;600;700&family=Roboto:wght@400;500;700&display=swap" rel="stylesheet">
<style>
:root{{--page:#0a0a0a;--bar:#181818;--ink:#ffffff;--muted:#b0b0b0;--btn:#737373;--red:#de272e;--ring:#ff5a5f}}
body.light{{--page:#f2f2f2;--bar:#ffffff;--ink:#181818;--muted:#6b6b6b;--ring:#c81e25}}
body{{margin:0;background:var(--page);color:var(--ink);font:15px/21px Roboto,Arial,sans-serif;padding:0 max(16px,env(safe-area-inset-left,0px)) 48px}}
.sc-bar{{max-width:760px;margin:0 auto;padding:20px 0 4px;display:flex;flex-direction:column;gap:12px}}
.sc-bar h1{{margin:0;font:700 22px/28px Poppins,Arial,sans-serif;text-transform:uppercase}}
.sc-bar p{{margin:0;color:var(--muted);font-size:13px;line-height:18px}}
.sc-row{{display:flex;flex-wrap:wrap;gap:12px 20px;align-items:center}}
.sc-group{{display:flex;flex-wrap:wrap;gap:6px}}
.sc-group button{{min-height:36px;padding:6px 12px;border:0;border-radius:2px;background:var(--btn);color:#fff;font:600 11px/13px Poppins,Arial,sans-serif;text-transform:uppercase;cursor:pointer}}
.sc-group button[aria-pressed="true"]{{background:var(--red);box-shadow:0 0 0 2px var(--page),0 0 0 3px var(--red)}}
.sc-group button:focus-visible{{outline:2px solid var(--ring);outline-offset:4px}}
.sc-label{{font:600 11px/13px Poppins,Arial,sans-serif;text-transform:uppercase;color:var(--muted)}}
.sc-stage{{max-width:760px;margin:0 auto;transition:max-width .2s}}
body.phone .sc-stage{{max-width:358px}}
@media (prefers-reduced-motion: reduce){{.sc-stage{{transition:none}}}}
</style>
{seed_js}
</head><body>
<div class="sc-bar">
  <h1>GTA VI vignettes</h1>
  <p>Click through the four MovieWeb GTA VI vignettes. Live data when online; build {stamp}.</p>
  <div class="sc-row">
    <div class="sc-group" role="group" aria-label="Vignette">{tabs}</div>
  </div>
  <div class="sc-row">
    <span class="sc-label">Theme</span><div class="sc-group" role="group" aria-label="Theme"><button type="button" data-theme-set="dark" aria-pressed="true">Dark</button><button type="button" data-theme-set="light" aria-pressed="false">Light</button></div>
    <span class="sc-label">Width</span><div class="sc-group" role="group" aria-label="Width"><button type="button" data-width="desktop" aria-pressed="true">Desktop</button><button type="button" data-width="phone" aria-pressed="false">Phone</button></div>
  </div>
</div>
<div class="sc-stage">{panes}</div>
{css_field}{js_field}<script>
(function () {{
  function press(group, btn) {{ [].forEach.call(group.querySelectorAll('button'), function (b) {{ b.setAttribute('aria-pressed', b === btn ? 'true' : 'false'); }}); }}
  function show(view) {{
    [].forEach.call(document.querySelectorAll('.sc-pane'), function (p) {{ p.hidden = p.getAttribute('data-pane') !== view; }});
    var btn = document.querySelector('[data-view="' + view + '"]'); if (btn) press(btn.parentNode, btn);
  }}
  document.addEventListener('click', function (ev) {{
    var b = ev.target.closest ? ev.target.closest('.sc-group button') : null; if (!b) return;
    if (b.hasAttribute('data-view')) {{ show(b.getAttribute('data-view')); try {{ history.replaceState(null, '', '#' + b.getAttribute('data-view')); }} catch (e) {{}} return; }}
    press(b.parentNode, b);
    if (b.hasAttribute('data-theme-set')) {{
      var t = b.getAttribute('data-theme-set'); document.body.classList.toggle('light', t === 'light');
      [].forEach.call(document.querySelectorAll('.mw-gta6'), function (r) {{ r.setAttribute('data-theme', t); }});
    }}
    if (b.hasAttribute('data-width')) document.body.classList.toggle('phone', b.getAttribute('data-width') === 'phone');
  }});
  [].forEach.call(document.querySelectorAll('.mw-gta6'), function (r) {{ r.setAttribute('data-theme', 'dark'); }});
  var h = (location.hash || '').slice(1); if (/^(mega|tracker|copies|revenue)$/.test(h)) show(h);
}})();
</script>
</body></html>
"""


def main():
    css, js = read("src", "mw-gta6.css"), read("src", "mw-gta6.js")
    emaki_check(js)
    css = harden(css)
    version = re.search(r"version: '([^']+)'", js).group(1)
    stamp = f"{version}+{datetime.now(timezone.utc):%Y%m%d}.{hashlib.sha256((js + css).encode()).hexdigest()[:7]}"
    js = js.replace("var BUILD = 'dev';", f"var BUILD = '{stamp}';", 1)
    cmp = json.loads(read("data", "comparisons.json"))
    titles = {"tracker": "GTA VI Sales Tracker", "copies": cmp["copies"]["title"], "revenue": cmp["revenue"]["title"]}
    css_field, js_field = "<style>\n" + css + "</style>\n", "<script>\n" + js + "</script>\n"
    out = []
    for folder, kind in WIDGETS.items():
        out.append(write(css_field, "widgets", folder, "css.html"))
        out.append(write(js_field, "widgets", folder, "js.html"))
        out.append(write(frame(kind, titles, DATA_SRC) + "\n", "widgets", folder, "html.html"))

    out.append(write(copy_page(stamp), "widgets", "index.html"))

    links = json.loads(read("data", "links.json"))
    if not links.get("items"):
        links = dict(links, items=PREVIEW_LINKS)
    seed = {
        "tracker": json.loads(read("data", "tracker.json")),
        "comparisons": json.loads(read("data", "comparisons.json")),
        "links": links,
    }
    seed_js = "<script>window.MWGTA6_SEED = " + json.dumps(seed, ensure_ascii=True).replace("</", "<\\/") + ";</script>"

    out.append(write(showcase_page(css_field, js_field, seed_js, titles, stamp), "preview", "showcase.html"))

    for name in sorted(os.listdir(os.path.join(ROOT, "preview"))):
        if not name.endswith(".html") or name in ("index.html", "showcase.html"):
            continue
        page = read("preview", name)
        n_seed = n_css = n_js = 0
        page, n_seed = re.subn(r"<script>window\.MWGTA6_SEED = .*?;</script>", lambda m: seed_js, page, flags=re.S)
        page, n_css = re.subn(r"<style>\n\.mw-gta6(?:\.mw-gta6)? \{.*?</style>\n", lambda m: css_field, page, count=1, flags=re.S)
        page, n_js = re.subn(r"<script>\n\(function \(\) \{\n  'use strict';.*?</script>\n", lambda m: js_field, page, count=1, flags=re.S)
        page = re.sub(r'<div class="mw-gta6" data-widget="([a-z]+)" data-src=""[^>]*>(?:</div>|.*?</section></div>)',
                      lambda m: frame(m.group(1), titles, ""), page, flags=re.S)
        if (n_seed, n_css, n_js) != (1, 1, 1):
            raise SystemExit(f"preview/{name}: expected one seed, CSS and JS block, found {n_seed}, {n_css}, {n_js}")
        out.append(write(page, "preview", name))
    print(f"Build {stamp}:\n  " + "\n  ".join(out))


if __name__ == "__main__":
    main()
