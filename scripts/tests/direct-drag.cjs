// Real mouse/touch gestures on rendered model surfaces. No direct control setters.
// --network uses the published site and asset hosts without fixture interception.
const { chromium } = require('playwright');
const fs = require('node:fs/promises');
const path = require('node:path');
const assert = require('node:assert/strict');
const root = path.resolve(__dirname, '../..');
const network = process.argv.includes('--network');
const base = process.env.PHYSAG_TEST_URL || (network ? 'https://supra-3d.github.io/PhysAg3D/' : 'http://127.0.0.1:8876/PhysAg3D/');
const output = process.env.PHYSAG_TEST_OUTPUT || null;
const removedControls = '#controls-toggle, .sidebar, #gallery-mode, #direct-clip, #gallery-clip, .joint-slider, .joint-number, #gallery-timeline, #pause-simulation, #simulation-row';
const cases = [
  ['camera', 'extra-img_145'], ['phone', 'studio-img_020'], ['globe', 'extra-img_110'],
  ['ladder', 'extra-img_149'], ['carousel', 'extra-img_099'], ['printer', 'studio-img_025'],
  ['record-player', 'studio-img_027'], ['laptop', 'extra-img_130'], ['cabinet', 'extra-img_123'],
].filter(([, id]) => !process.env.PHYSAG_TEST_IDS || process.env.PHYSAG_TEST_IDS.split(',').includes(id));

async function locateGesture(page) {
  return page.evaluate(async () => {
    const T = await import('./vendor/three.module.js');
    const v = window.__viewer, handles = v.adapter.getHandles().filter(h => !h.disabled && h.kind !== 'replay' && !h.springReturn);
    const canvas = document.getElementById('scene'), rect = canvas.getBoundingClientRect();
    const project = point => {
      const p = point.clone().project(v.camera);
      return { x: rect.left + (p.x + 1) * rect.width / 2, y: rect.top + (1 - p.y) * rect.height / 2, z: p.z };
    };
    const inside = p => p.x > rect.left + 15 && p.x < rect.right - 15 && p.y > rect.top + 15 && p.y < rect.bottom - 15 && p.z >= -1 && p.z <= 1;
    const raycaster = new T.Raycaster();
    const pick = point => {
      if (document.elementFromPoint(point.x, point.y) !== canvas) return null;
      raycaster.setFromCamera(new T.Vector2((point.x - rect.left) / rect.width * 2 - 1, -(point.y - rect.top) / rect.height * 2 + 1), v.camera);
      const hit = raycaster.intersectObjects([v.adapter.group], true)[0];
      if (!hit) return null;
      const matches = handles.map(h => {
        let distance = Infinity;
        for (const root of h.objects || []) {
          let d = 0;
          for (let node = hit.object; node; node = node.parent, d++) if (node === root) { distance = Math.min(distance, d); break; }
        }
        return { h, distance };
      }).filter(x => Number.isFinite(x.distance));
      matches.sort((a, b) => a.distance - b.distance || (b.h.selectionDepth || 0) - (a.h.selectionDepth || 0) || a.h.objects.length - b.h.objects.length);
      return matches[0]?.h || null;
    };
    const candidates = [];
    for (const handle of handles) {
      for (const object of handle.objects || []) object.traverse(mesh => {
        if (!mesh.isMesh || !mesh.geometry?.attributes.position) return;
        const box = new T.Box3().setFromObject(mesh, true), center = box.getCenter(new T.Vector3());
        candidates.push(project(center));
        for (const dx of [-.25, 0, .25]) for (const dy of [-.25, 0, .25]) {
          const p = center.clone(); p.x += (box.max.x - box.min.x) * dx; p.y += (box.max.y - box.min.y) * dy;
          candidates.push(project(p));
        }
        // A center-only XY sample can miss usable globe surfaces at a wide
        // desktop aspect ratio. Sample rendered vertices at different heights
        // too; the raycast below still requires a visible, selectable surface.
        const positions = mesh.geometry.attributes.position;
        for (let i = 0; i < positions.count; i += Math.max(1, Math.ceil(positions.count / 96))) {
          candidates.push(project(new T.Vector3().fromBufferAttribute(positions, i).applyMatrix4(mesh.matrixWorld)));
        }
      });
    }
    let screenGesture = null;
    // Prefer large visible mesh surfaces; do not select a chip or mutate poses.
    for (const start of candidates) {
      if (!inside(start)) continue;
      const h = pick(start);
      if (!h || !h.origin || !h.axis) continue;
      const pivot = project(h.origin);
      if (Math.hypot(start.x - pivot.x, start.y - pivot.y) < 25) continue;
      const value = Number(h.value), sign = value > (h.min + h.max) / 2 ? -1 : 1;
      let points = [];
      if (h.kind === 'hinge') {
        if (!screenGesture) {
          const axisPoint = project(h.origin.clone().addScaledVector(h.axis, v.camera.position.distanceTo(h.origin) * .05));
          const axisX = axisPoint.x - pivot.x, axisY = axisPoint.y - pivot.y;
          const length = Math.hypot(axisX, axisY);
          if (length > 1) {
            const dx = -axisY / length * 60 * sign, dy = axisX / length * 60 * sign;
            const screenPoints = Array.from({ length: 12 }, (_, i) => ({ x: start.x + dx * (i + 1) / 12, y: start.y + dy * (i + 1) / 12, z: start.z }));
            if (screenPoints.every(inside)) screenGesture = { id: h.id, label: h.label, start, points: screenPoints, before: value, kind: h.kind, path: 'screen-tangent' };
          }
        }
        // Avoid grazing the rotation plane: the UI deliberately switches to a
        // projected-arc gesture there, whereas this path tests a 3D plane arc.
        if (Math.abs(raycaster.ray.direction.dot(h.axis)) < .01) continue;
        const initial = raycaster.ray.intersectPlane(new T.Plane().setFromNormalAndCoplanarPoint(h.axis, h.origin), new T.Vector3());
        if (!initial) continue;
        const radius = initial.sub(h.origin);
        const angle = Math.min(.45, Math.abs((sign > 0 ? h.max : h.min) - value) * .5);
        if (angle < .01) continue;
        points = Array.from({ length: 12 }, (_, i) => project(radius.clone().applyAxisAngle(h.axis, sign * angle * (i + 1) / 12).add(h.origin)));
      } else if (h.kind === 'slide') {
        const hit = raycaster.intersectObjects([v.adapter.group], true)[0];
        const amount = (h.max - h.min) * .4 * sign;
        points = Array.from({ length: 12 }, (_, i) => project(hit.point.clone().addScaledVector(h.axis, amount * (i + 1) / 12)));
      }
      if (!points.length || !points.every(inside)) continue;
      const end = points.at(-1);
      if (Math.hypot(end.x - start.x, end.y - start.y) < 6) continue;
      return { id: h.id, label: h.label, start, points, before: value, kind: h.kind };
    }
    if (screenGesture) return screenGesture;
    throw new Error('No visible movable surface was found for a reliable direct gesture');
  });
}

(async () => {
  if (output) await fs.mkdir(output, { recursive: true });
  const browser = await chromium.launch({ channel: process.env.PHYSAG_BROWSER || 'msedge', headless: true });
  const report = [];
  try {
    for (const touch of [false, true]) {
      const context = await browser.newContext({ viewport: touch ? { width: 390, height: 844 } : { width: 1440, height: 1000 }, hasTouch: touch, isMobile: touch });
      if (!network) await context.route('**/viewer/resource-urls.js', async route => {
        const source = await fs.readFile(path.join(root, 'viewer/resource-urls.js'), 'utf8');
        const body = source.replace(/const mediaRoot\s*=\s*new URL\(`https:\/\/(?:media\.githubusercontent\.com|huggingface\.co)\/[^`]+`\);/,
          `const mediaRoot = new URL(${JSON.stringify(base + '__fixtures/')});`);
        assert.notEqual(body, source);
        await route.fulfill({ body, contentType: 'text/javascript' });
      });
      for (const [name, id] of cases) {
        const page = await context.newPage(), errors = [];
        page.on('pageerror', error => errors.push(error.message));
        const variant = (touch ? 'touch-' : 'mouse-') + name;
        try {
          await page.goto(base + 'viewer/?gallery=' + id + '&direct=1', { waitUntil: 'domcontentloaded' });
          await page.waitForFunction(() => window.__viewer?.ready, null, { timeout: network ? 180000 : 90000 });
          assert.equal(await page.locator(removedControls).count(), 0, 'Removed controls or playback UI is still present');
          assert.doesNotMatch(await page.locator('body').innerText(), /Original 3D motion|Motion controls/i);
          assert.equal(await page.evaluate(() => window.__viewer.adapter.getHandles().some(h => h.kind === 'replay')), false);
          const gesture = await locateGesture(page);
          let cdp;
          if (touch) {
            cdp = await context.newCDPSession(page);
            await cdp.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [{ x: gesture.start.x, y: gesture.start.y, radiusX: 1, radiusY: 1, id: 1 }] });
          } else { await page.mouse.move(gesture.start.x, gesture.start.y); await page.mouse.down(); }
          const selected = await page.evaluate(() => window.__viewer.direct.selectedId);
          assert.equal(selected, gesture.id, 'Pointer did not select the visible moving part');
          for (const point of gesture.points) {
            if (touch) await cdp.send('Input.dispatchTouchEvent', { type: 'touchMove', touchPoints: [{ x: point.x, y: point.y, radiusX: 1, radiusY: 1, id: 1 }] });
            else await page.mouse.move(point.x, point.y);
          }
          const during = await page.evaluate(id => window.__viewer.adapter.getHandles().find(h => h.id === id).value, gesture.id);
          if (touch) await cdp.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] }); else await page.mouse.up();
          const after = await page.evaluate(id => window.__viewer.adapter.getHandles().find(h => h.id === id).value, gesture.id);
          assert.ok(Math.abs(during - gesture.before) > 1e-5, 'Dragging the rendered part did not change its joint');
          assert.ok(Math.abs(after - gesture.before) > 1e-5, 'Joint movement disappeared on release');
          assert.equal(await page.evaluate(() => window.__viewer.controls.enabled), true, 'Orbit controls did not recover after dragging');
          assert.equal(await page.locator(removedControls).count(), 0, 'Dragging must not restore removed UI');
          if (output) await page.screenshot({ path: path.join(output, variant + '.png') });
          await page.locator('#reset-pose').click();
          await page.waitForFunction(({ id, before }) => Math.abs(window.__viewer.adapter.getHandles().find(h => h.id === id)?.value - before) < 1e-6,
            { id: gesture.id, before: gesture.before });
          const reset = await page.evaluate(id => window.__viewer.adapter.getHandles().find(h => h.id === id).value, gesture.id);
          assert.deepEqual(errors, []);
          const row = { case: variant, ok: true, id, handle: gesture.id, before: gesture.before, during, after, reset };
          report.push(row); console.log(JSON.stringify(row));
        } catch (error) {
          const row = { case: variant, ok: false, error: error.message, errors }; report.push(row); console.log(JSON.stringify(row));
          if (output) await page.screenshot({ path: path.join(output, variant + '-failure.png') }).catch(() => {});
        } finally { await page.close(); }
      }
      await context.close();
    }
  } finally { await browser.close(); }
  if (output) await fs.writeFile(path.join(output, 'direct-drag.json'), JSON.stringify(report, null, 2));
  assert.equal(report.filter(row => !row.ok).length, 0, 'Direct gesture checks failed');
})().catch(error => { console.error(error); process.exitCode = 1; });
