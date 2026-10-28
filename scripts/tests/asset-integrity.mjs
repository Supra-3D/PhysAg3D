// Audit the complete published collection without network, screenshots or reports.
// Run: node --expose-gc scripts/tests/asset-integrity.mjs
// Optional subset: PHYSAG_TEST_IDS=extra-img_123,extra-img_130
// Only image decoding is stubbed. Models, scene graphs, joints and vertex data
// use the production adapter and real GLTFLoader. This detects lost geometry;
// it does not certify semantic completeness of the original source asset.
import assert from 'node:assert/strict';
import { readFileSync, existsSync } from 'node:fs';
import { registerHooks } from 'node:module';
import { createHash } from 'node:crypto';

const root = new URL('../../', import.meta.url);
const source = new URL('scripts/browser-viewer/', root);
const offline = new URL('website/viewer/web/', root);
registerHooks({ resolve(specifier, context, nextResolve) {
  if (specifier === 'three') return { url: new URL('vendor/three.module.js', offline).href, shortCircuit: true };
  if (context.parentURL?.startsWith(source.href) && specifier.startsWith('.')) {
    const candidate = new URL(specifier, context.parentURL);
    if (!existsSync(candidate)) return { url: new URL(specifier, offline).href, shortCircuit: true };
  }
  return nextResolve(specifier, context);
} });
const T = await import(new URL('vendor/three.module.js', offline));
const { GLTFLoader } = await import(new URL('vendor/GLTFLoader.js', offline));
const originalFetch = globalThis.fetch;
globalThis.self = globalThis;
globalThis.createImageBitmap = async () => ({ width: 1, height: 1, close() {} });
globalThis.fetch = async (input, options) => {
  const url = new URL(typeof input === 'string' ? input : input.url || input.href);
  if (url.protocol === 'blob:') return originalFetch(input, options);
  let relative;
  if (url.hostname === 'media.githubusercontent.com' && url.pathname.includes('/website/')) relative = url.pathname.split('/website/')[1];
  else if (url.protocol === 'file:' && url.pathname.includes('/scripts/assets/')) relative = 'assets/' + url.pathname.split('/scripts/assets/')[1];
  assert(relative && !relative.includes('..'), `Unexpected resource: ${url}`);
  const published = new URL(relative, root), delivered = new URL('website/' + relative, root);
  const path = relative.endsWith('.json') && existsSync(published) ? published : delivered;
  const bytes = readFileSync(path);
  return new Response(bytes, { headers: { 'Content-Length': String(bytes.length) } });
};
const { createGalleryAdapter } = await import(new URL('gallery-adapter.js', source));
const catalog = JSON.parse(readFileSync(new URL('assets/gallery-models/catalog.json', root))).assets;
const requested = process.env.PHYSAG_TEST_IDS?.split(',').filter(Boolean);
const items = requested ? catalog.filter(item => requested.includes(item.id)) : catalog;
if (requested) assert.equal(items.length, new Set(requested).size, 'Unknown asset ID');

function byteHash(array) {
  return createHash('sha256').update(Buffer.from(array.buffer, array.byteOffset, array.byteLength)).digest('hex');
}
function rawCounts(json) {
  const counts = { meshes: 0, vertices: 0, triangles: 0, semanticNodes: 0 };
  function visit(index) {
    const node = json.nodes[index];
    if (node.extras && Object.keys(node.extras).length) counts.semanticNodes++;
    for (const primitive of json.meshes?.[node.mesh]?.primitives || []) {
      const vertices = json.accessors[primitive.attributes.POSITION].count;
      const indices = primitive.indices == null ? vertices : json.accessors[primitive.indices].count;
      counts.meshes++; counts.vertices += vertices;
      counts.triangles += [5, 6].includes(primitive.mode) ? Math.max(0, indices - 2) : (primitive.mode ?? 4) === 4 ? indices / 3 : 0;
    }
    for (const child of node.children || []) visit(child);
  }
  for (const node of json.scenes[json.scene || 0].nodes) visit(node);
  return counts;
}
function snapshot(scene, { hash = false, scanVertices = true } = {}) {
  scene.updateWorldMatrix(true, true);
  const counts = { meshes: 0, vertices: 0, triangles: 0 }, nodes = new Map(), problems = [];
  function visit(object, key, parentVisible) {
    const visible = parentVisible && object.visible;
    const row = { name: object.name, local: object.matrix.elements.slice(), world: object.matrixWorld.elements.slice(),
      visible, semantics: JSON.stringify(object.userData), morphs: object.morphTargetInfluences?.slice() || [] };
    if (![...row.local, ...row.world, ...row.morphs].every(Number.isFinite)) problems.push(`${key}: nonfinite transform/morph`);
    if (object.isMesh) {
      const geometry = object.geometry, position = geometry?.attributes.position;
      counts.meshes++; counts.vertices += position?.count || 0;
      counts.triangles += (geometry?.index?.count ?? position?.count ?? 0) / 3;
      row.vertices = position?.count || 0; row.triangles = (geometry?.index?.count ?? position?.count ?? 0) / 3;
      row.materials = [].concat(object.material).map(m => ({ name: m.name, visible: m.visible, opacity: m.opacity }));
      if (!position?.count) problems.push(`${key}: empty mesh`);
      if (!visible || row.materials.every(m => !m.visible || m.opacity === 0)) problems.push(`${key}: invisible mesh`);
      if (Math.abs(object.matrixWorld.determinant()) < 1e-14) problems.push(`${key}: collapsed transform`);
      if (scanVertices) {
        const attributes = [position, ...(geometry.morphAttributes.position || [])].filter(Boolean);
        for (const attribute of attributes) {
          const data = attribute.array || attribute.data.array;
          for (let i = 0; i < data.length; i++) if (!Number.isFinite(data[i])) { problems.push(`${key}: nonfinite vertex`); break; }
        }
      }
      if (hash) row.positionHash = byteHash(position.array || position.data.array);
    }
    nodes.set(key, row);
    object.children.forEach((child, index) => visit(child, `${key}/${index}`, visible));
  }
  visit(scene, 'scene', true);
  return { counts, nodes, problems };
}
function matrixDifference(a, b) { return Math.max(...a.map((x, i) => Math.abs(x - b[i]))); }
function assertStructure(actual, expected, label, checkPose = false) {
  assert.deepEqual(actual.counts, expected.counts, `${label}: geometry counts changed`);
  assert.deepEqual([...actual.nodes.keys()], [...expected.nodes.keys()], `${label}: scene nodes changed`);
  assert.deepEqual(actual.problems, expected.problems, `${label}: new invisible/collapsed/nonfinite geometry`);
  for (const [key, before] of expected.nodes) {
    const after = actual.nodes.get(key);
    assert.equal(after.name, before.name, `${label}: ${key} changed identity`);
    assert.equal(after.semantics, before.semantics, `${label}: ${key} lost node metadata`);
    assert.equal(after.vertices, before.vertices, `${label}: ${key} lost vertices`);
    assert.equal(after.triangles, before.triangles, `${label}: ${key} lost triangles`);
    assert.equal(after.visible, before.visible, `${label}: ${key} visibility changed`);
    assert.deepEqual(after.materials, before.materials, `${label}: ${key} material visibility changed`);
    if (checkPose) {
      assert(matrixDifference(after.local, before.local) < 1e-8, `${label}: ${key} local reset mismatch`);
      assert(matrixDifference(after.world, before.world) < 1e-8, `${label}: ${key} world reset mismatch`);
      assert.deepEqual(after.morphs, before.morphs, `${label}: ${key} morph reset mismatch`);
      assert.equal(after.positionHash, before.positionHash, `${label}: ${key} vertex reset mismatch`);
    }
  }
}
function disposeScene(scene) {
  const geometries = new Set(), materials = new Set(), textures = new Set();
  scene?.traverse(object => {
    if (object.geometry) geometries.add(object.geometry);
    for (const material of [].concat(object.material || [])) {
      materials.add(material);
      for (const value of Object.values(material)) if (value?.isTexture) textures.add(value);
    }
  });
  geometries.forEach(g => g.dispose()); materials.forEach(m => m.dispose());
  textures.forEach(t => { t.source?.data?.close?.(); t.dispose(); });
}

const totals = { assets: 0, meshes: 0, vertices: 0, triangles: 0, handles: 0, endpointPoses: 0, semanticNodes: 0 };
const failures = [], sourceProblems = [], initialPoseDifferences = [];
for (const item of items) {
  let pristine, adapter;
  try {
    const path = new URL('website/' + item.asset_url.replace(/^\//, ''), root), bytes = readFileSync(path);
    assert.equal(bytes.toString('ascii', 0, 4), 'glTF', 'Model is not materialized GLB');
    if (item.asset_sha256) assert.equal(byteHash(bytes), item.asset_sha256, 'Source hash differs from published catalog');
    const json = JSON.parse(bytes.toString('utf8', 20, 20 + bytes.readUInt32LE(12))), raw = rawCounts(json);
    pristine = await new GLTFLoader().parseAsync(bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength), new URL('.', path).href);
    const outer = new T.Group(); outer.rotation.x = Math.PI / 2; outer.add(pristine.scene); outer.updateMatrixWorld(true);
    const before = snapshot(pristine.scene, { hash: true });
    assert.deepEqual(before.counts, { meshes: raw.meshes, vertices: raw.vertices, triangles: raw.triangles }, 'GLTFLoader lost active-scene primitives');
    adapter = await createGalleryAdapter(item);
    const scene = adapter.group.children[0], rest = snapshot(scene, { hash: true });
    assertStructure(rest, before, 'adapter initial pose');
    if (before.problems.length) sourceProblems.push({ id: item.id, problems: before.problems });
    const differences = [];
    for (const [key, original] of before.nodes) {
      const current = rest.nodes.get(key), local = matrixDifference(current.local, original.local), world = matrixDifference(current.world, original.world);
      const vertices = current.positionHash !== original.positionHash;
      if (local > 1e-6 || world > 1e-6 || vertices || JSON.stringify(current.morphs) !== JSON.stringify(original.morphs)) differences.push({ name: current.name, local, world, vertices, morph: JSON.stringify(current.morphs) !== JSON.stringify(original.morphs) });
    }
    if (differences.length) initialPoseDifferences.push({ id: item.id, changedNodes: differences.length, changedVertexBuffers: differences.filter(d => d.vertices).length, maximumLocal: Math.max(...differences.map(d => d.local)), maximumWorld: Math.max(...differences.map(d => d.world)), names: differences.map(d => d.name) });
    const handles = adapter.getHandles();
    for (const handle of handles) {
      assert(!handle.disabled, `${handle.id}: disabled handle`);
      assert(handle.objects?.length, `${handle.id}: no owned geometry`);
      const targets = [...new Set([handle.min, handle.max])].filter(Number.isFinite);
      assert(targets.length, `${handle.id}: no finite endpoint`);
      for (const value of targets) {
        adapter.beginDirectInteraction(handle.id);
        assert(adapter.setDirectValue(handle.id, value), `${handle.id}: endpoint rejected`);
        assertStructure(snapshot(scene), rest, `${handle.id} at ${value}`);
        adapter.endDirectInteraction(handle.id);
        adapter.reset();
        assertStructure(snapshot(scene, { hash: true }), rest, `${handle.id} reset`, true);
        totals.endpointPoses++;
      }
    }
    totals.assets++; totals.handles += handles.length; totals.semanticNodes += raw.semanticNodes;
    for (const key of ['meshes', 'vertices', 'triangles']) totals[key] += raw[key];
    console.log(JSON.stringify({ status: 'passed', id: item.id, ...rest.counts, handles: handles.length, changedRestNodes: differences.length }));
  } catch (error) {
    failures.push({ id: item.id, error: error.message });
    console.log(JSON.stringify({ status: 'failed', id: item.id, error: error.message }));
  } finally {
    adapter?.dispose(); disposeScene(adapter?.group); disposeScene(pristine?.scene);
    adapter = pristine = null; globalThis.gc?.();
  }
}
globalThis.fetch = originalFetch;
console.log(JSON.stringify({ status: failures.length ? 'failed' : 'passed', tested: items.length, totals, failures, sourceProblems, initialPoseDifferences }));
if (failures.length) process.exitCode = 1;
