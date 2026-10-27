// Run with Playwright available in NODE_PATH. Uses the exact local LFS source
// bytes for repeatable coverage; --network keeps real asset-host requests.
const { chromium } = require('playwright');
const fs = require('node:fs/promises');
const path = require('node:path');
const assert = require('node:assert/strict');
const root = path.resolve(__dirname, '../..');
const network = process.argv.includes('--network');
const all = process.argv.includes('--all');
const base = process.env.PHYSAG_TEST_URL || `http://127.0.0.1:${network ? 8875 : 8876}/PhysAg3D/`;
const artifactDir = process.env.PHYSAG_TEST_OUTPUT;

(async () => {
  const catalog = JSON.parse(await fs.readFile(path.join(root, 'assets/gallery-models/catalog.json'), 'utf8')).assets;
  const selected = process.env.PHYSAG_TEST_IDS ? catalog.filter(a => process.env.PHYSAG_TEST_IDS.split(',').includes(a.id)) : all ? catalog : [
    ...catalog.filter(a => a.native_asset_id),
    ...['joint_controls', 'authored_deformation', 'recorded_motion', 'static_surface'].map(cap => catalog.find(a => !a.native_asset_id && a.capabilities.includes(cap))),
  ];
  const browser = await chromium.launch({ channel: process.env.PHYSAG_BROWSER || 'msedge', headless: true });
  try {
    const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
    if (!network) await context.route('**/viewer/resource-urls.js', async route => {
      // Change only the download host; serve large GLBs over HTTP, not through
      // DevTools' 100 MB message limit. Integrity hashes still run unchanged.
      const source = await fs.readFile(path.join(root, 'viewer/resource-urls.js'), 'utf8');
      const body = source.replace(
        /const mediaRoot\s*=\s*new URL\(`https:\/\/(?:media\.githubusercontent\.com|huggingface\.co)\/[^`]+`\);/,
        `const mediaRoot = new URL(${JSON.stringify(base + '__fixtures/')});`);
      assert.notEqual(body, source, 'Could not replace the published asset host with the fixture server');
      await route.fulfill({ body, contentType: 'text/javascript' });
    });
    const report = [];
    for (const item of selected) {
      const page = await context.newPage();
      let errors = [], api = [];
      page.on('pageerror', e => errors.push(e.message));
      page.on('request', r => { if (/\/api\//.test(r.url())) api.push(r.url()); });
      const started = Date.now();
      try {
        await page.goto(base + 'viewer/?gallery=' + encodeURIComponent(item.id) + '&direct=1', { waitUntil: 'domcontentloaded' });
        await page.waitForFunction(() => window.__viewer?.ready || document.getElementById('viewer-boot-retry')?.hidden === false, null, { timeout: network ? 180000 : 90000 });
        assert.equal(await page.evaluate(() => window.__viewer?.ready), true, await page.locator('#viewer-boot-label').textContent());
        const stats = await page.evaluate(() => {
          const v = window.__viewer, a = v.adapter;
          const handles = a.getHandles();
          const changes = handles.filter(h => h.kind !== 'replay' && Number.isFinite(h.max)).map(h => {
            const requested = h.min + (h.max - h.min) * 0.6;
            a.beginDirectInteraction(h.id); a.setDirectValue(h.id, requested);
            const updated = a.getHandles().find(x => x.id === h.id)?.value;
            a.endDirectInteraction(h.id);
            return { id: h.id, requested, updated };
          });
          for (const mode of a.modes) {
            a.setMode(mode.id);
            if (mode.id === 'animation' || mode.id === 'recorded') a.seek(a.duration * .45);
            a.update(.016);
          }
          a.setMode(a.modes[0].id); a.reset();
          const finite = a.group.matrixWorld.elements.every(Number.isFinite) && [...a.frameBounds.min, ...a.frameBounds.max].every(Number.isFinite);
          return { asset: v.assetId, runtime: v.runtime, controls: a.controls.length, handles: handles.length, modes: a.modes.map(x => x.id), finite, changes };
        });
        assert.equal(stats.asset, item.id); assert.equal(stats.runtime, 'browser'); assert.equal(stats.finite, true);
        for (const x of stats.changes) assert.ok(Math.abs(x.updated - x.requested) < 1e-6, JSON.stringify(x));
        assert.deepEqual(api, []); assert.deepEqual(errors, []);
        if (item.native_asset_id) {
          await page.locator('#controls-toggle').click();
          await page.locator('.sidebar').waitFor({ state: 'visible' });
          assert.ok(await page.locator('.joint-slider').count() > 0);
          await page.locator('#controls-toggle').click();
        }
        if (artifactDir && item.native_asset_id) {
          await fs.mkdir(artifactDir, { recursive: true });
          await page.screenshot({ path: path.join(artifactDir, item.native_asset_id + '.png') });
        }
        const row = { id: item.id, ok: true, seconds: +((Date.now() - started) / 1000).toFixed(1), ...stats };
        report.push(row); console.log(JSON.stringify(row));
      } catch (error) {
        const row = { id: item.id, ok: false, error: error.message, errors, api }; report.push(row); console.log(JSON.stringify(row));
      } finally { await page.close().catch(() => {}); }
    }
    if (artifactDir) await fs.writeFile(path.join(artifactDir, all ? 'all-assets.json' : network ? 'network-smoke.json' : 'smoke.json'), JSON.stringify(report, null, 2));
    assert.equal(report.filter(x => !x.ok).length, 0, 'Some browser cases failed');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
