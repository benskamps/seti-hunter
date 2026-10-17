// Drive /listen/ in headless Chromium and check the plan's B5 verification list.
//
//   python scripts/serve_listen.py --site ../brokenbranchdevwebsite --port 8767   (in another shell)
//   node scripts/drive_listen.mjs --site ../brokenbranchdevwebsite --base http://127.0.0.1:8767 [--out shots/]
//
// Playwright comes from the site checkout (it is the site's devDependency), so
// this repo carries no node_modules. Exit 0 = every check passed; the JSON
// report names each check, what was measured, and whether it passed.
//
// Checks (Plan B, Task B5, step 3, and Review Focus 1 and 5):
//   redaction       fixture snapshot: the pending and survivor signals' star, frequency
//                   and id are absent from innerText and from the HTML; a public star
//                   from the same fixture IS present (the check can fail)
//   no-hscroll      desktop and 375 px: scrollWidth <= innerWidth, and no element's box
//                   crosses the right edge (tokens.css hides overflow-x, so scrollWidth
//                   alone could not fail)
//   reduced-motion  with prefers-reduced-motion: reduce the frame counter is fixed for 2 s
//                   with the sky and the review tile on screen; without it, it moves
//   fallbacks       stale gist -> STALE badge; empty gist + last good -> STALE with the
//                   real numbers; empty gist + nothing cached -> DEMO badge; never "0"
//                   standing in for a missing number
//   console         no errors in any non-error mode
import { createRequire } from 'node:module';
import { mkdirSync } from 'node:fs';
import { resolve } from 'node:path';

const arg = (name, dflt) => { const i = process.argv.indexOf(`--${name}`); return i > 0 ? process.argv[i + 1] : dflt; };
const SITE = resolve(arg('site', '../brokenbranchdevwebsite'));
const BASE = arg('base', 'http://127.0.0.1:8767');
const OUT = resolve(arg('out', 'shots'));
mkdirSync(OUT, { recursive: true });
const { chromium } = createRequire(`${SITE}/package.json`)('playwright');

const PENDING = ['HIP4436', '2017.418', 'HIP4436_S_57803.9344_weird_t0412'];
const SURVIVOR = ['HIP17147', '1388.264', 'HIP17147_L_57523.8029_chirp_t0088'];
const results = [];
const check = (name, pass, detail) => { results.push({ name, pass: !!pass, detail }); };
const mode = (m) => fetch(`${BASE}/__mode?m=${m}`).then((r) => r.json());
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function open(browser, { width, height = 900, reduced = false, storage = null }) {
  const ctx = await browser.newContext({ viewport: { width, height }, reducedMotion: reduced ? 'reduce' : 'no-preference', deviceScaleFactor: 1 });
  if (storage) await ctx.addInitScript((s) => { try { localStorage.setItem('listen:last-snapshot', s); } catch (e) { /* */ } }, storage);
  const page = await ctx.newPage();
  const errors = [];
  page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });
  page.on('pageerror', (e) => errors.push(String(e)));
  await page.goto(`${BASE}/listen/`, { waitUntil: 'networkidle' });
  await sleep(1800);
  return { ctx, page, errors };
}

const overflow = (page) => page.evaluate(() => {
  const W = window.innerWidth, over = [];
  for (const n of document.querySelectorAll('body *')) {
    const r = n.getBoundingClientRect();
    if (r.width && r.right > W + 1 && !n.closest('.spec-scroll') && getComputedStyle(n).position !== 'fixed') over.push(`${n.className || n.tagName}:${Math.round(r.right)}`);
  }
  return { W, scrollWidth: document.documentElement.scrollWidth, over: over.slice(0, 8) };
});

const browser = await chromium.launch();
try {
  // ---- fixture: redaction, layout, console, at desktop and phone width
  await mode('fixture');
  let lastGood = null;
  for (const width of [1440, 375]) {
    const { ctx, page, errors } = await open(browser, { width });
    const text = await page.evaluate(() => document.body.innerText);
    const html = await page.content();
    const leaked = [...PENDING, ...SURVIVOR].filter((n) => text.includes(n) || html.includes(n));
    check(`redaction @${width}`, leaked.length === 0 && text.includes('GJ411'), { leaked, publicStarShown: text.includes('GJ411') });
    const o = await overflow(page);
    check(`no-hscroll @${width}`, o.scrollWidth <= o.W && o.over.length === 0, o);
    check(`console clean (fixture) @${width}`, errors.length === 0, errors);
    check(`review tile shown @${width}`, await page.locator('.review').count() === 1, {});
    await page.screenshot({ path: `${OUT}/listen-fixture-${width}.png`, fullPage: true });
    lastGood = await page.evaluate(() => localStorage.getItem('listen:last-snapshot'));
    await ctx.close();
  }

  // ---- reduced motion: the frame counter must not move; and must move without it
  for (const reduced of [true, false]) {
    const { ctx, page } = await open(browser, { width: 1440, reduced });
    await page.locator('#sky').scrollIntoViewIfNeeded();
    await sleep(600);
    const a = await page.evaluate(() => window.__listenFrames);
    await sleep(2000);
    const b = await page.evaluate(() => window.__listenFrames);
    if (reduced) {
      check('reduced-motion: no rAF loop (sky)', a === b, { before: a, after: b });
      await page.screenshot({ path: `${OUT}/listen-reduced-sky.png` });
      await page.locator('#wall').scrollIntoViewIfNeeded();
      await sleep(600);
      const c = await page.evaluate(() => window.__listenFrames);
      await sleep(2000);
      const d = await page.evaluate(() => window.__listenFrames);
      check('reduced-motion: no rAF loop (review tile)', c === d, { before: c, after: d });
      const still = await page.evaluate(() => { const cv = document.querySelector('.review canvas'); const px = cv.getContext('2d').getImageData(0, 0, cv.width, cv.height).data; let lit = 0; for (let i = 0; i < px.length; i += 4) if (px[i] > 60) lit++; return lit; });
      check('reduced-motion: review tile has a designed still (not blank)', still > 500, { litPixels: still });
      await page.screenshot({ path: `${OUT}/listen-reduced-wall.png` });
    } else {
      check('motion on: the frame counter does move (the check can fail)', b > a + 10, { before: a, after: b });
    }
    await ctx.close();
  }

  // ---- fallbacks (Review Focus 1)
  await mode('stale');
  {
    const { ctx, page, errors } = await open(browser, { width: 1440 });
    const badge = await page.locator('[data-slot="badge"]').first().textContent();
    check('stale gist -> STALE badge', /^STALE/.test(badge), { badge });
    check('console clean (stale)', errors.length === 0, errors);
    await ctx.close();
  }
  await mode('empty');
  {
    const { ctx, page, errors } = await open(browser, { width: 1440, storage: lastGood });
    const badge = await page.locator('[data-slot="badge"]').first().textContent();
    const flagged = await page.locator('[data-count="flagged"]').textContent();
    check('empty gist + last good -> STALE with real numbers', /^STALE/.test(badge) && flagged === '12', { badge, flagged });
    check('console clean (empty, cached)', errors.length === 0, errors);
    await ctx.close();
  }
  {
    const { ctx, page, errors } = await open(browser, { width: 1440 });
    const badge = await page.locator('[data-slot="badge"]').first().textContent();
    const flagged = await page.locator('[data-count="flagged"]').textContent();
    check('empty gist + nothing cached -> DEMO badge, demo numbers', /^DEMO DATA: THE RUN HASN.T STARTED/.test(badge) && flagged === '24', { badge, flagged });
    check('console clean (demo)', errors.length === 0, errors);
    await page.screenshot({ path: `${OUT}/listen-demo-1440.png`, fullPage: true });
    await ctx.close();
  }
  {
    const { ctx, page, errors } = await open(browser, { width: 375 });
    const o = await overflow(page);
    check('no-hscroll @375 (demo)', o.scrollWidth <= o.W && o.over.length === 0, o);
    check('console clean (demo) @375', errors.length === 0, errors);
    await page.screenshot({ path: `${OUT}/listen-demo-375.png`, fullPage: true });
    await ctx.close();
  }
} finally {
  await browser.close();
  await mode('empty').catch(() => {});
}

console.log(JSON.stringify(results, null, 1));
const failed = results.filter((r) => !r.pass);
console.log(`${results.length - failed.length}/${results.length} checks passed`);
process.exit(failed.length ? 1 : 0);
