// Run with Node 22.15+ after `git lfs pull`:
//   node scripts/tests/native-controls.mjs
// Uses the delivered GLB hierarchy, meshes and animation tracks. The geometry
// tests replace image decoding only; browser rendering still requires visual QA.
import assert from 'node:assert/strict';
import { readFileSync, existsSync } from 'node:fs';
import { registerHooks } from 'node:module';

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

// Exercise the production adapter, including its real GLTFLoader and mixer.
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
const integration = [];
for (const name of Object.keys(expected)) {
  const item = catalog.find(item => item.native_asset_id === name);
  const adapter = await createGalleryAdapter(item);
  assert.equal(adapter.mode, 'joints'); assert.equal(adapter.getHandles().length, expected[name]);
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
  adapter.setMode('animation'); adapter.seek(adapter.duration / 2);
  assert(adapter.getHandles().every(handle => !handle.id.startsWith('native:')));
  if (name === 'ladder') {
    assert.equal(adapter.clips.length, 1, 'The linked recording must play all six body tracks together.');
    for (const node of ['body_front', 'body_rear', 'body_left_A', 'body_left_B', 'body_right_A', 'body_right_B']) {
      assert(Math.abs(adapter.group.getObjectByName(node).quaternion.x) > .01, `${node} did not move with the recording`);
    }
  }
  adapter.setMode('joints');
  for (const control of adapter.controls) near(adapter.values[control.name], control.reference);
  if (name === 'phone') {
    const mesh = adapter.group.getObjectByName(T.PropertyBinding.sanitizeNodeName('outer | continuous black display fold'));
    near(mesh.morphTargetInfluences[12], 1);
  }
  integration.push(name); adapter.dispose();
  adapter.group.traverse(object => object.geometry?.dispose());
  adapter.materials.forEach(material => material.dispose()); adapter.textures.forEach(texture => texture.dispose());
}
globalThis.fetch = originalFetch;
console.log(JSON.stringify({ status: 'passed', controls: expected, ladderConfigurations: 501, maxClosureErrorMetres: maxClosureError, modeSwitchAndReset: integration, shutterHoldAndRelease: true }));
