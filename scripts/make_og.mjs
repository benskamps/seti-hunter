// Render site/listen/og.png (1200x630) from scripts/og/og.html.
//
//   python scripts/serve_listen.py --site ../brokenbranchdevwebsite --port 8767   (in another shell)
//   node scripts/make_og.mjs --site ../brokenbranchdevwebsite --base http://127.0.0.1:8767
//
// Playwright comes from the site checkout (its devDependency).
// Then shrink it to a 256-colour PNG (~180 KB, like the other og cards):
//   python -c "from PIL import Image; Image.open('site/listen/og.png').convert('RGB').quantize(256).save('site/listen/og.png', optimize=True)"
import { createRequire } from 'node:module';
import { resolve } from 'node:path';

const arg = (name, dflt) => { const i = process.argv.indexOf(`--${name}`); return i > 0 ? process.argv[i + 1] : dflt; };
const SITE = resolve(arg('site', '../brokenbranchdevwebsite'));
const BASE = arg('base', 'http://127.0.0.1:8767');
const { chromium } = createRequire(`${SITE}/package.json`)('playwright');

const browser = await chromium.launch();
try {
  const page = await browser.newPage({ viewport: { width: 1200, height: 630 }, deviceScaleFactor: 1 });
  await page.goto(`${BASE}/__og/og.html`, { waitUntil: 'networkidle' });
  await page.waitForSelector('body[data-ready="1"]');
  await page.evaluate(() => document.fonts.ready);
  await page.screenshot({ path: resolve('site/listen/og.png'), type: 'png' });
  console.log('wrote site/listen/og.png');
} finally {
  await browser.close();
}
