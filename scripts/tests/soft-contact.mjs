// PHYSAG_ASSET_ROOT=<HF mirror> node --expose-gc scripts/tests/soft-contact.mjs
// Checks every delivered soft surface with real evaluated morph/skin geometry.
import assert from 'node:assert/strict';
import { readFileSync, writeFileSync } from 'node:fs';
import { T, root, fixture, glbJSON, catalog, createGalleryAdapter, dispose } from './soft-fixtures.mjs';
const { LOCAL_SOFT_PROFILES, MORPH_SOFT_PROFILES, SKIN_SOFT_PROFILES } = await import(new URL('viewer/soft-profiles.js', root));
const profiles = { ...LOCAL_SOFT_PROFILES, ...MORPH_SOFT_PROFILES, ...SKIN_SOFT_PROFILES };
// These shapes follow a declared hinge/spring rather than a free soft contact.
const mechanisms = new Set(['studio-img_020', 'extra-img_112', 'extra-img_164', 'extra-img_178']);
const selected = process.env.PHYSAG_TEST_IDS?.split(',');
const baseline = process.argv.includes('--baseline');
const inventory = [];
for (const item of catalog) {
  const glb = glbJSON(item.asset_url.replace(/^\//, ''));
  const metadata = item.metadata || (item.metadata_url ? JSON.parse(readFileSync(fixture(item.metadata_url.replace(/^\//, '')))) : {});
  const deforms = glb.meshes?.some(m => m.primitives.some(p => p.targets?.length)) || glb.skins?.length;
  if (deforms || metadata.approximate_soft?.available || profiles[item.id]) inventory.push(item);
}
function worldVertex(object, index, out = new T.Vector3()) { return object.getVertexPosition(index, out).applyMatrix4(object.matrixWorld); }
function contacts(object, handle) {
  const geometry = object.geometry, total = (geometry.index?.count || geometry.attributes.position.count) / 3;
  const candidates = [];
  for (let faceIndex = 0; faceIndex < total; faceIndex += Math.max(1, Math.floor(total / 96))) {
    const indices = [0, 1, 2].map(k => geometry.index ? geometry.index.getX(faceIndex * 3 + k) : faceIndex * 3 + k);
    const vertices = indices.map(i => worldVertex(object, i));
    const point = vertices.reduce((p, v) => p.add(v), new T.Vector3()).divideScalar(3);
    const normal = new T.Vector3().crossVectors(vertices[1].clone().sub(vertices[0]), vertices[2].clone().sub(vertices[0])).normalize();
    const detail = { object, point, normal, faceIndex, face: { a: indices[0], b: indices[1], c: indices[2] } };
    if (normal.lengthSq() > .5 && (!handle.acceptsHit || handle.acceptsHit(detail))) candidates.push(detail);
  }
  if (!candidates.length) return [];
  const box = new T.Box3().setFromPoints(candidates.map(c => c.point)), size = box.getSize(new T.Vector3());
  const axis = size.x >= size.y && size.x >= size.z ? 'x' : size.y >= size.z ? 'y' : 'z';
  candidates.sort((a, b) => a.point[axis] - b.point[axis]);
  return [...new Set([.2, .5, .8].map(f => candidates[Math.floor((candidates.length - 1) * f)]))];
}
function positions(object) {
  const values = new Float64Array(object.geometry.attributes.position.count * 3), point = new T.Vector3();
  for (let i = 0; i < values.length / 3; i++) worldVertex(object, i, point).toArray(values, i * 3);
  return values;
}
function errorFrom(a, b) { let max = 0; for (let i = 0; i < a.length; i++) max = Math.max(max, Math.abs(a[i] - b[i])); return max; }
const results = [], failures = [];
let tests = 0;
for (const item of inventory.filter(item => !mechanisms.has(item.id) && (!selected || selected.includes(item.id)))) {
  let adapter;
  const row = { id: item.id, name: item.name, handles: 0, meshes: 0, contacts: 0, failures: [] };
  try {
    adapter = await createGalleryAdapter(item);
    const handles = adapter.getHandles().filter(h => h.interaction === 'soft' && !h.disabled);
    row.handles = handles.length;
    assert(handles.length, 'Soft asset has no contact control');
    for (const handle of handles) for (const object of handle.objects.filter(o => o.isMesh)) {
      row.meshes++;
      const points = contacts(object, handle);
      // An all-rigid backing mesh may be deliberately excluded by vertex weights.
      if (!points.length) continue;
      for (const contact of points) {
        adapter.reset(); adapter.group.updateMatrixWorld(true);
        const before = positions(object);
        const transforms = [];
        adapter.group.traverse(o => transforms.push([o, o.matrixWorld.clone()]));
        assert(adapter.beginDirectInteraction(handle.id, contact));
        assert(adapter.setDirectValue(handle.id, .75));
        adapter.group.updateMatrixWorld(true);
        const after = positions(object);
        let maximum = 0, peakIndex = 0;
        for (let i = 0; i < before.length / 3; i++) {
          const distance = Math.hypot(...[0, 1, 2].map(k => after[i * 3 + k] - before[i * 3 + k]));
          if (distance > maximum) { maximum = distance; peakIndex = i; }
        }
        const hitDelta = new T.Vector3();
        for (const index of [contact.face.a, contact.face.b, contact.face.c]) hitDelta.add(new T.Vector3().fromArray(after, index * 3).sub(new T.Vector3().fromArray(before, index * 3)).divideScalar(3));
        const size = new T.Box3().setFromObject(object, true).getSize(new T.Vector3()).length() || 1;
        const contactRatio = maximum ? hitDelta.length() / maximum : 0;
        const peakDistance = new T.Vector3().fromArray(before, peakIndex * 3).distanceTo(contact.point) / size;
        if (maximum < size * 1e-5 || contactRatio < .5) row.failures.push({ handle: handle.id, mesh: object.name, face: contact.faceIndex, contactRatio, peakDistance, error: 'Deformation is not centered at contact' });
        if (!baseline) {
          for (const [node, matrix] of transforms) assert(errorFrom(node.matrixWorld.elements, matrix.elements) < 1e-6, 'Contact moved a bone or rigid transform: ' + node.name);
          const sign = handle.action === 'pull' ? 1 : -1;
          assert(hitDelta.dot(contact.normal) * sign > 0, 'Contact displacement has the wrong normal direction');
          adapter.setDirectValue(handle.id, 0);
          adapter.setDirectValue(handle.id, .75);
          assert(errorFrom(positions(object), after) < size * 2e-6, 'Returning through zero moved the contact region');
          adapter.endDirectInteraction(handle.id); adapter.update(.03);
          const releasingPoint = [contact.face.a, contact.face.b, contact.face.c].reduce((p, i) => p.add(worldVertex(object, i)), new T.Vector3()).divideScalar(3);
          adapter.beginDirectInteraction(handle.id, { ...contact, point: releasingPoint });
          adapter.setDirectValue(handle.id, .75);
          assert(errorFrom(positions(object), after) < size * 2e-6, 'Re-grabbing during spring-back moved the material contact');
        }
        adapter.endDirectInteraction(handle.id);
        for (let frame = 0; frame < 100; frame++) adapter.update(.1);
        assert(errorFrom(positions(object), before) < size * 2e-6, 'Release did not restore the contact baseline');
        row.contacts++; tests++;
      }
    }
    assert(row.contacts, 'No eligible soft contact triangles');
  } catch (error) { row.failures.push({ error: error.message, stack: error.stack?.split('\n').slice(1, 3).join(' ') }); }
  finally { dispose(adapter); adapter = null; globalThis.gc?.(); }
  results.push(row); failures.push(...row.failures.map(f => ({ id: item.id, ...f })));
  console.log(JSON.stringify({ id: row.id, handles: row.handles, meshes: row.meshes, contacts: row.contacts, failures: row.failures.length }));
}
const report = { scanned: catalog.length, deformingCandidates: inventory.length, mechanismOnly: [...mechanisms], tested: results.length, contacts: tests, failures, results };
if (process.env.PHYSAG_TEST_OUTPUT) writeFileSync(process.env.PHYSAG_TEST_OUTPUT, JSON.stringify(report, null, 2));
console.log(JSON.stringify({ scanned: report.scanned, candidates: inventory.length, tested: results.length, contacts: tests, failures: failures.length }));
if (!baseline) assert.equal(failures.length, 0, 'Soft contact regressions; inspect PHYSAG_TEST_OUTPUT');
