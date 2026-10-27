// Run with Node 22.15+ after `git lfs pull`:
//   node scripts/tests/native-controls.mjs
// Uses the delivered GLB hierarchy, meshes and animation tracks. The geometry
// tests replace image decoding only; browser rendering still requires visual QA.
import assert from 'node:assert/strict';
import { readFileSync, existsSync } from 'node:fs';
import { registerHooks } from 'node:module';
import { createHash } from 'node:crypto';

const root = new URL('../../', import.meta.url);
const source = new URL('scripts/browser-viewer/', root);
const offline = new URL('website/viewer/web/', root);
registerHooks({
  resolve(specifier, context, nextResolve) {
    if (specifier === 'three') return { url: new URL('vendor/three.module.js', offline).href, shortCircuit: true };
    if (context.parentURL?.startsWith(source.href) && specifier.startsWith('.')) {
      const candidate = new URL(specifier, context.parentURL);
      if (!existsSync(candidate)) return { url: new URL(specifier, offline).href, shortCircuit: true };
    }
    return nextResolve(specifier, context);
  },
});
const T = await import(new URL('vendor/three.module.js', offline));
const { createNativeControls, LADDER_CLOSURE_MAX } = await import(new URL('native-controls.js', source));
const near = (a, b, tolerance = 1e-7) => assert(Math.abs(a - b) <= tolerance, `${a} != ${b}`);
const expected = { camera: 6, phone: 2, globe: 1, ladder: 2, carousel: 1 };

function readGLB(name) {
  const path = new URL(`website/viewer/assets/${name}/appearance.glb`, root);
  const buffer = readFileSync(path);
  assert.equal(buffer.toString('ascii', 0, 4), 'glTF', `Run git lfs pull: ${path.pathname}`);
  return JSON.parse(buffer.toString('utf8', 20, 20 + buffer.readUInt32LE(12)));
}
function build(name) {
  const json = readGLB(name);
  const nodes = json.nodes.map(node => {
    const object = new T.Group(); object.name = T.PropertyBinding.sanitizeNodeName(node.name || '');
    if (node.translation) object.position.fromArray(node.translation);
    if (node.rotation) object.quaternion.fromArray(node.rotation);
    if (node.scale) object.scale.fromArray(node.scale);
    const mesh = json.meshes[node.mesh];
    if (mesh?.weights) object.morphTargetInfluences = [...mesh.weights];
    return object;
  });
  json.nodes.forEach((node, i) => (node.children || []).forEach(child => nodes[i].add(nodes[child])));
  const scene = new T.Group(); json.scenes[json.scene || 0].nodes.forEach(i => scene.add(nodes[i]));
  const outer = new T.Group(); outer.rotation.x = Math.PI / 2; outer.add(scene); outer.updateMatrixWorld(true);
  return { nodes, scene, native: createNativeControls({ native_asset_id: name }, { scene }) };
}

for (const [name, count] of Object.entries(expected)) {
  const { native } = build(name);
  assert.equal(native.controls.length, count); assert.equal(native.getHandles().length, count);
  for (const control of native.controls) {
    native.setValue(control.name, control.range[1]);
    const handle = native.getHandles().find(handle => handle.name === control.name);
    near(handle.value, control.range[1]); near(handle.axis.length(), 1);
    assert(handle.origin.toArray().every(Number.isFinite));
  }
  native.reset(); for (const control of native.controls) near(native.values[control.name], control.reference);
}
assert.equal(createNativeControls({}, {}), null);

const phone = build('phone');
phone.native.setValue('outer_fold', Math.PI / 4); near(phone.native.values.camera_fold, Math.PI);
near(phone.nodes[24].morphTargetInfluences[3], 1); near(phone.nodes[21].morphTargetInfluences[12], 1);
phone.native.setValue('camera_fold', Math.PI / 8);
near(phone.nodes[21].morphTargetInfluences[1], .5); near(phone.nodes[21].morphTargetInfluences[2], .5);
near(phone.nodes[24].morphTargetInfluences[3], 1);
for (const [node, joint] of [[phone.nodes[18], 'outer_fold'], [phone.nodes[5], 'camera_fold']]) {
  const rotation = new T.Quaternion().setFromAxisAngle(new T.Vector3(0, -1, 0), phone.native.values[joint]);
  near(Math.abs(rotation.dot(node.quaternion)), 1);
}
const camera = build('camera');
camera.native.beginInteraction('native:shutter_press'); camera.native.setValue('shutter_press', .0013);
camera.native.update(.1); near(camera.native.values.shutter_press, .0013);
camera.native.endInteraction('native:shutter_press');
for (let i = 0; i < 60; i++) camera.native.update(1 / 60);
near(camera.native.values.shutter_press, 0); assert(!camera.native.active);
camera.native.setValue('mode_dial', 3 * Math.PI); near(camera.native.values.mode_dial, 3 * Math.PI);
camera.native.setValue('lens_extension', .1); near(camera.native.values.lens_extension, .012);

const ladder = build('ladder'); let maxClosureError = 0;
for (let i = 0; i <= 500; i++) {
  ladder.native.setValue('front_joint', -.02 + .32 * (i % 71) / 70);
  ladder.native.setValue('rear_joint', -.61 + (LADDER_CLOSURE_MAX + .61) * i / 500);
  for (const [index, side] of [[1, -1], [20, 1]]) {
    const fromB = new T.Vector3(0, .0285, -.166).applyMatrix4(ladder.nodes[index].matrixWorld);
    const onRear = new T.Vector3(side * .283, -.312, -.098).applyMatrix4(ladder.nodes[18].matrixWorld);
    maxClosureError = Math.max(maxClosureError, fromB.distanceTo(onRear));
  }
}
assert(maxClosureError < 1e-6, `Link closure error ${maxClosureError}`);
ladder.native.setValue('rear_joint', .025); near(ladder.native.values.rear_joint, LADDER_CLOSURE_MAX);

// Exercise the production adapter and its real GLTFLoader. Saved animation
// tracks may supply soft shapes, but no whole-scene playback is exposed.
// No network is used: the public asset URLs resolve to the checked-out source.
const originalFetch = globalThis.fetch;
globalThis.self = globalThis;
globalThis.createImageBitmap = async () => ({ width: 1, height: 1, close() {} });
globalThis.fetch = async (input, options) => {
  const url = new URL(typeof input === 'string' ? input : input.url || input.href);
  if (url.protocol === 'blob:') return originalFetch(input, options);
  const prefix = '/website/', index = url.pathname.indexOf(prefix);
  let path;
  if (index >= 0) path = new URL('website/' + url.pathname.slice(index + prefix.length), root);
  else if (url.hostname === 'huggingface.co' && /^\/datasets\/supra3d\/physag3d-web-assets\/resolve\/[^/]+\/assets\//.test(url.pathname)) path = new URL('website/assets/' + url.pathname.split('/assets/')[1], root);
  else if (url.protocol === 'file:' && url.pathname.includes('/scripts/assets/')) path = new URL('website/assets/' + url.pathname.split('/scripts/assets/')[1], root);
  assert(path, `Unexpected network request: ${url}`);
  const bytes = readFileSync(path);
  return new Response(bytes, { headers: { 'Content-Length': String(bytes.length) } });
};
const { createGalleryAdapter } = await import(new URL('gallery-adapter.js', source));
const catalog = JSON.parse(readFileSync(new URL('website/assets/gallery-models/catalog.json', root))).assets;
function shapeSnapshot(adapter) {
  const hash = createHash('sha256');
  adapter.group.updateMatrixWorld(true);
  adapter.group.traverse(object => {
    hash.update(JSON.stringify([object.name, object.matrix.elements, object.morphTargetInfluences || []]));
    const positions = object.geometry?.attributes.position.array;
    if (positions) hash.update(Buffer.from(positions.buffer, positions.byteOffset, positions.byteLength));
  });
  return hash.digest('hex');
}
function assertNoPlayback(adapter) {
  const before = shapeSnapshot(adapter), mode = adapter.mode;
  assert(adapter.modes.every(mode => ['joints', 'static'].includes(mode.id)));
  assert(adapter.getHandles().every(handle => handle.kind !== 'replay'));
  adapter.setMode('animation'); adapter.setMode('recorded'); adapter.setClip(0);
  adapter.seek(.5); adapter.seekFrame(10); adapter.toggle(); adapter.update(.1);
  assert.equal(adapter.mode, mode); assert.equal(adapter.playing, false);
  assert.equal(adapter.duration, 0); assert.equal(adapter.time, 0); assert.equal(adapter.frame, 0);
  assert.deepEqual(adapter.clips, []);
  assert.equal(shapeSnapshot(adapter), before, 'A legacy playback API moved the model');
  assert.equal(adapter.setDirectValue('animation:0:timeline', .5), false);
  assert.equal(adapter.setDirectValue('recorded:timeline', .5), false);
}
function dispose(adapter) {
  adapter.dispose();
  adapter.group.traverse(object => object.geometry?.dispose());
  adapter.materials.forEach(material => material.dispose()); adapter.textures.forEach(texture => texture.dispose());
}
const integration = [];
for (const name of Object.keys(expected)) {
  const item = catalog.find(item => item.native_asset_id === name);
  const adapter = await createGalleryAdapter(item);
  assert.equal(adapter.mode, 'joints'); assert.equal(adapter.getHandles().length, expected[name]);
  const rest = shapeSnapshot(adapter);
  const first = adapter.controls[0]; adapter.setDirectValue('native:' + first.name, (first.range[0] + first.range[1]) / 2);
  near(adapter.values[first.name], (first.range[0] + first.range[1]) / 2);
  if (name === 'camera') {
    adapter.pause(); adapter.beginDirectInteraction('native:shutter_press'); adapter.setDirectValue('native:shutter_press', .0013);
    adapter.update(.1); near(adapter.values.shutter_press, .0013);
    adapter.endDirectInteraction('native:shutter_press'); for (let i = 0; i < 60; i++) adapter.update(1 / 60);
    near(adapter.values.shutter_press, 0);
    adapter.beginDirectInteraction('native:shutter_press'); adapter.setDirectValue('native:shutter_press', .0013);
    adapter.pause(); for (let i = 0; i < 60; i++) adapter.update(1 / 60);
    near(adapter.values.shutter_press, 0);
  }
  assertNoPlayback(adapter);
  adapter.reset();
  for (const control of adapter.controls) near(adapter.values[control.name], control.reference);
  assert.equal(shapeSnapshot(adapter), rest, `${name} reset did not restore its complete shape`);
  if (name === 'phone') {
    const mesh = adapter.group.getObjectByName(T.PropertyBinding.sanitizeNodeName('outer | continuous black display fold'));
    near(mesh.morphTargetInfluences[12], 1);
  }
  integration.push(name); dispose(adapter);
}
const softIntegration = [];
for (const [id, source] of [
  ['studio-img_001', 'browser_local_visual_deformation'],
  ['studio-img_009', 'original_morph_shapes'],
  ['extra-img_086', 'original_skinned_shapes'],
  ['studio-img_011', 'original_recorded_skin'],
  ['studio-img_035', 'authored_vertex_deltas'],
]) {
  const adapter = await createGalleryAdapter(catalog.find(item => item.id === id));
  const handle = adapter.getHandles().find(handle => handle.axisSource === source);
  assert(handle, `${id} lost its ${source} direct control`);
  const rest = shapeSnapshot(adapter);
  assertNoPlayback(adapter);
  assert.equal(adapter.beginDirectInteraction(handle.id), true);
  assert.equal(adapter.setDirectValue(handle.id, .65), true);
  near(adapter.getHandles().find(candidate => candidate.id === handle.id).value, .65);
  assert.notEqual(shapeSnapshot(adapter), rest, `${id} soft manipulation did not affect its shape`);
  adapter.update(.1); near(adapter.getHandles().find(candidate => candidate.id === handle.id).value, .65);
  assert.equal(adapter.endDirectInteraction(handle.id), true);
  for (let i = 0; i < 60; i++) adapter.update(.05);
  near(adapter.getHandles().find(candidate => candidate.id === handle.id).value, 0);
  adapter.reset();
  assert.equal(shapeSnapshot(adapter), rest, `${id} reset did not restore its complete shape`);
  softIntegration.push({ id, source }); dispose(adapter);
}
// An authored non-native joint remains independently draggable; a rigid asset
// delivered only as an animation remains inspectable without a replay handle.
const jointAdapter = await createGalleryAdapter(catalog.find(item => item.id === 'studio-img_025'));
const jointRest = shapeSnapshot(jointAdapter), joint = jointAdapter.getHandles().find(handle => ['hinge', 'slide'].includes(handle.kind));
assert(joint, 'The printer lost its authored joint');
assert.equal(jointAdapter.setDirectValue(joint.id, joint.min + (joint.max - joint.min) * .6), true);
assert.notEqual(shapeSnapshot(jointAdapter), jointRest);
assertNoPlayback(jointAdapter); jointAdapter.reset(); assert.equal(shapeSnapshot(jointAdapter), jointRest); dispose(jointAdapter);
const staticAdapter = await createGalleryAdapter(catalog.find(item => item.id === 'extra-img_088'));
assert.equal(staticAdapter.mode, 'static'); assert.deepEqual(staticAdapter.getHandles(), []);
assertNoPlayback(staticAdapter); dispose(staticAdapter);
// Regression: removing playback must not strand independently articulated
// gallery parts. Each control affects its own node without moving neighbours.
const restoredGallery = [];
for (const [id, count] of [['studio-img_027', 5], ['extra-img_130', 1], ['extra-img_123', 5]]) {
  const adapter = await createGalleryAdapter(catalog.find(item => item.id === id));
  assert.equal(adapter.mode, 'joints'); assert.equal(adapter.getHandles().length, count);
  const rest = shapeSnapshot(adapter);
  for (const handle of adapter.getHandles()) {
    const others = adapter.getHandles().filter(other => other.id !== handle.id).map(other => ({
      id: other.id, value: other.value, matrix: other.objects[0].matrixWorld.clone(),
    }));
    const matrix = handle.objects[0].matrixWorld.clone();
    const target = handle.min + (handle.max - handle.min) * .6;
    assert(adapter.setDirectValue(handle.id, target));
    const changed = adapter.getHandles().find(other => other.id === handle.id);
    near(changed.value, target); assert(!changed.objects[0].matrixWorld.equals(matrix), `${id}: ${handle.id} did not move`);
    for (const other of others) {
      const current = adapter.getHandles().find(h => h.id === other.id);
      near(current.value, other.value);
      assert(current.objects[0].matrixWorld.equals(other.matrix), `${id}: moving ${handle.id} moved ${other.id}`);
    }
    assertNoPlayback(adapter);
    adapter.reset(); assert.equal(shapeSnapshot(adapter), rest, `${id}: complete reset failed`);
  }
  restoredGallery.push({ id, independentParts: count }); dispose(adapter);
}
const keyboard = await createGalleryAdapter(catalog.find(item => item.id === 'studio-img_038'));
assert.deepEqual(keyboard.getHandles(), [], 'Do not fabricate missing per-key articulation');
assertNoPlayback(keyboard); dispose(keyboard);
console.log(JSON.stringify({ restoredGallery, keyboardHasNoSourceJoints: true }));
globalThis.fetch = originalFetch;
console.log(JSON.stringify({ status: 'passed', controls: expected, ladderConfigurations: 501, maxClosureErrorMetres: maxClosureError, directOnlyAndReset: integration, shutterHoldAndRelease: true, softHoldReleaseAndReset: softIntegration, authoredJointAndStaticFallback: true }));
