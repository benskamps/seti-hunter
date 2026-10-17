/* ==========================================================================
   /listen/ — the seti-hunter survey wing
   --------------------------------------------------------------------------
   Reads three things, never anything else:
     /api/listen        the live snapshot (schema 1), proxied and allowlisted by
                        the site from the survey's public gist (~15 min fresh)
     figures.json       the daily export of eliminated signals with cutouts
     stars.js           the 1,133-star sample + the ladder's bands, baked
   Fallback chain when /api/listen is empty or unreachable (Review Focus 1):
     the last good snapshot this browser saw (STALE badge) -> demo-snapshot.json
     (DEMO badge, the real six-target pilot). Never blank zeros as if real.
   House rules kept here: every number comes from data; data is written with
   textContent only; all cosmetic randomness is seeded; rAF loops run only when
   the panel is on screen and the tab is visible; prefers-reduced-motion gets
   a designed still frame, never a blank.
   ========================================================================== */
(function () {
    'use strict';

    const STARS = window.LISTEN_STARS;
    const REDUCE = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const STALE_MS = 60 * 60 * 1000;
    const POLL_MS = 5 * 60 * 1000;
    const LS_KEY = 'listen:last-snapshot';
    const PAGE = 36;
    const NF = new Intl.NumberFormat('en-US');
    const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

    // The frame counter the reduced-motion check reads: it must stay fixed when motion is off.
    window.__listenFrames = 0;
    const tickFrame = () => { window.__listenFrames += 1; };

    /* ------------------------------------------------------------ utilities */
    const $ = (sel, root) => (root || document).querySelector(sel);
    const $$ = (sel, root) => Array.from((root || document).querySelectorAll(sel));

    function el(tag, props, ...kids) {
        const node = document.createElement(tag);
        if (props) {
            for (const [k, v] of Object.entries(props)) {
                if (v === undefined || v === null || v === false) continue;
                if (k === 'class') node.className = v;
                else if (k === 'text') node.textContent = v;
                else if (k === 'style') for (const [sk, sv] of Object.entries(v)) node.style.setProperty(sk, sv);
                else if (k.startsWith('on')) node.addEventListener(k.slice(2), v);
                else node.setAttribute(k, v === true ? '' : String(v));
            }
        }
        for (const kid of kids.flat()) {
            if (kid === null || kid === undefined || kid === false) continue;
            node.appendChild(typeof kid === 'string' || typeof kid === 'number' ? document.createTextNode(String(kid)) : kid);
        }
        return node;
    }
    const svgNS = 'http://www.w3.org/2000/svg';
    function sv(tag, attrs, parent) {
        const node = document.createElementNS(svgNS, tag);
        for (const [k, v] of Object.entries(attrs || {})) {
            if (k === 'text') node.textContent = v;
            else node.setAttribute(k, String(v));
        }
        if (parent) parent.appendChild(node);
        return node;
    }
    const num = (v) => (typeof v === 'number' && Number.isFinite(v) ? v : null);
    const fmt = (v) => (num(v) === null ? '—' : NF.format(v));
    const store = {
        get(k) { try { return window.localStorage.getItem(k); } catch (e) { return null; } },
        set(k, v) { try { window.localStorage.setItem(k, v); } catch (e) { /* private mode: fine */ } },
    };
    function parseJSON(text) { try { return JSON.parse(text); } catch (e) { return null; } }
    function fnv1a(str) { let h = 0x811c9dc5; for (let i = 0; i < str.length; i++) { h ^= str.charCodeAt(i); h = Math.imul(h, 0x01000193); } return h >>> 0; }
    function mulberry32(a) { return function () { a |= 0; a = (a + 0x6D2B79F5) | 0; let t = Math.imul(a ^ (a >>> 15), 1 | a); t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296; }; }
    function utcStamp(iso) {
        const d = new Date(iso);
        if (Number.isNaN(d.getTime())) return '';
        return `${d.getUTCDate()} ${MON[d.getUTCMonth()]} ${d.getUTCFullYear()}, ${String(d.getUTCHours()).padStart(2, '0')}:${String(d.getUTCMinutes()).padStart(2, '0')} UTC`;
    }
    function utcDate(iso) {
        const d = new Date(iso);
        return Number.isNaN(d.getTime()) ? '' : `${d.getUTCDate()} ${MON[d.getUTCMonth()]} ${d.getUTCFullYear()}`;
    }
    function ago(ms) {
        const m = Math.round(ms / 60000);
        if (m < 90) return `${Math.max(m, 0)} min`;
        const h = Math.round(m / 60);
        return h < 48 ? `${h} h` : `${Math.round(h / 24)} days`;
    }
    const mjdDate = (m) => new Date((m - 40587) * 86400000);

    // When visible to the reader (on screen and tab not hidden), a panel may animate.
    function watchVisibility(node, onChange) {
        let onScreen = false;
        const fire = () => onChange(onScreen && !document.hidden);
        if ('IntersectionObserver' in window) {
            new IntersectionObserver((entries) => { onScreen = entries[0].isIntersecting; fire(); }, { rootMargin: '80px' }).observe(node);
        } else { onScreen = true; }
        document.addEventListener('visibilitychange', fire);
        fire();
    }

    /* ------------------------------------------------------------ the ladder's words */
    const RUNGS = {
        1: { c: '#e8833a', label: 'present in an OFF scan', stamp: 'in an OFF scan', sub: 'there when the telescope looked away',
            plain: 'It was there when the telescope pointed away from the star, so it isn’t coming from the star. Almost always a transmitter on or near Earth.' },
        2: { c: '#d0573f', label: 'missing from an ON scan', stamp: 'missing from an ON', sub: 'it didn’t follow the star',
            plain: 'It didn’t appear in every look at the star along its own drift line. A source on the star would be there each time the telescope came back.' },
        3: { c: '#8fa3ad', label: 'an instrument artifact', stamp: 'instrument artifact', sub: 'a coarse-channel spike or edge',
            plain: 'It sits exactly where the receiver’s own filterbank makes a spike or an edge. The instrument made it, not the sky.' },
        4: { c: '#cfa42c', label: 'inside a human transmitter band', stamp: 'human band', sub: 'GPS, Iridium, Wi-Fi and kin',
            plain: 'It falls inside a band that human transmitters use, read from the frozen ladder. It is far likelier to be one of ours.' },
        5: { c: '#a88bc9', label: 'also seen around another star', stamp: 'at another star', sub: 'the same carrier somewhere else',
            plain: 'The same frequency and drift turned up around a different star on another date. One source can’t sit beside two stars at once; local interference can.' },
    };
    const SHAPES = { wide_drift: 'wide drifting carrier', chirp: 'curving drift (chirp)', intermittent: 'intermittent tone', comb: 'comb', weird: 'weird channel (no limit claimed)' };
    const BAND_NAMES = { gps_l5: 'GPS L5', gps_l2: 'GPS L2', gps_l1: 'GPS L1', inmarsat: 'Inmarsat', glonass: 'GLONASS', iridium: 'Iridium', spacecraft_telemetry: 'spacecraft telemetry', wifi_ism: 'Wi-Fi / ISM' };
    const bandName = (k) => BAND_NAMES[k] || String(k).replace(/_/g, ' ');

    /* ------------------------------------------------------------ state */
    const state = {
        snap: null, source: 'none', reason: null,
        figures: [], items: [], view: [],
        filter: null, query: '', shown: PAGE, ledger: -1,
        searched: new Set(), loadedAt: 0,
    };

    /* ------------------------------------------------------------ loading */
    async function getJSON(url) {
        const r = await fetch(url, { cache: 'no-store', headers: { Accept: 'application/json' } });
        if (!r.ok) throw new Error(`${url} ${r.status}`);
        return r.json();
    }
    const validSnap = (s) => !!s && typeof s === 'object' && s.schema === 1 && !s.empty
        && !!s.funnel && typeof s.funnel === 'object' && !!s.progress && typeof s.progress === 'object';

    async function loadSnapshot() {
        let reason = null;
        try {
            const s = await getJSON('/api/listen');
            if (validSnap(s)) { store.set(LS_KEY, JSON.stringify(s)); return { snap: s, source: 'live', reason: null }; }
            reason = (s && s.reason) || 'bad-shape';
        } catch (e) { reason = 'unreachable'; }
        const cached = parseJSON(store.get(LS_KEY));
        if (validSnap(cached)) return { snap: cached, source: 'cached', reason };
        try {
            const d = await getJSON('demo-snapshot.json');
            if (validSnap(d)) return { snap: d, source: 'demo', reason };
        } catch (e) { /* fall through */ }
        return { snap: null, source: 'none', reason };
    }

    const validItem = (it) => !!it && typeof it === 'object' && typeof it.id === 'string'
        && Number.isInteger(it.rung) && it.rung >= 1 && it.rung <= 5;

    async function loadFigures(source) {
        const base = source === 'demo' ? 'demo/' : '';
        try {
            const arr = await getJSON(`${base}figures.json`);
            return Array.isArray(arr) ? arr.filter(validItem).map((it) => ({ ...it, base })) : [];
        } catch (e) { return []; }
    }

    // Wall/ribbon items: the daily figures (with cutouts and scans) plus any newer live
    // eliminations from the snapshot (their cutouts arrive with the next daily export).
    function mergeItems(figures, snap) {
        const byId = new Map();
        for (const it of figures) byId.set(it.id, it);
        for (const r of (snap && Array.isArray(snap.recent_eliminated) ? snap.recent_eliminated : [])) {
            if (!validItem(r) || byId.has(r.id)) continue;
            byId.set(r.id, { ...r, figure: null, tile: null, scans: null, base: '' });
        }
        return Array.from(byId.values()).sort((a, b) => (num(b.weirdness) ?? -Infinity) - (num(a.weirdness) ?? -Infinity)
            || String(a.id).localeCompare(String(b.id)));
    }

    function parseSearched(hex) {
        const set = new Set();
        if (typeof hex !== 'string' || !/^[0-9a-f]+$/.test(hex) || !STARS) return set;
        for (let i = 0; i < STARS.stars.length; i++) {
            const pos = hex.length - 1 - (i >> 2);
            if (pos < 0) break;
            if ((parseInt(hex[pos], 16) >> (i & 3)) & 1) set.add(i);
        }
        return set;
    }

    /* ------------------------------------------------------------ mode & badges */
    function modeInfo() {
        const s = state.snap;
        if (!s) return { mode: 'demo', status: 'demo', text: 'No numbers yet: the survey hasn’t published, and the demo didn’t load' };
        if (state.source === 'demo') {
            return { mode: 'demo', status: 'demo',
                text: `DEMO DATA: THE RUN HASN’T STARTED · REAL SIGNALS FROM THE ${fmt(s.progress.cadences_total)}-TARGET PILOT, NOT THE SURVEY` };
        }
        const t = Date.parse(s.as_of_utc);
        const age = Date.now() - t;
        if (state.source === 'cached' || !(age < STALE_MS)) {
            return { mode: 'stale', status: 'stale',
                text: `STALE · LAST GOOD NUMBERS ARE ${Number.isFinite(age) ? ago(age).toUpperCase() : 'OF UNKNOWN AGE'} OLD · AS OF ${utcStamp(s.as_of_utc).toUpperCase()}` };
        }
        if (s.mode !== 'MEASURED') return { mode: 'measured', status: 'live', text: `LIVE · NO CADENCE SCORED YET · AS OF ${utcStamp(s.as_of_utc).toUpperCase()}` };
        return { mode: 'measured', status: 'live', text: `MEASURED · AS OF ${utcStamp(s.as_of_utc).toUpperCase()}` };
    }

    function setBadge(node, mode, text) { if (!node) return; node.dataset.mode = mode; node.textContent = text; }

    function renderBadges() {
        const m = modeInfo();
        for (const b of $$('[data-slot="badge"]')) setBadge(b, m.mode, m.text);
        const status = $('[data-slot="status"]');
        status.dataset.state = m.status;
        $('[data-slot="status-text"]').textContent = m.status === 'live' ? `live · as of ${utcStamp(state.snap.as_of_utc)}`
            : m.status === 'stale' ? `stale · showing the last good numbers` : 'demo · the run hasn’t started';
        const s = state.snap;
        const withFig = state.items.filter((it) => it.tile).length;
        setBadge($('[data-slot="badge-wall"]'), m.mode, state.source === 'demo'
            ? `DEMO · REAL CUTOUTS FROM THE PILOT (${fmt(s && s.progress.cadences_total)} TARGETS) · THE SURVEY’S OWN APPEAR DAILY ONCE IT RUNS`
            : `${m.mode === 'stale' ? 'STALE' : 'MEASURED'} · ${fmt(state.items.length)} ELIMINATIONS LISTED · ${fmt(withFig)} WITH CUTOUTS FROM THE DAILY EXPORT`);
        setBadge($('[data-slot="badge-heart"]'), m.mode, state.source === 'demo'
            ? 'DEMO · PILOT TOTALS · SPEEDS REPRESENTATIVE, FROM THE MEASURED 1.2–1.4 MB/S RANGE'
            : m.text);
    }

    /* ------------------------------------------------------------ count-up */
    function countUp(node, target, opts) {
        if (!node) return;
        const o = opts || {};
        if (num(target) === null) { node.textContent = '—'; return; }
        const from = num(Number(node.dataset.shown)) ?? 0;
        node.dataset.shown = String(target);
        if (REDUCE || from === target) { node.textContent = fmt(target); return; }
        const t0 = performance.now(), ms = o.ms || 1000;
        let done = false;
        (function tick(t) {
            if (done) return;
            const p = Math.min(1, (t - t0) / ms), e = 1 - Math.pow(1 - p, 3);
            node.textContent = fmt(Math.round(from + (target - from) * e));
            if (p < 1) requestAnimationFrame(tick); else done = true;
        })(t0);
        // A throttled or background tab may never run the frames: never leave a
        // mid-count number (often a 0 that isn't real) standing in for the reading.
        setTimeout(() => { if (!done) { done = true; node.textContent = fmt(target); } }, ms + 250);
    }

    function totals() {
        const s = state.snap;
        if (!s) return {};
        const f = s.funnel, r = f.eliminated_by_rung || {};
        const rungs = [1, 2, 3, 4, 5].map((k) => num(r[String(k)]));
        return {
            stars_done: num(s.progress.stars_done), stars_total: num(s.progress.stars_total),
            flagged: num(f.flagged), under_review: num(f.under_review),
            eliminated: rungs.every((v) => v === null) ? null : rungs.reduce((a, v) => a + (v || 0), 0),
        };
    }

    /* ------------------------------------------------------------ hero */
    function renderHero() {
        const t = totals();
        const total = num(t.stars_total) ?? (STARS ? STARS.count : null);
        for (const n of $$('[data-slot="star-total"], [data-slot="star-total-2"]')) n.textContent = fmt(total);
        for (const n of $$('[data-count]')) {
            const key = n.dataset.count === 'stars_done_ring' ? 'stars_done' : n.dataset.count;
            countUp(n, t[key]);
        }
    }

    /* ------------------------------------------------------------ funnel */
    function renderFunnel() {
        const host = $('[data-slot="funnel"]');
        host.textContent = '';
        const s = state.snap;
        const f = s ? s.funnel : {};
        const r = (f && f.eliminated_by_rung) || {};
        const flagged = num(f.flagged);
        const batch = s && s.pending_batch_utc ? utcDate(s.pending_batch_utc) : '';
        const rows = [
            { key: 'flagged', v: flagged, t: 'Flagged by the detectors', s: 'every tile over a shape’s threshold, plus the weird channel', c: '#ece1cc', top: true },
            'gap',
            ...[1, 2, 3, 4, 5].map((k) => ({ key: `r${k}`, rung: k, v: num(r[String(k)]), t: RUNGS[k].label.replace(/^./, (ch) => ch.toUpperCase()), s: RUNGS[k].sub, c: RUNGS[k].c })),
            'gap',
            { key: 'untested', v: num(f.untested), t: 'Untested', s: 'no OFF scans to compare against', c: '#a0926f' },
            { key: 'not_recovered', v: num(f.not_recovered), t: 'Not re-found', s: 'a second look couldn’t see it again', c: '#7d715f' },
            { key: 'incomplete', v: num(f.incomplete), t: 'Incomplete', s: 'its track left the recorded band', c: '#6f6557' },
            'gap',
            { key: 'pending_final_check', v: num(f.pending_final_check), t: 'Pending final check', s: batch ? `waiting on rung 5 · the ${batch} 00:00 UTC batch` : 'waiting on rung 5 · counted once a day', c: '#c9a86a' },
            { key: 'under_review', v: num(f.under_review), t: 'Under private review', s: 'passed all five rungs; held while it’s checked', c: '#ffd166', review: true },
            { key: 'public_candidates', v: num(f.public_candidates), t: 'Public candidates', s: 'released after review, with everything', c: '#8aa86b' },
        ];
        let sum = 0, allKnown = flagged !== null;
        for (const row of rows) {
            if (row === 'gap') { host.appendChild(el('li', { class: 'frow-gap', 'aria-hidden': 'true' })); continue; }
            if (!row.top) { if (row.v === null) allKnown = false; else sum += row.v; }
            const share = flagged ? Math.min(1, (row.v || 0) / flagged) : 0;
            const fill = el('span', { class: `frow-fill${row.v ? ' min' : ''}`, style: { '--frow-c': row.c } });
            const n = el('span', { class: 'frow-n', style: { '--frow-c': row.c }, text: '—' });
            const inner = [
                el('span', { class: 'frow-lab' }, row.rung ? el('span', { class: `rung r${row.rung}`, text: String(row.rung), 'aria-hidden': 'true' }) : null, el('span', null, el('span', { class: 't', text: row.t }), el('span', { class: 's', text: row.s }))),
                el('span', { class: 'frow-trk' }, fill), n,
            ];
            const cls = `frow${row.top ? ' frow-top' : ''}${row.review ? ' frow-review' : ''}`;
            const node = row.rung
                ? el('button', { type: 'button', class: cls, style: { '--frow-c': row.c }, 'aria-pressed': state.filter === row.rung ? 'true' : 'false',
                    'aria-label': `${row.t}: ${fmt(row.v)}. Show these on the Wall.`, onclick: () => { setFilter(state.filter === row.rung ? null : row.rung); $('#wall').scrollIntoView({ behavior: REDUCE ? 'auto' : 'smooth', block: 'start' }); } }, inner)
                : el('div', { class: cls, style: { '--frow-c': row.c } }, inner);
            host.appendChild(el('li', null, node));
            if (row.review) host.appendChild(el('li', { class: 'standing-note', text: 'Some signals under review may be planted test signals; we check each one first.' }));
            requestAnimationFrame(() => { fill.style.width = `${(share * 100).toFixed(2)}%`; });
            countUp(n, row.v);
        }
        const sumEl = $('[data-slot="funnel-sum"]');
        sumEl.className = 'funnel-sum';
        if (!allKnown) { sumEl.classList.add('blank'); sumEl.textContent = 'Waiting for numbers: rows stay blank rather than show zeros that aren’t real.'; }
        else if (sum === flagged) sumEl.textContent = `The rows add up: ${fmt(sum)} = ${fmt(flagged)} flagged ✓`;
        else { sumEl.classList.add('bad'); sumEl.textContent = `The rows sum to ${fmt(sum)}, the top line says ${fmt(flagged)}: a gap of ${fmt(Math.abs(flagged - sum))}, shown rather than hidden.`; }
    }

    /* ------------------------------------------------------------ sky */
    const sky = { ready: false, playing: false, t0: 0, shown: 0, trail: [], visible: false, raf: 0 };
    function initSky() {
        const cv = $('#sky-canvas');
        if (!cv || !STARS) return;
        const W = 1400, H = 700, cx = W / 2, cy = H / 2, sxk = (W / 2) / (2 * Math.SQRT2) * 0.96, syk = (H / 2) / Math.SQRT2 * 0.92;
        const D = Math.PI / 180;
        // Hammer-Aitoff, RA increasing to the left, centred on RA 0h.
        function proj(ra, dec) {
            let l = (ra > 180 ? ra - 360 : ra) * D; l = -l; const b = dec * D;
            const z = Math.sqrt(1 + Math.cos(b) * Math.cos(l / 2));
            return [cx + sxk * 2 * Math.SQRT2 * Math.cos(b) * Math.sin(l / 2) / z, cy - syk * Math.SQRT2 * Math.sin(b) / z];
        }
        // galactic -> equatorial (J2000): eq = R^T gal
        const R = [[-0.0548755604, -0.8734370902, -0.4838350155], [0.4941094279, -0.4448296300, 0.7469822445], [-0.8676661490, -0.1980763734, 0.4559837762]];
        function gal2eq(l, b) {
            l *= D; b *= D; const v = [Math.cos(b) * Math.cos(l), Math.cos(b) * Math.sin(l), Math.sin(b)];
            const x = R[0][0] * v[0] + R[1][0] * v[1] + R[2][0] * v[2], y = R[0][1] * v[0] + R[1][1] * v[1] + R[2][1] * v[2], z = R[0][2] * v[0] + R[1][2] * v[1] + R[2][2] * v[2];
            let ra = Math.atan2(y, x) / D; if (ra < 0) ra += 360; return [ra, Math.asin(z) / D];
        }
        const g = cv.getContext('2d');
        let scale = 1, bg = null;
        const COL = { LS: '#fff3c4', L: '#7fe0d0', S: '#c4b5fd' };
        const sprite = {};
        function makeSprite(color, r) {
            const c = document.createElement('canvas'); const s = Math.ceil(r * 6 * scale); c.width = c.height = s;
            const x = c.getContext('2d'), m = s / 2, gr = x.createRadialGradient(m, m, 0, m, m, m);
            gr.addColorStop(0, color); gr.addColorStop(0.32, color + '77'); gr.addColorStop(1, color + '00');
            x.fillStyle = gr; x.fillRect(0, 0, s, s); return c;
        }
        const rnd0 = mulberry32(fnv1a('listen-sky'));
        const pts = STARS.stars.map((s, i) => { const [x, y] = proj(s[1], s[2]); return { i, n: s[0], x, y, bands: s[3], m: s[4], ph: rnd0() * 6.283 }; });
        const order = pts.slice().sort((a, b) => a.m - b.m);
        const mjd0 = order[0].m, mjd1 = order[order.length - 1].m;
        sky.shown = order.length;

        function drawBackground() {
            bg = document.createElement('canvas'); bg.width = cv.width; bg.height = cv.height;
            const b = bg.getContext('2d'); b.scale(scale, scale);
            const rnd = mulberry32(fnv1a('listen-milky-way'));
            const outline = () => { b.beginPath(); for (let i = 0; i <= 360; i++) { const t = i / 360 * 2 * Math.PI; b.lineTo(cx + sxk * 2 * Math.SQRT2 * Math.cos(t), cy + syk * Math.SQRT2 * Math.sin(t)); } b.closePath(); };
            b.save(); outline();
            const grd = b.createRadialGradient(cx, cy, 10, cx, cy, W / 2); grd.addColorStop(0, '#0d1a33'); grd.addColorStop(1, '#03050b');
            b.fillStyle = grd; b.fill(); b.clip();
            for (let i = 0; i < 2400; i++) { b.fillStyle = `rgba(205,218,255,${(rnd() * 0.32).toFixed(3)})`; b.fillRect(rnd() * W, rnd() * H, 1.1, 1.1); }
            b.globalCompositeOperation = 'lighter';
            for (let i = 0; i < 16000; i++) { // the Milky Way: gaussian in latitude, brighter toward the centre
                const l = rnd() * 360, u = rnd(), v = rnd();
                const gb = Math.sqrt(-2 * Math.log(u + 1e-9)) * Math.cos(2 * Math.PI * v) * 6.5;
                const core = Math.exp(-Math.pow((((l + 180) % 360) - 180) / 55, 2));
                const [ra, dec] = gal2eq(l, gb); const [x, y] = proj(ra, dec);
                const a = 0.04 + 0.1 * core, r = 2.5 + rnd() * 6;
                const gg = b.createRadialGradient(x, y, 0, x, y, r);
                gg.addColorStop(0, `rgba(196,176,255,${a.toFixed(3)})`); gg.addColorStop(1, 'rgba(196,176,255,0)');
                b.fillStyle = gg; b.fillRect(x - r, y - r, 2 * r, 2 * r);
            }
            b.globalCompositeOperation = 'source-over';
            b.strokeStyle = 'rgba(143,170,190,.12)'; b.lineWidth = 1;
            for (let dec = -60; dec <= 60; dec += 30) { b.beginPath(); for (let ra = 0; ra <= 360; ra += 2) { const [x, y] = proj(ra === 360 ? 359.99 : ra, dec); if (ra) b.lineTo(x, y); else b.moveTo(x, y); } b.stroke(); }
            for (let ra = 0; ra < 360; ra += 30) { b.beginPath(); for (let dec = -90; dec <= 90; dec += 2) { const [x, y] = proj(ra, dec); if (dec > -90) b.lineTo(x, y); else b.moveTo(x, y); } b.stroke(); }
            b.restore();
            outline(); b.strokeStyle = 'rgba(143,170,190,.32)'; b.stroke();
            b.fillStyle = 'rgba(160,185,205,.6)'; b.font = '13px "JetBrains Mono", monospace'; b.textAlign = 'center';
            for (const [ra, t] of [[0, '0h'], [90, '6h'], [270, '18h']]) { const [x, y] = proj(ra, 0); b.fillText(t, x, y - 6); }
            const [gx, gy] = proj(...gal2eq(0, 0)); b.fillStyle = 'rgba(196,176,255,.7)'; b.font = 'italic 13px Fraunces, Georgia, serif'; b.fillText('galactic centre', gx, gy + 24);
            for (const k of Object.keys(COL)) sprite[k] = makeSprite(COL[k], k === 'LS' ? 1.9 : 1.5);
        }
        function size() {
            const dpr = Math.min(window.devicePixelRatio || 1, 2);
            const cssW = cv.getBoundingClientRect().width || W;
            scale = Math.max(0.5, Math.min(2, (cssW * dpr) / W));
            cv.width = Math.round(W * scale); cv.height = Math.round(H * scale);
            drawBackground();
        }
        let hb = null; // the star the heartbeat says is streaming, if it is in the sample
        function frame(now) {
            g.setTransform(1, 0, 0, 1, 0, 0); g.clearRect(0, 0, cv.width, cv.height); g.drawImage(bg, 0, 0); g.setTransform(scale, 0, 0, scale, 0, 0);
            if (sky.playing) {
                const f = Math.min(1, (now - sky.t0) / 24000), m = mjd0 + (mjd1 - mjd0) * f;
                while (sky.shown < order.length && order[sky.shown].m <= m) { sky.trail.push([order[sky.shown].x, order[sky.shown].y, now]); sky.shown++; }
                $('[data-slot="sky-date"]').textContent = `${MON[mjdDate(m).getUTCMonth()]} ${mjdDate(m).getUTCFullYear()}`;
                $('[data-slot="sky-count"]').textContent = `${fmt(sky.shown)} of ${fmt(order.length)} stars observed`;
                if (f >= 1) { sky.playing = false; skyHud(); }
            }
            g.globalCompositeOperation = 'lighter';
            const shownSet = sky.shown >= order.length ? null : order.slice(0, sky.shown);
            for (const p of shownSet || pts) {
                const tw = REDUCE ? 0.95 : 0.72 + 0.28 * Math.sin(now / 900 + p.ph);
                const sp = sprite[p.bands] || sprite.LS; const half = sp.width / scale / 2;
                g.globalAlpha = tw; g.drawImage(sp, p.x - half, p.y - half, half * 2, half * 2);
            }
            g.globalAlpha = 1;
            sky.trail = sky.trail.filter((t) => now - t[2] < 1600);
            for (let i = 1; i < sky.trail.length; i++) {
                const a = 1 - (now - sky.trail[i][2]) / 1600;
                g.strokeStyle = `rgba(255,209,102,${(a * 0.5).toFixed(3)})`; g.lineWidth = 1.3;
                g.beginPath(); g.moveTo(sky.trail[i - 1][0], sky.trail[i - 1][1]); g.lineTo(sky.trail[i][0], sky.trail[i][1]); g.stroke();
                g.strokeStyle = `rgba(255,209,102,${a.toFixed(3)})`; g.beginPath(); g.arc(sky.trail[i][0], sky.trail[i][1], 3 + 10 * (1 - a), 0, 7); g.stroke();
            }
            g.globalCompositeOperation = 'source-over';
            if (!sky.playing) {
                // searched so far: a gold ring with a hot core (brightness is a reading)
                for (const i of state.searched) {
                    const p = pts[i]; if (!p) continue;
                    g.strokeStyle = 'rgba(255,209,102,.85)'; g.lineWidth = 1.3; g.beginPath(); g.arc(p.x, p.y, 4.6, 0, 7); g.stroke();
                    g.fillStyle = '#ffe6a3'; g.beginPath(); g.arc(p.x, p.y, 1.8, 0, 7); g.fill();
                }
                if (hb) {
                    const ph = REDUCE ? 0.35 : (now / 1800) % 1;
                    g.strokeStyle = `rgba(127,224,208,${(1 - ph).toFixed(3)})`; g.lineWidth = 1.6; g.beginPath(); g.arc(hb.x, hb.y, 7 + ph * 18, 0, 7); g.stroke();
                    g.fillStyle = '#7fe0d0'; g.beginPath(); g.arc(hb.x, hb.y, 3.2, 0, 7); g.fill();
                    g.font = 'italic 15px Fraunces, Georgia, serif'; g.fillStyle = 'rgba(223,240,236,.95)'; g.textAlign = 'left';
                    g.fillText(`now: ${hb.n}`, hb.x + 12, hb.y - 10);
                }
            }
            tickFrame();
        }
        function loop(now) {
            sky.raf = 0;
            frame(now);
            if (sky.visible && (!REDUCE || sky.playing)) sky.raf = requestAnimationFrame(loop);
        }
        function kick() { if (!sky.raf && sky.visible && (!REDUCE || sky.playing)) sky.raf = requestAnimationFrame(loop); }
        sky.redraw = () => {
            const name = state.snap && state.snap.heartbeat && state.snap.heartbeat.star;
            hb = name ? pts.find((p) => p.n === name) || null : null;
            frame(performance.now());
            skyHud();
            kick();
        };
        function skyHud() {
            if (sky.playing) return;
            $('[data-slot="sky-date"]').textContent = state.snap ? `${fmt(state.searched.size)} searched` : '2016–2019';
            $('[data-slot="sky-count"]').textContent = `of ${fmt(pts.length)} stars in the sample`;
            const note = $('[data-slot="sky-note"]');
            note.textContent = `Hammer–Aitoff projection, equatorial coordinates, right ascension increasing to the left. ${fmt(pts.length)} stars from ${STARS.sample}. Hover or tap a star for its name.`
                + (REDUCE ? ' Motion is reduced: the map is a still, and Replay jumps to its last frame.' : '');
        }
        size();
        watchVisibility(cv, (v) => { sky.visible = v; if (v) kick(); });
        let resizeT = 0;
        window.addEventListener('resize', () => { clearTimeout(resizeT); resizeT = setTimeout(() => { size(); frame(performance.now()); }, 150); });
        $('[data-action="replay"]').addEventListener('click', () => {
            if (REDUCE) { sky.playing = false; sky.shown = order.length; frame(performance.now()); $('[data-slot="sky-date"]').textContent = '2016–2019'; $('[data-slot="sky-count"]').textContent = `${fmt(order.length)} of ${fmt(order.length)} stars observed`; return; }
            sky.playing = true; sky.t0 = performance.now(); sky.shown = 0; sky.trail = []; kick();
        });
        const tip = $('[data-slot="tip"]');
        function pick(e) {
            const r = cv.getBoundingClientRect(); const x = (e.clientX - r.left) * W / r.width, y = (e.clientY - r.top) * H / r.height;
            let best = null, bd = 160;
            const pool = sky.shown >= order.length ? pts : order.slice(0, sky.shown);
            for (const p of pool) { const d = (p.x - x) ** 2 + (p.y - y) ** 2; if (d < bd) { bd = d; best = p; } }
            if (!best) { tip.hidden = true; return; }
            const bandTxt = { LS: 'L- and S-band', L: 'L-band only', S: 'S-band only' }[best.bands] || best.bands;
            const d = mjdDate(best.m);
            tip.textContent = '';
            tip.append(el('b', { text: best.n }), el('span', { text: `${bandTxt} · first observed ${MON[d.getUTCMonth()]} ${d.getUTCFullYear()}` }),
                el('span', { text: state.searched.has(best.i) ? 'searched by this survey ✓' : 'not searched yet' }));
            showTip(e.clientX, e.clientY);
        }
        cv.addEventListener('pointermove', pick);
        cv.addEventListener('pointerdown', pick);
        cv.addEventListener('pointerleave', () => { tip.hidden = true; });
        sky.ready = true;
    }
    function showTip(x, y) {
        const tip = $('[data-slot="tip"]');
        tip.hidden = false;
        const w = tip.offsetWidth || 240;
        tip.style.left = `${Math.max(8, Math.min(window.innerWidth - w - 8, x + 14))}px`;
        tip.style.top = `${Math.min(window.innerHeight - 90, y + 16)}px`;
    }

    /* ------------------------------------------------------------ spectrum ribbon */
    function renderSpectrum() {
        const svg = $('#spec-svg');
        if (!svg || !STARS) return;
        svg.textContent = '';
        // 1.1-2.8 GHz, widened in 100 MHz steps if any eliminated signal sits outside it
        // (the L-band files reach below 1.1 GHz), so every signal on the Wall has its pin.
        const freqs = state.items.map((it) => num(it.peak_freq_mhz)).filter((v) => v !== null);
        const lo = Math.min(...freqs, 1100), hi = Math.max(...freqs, 2800);
        const F0 = lo < 1100 ? Math.floor((lo - 10) / 100) * 100 : 1100;
        const F1 = hi > 2800 ? Math.ceil((hi + 10) / 100) * 100 : 2800;
        const X0 = 40, X1 = 1160, BASE = 222, NB = Math.round((F1 - F0) / 10);
        const X = (f) => X0 + (f - F0) / (F1 - F0) * (X1 - X0);
        const defs = sv('defs', {}, svg);
        const hatch = sv('pattern', { id: 'hatch', width: 6, height: 6, patternUnits: 'userSpaceOnUse', patternTransform: 'rotate(45)' }, defs);
        sv('rect', { width: 6, height: 6, fill: '#0b1220' }, hatch); sv('line', { x1: 0, y1: 0, x2: 0, y2: 6, stroke: '#2f3d52', 'stroke-width': 2.2 }, hatch);
        const wg = sv('linearGradient', { id: 'wg', x1: 0, x2: 0, y1: 0, y2: 1 }, defs);
        sv('stop', { offset: 0, 'stop-color': '#38bdf8', 'stop-opacity': 0.2 }, wg); sv('stop', { offset: 1, 'stop-color': '#38bdf8', 'stop-opacity': 0.02 }, wg);
        const rg = sv('linearGradient', { id: 'ridge', x1: 0, x2: 0, y1: 0, y2: 1 }, defs);
        sv('stop', { offset: 0, 'stop-color': '#7fe0d0', 'stop-opacity': 0.8 }, rg); sv('stop', { offset: 1, 'stop-color': '#7fe0d0', 'stop-opacity': 0.08 }, rg);
        // receivers (recorded bandwidths)
        let ry = 24;
        for (const [k, col] of [['L', '#7fe0d0'], ['S', '#c4b5fd']]) {
            const [a, c] = STARS.receivers[k];
            sv('line', { x1: X(a), x2: X(c), y1: ry, y2: ry, stroke: col, 'stroke-width': 3, 'stroke-linecap': 'round', opacity: 0.85 }, svg);
            sv('text', { x: X(a) + 4, y: ry - 7, fill: col, 'font-size': 12, text: `${k}-band receiver · ${(a / 1000).toFixed(1)}–${(c / 1000).toFixed(1)} GHz` }, svg);
            ry += 20;
        }
        // the water hole, between hydrogen and hydroxyl
        sv('rect', { x: X(1420), y: 64, width: X(1720) - X(1420), height: BASE - 64, fill: 'url(#wg)' }, svg);
        sv('text', { x: (X(1420) + X(1720)) / 2, y: 80, fill: '#7dd3fc', 'font-size': 13, 'text-anchor': 'middle', 'font-style': 'italic', 'font-family': 'Fraunces, Georgia, serif', text: 'the water hole' }, svg);
        // axis strip
        sv('rect', { x: X0, y: BASE, width: X1 - X0, height: 14, rx: 3, fill: '#1a2436' }, svg);
        for (let f = F0; f <= F1; f += 100) {
            sv('line', { x1: X(f), x2: X(f), y1: BASE + 14, y2: BASE + (f % 200 === 0 ? 22 : 18), stroke: '#475569' }, svg);
            if (f % 200 === 0) sv('text', { x: X(f), y: BASE + 36, fill: '#8aa3b5', 'font-size': 11, 'text-anchor': 'middle', text: `${(f / 1000).toFixed(1)} GHz` }, svg);
        }
        // notch filters: no data recorded
        for (const [a, c] of STARS.notches) {
            sv('rect', { x: X(a), y: 100, width: X(c) - X(a), height: BASE - 100 + 14, fill: 'url(#hatch)', opacity: 0.95 }, svg);
            sv('text', { x: (X(a) + X(c)) / 2, y: 113, fill: '#8aa3b5', 'font-size': 10.5, 'text-anchor': 'middle', text: 'notch: no data' }, svg);
        }
        // rung 4's human-transmitter bands, from the frozen ladder
        const labelEnds = []; // stack band labels only where they would collide
        STARS.bands.slice().sort((p, q) => p[1] - q[1]).forEach(([k, a, c]) => {
            const w = Math.max(3, X(c) - X(a)), mid = X(a) + w / 2, name = bandName(k), half = name.length * 3.3;
            sv('rect', { x: X(a), y: 132, width: w, height: BASE - 132, fill: '#cfa42c', opacity: 0.16 }, svg);
            sv('rect', { x: X(a), y: BASE - 3, width: w, height: 3, fill: '#cfa42c', opacity: 0.9 }, svg);
            let lvl = 0;
            while (labelEnds[lvl] !== undefined && mid - half < labelEnds[lvl] + 6) lvl++;
            labelEnds[lvl] = mid + half;
            sv('text', { x: mid, y: 145 + lvl * 13, fill: '#e3c160', 'font-size': 10.5, 'text-anchor': 'middle', text: name }, svg);
        });
        // natural lines, drawn as a guide
        for (const [f, t] of [[1420.406, 'H I'], [1612.231, 'OH'], [1665.402, ''], [1667.359, 'OH'], [1720.53, 'OH']]) {
            sv('line', { x1: X(f), x2: X(f), y1: 88, y2: BASE, stroke: '#38bdf8', 'stroke-width': 1.1, 'stroke-dasharray': '2 3', opacity: 0.8 }, svg);
            if (t) sv('text', { x: X(f) + 3, y: 98, fill: '#7dd3fc', 'font-size': 10, text: t }, svg);
        }
        const items = state.items.filter((it) => num(it.peak_freq_mhz) !== null && it.peak_freq_mhz >= F0 && it.peak_freq_mhz <= F1);
        // the ridge: every eliminated signal, counted per 10 MHz (height ~ sqrt(count))
        const bins = new Array(NB).fill(0);
        for (const it of items) bins[Math.min(NB - 1, Math.floor((it.peak_freq_mhz - F0) / 10))] += 1;
        const peak = Math.max(1, ...bins);
        if (items.length) {
            let d = `M ${X0} ${BASE}`;
            bins.forEach((n, i) => { const h = n ? 4 + 26 * Math.sqrt(n / peak) : 0; d += ` L ${X(F0 + i * 10)} ${BASE - h} L ${X(F0 + (i + 1) * 10)} ${BASE - h}`; });
            d += ` L ${X1} ${BASE} Z`;
            sv('path', { d, fill: 'url(#ridge)', opacity: 0.55 }, svg);
        }
        // pins: the 60 weirdest, stacked when close
        const pins = items.slice(0, 60).sort((a, b) => a.peak_freq_mhz - b.peak_freq_mhz);
        const lastX = [];
        const tip = $('[data-slot="tip"]');
        pins.forEach((it, i) => {
            const x = X(it.peak_freq_mhz); let lvl = 0;
            while (lastX[lvl] !== undefined && x - lastX[lvl] < 9) lvl++;
            lastX[lvl] = x; const y = BASE - 40 - lvl * 11;
            const label = `${it.star} · ${it.peak_freq_mhz.toFixed(3)} MHz · eliminated at rung ${it.rung}`;
            const gp = sv('g', { class: 'pin', tabindex: 0, role: 'button', 'aria-label': `${label}. Open its Ledger entry.` }, svg);
            sv('line', { x1: x, x2: x, y1: BASE, y2: y, stroke: RUNGS[it.rung].c, 'stroke-width': 1.2, opacity: 0.7 }, gp);
            const c = sv('circle', { cx: x, cy: y, r: 4.6, fill: RUNGS[it.rung].c, stroke: '#05070d', 'stroke-width': 1.2 }, gp);
            if (!REDUCE && c.animate) c.animate([{ transform: 'translateY(-50px)', opacity: 0 }, { transform: 'translateY(0)', opacity: 1 }], { duration: 700, delay: 200 + i * 40, easing: 'cubic-bezier(.2,.8,.2,1.2)', fill: 'backwards' });
            const open = () => openLedgerById(it.id);
            gp.addEventListener('click', open);
            gp.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); open(); } });
            gp.addEventListener('pointermove', (e) => { tip.textContent = ''; tip.append(el('b', { text: `${it.star} · ${it.peak_freq_mhz.toFixed(3)} MHz` }), el('span', { text: `eliminated at rung ${it.rung}: ${RUNGS[it.rung].label}` })); showTip(e.clientX, e.clientY); });
            gp.addEventListener('pointerleave', () => { tip.hidden = true; });
        });
        // legend
        const lg = sv('g', { transform: `translate(${X0},${BASE + 62})` }, svg);
        let lx = 0;
        for (const k of [1, 2, 3, 4, 5]) {
            sv('circle', { cx: lx + 5, cy: -4, r: 4.4, fill: RUNGS[k].c }, lg);
            const t = `${k} · ${RUNGS[k].stamp}`;
            sv('text', { x: lx + 14, y: 0, fill: '#8aa3b5', 'font-size': 11, text: t }, lg);
            lx += t.length * 6.9 + 30;
        }
        renderCallouts(items);
        const note = $('[data-slot="band-note"]');
        note.textContent = `Human-transmitter bands: ${STARS.bands_source === 'ladder.yaml' ? 'read from the frozen ladder.yaml' : 'the ladder’s initial list (ladder.yaml not frozen yet)'}. `
            + (F0 < 1100 ? `The axis starts at ${(F0 / 1000).toFixed(1)} GHz so the ${fmt(items.filter((it) => it.peak_freq_mhz < 1100).length)} signals found below 1.1 GHz keep their pins. ` : '')
            + `The teal ridge counts every eliminated signal per 10 MHz (height grows with the square root of the count); pins mark the ${fmt(pins.length)} weirdest. H I and OH lines are drawn as a guide, never as data.`;
    }

    function renderCallouts(items) {
        const host = $('[data-slot="callouts"]');
        host.textContent = '';
        const n = items.length;
        if (!n) {
            for (const t of ['Nothing eliminated yet: the ribbon fills as the run goes.', 'Each pin will carry the rung that eliminated it.', 'These three callouts are computed from the pins, never typed.']) {
                host.appendChild(el('div', { class: 'co blank' }, el('span', { class: 'big', text: '—' }), t));
            }
            return;
        }
        const inBand = (it) => STARS.bands.find(([, a, c]) => it.peak_freq_mhz >= a && it.peak_freq_mhz <= c);
        const hits = items.filter(inBand);
        const perBand = {};
        for (const it of hits) { const k = inBand(it)[0]; perBand[k] = (perBand[k] || 0) + 1; }
        // Ties are stated as ties: "most of them in X" only when X really leads.
        const bandCounts = Object.entries(perBand).sort((a, b) => b[1] - a[1]);
        const bandLead = bandCounts.length && (bandCounts.length === 1 || bandCounts[0][1] > bandCounts[1][1]) ? bandCounts[0] : null;
        const rungCounts = [1, 2, 3, 4, 5].map((k) => [k, items.filter((it) => it.rung === k).length]).filter(([, c]) => c > 0);
        const rungMax = Math.max(...rungCounts.map(([, c]) => c));
        const rungTop = rungCounts.filter(([, c]) => c === rungMax).map(([k]) => k);
        const list = (ks) => (ks.length === 1 ? String(ks[0]) : `${ks.slice(0, -1).join(', ')} and ${ks[ks.length - 1]}`);
        const water = items.filter((it) => it.peak_freq_mhz >= 1420 && it.peak_freq_mhz <= 1720).length;
        host.appendChild(el('div', { class: 'co' }, el('span', { class: 'big', text: `${fmt(hits.length)} of ${fmt(n)}` }),
            'eliminated signals sit inside a ', el('b', { text: 'known human transmitter band' }),
            !hits.length ? '. None so far.'
                : bandLead ? `, most of them in ${bandName(bandLead[0])} (${fmt(bandLead[1])}).`
                    : `, spread evenly across ${fmt(bandCounts.length)} bands.`));
        host.appendChild(rungTop.length === 1
            ? el('div', { class: 'co' }, el('span', { class: 'big', text: `Rung ${rungTop[0]}` }),
                `eliminated the most: ${fmt(rungMax)} of ${fmt(n)}, `, el('b', { text: RUNGS[rungTop[0]].label }), '.')
            : el('div', { class: 'co' }, el('span', { class: 'big', text: `Rungs ${list(rungTop)}` }),
                `tie for the most eliminations, ${fmt(rungMax)} each of ${fmt(n)}.`));
        host.appendChild(el('div', { class: 'co' }, el('span', { class: 'big', text: fmt(water) }),
            'landed in ', el('b', { text: 'the water hole' }), ' (1.42–1.72 GHz), the quiet stretch between the hydrogen and hydroxyl lines.'));
    }

    /* ------------------------------------------------------------ the wall */
    function setFilter(rung) {
        state.filter = rung;
        state.shown = PAGE;
        renderChips();
        renderWall();
        // the Funnel's rung rows are the only buttons in it, in rung order
        $$('button.frow').forEach((b, i) => b.setAttribute('aria-pressed', state.filter === i + 1 ? 'true' : 'false'));
    }
    function filtered() {
        const q = state.query.trim().toLowerCase();
        return state.items.filter((it) => (state.filter ? it.rung === state.filter : true) && (q ? String(it.star).toLowerCase().includes(q) : true));
    }
    function renderChips() {
        const host = $('[data-slot="chips"]');
        host.textContent = '';
        const counts = [0, 0, 0, 0, 0, 0];
        for (const it of state.items) counts[it.rung] += 1;
        host.appendChild(el('button', { type: 'button', class: 'chip', 'aria-pressed': state.filter === null ? 'true' : 'false', onclick: () => setFilter(null) },
            'all ', el('b', { text: fmt(state.items.length) })));
        for (const k of [1, 2, 3, 4, 5]) {
            host.appendChild(el('button', { type: 'button', class: 'chip', style: { '--chip-c': RUNGS[k].c }, 'aria-pressed': state.filter === k ? 'true' : 'false',
                disabled: counts[k] === 0, title: RUNGS[k].label, onclick: () => setFilter(state.filter === k ? null : k) },
            el('i'), `${k} · ${RUNGS[k].stamp} `, el('b', { text: fmt(counts[k]) })));
        }
    }
    function stamp(rung) {
        return el('span', { class: 'stamp', style: { '--tile-c': RUNGS[rung].c } }, el('span', { class: 'rn', text: String(rung) }), RUNGS[rung].stamp);
    }
    function tileNode(it, idx) {
        const fig = it.tile ? el('img', { src: `${it.base}${it.tile}`, alt: `ON-scan waterfall, ${it.star} at ${num(it.peak_freq_mhz) !== null ? it.peak_freq_mhz.toFixed(3) : '?'} MHz`, loading: 'lazy', decoding: 'async', width: 300, height: 232 })
            : el('span', { class: 'nofig', text: it.scans === null ? 'cutout arrives with the daily figures' : 'no cutout kept' });
        return el('button', { type: 'button', class: `tile${REDUCE ? '' : ' fresh'}`, style: { '--tile-c': RUNGS[it.rung].c },
            'aria-label': `${it.star}, ${num(it.peak_freq_mhz) !== null ? it.peak_freq_mhz.toFixed(3) : ''} MHz, eliminated at rung ${it.rung}: ${RUNGS[it.rung].label}. Open its Ledger entry.`,
            onclick: () => openLedger(idx) },
        el('span', { class: 'wf' }, fig), stamp(it.rung),
        el('span', { class: 'cap' },
            el('span', { class: 'row' }, el('span', { class: 't', text: it.star }), el('span', { class: 'w', text: num(it.weirdness) !== null ? it.weirdness.toFixed(1) : '' })),
            el('span', { class: 'row' }, el('span', { class: 'mhz', text: num(it.peak_freq_mhz) !== null ? `${it.peak_freq_mhz.toFixed(3)} MHz` : '' }), el('span', { class: 'mhz', text: it.band ? `${it.band}-band` : '' })),
            el('span', { class: 'why', text: it.reason || `eliminated at rung ${it.rung}: ${RUNGS[it.rung].label}` })));
    }
    let reviewArt = null;
    function goldSlot() {
        const s = state.snap;
        const n = s ? num(s.funnel.under_review) : null;
        if (n && n > 0) return reviewTile(n);
        return el('div', { class: 'tile slot-open' },
            el('span', { class: 'wf' }, el('span', null, 'nothing yet', el('small', { text: 'anything that passes all five rungs pins here' }))),
            el('span', { class: 'cap' }, el('span', { class: 'row' }, el('span', { class: 't', text: 'Still unexplained' }), el('span', { class: 'open-tag', text: 'OPEN' })),
                el('span', { class: 'why', text: s ? `${fmt(n)} under private review` : 'waiting for numbers' })));
    }
    function reviewTile(n) {
        const cv = el('canvas', { width: 640, height: 300, 'aria-hidden': 'true' });
        const node = el('figure', { class: 'review', 'aria-label': `${fmt(n)} signal${n === 1 ? '' : 's'} under private review. No star, frequency or date is shown.` },
            el('div', { class: 'viz' }, cv, el('div', { class: 'frost' }),
                el('div', { class: 'seal' }, el('span', { class: 'seal-dot' }), 'UNDER PRIVATE REVIEW'),
                el('div', { class: 'redact', 'aria-hidden': 'true' }, 'star', el('i', { style: { width: '70px' } }), el('br'), 'freq', el('i', { style: { width: '84px' } }), el('br'), 'date', el('i', { style: { width: '56px' } }))),
            el('figcaption', { class: 'rpanel' },
                el('h3', { text: `${fmt(n)} signal${n === 1 ? '' : 's'} passed all five rungs` }),
                el('ol', { class: 'steps' },
                    el('li', null, el('i'), 'Re-checked on full-resolution data'),
                    el('li', null, el('i'), 'A second reviewer agrees it passes'),
                    el('li', null, el('i'), 'Re-observation requested'),
                    el('li', null, el('i'), 'Public release, with everything')),
                el('p', { class: 'note standing', text: 'Some signals under review may be planted test signals; we check each one first.' }),
                el('p', { class: 'note', text: 'The waterfall above is generated art, not the signal. If review eliminates it, it joins the Ledger like any other, with the step and the reason.' })));
        reviewArt = cv;
        return node;
    }
    // Generated art for the review tile, seeded: a breathing carrier with two sidebands.
    function runReviewArt(cv) {
        const g = cv.getContext('2d'), W = cv.width, H = cv.height;
        const rnd = mulberry32(fnv1a('under-review'));
        const img = g.createImageData(W, 1);
        let t = 0, visible = false, raf = 0;
        const col = (v) => { v = Math.max(0, Math.min(1, v)); return [255 * Math.min(1, v * 1.8), 255 * Math.min(1, Math.max(0, (v - 0.4) * 1.8)), 255 * Math.min(1, v * 0.9 * (1 - v) + 0.04)]; };
        function row() {
            const cx = W * 0.42 + Math.sin(t / 150) * W * 0.16, breathe = 0.6 + 0.4 * Math.sin(t / 23);
            for (let x = 0; x < W; x++) {
                let v = rnd() * 0.16 + (rnd() < 0.003 ? 0.35 : 0);
                const d = Math.abs(x - cx); if (d < 3.5) v += 0.95 * breathe * (1 - d / 3.5);
                const d2 = Math.abs(x - (cx + 34)); if (d2 < 2) v += 0.45 * breathe * (1 - d2 / 2);
                const d3 = Math.abs(x - (cx + 68)); if (d3 < 2) v += 0.3 * breathe * (1 - d3 / 2);
                const c = col(v), i = x * 4; img.data[i] = c[0]; img.data[i + 1] = c[1]; img.data[i + 2] = c[2]; img.data[i + 3] = 255;
            }
        }
        for (let k = 0; k < H; k++) { row(); g.putImageData(img, 0, k); t++; } // the designed still: a full field
        if (REDUCE) return;
        function step() {
            raf = 0;
            if (!document.body.contains(cv)) return;
            g.drawImage(cv, 0, 1, W, H - 1, 0, 0, W, H - 1); row(); g.putImageData(img, 0, H - 1); t++;
            tickFrame();
            if (visible) raf = requestAnimationFrame(step);
        }
        watchVisibility(cv, (v) => { visible = v; if (v && !raf) raf = requestAnimationFrame(step); });
    }
    function renderWall() {
        const host = $('[data-slot="wall"]');
        host.textContent = '';
        host.appendChild(goldSlot());
        if (reviewArt && document.body.contains(reviewArt)) { runReviewArt(reviewArt); reviewArt = null; }
        state.view = filtered();
        if (!state.view.length) {
            host.appendChild(el('p', { class: 'wall-empty', text: state.items.length
                ? 'No eliminated signal matches that filter.'
                : 'Nothing eliminated yet. The Wall fills as the run goes; figures arrive once a day.' }));
        }
        state.view.slice(0, state.shown).forEach((it, i) => host.appendChild(tileNode(it, i)));
        const more = $('[data-action="more"]');
        const left = state.view.length - state.shown;
        more.hidden = left <= 0;
        more.textContent = `Show more (${fmt(Math.max(0, left))} left)`;
    }

    /* ------------------------------------------------------------ the ledger */
    function openLedgerById(id) {
        state.filter = null; state.query = ''; const find = $('[data-slot="find"]'); if (find) find.value = '';
        state.view = filtered();
        const i = state.view.findIndex((it) => it.id === id);
        if (i >= 0) openLedger(i);
    }
    function fingerprint(scans) {
        if (!Array.isArray(scans) || !scans.length) return el('p', { class: 'lg-why', text: 'The six-scan fingerprint arrives with the daily figures.' });
        const snrs = scans.map((s) => (num(s.snr) === null ? 0 : Math.max(0, s.snr)));
        const top = Math.log10(1 + Math.max(100, ...snrs));
        const h = (v) => Math.max(2, 56 * Math.log10(1 + v) / top);
        const bars = el('div', { class: 'fpx', role: 'img', 'aria-label': `Six-scan fingerprint: ${scans.map((s) => `${s.role} SNR ${num(s.snr) === null ? 'n/a' : s.snr}`).join(', ')}` },
            el('span', { class: 'thr', style: { bottom: `${h(8).toFixed(1)}px` } }),
            scans.map((s, i) => el('i', { class: `${s.role === 'ON' ? 'on' : 'off'}${s.present ? ' present' : ''}`, style: { height: `${h(snrs[i]).toFixed(1)}px` }, title: `${s.role} ${i + 1}: SNR ${s.snr}` })));
        const line = scans.map((s) => `${s.role} ${num(s.snr) === null ? '—' : (s.snr >= 100 ? fmt(Math.round(s.snr)) : s.snr.toFixed(1))}`).join(' → ');
        return el('div', null, bars, el('p', { class: 'fp-snr', text: line }), el('p', { class: 'fp-snr', text: 'Bar height: log signal-to-noise. Dashed: the SNR 8 detection line rung 1 uses.' }));
    }
    function openLedger(i) {
        const dlg = $('#ledger');
        const it = state.view[i];
        if (!it || !dlg) return;
        state.ledger = i;
        const f = num(it.peak_freq_mhz);
        $('[data-slot="lg-id"]').textContent = it.id;
        $('[data-slot="lg-title"]').textContent = `${it.star} · ${f !== null ? f.toFixed(3) : '?'} MHz`;
        const st = $('[data-slot="lg-stamp"]'); st.textContent = '';
        st.appendChild(el('span', { class: 'stamp', style: { '--tile-c': RUNGS[it.rung].c } }, el('span', { class: 'rn', text: String(it.rung) }), `eliminated at rung ${it.rung} · ${RUNGS[it.rung].label}`));
        const fig = $('[data-slot="lg-figure"]'); fig.textContent = '';
        if (it.figure) {
            fig.append(el('img', { src: `${it.base}${it.figure}`, alt: `${it.star} ${f !== null ? f.toFixed(3) : ''} MHz: ON waterfall, OFF waterfall, and the integrated spectrum`, width: 1620, height: 504 }),
                el('figcaption', { text: 'Left: the ON-scan waterfall. Middle: the OFF scan at the same frequencies. Right: integrated power, ON against OFF, with the weirdness axes. As rendered by the survey.' }));
        } else {
            fig.appendChild(el('p', { class: 'nofig', text: it.scans === null ? 'The full figure arrives with the daily export.' : 'No figure was kept for this signal.' }));
        }
        const kv = el('dl', { class: 'kv' });
        const add = (k, v) => { if (v !== '' && v !== null && v !== undefined) kv.append(el('dt', { text: k }), el('dd', { text: v })); };
        add('star', it.star); add('band', it.band ? `${it.band}-band` : ''); add('shape', SHAPES[it.shape] || it.shape);
        add('frequency', f !== null ? `${f.toFixed(6)} MHz` : ''); add('drift', num(it.drift_rate_hz_s) !== null ? `${it.drift_rate_hz_s.toFixed(3)} Hz/s` : '');
        add('weirdness', num(it.weirdness) !== null ? it.weirdness.toFixed(2) : ''); add('decided', it.decided_utc ? utcStamp(it.decided_utc) : '');
        const sig = $('[data-slot="lg-signal"]'); sig.textContent = ''; sig.appendChild(kv);
        const fp = $('[data-slot="lg-fp"]'); fp.textContent = ''; fp.appendChild(fingerprint(it.scans));
        const lad = $('[data-slot="lg-ladder"]'); lad.textContent = '';
        lad.append(el('div', { class: 'lg-rungs', role: 'img', 'aria-label': `Passed rungs 1 to ${it.rung - 1}, eliminated at rung ${it.rung}` },
            [1, 2, 3, 4, 5].map((k) => el('span', { class: `rung ${k < it.rung ? 'pass' : k === it.rung ? `r${k}` : 'dim'}`, text: k < it.rung ? '✓' : String(k), title: k < it.rung ? `passed rung ${k}` : k === it.rung ? `eliminated at rung ${k}` : `rung ${k} not reached` }))),
        el('p', { class: 'lg-why', text: `Eliminated at rung ${it.rung}: ${it.reason || RUNGS[it.rung].label}` }));
        $('[data-slot="lg-plain"]').textContent = RUNGS[it.rung].plain;
        $('[data-action="lg-prev"]').disabled = i <= 0;
        $('[data-action="lg-next"]').disabled = i >= state.view.length - 1;
        const hash = `#signal=${encodeURIComponent(it.id)}`;
        if (window.location.hash !== hash) history.replaceState(null, '', hash);
        if (!dlg.open) { if (typeof dlg.showModal === 'function') dlg.showModal(); else dlg.setAttribute('open', ''); }
    }
    function initLedger() {
        const dlg = $('#ledger');
        $('[data-action="lg-close"]').addEventListener('click', () => dlg.close());
        $('[data-action="lg-prev"]').addEventListener('click', () => openLedger(state.ledger - 1));
        $('[data-action="lg-next"]').addEventListener('click', () => openLedger(state.ledger + 1));
        dlg.addEventListener('click', (e) => { if (e.target === dlg) dlg.close(); });
        dlg.addEventListener('keydown', (e) => {
            if (e.key === 'ArrowLeft' && state.ledger > 0) openLedger(state.ledger - 1);
            if (e.key === 'ArrowRight' && state.ledger < state.view.length - 1) openLedger(state.ledger + 1);
        });
        dlg.addEventListener('close', () => { if (window.location.hash.startsWith('#signal=')) history.replaceState(null, '', window.location.pathname + window.location.search); });
    }

    /* ------------------------------------------------------------ heartbeat */
    function renderHeartbeat() {
        const s = state.snap;
        const p = s ? s.progress : {};
        const t = totals();
        const ring = $('[data-slot="ring"]');
        const share = num(t.stars_done) !== null && t.stars_total ? Math.min(1, t.stars_done / t.stars_total) : 0;
        requestAnimationFrame(() => ring.setAttribute('stroke-dashoffset', (540.35 * (1 - share)).toFixed(1)));
        const hb = s && s.heartbeat;
        const idx = hb && Number.isInteger(hb.scan_idx) ? Math.max(0, Math.min(5, hb.scan_idx)) : null;
        $('[data-slot="now-star"]').textContent = hb && hb.star ? `${hb.star}${idx !== null ? ` · scan ${idx + 1} of 6` : ''}` : '—';
        $$('[data-slot="lights"] .lt').forEach((l, i) => { l.classList.toggle('act', idx === i); l.classList.toggle('done', idx !== null && i < idx); });
        const bytes = num(p.bytes_streamed);
        $('[data-slot="streamed"]').textContent = bytes === null ? '—' : bytes >= 1e12 ? `${(bytes / 1e12).toFixed(2)} TB` : `${(bytes / 1e9).toFixed(1)} GB`;
        $('[data-slot="cad-done"]').textContent = num(p.cadences_done) === null ? '—' : `${fmt(p.cadences_done)} of ${fmt(p.cadences_total)}`;
        $('[data-slot="cad-parked"]').textContent = fmt(p.cadences_parked);
        $('[data-slot="cad-incomplete"]').textContent = fmt(p.cadences_incomplete);
        const upd = $('[data-slot="heart-updated"]');
        upd.textContent = hb && hb.updated_utc ? `heartbeat ${utcStamp(hb.updated_utc)}${state.source !== 'demo' ? ` · ${ago(Date.now() - Date.parse(hb.updated_utc))} ago` : ''}` : '';
        drawSpark(s && Array.isArray(s.speed_series) ? s.speed_series.filter((v) => num(v) !== null) : []);
    }
    function drawSpark(series) {
        const cv = $('[data-slot="spark"]');
        const dpr = Math.min(window.devicePixelRatio || 1, 2);
        const w = Math.max(200, Math.round((cv.getBoundingClientRect().width || 600) * dpr)), h = Math.round(58 * dpr);
        cv.width = w; cv.height = h;
        const g = cv.getContext('2d');
        g.clearRect(0, 0, w, h);
        g.font = `${11 * dpr}px "JetBrains Mono", monospace`;
        if (series.length < 2) { g.fillStyle = '#8aa3b5'; g.fillText('no downloads logged yet', 8 * dpr, h / 2 + 4 * dpr); return; }
        const lo = Math.min(...series), hi = Math.max(...series);
        const pad = Math.max(0.05, (hi - lo) * 0.25), y0 = lo - pad, y1 = hi + pad;
        const X = (i) => 6 * dpr + i / (series.length - 1) * (w - 120 * dpr), Y = (v) => h - 6 * dpr - (v - y0) / (y1 - y0) * (h - 12 * dpr);
        g.strokeStyle = '#1d2838'; g.lineWidth = 1; g.beginPath(); g.moveTo(X(0), Y(lo)); g.lineTo(X(series.length - 1), Y(lo)); g.moveTo(X(0), Y(hi)); g.lineTo(X(series.length - 1), Y(hi)); g.stroke();
        g.beginPath(); series.forEach((v, i) => (i ? g.lineTo(X(i), Y(v)) : g.moveTo(X(i), Y(v))));
        g.strokeStyle = '#7fe0d0'; g.lineWidth = 2 * dpr; g.stroke();
        g.lineTo(X(series.length - 1), h); g.lineTo(X(0), h); g.closePath();
        const gr = g.createLinearGradient(0, 0, 0, h); gr.addColorStop(0, 'rgba(127,224,208,.3)'); gr.addColorStop(1, 'rgba(127,224,208,0)'); g.fillStyle = gr; g.fill();
        g.fillStyle = '#eef4f8'; g.font = `600 ${15 * dpr}px "JetBrains Mono", monospace`;
        g.fillText(`${series[series.length - 1].toFixed(2)} MB/s`, w - 108 * dpr, h / 2);
        g.fillStyle = '#8aa3b5'; g.font = `${10 * dpr}px "JetBrains Mono", monospace`;
        g.fillText(`range ${lo.toFixed(2)}–${hi.toFixed(2)}`, w - 108 * dpr, h / 2 + 16 * dpr);
    }

    /* ------------------------------------------------------------ page chrome: reveal + spine */
    function initChrome() {
        const secs = $$('.sec');
        if (!REDUCE && 'IntersectionObserver' in window) {
            const io = new IntersectionObserver((entries) => { for (const e of entries) if (e.isIntersecting) { e.target.classList.add('in'); io.unobserve(e.target); } }, { rootMargin: '0px 0px -8% 0px' });
            secs.forEach((s) => { s.classList.add('reveal'); io.observe(s); });
            // failsafe: a reveal must never leave content invisible (throttled tabs, odd scrollers)
            setTimeout(() => secs.forEach((s) => s.classList.add('in')), 4000);
        }
        const spine = $('.spine i');
        let pending = false;
        const update = () => { pending = false; const max = document.documentElement.scrollHeight - window.innerHeight; spine.style.setProperty('--grow', `${max > 0 ? (window.scrollY / max * 100).toFixed(1) : 0}%`); };
        window.addEventListener('scroll', () => { if (!pending) { pending = true; requestAnimationFrame(update); } }, { passive: true });
        update();
        $('[data-action="more"]').addEventListener('click', () => { state.shown += PAGE; renderWall(); });
        const find = $('[data-slot="find"]');
        find.addEventListener('input', () => { state.query = find.value; state.shown = PAGE; renderWall(); });
        // the fingerprint guides in "how to read" (drawn as a guide, not data)
        for (const host of $$('.fp-bars')) {
            host.append(el('span', { class: 'thr' }), ...host.dataset.fp.split(',').map((v, i) => el('i', { class: i % 2 ? 'off' : 'on', style: { height: `${v}px` } })));
        }
    }

    /* ------------------------------------------------------------ boot */
    function renderAll() {
        renderBadges(); renderHero(); renderFunnel(); renderChips(); renderWall(); renderSpectrum(); renderHeartbeat();
        if (sky.ready) sky.redraw();
    }
    async function refresh(first) {
        const got = await loadSnapshot();
        if (!first && got.source === 'demo' && state.source !== 'demo' && state.snap) return; // keep the last good live numbers
        const changedSource = got.source !== state.source;
        state.snap = got.snap; state.source = got.source; state.reason = got.reason; state.loadedAt = Date.now();
        state.searched = parseSearched(got.snap && got.snap.progress.searched);
        if (first || changedSource) state.figures = await loadFigures(got.source);
        state.items = mergeItems(state.figures, state.snap);
        renderAll();
    }
    async function boot() {
        if (!STARS || !Array.isArray(STARS.stars)) {
            $('[data-slot="status-text"]').textContent = 'stars.js is missing: run python scripts/bake_stars.py';
            return;
        }
        initChrome(); initLedger(); initSky();
        await refresh(true);
        const m = window.location.hash.match(/^#signal=(.+)$/);
        if (m) openLedgerById(decodeURIComponent(m[1]));
        setInterval(() => { if (!document.hidden) refresh(false); }, POLL_MS);
        // the badge's "as of" ages while the tab sits open: re-judge staleness each minute
        setInterval(() => { if (!document.hidden && state.snap) renderBadges(); }, 60000);
        console.log('%c● listening %c seti-hunter · 1,133 stars · eliminated, never hidden', 'color:#7fe0d0;font-weight:700', 'color:#c9a86a');
    }

    // For checks and for the curious: the page's state as text.
    window.render_state_to_text = () => JSON.stringify({
        source: state.source, reason: state.reason, badge: modeInfo().text, as_of_utc: state.snap && state.snap.as_of_utc,
        funnel: state.snap && state.snap.funnel, items: state.items.length, searched: state.searched.size,
        reduced_motion: REDUCE, frames: window.__listenFrames,
    });

    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot); else boot();
})();
