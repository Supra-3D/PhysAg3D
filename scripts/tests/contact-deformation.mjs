import assert from 'node:assert/strict';
import { T, root } from './soft-fixtures.mjs';
const { createContactControl } = await import(new URL('viewer/contact-deformation.js', root));
const point = (mesh, i) => mesh.getVertexPosition(i, new T.Vector3()).applyMatrix4(mesh.matrixWorld);
function snapshot(mesh) { return Array.from({ length: mesh.geometry.attributes.position.count }, (_, i) => point(mesh, i)); }
function same(actual, expected, label) { assert(actual.every((p, i) => p.distanceTo(expected[i]) < 2e-6), label); }
function hit(mesh, faceIndex) {
  const indices = [0, 1, 2].map(k => mesh.geometry.index.getX(faceIndex * 3 + k));
  const [a, b, c] = indices.map(i => point(mesh, i));
  return { object: mesh, faceIndex, face: { a: indices[0], b: indices[1], c: indices[2] },
    point: a.clone().add(b).add(c).divideScalar(3), normal: b.clone().sub(a).cross(c.clone().sub(a)).normalize() };
}
for (const mode of ['plain', 'relative-morph', 'absolute-morph', 'skin']) {
  const geometry = new T.SphereGeometry(1, 32, 24), parent = new T.Group();
  parent.rotation.set(.5, .3, -.7); parent.scale.set(1.6, .7, 1.2);
  const mesh = mode === 'skin' ? new T.SkinnedMesh(geometry, new T.MeshBasicMaterial()) : new T.Mesh(geometry, new T.MeshBasicMaterial());
  parent.add(mesh);
  if (mode.includes('morph')) {
    const target = geometry.attributes.position.clone();
    for (let i = 0; i < target.count; i++) target.setXYZ(i, target.getX(i) * (mode === 'relative-morph' ? .1 : 1.1), mode === 'relative-morph' ? 0 : target.getY(i), mode === 'relative-morph' ? 0 : target.getZ(i));
    geometry.morphTargetsRelative = mode === 'relative-morph'; geometry.morphAttributes.position = [target];
    mesh.updateMorphTargets(); mesh.morphTargetInfluences[0] = 1;
  }
  if (mode === 'skin') {
    const rootBone = new T.Bone(), tip = new T.Bone(); rootBone.name = 'rigid_support'; tip.name = 'foam_region';
    rootBone.add(tip); mesh.add(rootBone); tip.position.y = .5;
    const indices = [], weights = [];
    for (let i = 0; i < geometry.attributes.position.count; i++) { indices.push(0, 1, 0, 0); const w = geometry.attributes.position.getY(i) > 0 ? 1 : 0; weights.push(1-w, w, 0, 0); }
    geometry.setAttribute('skinIndex', new T.Uint16BufferAttribute(indices, 4)); geometry.setAttribute('skinWeight', new T.Float32BufferAttribute(weights, 4));
    parent.updateMatrixWorld(true); mesh.bind(new T.Skeleton([rootBone, tip]));
    tip.rotation.z = .25; tip.scale.set(1, .9, 1.1); parent.updateMatrixWorld(true); mesh.skeleton.update();
  }
  parent.updateMatrixWorld(true);
  const rest = snapshot(mesh), originalPositions = geometry.attributes.position.array.slice();
  const originalMorphs = mesh.morphTargetInfluences?.slice();
  const profile = { label: 'Press', action: 'press', ...(mode === 'skin' ? { bones: /^foam_/ } : {}) };
  const control = createContactControl('test', profile, [mesh], 'test');
  const a = hit(mesh, 120), b = hit(mesh, 260);
  assert(control.descriptor.acceptsHit(a));
  control.begin(a); control.set(.8);
  const first = snapshot(mesh), delta = a.face;
  const average = [delta.a, delta.b, delta.c].reduce((v, i) => v.add(first[i].clone().sub(rest[i])), new T.Vector3()).divideScalar(3);
  assert(average.dot(a.normal) < -1e-4, mode + ': incorrect world normal response');
  assert.deepEqual(geometry.attributes.position.array, originalPositions, 'Mutated shared source geometry');
  control.set(0); same(snapshot(mesh), rest, mode + ': zero did not restore');
  control.set(.8); same(snapshot(mesh), first, mode + ': zero crossing lost contact');
  control.set(.35); const secondHit = hit(mesh, 260);
  control.begin(secondHit); control.set(.8);
  const moved = snapshot(mesh);
  const local = [b.face.a, b.face.b, b.face.c].reduce((sum, i) => sum + moved[i].distanceTo(rest[i]), 0) / 3;
  assert(local > .005, mode + ': re-grab missed its new triangle');
  if (mode === 'skin') {
    for (let i = 0; i < rest.length; i++) if (geometry.attributes.skinWeight.getY(i) === 0) assert(moved[i].distanceTo(rest[i]) < 2e-6, 'Rigid support deformed');
    assert.equal(control.descriptor.acceptsHit(hit(mesh, 1200)), false, 'Rigid support is pressable');
  }
  control.reset(); same(snapshot(mesh), rest, mode + ': reset drift');
  if (originalMorphs) assert.deepEqual(mesh.morphTargetInfluences, originalMorphs);
  control.dispose(); assert.equal(mesh.geometry, geometry);
  console.log(mode + ': world-space contact, zero crossing, re-grab, reset and source isolation passed');
}
