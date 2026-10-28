// Compare every retained Gallery asset with the delivered package's adapter.
// Only image decoding and resource hosting differ. Test the actual original
// transforms, skin positions and morph weights at the same drag coordinate.
import assert from 'node:assert/strict';
import { readFileSync, existsSync } from 'node:fs';
import { registerHooks } from 'node:module';
import { createHash } from 'node:crypto';

const root = new URL('../../', import.meta.url);
const source = new URL('scripts/browser-viewer/', root);
const original = new URL('website/viewer/web/', root);
registerHooks({ resolve(s, c, next) {
  if (s === 'three') return { url: new URL('vendor/three.module.js', original).href, shortCircuit: true };
  if (c.parentURL?.startsWith(source.href) && s.startsWith('.') && !existsSync(new URL(s, c.parentURL))) {
    return { url: new URL(s, original).href, shortCircuit: true };
  }
  return next(s, c);
} });
const networkFetch = globalThis.fetch;
globalThis.self = globalThis;
globalThis.location = new URL('http://source.test/viewer/');
globalThis.createImageBitmap = async () => ({ width: 1, height: 1, close() {} });
globalThis.fetch = async input => {
  const url = new URL(typeof input === 'string' ? input : input.url || input.href);
  if (url.protocol === 'blob:') return networkFetch(input);
  let relative;
  if (url.hostname === 'source.test') relative = url.pathname.slice(1);
  else if (url.hostname === 'media.githubusercontent.com') relative = url.pathname.split('/website/')[1];
  else if (url.hostname === 'huggingface.co' && url.pathname.includes('/resolve/main/')) relative = url.pathname.split('/resolve/main/')[1];
  else if (url.protocol === 'file:' && url.pathname.includes('/scripts/assets/')) relative = 'assets/' + url.pathname.split('/scripts/assets/')[1];
  assert(relative && !relative.includes('..'), 'Unexpected source resource: ' + url);
  return new Response(readFileSync(new URL('website/' + relative, root)));
};
const { createGalleryAdapter: delivered } = await import(new URL('gallery-adapter.js', original));
const { createGalleryAdapter: deployed } = await import(new URL('gallery-adapter.js', source));
const catalog = JSON.parse(readFileSync(new URL('assets/gallery-models/catalog.json', root))).assets;
const requested = process.env.PHYSAG_TEST_IDS?.split(',');
const items = catalog.filter(a => !a.native_asset_id && (!requested || requested.includes(a.id)));
function snapshot(adapter) {
  const hash = createHash('sha256');
  adapter.group.updateMatrixWorld(true);
  adapter.group.traverse(o => {
    hash.update(JSON.stringify([o.name, o.visible, o.matrixWorld.elements, o.morphTargetInfluences || []]));
    const a = o.geometry?.attributes.position;
    if (a) { const b = a.array || a.data.array; hash.update(Buffer.from(b.buffer, b.byteOffset, b.byteLength)); }
  });
  return hash.digest('hex');
}
function descriptors(adapter) {
  return adapter.getHandles().map(h => ({ id: h.id, kind: h.kind, min: h.min, max: h.max,
    coupled: h.coupled, origin: h.origin?.toArray(), axis: h.axis?.toArray(), objects: h.objects.map(o => o.name) }));
}
function dispose(a) {
  a?.dispose(); a?.group.traverse(o => o.geometry?.dispose());
  a?.materials.forEach(m => m.dispose()); a?.textures.forEach(t => { t.source?.data?.close?.(); t.dispose(); });
}
let poses = 0, handles = 0;
const failures = [];
for (const item of items) {
  let before, after;
  try {
    before = await delivered(item); after = await deployed(item);
    assert.equal(after.mode, before.mode, 'Default source interaction changed');
    assert.deepEqual(descriptors(after), descriptors(before), 'Source drag descriptors changed');
    assert.equal(snapshot(after), snapshot(before), 'Default source appearance changed');
    const sourceHandles = before.getHandles(); handles += sourceHandles.length;
    // Sample each source channel category. Replay handles share the same
    // original motion coordinate; all joints/skin nodes are compared together.
    const samples = [...new Map(sourceHandles.map(h => [h.kind + ':' + (h.axisSource || ''), h])).values()];
    for (const h of samples) for (const fraction of [.23, .63, 1]) {
      const value = h.min + (h.max - h.min) * fraction;
      before.beginDirectInteraction(h.id); after.beginDirectInteraction(h.id);
      assert(before.setDirectValue(h.id, value)); assert(after.setDirectValue(h.id, value));
      assert.equal(snapshot(after), snapshot(before), h.id + ': source geometry/motion differs');
      after.toggle(); after.update(0);
      assert.equal(after.playing, false, 'Automatic playback returned');
      before.reset(); after.reset();
      assert.equal(snapshot(after), snapshot(before), 'Reset differs from the source');
      poses++;
    }
  } catch (error) { failures.push({ id: item.id, error: error.message }); }
  finally { dispose(before); dispose(after); before = after = null; globalThis.gc?.(); }
}
console.log(JSON.stringify({ tested: items.length, sourceHandles: handles, matchingPoses: poses, failures }));
assert.equal(failures.length, 0);
