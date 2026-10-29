// Run with node scripts/test-downloads.cjs; no browser or external packages required.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root = path.resolve(__dirname, '..');
function context(prefix = '') {
  const ctx = vm.createContext({window: {}});
  for (const name of ['download-data.js', 'downloads.js', 'gallery-data.js']) {
    vm.runInContext(fs.readFileSync(path.join(root, prefix, name), 'utf8'), ctx);
  }
  return ctx.window;
}
function link() {
  return {dataset: {}, attrs: {}, setAttribute(k,v){this.attrs[k]=v},
    removeAttribute(k){delete this.attrs[k];delete this[k]}};
}
for (const prefix of ['', 'website/']) {
  const w = context(prefix);
  const manifest = w.PHYSAG3D_DOWNLOAD_MANIFEST;
  const bind = w.PHYSAG3D_DOWNLOADS.bind;
  assert.equal(Object.keys(manifest.assets).length, 236);
  for (const item of w.PHYSAG3D_GALLERY) {
    const a = link();
    assert.equal(bind(a, item.id, item.caseId), true, item.id);
    assert.equal(a.dataset.caseId, item.caseId);
    assert.equal(a.download, item.caseId + '.zip');
    assert.ok(a.href.endsWith('/' + item.caseId + '.zip?download=true'));
    assert.equal(a.attrs['aria-disabled'], undefined);
  }
  // Hero order is checked against each native input image, not gallery position.
  const hero = fs.readFileSync(path.join(root, prefix, 'hero.js'), 'utf8');
  const ids = vm.runInNewContext(hero.match(/const galleryIds=(\[[^;]+\]);/)[1]);
  const inputs = vm.runInNewContext(hero.match(/const inputs=(\[[\s\S]+?\]);/)[1]);
  const a = link();
  ids.forEach((id, i) => {
    assert.equal(bind(a, id), true);
    assert.equal(a.dataset.caseId, inputs[i].match(/img_\d{3}/)[0]);
    assert.equal(a.download, a.dataset.caseId + '.zip');
  });
  assert.equal(bind(a, ids[0], 'img_001'), false, 'Mismatched case must not download');
  assert.equal(a.href, undefined);
  assert.equal(a.attrs['aria-disabled'], 'true');
  assert.equal(bind(a, 'extra-img_999'), false);
  assert.equal(bind(a, ids[0]), true, 'Valid rebind restores a reused link');
  assert.equal(a.attrs['aria-disabled'], undefined);
  const html = fs.readFileSync(path.join(root, prefix, 'index.html'), 'utf8');
  const scripts = [...html.matchAll(/<script src="([^"?]+)(?:\?[^\"]*)?"/g)].map(m=>m[1]);
  for (const consumer of ['gallery.js', 'hero.js']) {
    assert.ok(scripts.indexOf('download-data.js') < scripts.indexOf('downloads.js'));
    assert.ok(scripts.indexOf('downloads.js') < scripts.indexOf(consumer));
  }
  for (const id of ['hero-download','gallery-asset-download']) assert.match(html, new RegExp('<a id="'+id+'"'));
  console.log(prefix || 'Published site', ':', w.PHYSAG3D_GALLERY.length, 'gallery records and 5 hero IDs verified');
}
console.log('All download identity, invalid-ID, rebind and script-order checks passed.');
