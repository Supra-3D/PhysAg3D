// Load the delivered geometry in Node; only texture decoding is stubbed.
import assert from 'node:assert/strict';
import { readFileSync, existsSync, openSync, readSync, closeSync } from 'node:fs';
import { registerHooks } from 'node:module';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

export const root = new URL('../../', import.meta.url);
const mirror = process.env.PHYSAG_ASSET_ROOT;
export function fixture(relative) {
  assert(!relative.includes('..'), 'Unsafe fixture path');
  const candidates = [mirror && path.join(mirror, relative), fileURLToPath(new URL(relative, root)), fileURLToPath(new URL('website/' + relative, root))].filter(Boolean);
  const found = candidates.find(existsSync);
  assert(found, 'Missing source asset; set PHYSAG_ASSET_ROOT to the complete dataset mirror: ' + relative);
  return found;
}
export function glbJSON(relative) {
  const fd = openSync(fixture(relative), 'r'), header = Buffer.alloc(20);
  try {
    readSync(fd, header, 0, 20, 0);
    assert.equal(header.toString('ascii', 0, 4), 'glTF', 'Unresolved asset: ' + relative);
    const chunk = Buffer.alloc(header.readUInt32LE(12));
    readSync(fd, chunk, 0, chunk.length, 20);
    return JSON.parse(chunk.toString('utf8'));
  } finally { closeSync(fd); }
}
registerHooks({ resolve(specifier, context, next) {
  if (specifier === 'three') return { url: new URL('viewer/vendor/three.module.js', root).href, shortCircuit: true };
  return next(specifier, context);
} });
const networkFetch = globalThis.fetch;
globalThis.self = globalThis;
globalThis.createImageBitmap = async () => ({ width: 1, height: 1, close() {} });
globalThis.fetch = async input => {
  const url = new URL(typeof input === 'string' ? input : input.url || input.href);
  if (url.protocol === 'blob:') return networkFetch(input);
  let relative;
  if (url.href.startsWith(root.href)) relative = decodeURIComponent(url.href.slice(root.href.length));
  else if (url.hostname === 'huggingface.co' && url.pathname.includes('/resolve/main/')) relative = url.pathname.split('/resolve/main/')[1];
  assert(relative, 'Unexpected fixture URL: ' + url);
  return new Response(readFileSync(fixture(relative)));
};
export const T = await import(new URL('viewer/vendor/three.module.js', root));
export const { createGalleryAdapter } = await import(new URL('viewer/gallery-adapter.js', root));
export const catalog = JSON.parse(readFileSync(new URL('website/assets/gallery-models/catalog.json', root))).assets;
export function dispose(adapter) {
  adapter?.dispose();
  adapter?.group.traverse(object => object.geometry?.dispose());
  adapter?.materials.forEach(material => material.dispose());
  adapter?.textures.forEach(texture => { texture.source?.data?.close?.(); texture.dispose(); });
}
