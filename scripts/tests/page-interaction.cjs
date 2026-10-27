// Run with Playwright in NODE_PATH and scripts/tests/fixture-server.py running.
// Exercises the published home page and embedded viewer through real UI events.
// --network uses the published site with no asset rewrites or blocked requests.
const { chromium } = require('playwright');
const fs = require('node:fs/promises');
const path = require('node:path');
const assert = require('node:assert/strict');

const root = path.resolve(__dirname, '../..');
const network = process.argv.includes('--network');
const base = process.env.PHYSAG_TEST_URL || (network ? 'https://supra-3d.github.io/PhysAg3D/' : 'http://127.0.0.1:8876/PhysAg3D/');
const output = process.env.PHYSAG_TEST_OUTPUT || 'D:/code/PhysAg3D-audit/page-checks';
const reports = [];

async function fixtures(context) {
  await context.route('**/viewer/resource-urls.js', async route => {
    const source = await fs.readFile(path.join(root, 'viewer/resource-urls.js'), 'utf8');
    const body = source.replace(
      /const mediaRoot\s*=\s*new URL\(`https:\/\/(?:media\.githubusercontent\.com|huggingface\.co)\/[^`]+`\);/,
      `const mediaRoot = new URL(${JSON.stringify(base + '__fixtures/')});`);
    assert.notEqual(body, source, 'Could not replace the published asset host with the fixture server');
    await route.fulfill({ contentType: 'text/javascript', body });
  });
  await context.route(/^https:\/\/(?:media\.githubusercontent\.com|huggingface\.co)\//, async route => {
    const url = new URL(route.request().url());
    if (/\.mp4$/i.test(url.pathname)) return route.abort();
    const relative = url.hostname === 'huggingface.co'
      ? url.pathname.match(/^\/datasets\/supra3d\/physag3d-web-assets\/resolve\/[^/]+\/(.+)$/)?.[1]
      : url.pathname.split('/website/')[1];
    if (!relative) return route.abort();
    const filename = path.resolve(root, 'website', decodeURIComponent(relative));
    if (!filename.startsWith(path.join(root, 'website') + path.sep)) return route.abort();
    try { await route.fulfill({ path: filename }); } catch { await route.abort().catch(() => {}); }
  });
  await context.route('**/*.mp4', route => route.abort());
}

async function viewer(page, expected) {
  const element = await page.locator('#asset-dialog iframe').elementHandle();
  assert.ok(element, 'Expected an embedded viewer');
  const frame = await element.contentFrame();
  assert.ok(frame);
  await frame.waitForFunction(() => window.__viewer?.ready || document.getElementById('viewer-boot-retry')?.hidden === false, null, { timeout: network ? 180000 : 90000 });
  assert.equal(await frame.evaluate(() => window.__viewer?.ready), true, await frame.locator('#viewer-boot-label').textContent());
  assert.equal(await frame.evaluate(() => window.__viewer.assetId), expected);
  await page.waitForFunction(() => document.querySelector('#asset-dialog iframe')?.dataset.ready === 'true');
  assert.equal(await page.locator('#explore-loading').isVisible(), false);
  return frame;
}

async function operate(frame) {
  await frame.locator('#controls-toggle').click();
  await frame.locator('.sidebar').waitFor({ state: 'visible' });
  const slider = frame.locator('.sidebar .joint-slider').first();
  await slider.waitFor({ state: 'visible' });
  const before = await frame.evaluate(() => {
    const control = window.__viewer.adapter.controls[0];
    return { name: control.name, value: window.__viewer.adapter.values[control.name], min: control.range[0], max: control.range[1] };
  });
  const key = before.value > (before.min + before.max) / 2 ? 'Home' : 'End';
  await slider.focus();
  await slider.press(key);
  const after = await frame.evaluate(name => window.__viewer.adapter.values[name], before.name);
  assert.ok(Math.abs(after - before.value) > 1e-8, 'Keyboard slider operation did not change the model control');
  assert.ok(Math.abs(after - (key === 'Home' ? before.min : before.max)) < 1e-6);
  return { control: before.name, before: before.value, after, key };
}

async function escape(page) {
  await page.keyboard.press('Escape');
  await page.waitForFunction(() => !document.getElementById('asset-dialog').open);
  assert.equal(await page.locator('#asset-dialog iframe').count(), 0);
  assert.equal(await page.evaluate(() => document.body.style.overflow), '');
}

async function noHorizontalOverflow(page, frame) {
  for (const [name, target] of [['home', page], ['viewer', frame]]) {
    const dimensions = await target.evaluate(() => ({ viewport: innerWidth, document: document.documentElement.scrollWidth, body: document.body.scrollWidth }));
    assert.ok(dimensions.document <= dimensions.viewport + 1 && dimensions.body <= dimensions.viewport + 1,
      name + ' horizontal overflow: ' + JSON.stringify(dimensions));
  }
}

(async () => {
  await fs.mkdir(output, { recursive: true });
  const browser = await chromium.launch({ channel: process.env.PHYSAG_BROWSER || 'msedge', headless: true });
  try {
    for (const mobile of [false, true]) {
      const context = await browser.newContext({ viewport: mobile ? { width: 390, height: 844 } : { width: 1440, height: 1000 }, isMobile: mobile, hasTouch: mobile, reducedMotion: 'reduce' });
      if (!network) await fixtures(context);
      const page = await context.newPage(), errors = [], api = [];
      page.on('pageerror', error => errors.push(error.message));
      page.on('request', request => { if (/\/api\//.test(request.url())) api.push(request.url()); });
      const variant = mobile ? 'mobile' : 'desktop';
      try {
        await page.goto(base, { waitUntil: 'domcontentloaded' });
        await page.locator('.gallery-card-open').first().waitFor();
        for (const [feature, id] of mobile ? [['phone', 'studio-img_020']] : [['camera', 'extra-img_145'], ['phone', 'studio-img_020']]) {
          await page.locator(`[data-case="${feature}"]`).click();
          const frame = await viewer(page, id), result = await operate(frame);
          await noHorizontalOverflow(page, frame);
          const box = await frame.locator('.sidebar .joint-slider').first().boundingBox();
          assert.ok(box && box.width > 30 && box.height > 0, 'Slider is not laid out');
          await page.screenshot({ path: path.join(output, `${variant}-${feature}-controls.png`) });
          await escape(page);
          reports.push({ case: `${variant}-${feature}`, ok: true, ...result });
        }
        // The same Studio must reopen from a real Gallery card after Escape.
        await page.locator('#asset-search').fill('img_025');
        await page.locator('.gallery-card-open[data-gallery-id="studio-img_025"]').click();
        const galleryFrame = await viewer(page, 'studio-img_025'), galleryResult = await operate(galleryFrame);
        await noHorizontalOverflow(page, galleryFrame);
        await page.screenshot({ path: path.join(output, `${variant}-gallery-controls.png`) });
        await escape(page);
        reports.push({ case: `${variant}-gallery-reopen`, ok: true, ...galleryResult });

        // Deterministic delayed-download cancellation needs a fixture route;
        // real-network mode leaves every request untouched.
        if (!mobile && !network) {
          let release, entered;
          const held = new Promise(resolve => { release = resolve; });
          const requested = new Promise(resolve => { entered = resolve; });
          let blockNextCamera = true;
          await context.route('**/__fixtures/**', async route => {
            if (blockNextCamera && /\/img_145\/.*\.glb(?:\?|$)/.test(route.request().url())) {
              blockNextCamera = false; entered(); await held;
            }
            await route.continue().catch(() => {});
          });
          await page.locator('[data-case="camera"]').click();
          let requestTimeout;
          try {
            await Promise.race([requested, new Promise((_, reject) => {
              requestTimeout = setTimeout(() => reject(new Error('Delayed camera download was not reached')), 30000);
            })]);
          } finally { clearTimeout(requestTimeout); }
          assert.equal(await page.locator('#explore-loading').isVisible(), true);
          await page.locator('#asset-dialog .dialog-close').click();
          await page.waitForFunction(() => !document.getElementById('asset-dialog').open);
          assert.equal(await page.locator('#asset-dialog iframe').count(), 0);
          await page.locator('[data-case="phone"]').click();
          release();
          const next = await viewer(page, 'studio-img_020');
          assert.equal(await page.locator('#asset-dialog iframe').count(), 1);
          await next.locator('#scene').focus(); await escape(page);
          reports.push({ case: 'close-during-load-and-reopen', ok: true });
        }
        assert.deepEqual(errors, []); assert.deepEqual(api, []);
      } catch (error) {
        reports.push({ case: variant, ok: false, error: error.message, errors, api });
        await page.screenshot({ path: path.join(output, `${variant}-failure.png`) }).catch(() => {});
      } finally { await context.close(); }
    }
  } finally { await browser.close(); }
  await fs.writeFile(path.join(output, 'page-interaction.json'), JSON.stringify(reports, null, 2));
  reports.forEach(row => console.log(JSON.stringify(row)));
  assert.equal(reports.filter(row => !row.ok).length, 0, 'Page interaction tests failed');
})().catch(error => { console.error(error); process.exitCode = 1; });
