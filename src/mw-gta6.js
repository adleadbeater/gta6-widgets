(function () {
  'use strict';

  var NS = 'MWGTA6';
  if (window[NS]) { window[NS].mountAll(); return; }

  var REFRESH_MS = 300000;
  var TICK_MS = 250;
  var CAP_SEC = 36 * 3600;
  var DOT = ' \u00b7 ';
  var DASH = '\u2014';
  var UP = '\u25b2';
  var MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  var CATS = { tracker: 'GTA 6 Sales Tracker', copies: 'GTA 6 Copies Chart', revenue: 'GTA 6 Revenue Chart' };
  var PLATFORMS = [
    { id: 'all', label: 'All platforms' },
    { id: 'ps5', label: 'PS5' },
    { id: 'xbox', label: 'Xbox Series X|S' }
  ];
  var MODES = [
    { id: 'launch', label: 'Launch' },
    { id: 'all', label: 'All time' }
  ];
  var ESC = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };

  var instances = [];
  var requests = {};

  /* ---------- helpers ---------- */

  function esc(v) {
    return String(v == null ? '' : v).replace(/[&<>"']/g, function (ch) { return ESC[ch]; });
  }

  function warn(msg, err) {
    if (window.console && console.warn) console.warn('[mw-gta6] ' + msg, err || '');
  }

  function track(cat, action, label) {
    var tries = 0;
    label = String(label || '').slice(0, 200);
    (function attempt() {
      var s = window.websiteSentinel;
      if (s && typeof s.sendEvent === 'function') {
        try { s.sendEvent(cat, action, label); } catch (e) { /* tracking must never break the widget */ }
        return;
      }
      tries += 1;
      if (tries < 20) setTimeout(attempt, 250);
    })();
  }

  function dateParts(iso) {
    var p = String(iso || '').slice(0, 10).split('-');
    var m = parseInt(p[1], 10) - 1;
    var d = parseInt(p[2], 10);
    if (!(m >= 0 && m < 12) || !d) return null;
    return { y: p[0], m: MONTHS[m], d: d };
  }
  function fmtDate(iso) { var p = dateParts(iso); return p ? p.m + ' ' + p.d + ', ' + p.y : DASH; }
  function fmtShort(iso) { var p = dateParts(iso); return p ? p.m + ' ' + p.d : DASH; }
  function whole(n) { return Math.floor(n).toLocaleString('en-US'); }
  function trim2(n) { return String(parseFloat(n.toFixed(2))); }
  function mUnits(n) { return trim2(n / 1e6) + 'M'; }
  function usd(n, plus) {
    var s = n >= 1e9 ? '$' + trim2(n / 1e9) + 'B' : '$' + Math.round(n / 1e6) + 'M';
    return plus ? s + '+' : s;
  }
  function time(r) { return Date.parse(r.at || r.date); }
  function isNum(v) { return typeof v === 'number' && isFinite(v) && v >= 0; }

  /* ---------- data ---------- */

  function fetchJSON(url) {
    var bucket = Math.floor(Date.now() / REFRESH_MS);
    var key = url + '|' + bucket;
    if (requests[key]) return requests[key];
    var ctrl = window.AbortController ? new AbortController() : null;
    var timer = ctrl ? setTimeout(function () { ctrl.abort(); }, 10000) : null;
    var href = url + (url.indexOf('?') < 0 ? '?' : '&') + 'v=' + bucket;
    requests[key] = fetch(href, { credentials: 'omit', signal: ctrl ? ctrl.signal : undefined })
      .then(function (r) {
        if (timer) clearTimeout(timer);
        if (!r.ok) throw new Error('HTTP ' + r.status + ' for ' + url);
        return r.json();
      })
      .catch(function (e) {
        if (timer) clearTimeout(timer);
        delete requests[key];
        throw e;
      });
    return requests[key];
  }

  function loadData(root, names) {
    var base = String(root.getAttribute('data-src') || '').trim();
    var seed = window.MWGTA6_SEED || null;
    if (base && !/^https:\/\//i.test(base)) return Promise.reject(new Error('data-src must be an https URL'));
    if (base && base.charAt(base.length - 1) !== '/') base += '/';
    return Promise.all(names.map(function (name) {
      if (!base) {
        return seed && seed[name] ? Promise.resolve(seed[name]) : Promise.reject(new Error('no data-src and no seed for ' + name));
      }
      return fetchJSON(base + name + '.json').catch(function (e) {
        if (seed && seed[name]) return seed[name];
        throw e;
      });
    }));
  }

  function validTracker(d) {
    if (!d || !Array.isArray(d.readings) || !d.readings.length) return false;
    for (var i = 0; i < d.readings.length; i++) {
      var r = d.readings[i];
      if (!r || !isNum(r.units) || !isNum(r.revenue) || !dateParts(r.date) || isNaN(time(r))) return false;
      if (r.platforms) {
        var p = r.platforms;
        if (!p.ps5 || !p.xbox || !isNum(p.ps5.units) || !isNum(p.xbox.units) || !isNum(p.ps5.revenue) || !isNum(p.xbox.revenue)) return false;
      }
    }
    return true;
  }

  function validComparisons(d) {
    if (!d) return false;
    return ['copies', 'revenue'].every(function (k) {
      var s = d[k];
      return s && s.title && ['launch', 'all'].every(function (m) {
        return s[m] && Array.isArray(s[m].items) && s[m].items.length && s[m].items.every(function (x) {
          return x && x.title && (x.live === true || isNum(x.amt));
        });
      });
    });
  }

  function model(t) {
    var rs = t.readings.slice().sort(function (a, b) { return time(b) - time(a); });
    var r0 = rs[0];
    var r1 = rs[1] || null;
    var uRate = 0;
    var rRate = 0;
    if (r1) {
      var dt = (time(r0) - time(r1)) / 1000;
      if (dt > 0) {
        uRate = Math.max(0, (r0.units - r1.units) / dt);
        rRate = Math.max(0, (r0.revenue - r1.revenue) / dt);
      }
    }
    var withP = rs.filter(function (r) { return !!r.platforms; });
    var off = t.official;
    var official = off && isNum(off.units) && isNum(off.revenue) && dateParts(off.date) && Date.parse(off.date) >= time(r0) ? off : null;
    return {
      rs: rs, r0: r0, r1: r1, t0: time(r0), uRate: uRate, rRate: rRate,
      p0: withP[0] || null, p1: withP[1] || null, official: official,
      sourceUrl: (t.source && /^https:\/\//.test(t.source.url)) ? t.source.url : 'https://sensortower.com/grand-theft-auto-VI/sales-tracker'
    };
  }

  function live(m, now) {
    if (m.official) return { units: m.official.units, revenue: m.official.revenue, stale: false, official: true };
    var dt = Math.max(0, (now - m.t0) / 1000);
    var stale = dt > CAP_SEC;
    if (stale) dt = CAP_SEC;
    return { units: m.r0.units + m.uRate * dt, revenue: m.r0.revenue + m.rRate * dt, stale: stale, official: false };
  }

  function forPlatform(m, L, key) {
    if (key === 'all' || !m.p0) return L;
    var p = m.p0.platforms[key];
    return { units: L.units * p.units / m.p0.units, revenue: L.revenue * p.revenue / m.p0.revenue };
  }

  /* ---------- tracker ---------- */

  function trackerHTML(st) {
    var m = st.m;
    var L = live(m, Date.now());
    var V = forPlatform(m, L, st.platform);
    var dU = null;
    var dR = null;
    var since = '';
    if (st.platform === 'all') {
      if (m.r1) { dU = m.r0.units - m.r1.units; dR = m.r0.revenue - m.r1.revenue; since = fmtShort(m.r1.date); }
    } else if (m.p0 && m.p1) {
      var a = m.p0.platforms[st.platform];
      var b = m.p1.platforms[st.platform];
      dU = a.units - b.units; dR = a.revenue - b.revenue; since = fmtShort(m.p1.date);
    }
    function change(v, f) {
      if (v === null) return '<div class="mw-gta6__chg">' + DASH + '</div>';
      return '<div class="mw-gta6__chg"><span class="mw-gta6__up" aria-hidden="true">' + UP + ' </span><strong>+' +
        esc(f(v)) + '</strong> since ' + esc(since) + '</div>';
    }
    var meta = L.official
      ? 'Official figure from Take-Two' + DOT + esc(fmtDate(m.official.date))
      : 'Worldwide digital sales on PS5 and Xbox Series X|S' + DOT + 'Latest Sensor Tower reading ' + esc(fmtDate(m.r0.date));

    var h = '';
    h += '<div class="mw-gta6__head"><h2 class="mw-gta6__h">GTA 6 Sales Tracker</h2>' +
      '<span class="mw-gta6__badge">' + (L.official ? 'Official' : 'Live estimate') + '</span></div>';
    h += '<p class="mw-gta6__meta">' + meta + '<span data-live="status">' + (L.stale ? DOT + 'Awaiting next update' : '') + '</span></p>';
    h += '<p class="mw-gta6__sr">As of the ' + esc(fmtDate(m.r0.date)) + ' reading: ' + esc(mUnits(m.r0.units)) +
      ' copies and ' + esc(usd(m.r0.revenue)) + ' in revenue.</p>';

    if (m.p0) {
      h += '<div class="mw-gta6__btns" role="group" aria-label="Platform">';
      PLATFORMS.forEach(function (p) {
        h += '<button type="button" class="mw-gta6__btn" data-platform="' + p.id + '" aria-pressed="' +
          (p.id === st.platform ? 'true' : 'false') + '">' + esc(p.label) + '</button>';
      });
      h += '</div>';
    }

    h += '<div class="mw-gta6__stats">';
    h += '<div class="mw-gta6__stat"><div class="mw-gta6__label">Revenue</div>' +
      '<div class="mw-gta6__num" data-live="rev" aria-live="off">$' + whole(V.revenue) + '</div>' + change(dR, usd) + '</div>';
    h += '<div class="mw-gta6__stat"><div class="mw-gta6__label">Copies sold</div>' +
      '<div class="mw-gta6__num" data-live="units" aria-live="off">' + whole(V.units) + '</div>' + change(dU, mUnits) + '</div>';
    h += '</div>';

    if (m.p0) {
      var ps = m.p0.platforms.ps5;
      var xb = m.p0.platforms.xbox;
      var share = ps.units / m.p0.units;
      var psPct = Math.round(share * 100);
      h += '<div class="mw-gta6__block"><div class="mw-gta6__label">Platform split</div>';
      h += '<div class="mw-gta6__split" role="img" aria-label="PS5 ' + psPct + ' percent, Xbox Series X|S ' + (100 - psPct) + ' percent">' +
        '<span style="width:' + (share * 100).toFixed(1) + '%"></span><span></span></div>';
      h += '<div class="mw-gta6__legend">' +
        '<div><span class="mw-gta6__sw" aria-hidden="true"></span><strong>PS5 ' + psPct + '%</strong> <span class="mw-gta6__muted">' +
        esc(mUnits(ps.units)) + ' copies' + DOT + esc(usd(ps.revenue)) + '</span></div>' +
        '<div><span class="mw-gta6__sw mw-gta6__sw--alt" aria-hidden="true"></span><strong>Xbox Series X|S ' + (100 - psPct) +
        '%</strong> <span class="mw-gta6__muted">' + esc(mUnits(xb.units)) + ' copies' + DOT + esc(usd(xb.revenue)) + '</span></div>' +
        '</div></div>';
    }

    var rows = m.rs.slice(0, 5);
    h += '<div class="mw-gta6__scroll"><table class="mw-gta6__table"><thead><tr>' +
      '<th scope="col">Reading</th><th scope="col">Copies</th><th scope="col">Revenue</th><th scope="col">Change</th></tr></thead><tbody>';
    rows.forEach(function (r, i) {
      var prev = m.rs[i + 1];
      var chg = prev ? '<span class="mw-gta6__up" aria-hidden="true">' + UP + ' </span>' + esc(mUnits(r.units - prev.units)) : DASH;
      h += '<tr><td>' + esc(fmtDate(r.date)) + '</td><td>' + esc(mUnits(r.units)) + '</td><td>' + esc(usd(r.revenue)) +
        '</td><td class="mw-gta6__chgcell">' + chg + '</td></tr>';
    });
    h += '</tbody></table></div>';

    h += '<p class="mw-gta6__caption">Live figure is projected from the latest reading and resets when Sensor Tower updates. ' +
      'Estimates only; excludes physical copies. Source: <a href="' + esc(m.sourceUrl) + '" target="_blank" rel="noopener">Sensor Tower</a></p>';
    return h;
  }

  function tickTracker(st) {
    var L = live(st.m, Date.now());
    if (L.stale !== st.stale) { st.stale = L.stale; render(st); return; }
    var V = forPlatform(st.m, L, st.platform);
    var r = st.el.querySelector('[data-live="rev"]');
    var u = st.el.querySelector('[data-live="units"]');
    if (r) r.textContent = '$' + whole(V.revenue);
    if (u) u.textContent = whole(V.units);
  }

  /* ---------- charts ---------- */

  function chartRows(st) {
    var set = st.cmp[st.kind];
    var view = set[st.mode];
    var L = live(st.m, Date.now());
    var liveAmt = st.kind === 'copies' ? L.units : L.revenue;
    var items = view.items.map(function (x) {
      var o = {};
      for (var k in x) { if (Object.prototype.hasOwnProperty.call(x, k)) o[k] = x[k]; }
      if (x.live) { o.amt = liveAmt; o.me = true; }
      return o;
    });
    items.sort(function (a, b) { return b.amt - a.amt; });
    var myIdx = -1;
    for (var i = 0; i < items.length; i++) { if (items[i].me) { myIdx = i; break; } }
    var list = items.slice(0, 10);
    var pinned = myIdx >= 10 ? items[myIdx] : null;
    if (pinned) list.push(pinned);
    var max = Math.max.apply(null, list.map(function (x) { return x.amt; }));
    var fmt = st.kind === 'copies' ? function (x) { return mUnits(x.amt); } : function (x) { return usd(x.amt, x.plus); };

    var out = '';
    list.forEach(function (x, i) {
      var isPin = pinned && x === pinned;
      var rank = isPin ? (view.pinRank || String(myIdx + 1)) : String(i + 1);
      var sub = x.year + DOT + x.sub;
      var subShort = String(x.year) + (x.sub === 'Lifetime' ? '' : DOT + String(x.sub).replace(/^(Film|Game) \u00b7 /, ''));
      var val = fmt(x);
      if (isPin) out += '<li class="mw-gta6__gap" aria-hidden="true">\u00b7\u00b7\u00b7</li>';
      out += '<li class="mw-gta6__row' + (x.me ? ' mw-gta6__row--me' : '') + '" aria-label="' +
        esc(rank + '. ' + x.title + ' (' + x.year + '), ' + x.sub + ': ' + val) + '">' +
        '<span class="mw-gta6__rank" aria-hidden="true">' + esc(rank) + '</span>' +
        '<span class="mw-gta6__lab" aria-hidden="true"><span class="mw-gta6__title" title="' + esc(x.title) + '">' + esc(x.title) + '</span>' +
        '<span class="mw-gta6__sub">' + esc(sub) + '</span><span class="mw-gta6__subs">' + esc(subShort) + '</span></span>' +
        '<span class="mw-gta6__barwrap" aria-hidden="true"><span class="mw-gta6__bar' + (x.film ? ' mw-gta6__bar--film' : '') +
        '" style="--w:' + (x.amt / max).toFixed(4) + '"></span><span class="mw-gta6__val">' + esc(val) + '</span></span></li>';
    });
    return { html: out, key: mUnits(liveAmt) + usd(liveAmt) };
  }

  function sourcesHTML(list) {
    if (!Array.isArray(list)) return '';
    return 'Source: ' + list.map(function (s) {
      if (s && s.url && /^https:\/\//.test(s.url)) {
        return '<a href="' + esc(s.url) + '" target="_blank" rel="noopener">' + esc(s.name) + '</a>';
      }
      return esc(s && s.name);
    }).join(DOT);
  }

  function chartHTML(st) {
    var set = st.cmp[st.kind];
    var view = set[st.mode];
    var rows = chartRows(st);
    st.last = rows.key;
    var h = '';
    h += '<div class="mw-gta6__head"><h2 class="mw-gta6__h">' + esc(set.title) + '</h2></div>';
    h += '<p class="mw-gta6__meta">' + esc(view.meta) + '</p>';
    h += '<div class="mw-gta6__chart-head"><div class="mw-gta6__switch" role="group" aria-label="Time period">';
    MODES.forEach(function (md) {
      h += '<button type="button" data-mode="' + md.id + '" aria-pressed="' + (md.id === st.mode ? 'true' : 'false') + '">' + esc(md.label) + '</button>';
    });
    h += '</div>';
    if (set.legend) {
      h += '<div class="mw-gta6__keys"><div><span class="mw-gta6__sw" aria-hidden="true"></span>Games</div>' +
        '<div><span class="mw-gta6__sw mw-gta6__sw--alt" aria-hidden="true"></span>Films</div></div>';
    }
    h += '</div>';
    h += '<ol class="mw-gta6__bars">' + rows.html + '</ol>';
    if (view.note) h += '<p class="mw-gta6__caption">' + esc(view.note) + '</p>';
    h += '<p class="mw-gta6__caption">' + sourcesHTML(set.sources) + '</p>';
    return h;
  }

  function tickChart(st) {
    var rows = chartRows(st);
    if (rows.key === st.last) return;
    st.last = rows.key;
    var ol = st.el.querySelector('.mw-gta6__bars');
    if (ol) ol.innerHTML = rows.html;
  }

  /* ---------- lifecycle ---------- */

  function render(st) {
    var active = document.activeElement;
    var refocus = null;
    if (active && st.el.contains(active)) {
      if (active.getAttribute('data-platform')) refocus = '[data-platform="' + active.getAttribute('data-platform') + '"]';
      else if (active.getAttribute('data-mode')) refocus = '[data-mode="' + active.getAttribute('data-mode') + '"]';
    }
    if (st.kind === 'tracker') {
      st.stale = live(st.m, Date.now()).stale;
      st.el.innerHTML = trackerHTML(st);
    } else {
      st.el.innerHTML = chartHTML(st);
    }
    st.el.setAttribute('aria-label', st.kind === 'tracker' ? 'GTA 6 sales tracker' : st.cmp[st.kind].title);
    if (refocus) {
      var target = st.el.querySelector(refocus);
      if (target) target.focus();
    }
  }

  function bind(st) {
    st.el.addEventListener('click', function (ev) {
      var t = ev.target;
      while (t && t !== st.el && !(t.tagName === 'BUTTON' || t.tagName === 'A')) t = t.parentNode;
      if (!t || t === st.el) return;
      var cat = CATS[st.kind];
      if (t.tagName === 'A') { track(cat, 'Link Click', t.textContent); return; }
      var p = t.getAttribute('data-platform');
      var md = t.getAttribute('data-mode');
      if (p && p !== st.platform) {
        st.platform = p;
        render(st);
        track(cat, 'Platform Switch', p);
      } else if (md && md !== st.mode) {
        st.mode = md;
        render(st);
        track(cat, 'Toggle', st.kind + DOT + md);
      }
    });
  }

  function observe(st) {
    if (!('IntersectionObserver' in window)) {
      st.visible = true;
      track(CATS[st.kind], 'Impression', st.kind);
      return;
    }
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        st.visible = e.isIntersecting;
        if (!st.impressed && e.intersectionRatio >= 0.5) {
          st.impressed = true;
          track(CATS[st.kind], 'Impression', st.kind);
        }
      });
    }, { threshold: [0, 0.5] });
    io.observe(st.el);
  }

  function needsFor(kinds) {
    var names = ['tracker'];
    if (kinds.indexOf('copies') >= 0 || kinds.indexOf('revenue') >= 0) names.push('comparisons');
    return names;
  }

  function apply(inst, res) {
    var t = res[0];
    var cmp = res[1] || null;
    if (!validTracker(t)) throw new Error('tracker.json failed validation');
    if (inst.names.length > 1 && !validComparisons(cmp)) throw new Error('comparisons.json failed validation');
    var m = model(t);
    inst.parts.forEach(function (st) { st.m = m; st.cmp = cmp; render(st); });
  }

  function mount(root) {
    if (root.getAttribute('data-mounted') === '1') return;
    root.setAttribute('data-mounted', '1');
    var kind = root.getAttribute('data-widget');
    var kinds = kind === 'mega' ? ['tracker', 'copies', 'revenue'] : [kind];
    if (!CATS[kinds[0]]) { warn('unknown data-widget "' + kind + '"'); root.hidden = true; return; }
    var names = needsFor(kinds);
    loadData(root, names).then(function (res) {
      root.innerHTML = kinds.map(function (k) { return '<section class="mw-gta6__panel" data-part="' + k + '"></section>'; }).join('');
      var inst = { root: root, names: names, parts: [] };
      kinds.forEach(function (k, i) {
        inst.parts.push({ kind: k, el: root.children[i], platform: 'all', mode: 'launch', last: '', visible: false, impressed: false, stale: false });
      });
      apply(inst, res);
      inst.parts.forEach(function (st) { bind(st); observe(st); });
      root.hidden = false;
      instances.push(inst);
    }).catch(function (e) {
      root.innerHTML = '';
      root.hidden = true;
      warn('widget hidden: ' + (e && e.message), e);
    });
  }

  function mountAll() {
    var roots = document.querySelectorAll('.mw-gta6[data-widget]');
    for (var i = 0; i < roots.length; i++) mount(roots[i]);
  }

  setInterval(function () {
    if (document.hidden) return;
    instances.forEach(function (inst) {
      inst.parts.forEach(function (st) {
        if (!st.visible) return;
        if (st.kind === 'tracker') tickTracker(st); else tickChart(st);
      });
    });
  }, TICK_MS);

  setInterval(function () {
    instances.forEach(function (inst) {
      loadData(inst.root, inst.names).then(function (res) { apply(inst, res); })
        .catch(function (e) { warn('refresh failed, keeping last data', e); });
    });
  }, REFRESH_MS);

  window[NS] = { mountAll: mountAll, version: '1.0.0' };

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', mountAll);
  else mountAll();
})();
