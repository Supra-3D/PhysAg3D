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
const demoIds = ['extra-img_145', 'studio-img_020', 'extra-img_110', 'extra-img_149', 'extra-img_099'];
const removedControls = '#controls-toggle, .sidebar, #gallery-mode, #direct-clip, #gallery-clip, .joint-slider, .joint-number, #gallery-timeline, #pause-simulation, #simulation-row';

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

async function inspectViewer(frame, collection) {
  assert.equal(await frame.locator(removedControls).count(), 0, 'Removed controls or playback UI is still present');
  assert.doesNotMatch(await frame.locator('body').innerText(), /Original 3D motion|Motion controls/i);
  const scope = new URL(frame.url()).searchParams.get('collection');
  assert.equal(scope, collection, 'The viewer lost the entry collection');
  const options = await frame.locator('#asset-select option').evaluateAll(nodes => nodes.map(node => node.value));
  if (collection === 'demo') assert.deepEqual(options, demoIds);
  else {
    const catalog = JSON.parse(await fs.readFile(path.join(root, 'assets/gallery-models/catalog.json'), 'utf8')).assets;
    assert.deepEqual(options, catalog.map(asset => asset.id));
    assert.equal(new Set(options).size, catalog.length);
    assert.ok(demoIds.every(id => options.includes(id)), 'Gallery must retain all five featured assets');
  }
  assert.equal(await frame.locator('#asset-select').isVisible(), true);
  assert.equal(await frame.evaluate(() => window.__viewer.directMode && !!window.__viewer.direct), true);
  const before = await frame.evaluate(() => window.__viewer.adapter.getHandles().map(h => ({ id: h.id, kind: h.kind, value: h.value })));
  assert.ok(before.length > 0, 'Expected movable parts');
  assert.ok(before.every(handle => handle.kind !== 'replay'), 'Saved playback handles should be removed');
  // Real movement and reset after dragging are covered by direct-drag.cjs.
  // Here the actual embedded reset button must be reachable and preserve the initial pose.
  await frame.locator('#reset-pose').click();
  const after = await frame.evaluate(() => window.__viewer.adapter.getHandles().map(h => ({ id: h.id, kind: h.kind, value: h.value })));
  assert.deepEqual(after, before, 'Reset changed the initial pose');
  const box = await frame.locator('#scene').boundingBox();
  assert.ok(box && box.width > 100 && box.height > 100, 'The model canvas is not laid out');
  return { collection: scope, options: options.length, handles: before.length, reset: true };
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
          const frame = await viewer(page, id), result = await inspectViewer(frame, 'demo');
          await noHorizontalOverflow(page, frame);
          await page.screenshot({ path: path.join(output, `${variant}-${feature}-direct.png`) });
          if (!mobile && feature === 'camera') {
            await frame.locator('#asset-select').selectOption('studio-img_020');
            await frame.waitForFunction(() => window.__viewer?.ready && window.__viewer.assetId === 'studio-img_020', null, { timeout: network ? 180000 : 90000 });
            await inspectViewer(frame, 'demo');
            assert.equal(new URL(frame.url()).searchParams.get('gallery'), 'studio-img_020', 'Model selection did not update the URL');
            reports.push({ case: 'desktop-demo-switch', ok: true, collection: 'demo', options: 5 });
          }
          await escape(page);
          reports.push({ case: `${variant}-${feature}`, ok: true, ...result });
        }
        // The same Studio must reopen from a real Gallery card after Escape.
        await page.locator('#asset-search').fill('img_025');
        await page.locator('.gallery-card-open[data-gallery-id="studio-img_025"]').click();
        const galleryFrame = await viewer(page, 'studio-img_025'), galleryResult = await inspectViewer(galleryFrame, 'gallery');
        await noHorizontalOverflow(page, galleryFrame);
        await page.screenshot({ path: path.join(output, `${variant}-gallery-direct.png`) });
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
          await inspectViewer(next, 'demo');
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
