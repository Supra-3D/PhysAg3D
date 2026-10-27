import * as THREE from 'three';
import { OrbitControls } from './vendor/OrbitControls.js';
import { RoomEnvironment } from './vendor/RoomEnvironment.js';

const $ = (id) => document.getElementById(id);
const dom = Object.fromEntries(['asset-select', 'asset-file', 'import-button', 'asset-title', 'asset-code', 'asset-description', 'joint-count', 'joint-list', 'model-stats', 'engine-status', 'engine-label', 'loading-overlay', 'loading-label', 'notification', 'drop-overlay', 'reset-pose', 'reset-camera', 'auto-orbit', 'wireframe', 'mode-pose', 'mode-physics', 'simulation-row', 'simulation-label', 'pause-simulation'].map((id) => [id, $(id)]));
let assets = [], session = null, model = null, latestState = null, generation = 0;
let content = null, ground = null, grid = null, materials = [], textures = [];
let jointViews = new Map(), editing = new Set(), wireframe = false, ready = false;
let controlInFlight = false, pendingTargets = {}, pendingOptions = {}, controlTimer;
let pollInFlight = false, notificationTimer, dragDepth = 0, lastWarning = '', controlEpoch = 0;
let connection = 'starting', desiredAssetId = null, renderedAssetId = null, recoverySnapshot = null;
let reconnectTimer = null, reconnectAttempt = 0, reconnectInFlight = false, lastSessionCheck = 0;
let renderRequested = true, disposed = false, suspended = document.hidden, animationFrame = 0;
let releaseHeldControl = null;
let presentedGeneration = -1;
const requests = new Map(), ownedSessions = new Set();
const query = new URLSearchParams(window.location.search);
const embedded = query.get('embed') === '1';
const directMode = query.get('direct') !== '0';
const showcase = embedded && query.get('showcase') === '1';
let parentActive = !showcase, lastDemoState = null;
if (showcase) suspended = true;
let directController = null, directGesture = null, directStopTimer = null, directPulseControl = null;
let directModulePromise = null;
const builtinNames = { camera: 'Camera', phone: 'Phone', globe: 'Globe', ladder: 'Ladder', carousel: 'Carousel' };
const builtinJoints = {
  screen_hinge: 'Display opening', mode_dial: 'Main dial', focus_ring: 'Lens rotation',
  lens_extension: 'Lens extension', secondary_dial: 'Secondary dial', shutter_press: 'Shutter',
  outer_fold: 'Outer fold', camera_fold: 'Camera fold', body_globe_joint: 'Globe rotation',
  front_joint: 'Front frame', rear_joint: 'Rear frame', carousel_bearing: 'Platform rotation',
};
const assetName = (asset) => builtinNames[asset?.id] || asset?.name || 'Imported asset';

function motionHint(paused = false) {
  const hint = desiredAssetId === 'ladder'
    ? 'Move the front frame first. Return the rear frame before lowering the front.'
    : 'Adjust a control to move the object.';
  return paused ? `Paused. Resume to move the object. ${desiredAssetId === 'ladder' ? hint : ''}`.trim() : hint;
}

if (embedded) document.body.classList.add('embedded');
if (directMode) {
  document.body.classList.add('direct-mode', 'direct-native');
  const sheet = document.createElement('link');
  sheet.rel = 'stylesheet'; sheet.href = './direct-manipulation.css';
  document.head.append(sheet);
  const toolbar = document.createElement('div');
  toolbar.className = 'direct-native-bar'; toolbar.setAttribute('aria-label', 'Simulation controls');
  toolbar.append(dom['simulation-row'], dom['reset-pose']);
  $('viewer').append(toolbar);
  $('input-reference').classList.add('direct-reference');
  $('viewer').append($('input-reference'));
  document.querySelector('.viewport-hint').textContent = 'Select a moving part · Drag its handle · Drag empty space to orbit';
}

function postToParent(type, detail = {}) {
  if (embedded && window.parent !== window) window.parent.postMessage({ type, ...detail }, location.origin);
}

function updateReference(asset) {
  const photo = $('input-photo'), figure = $('input-reference');
  figure.hidden = true;
  photo.onload = null;
  photo.onerror = null;
  photo.removeAttribute('src');
  if (asset.imported) return;
  photo.alt = `Input photograph of ${assetName(asset).toLowerCase()}`;
  photo.onload = () => { if (!disposed) figure.hidden = false; };
  photo.onerror = () => { figure.hidden = true; };
  photo.src = `/api/assets/${encodeURIComponent(asset.id)}/thumbnail`;
}

const canvas = $('scene');
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true, preserveDrawingBuffer: true });
renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 0.94;
renderer.shadowMap.enabled = true;
renderer.shadowMap.autoUpdate = false;
renderer.shadowMap.type = THREE.PCFShadowMap;
renderer.setClearColor(0xeff2eb, 0);
const scene = new THREE.Scene();
const studio = new RoomEnvironment();
const pmrem = new THREE.PMREMGenerator(renderer);
scene.environment = pmrem.fromScene(studio, 0.04).texture;
scene.environmentIntensity = 0.7;
studio.dispose();
pmrem.dispose();
const camera = new THREE.PerspectiveCamera(36, 1, 0.001, 1000);
camera.up.set(0, 0, 1);
camera.position.set(1.8, -2.1, 1.5);
const controls = new OrbitControls(camera, canvas);
controls.addEventListener('change', () => { renderRequested = true; });
controls.enableDamping = true;
controls.dampingFactor = 0.08;
controls.autoRotateSpeed = 1.25;
controls.maxPolarAngle = Math.PI * 0.93;
controls.screenSpacePanning = true;
const hemi = new THREE.HemisphereLight(0xffffff, 0x9ca6b0, 1.0);
hemi.position.set(0, 0, 5);
scene.add(hemi);
const key = new THREE.DirectionalLight(0xffffff, 2.2);
key.position.set(-2.5, -3.5, 5);
key.castShadow = true;
key.shadow.mapSize.set(2048, 2048);
key.shadow.bias = -0.0001;
key.shadow.normalBias = 0.002;
key.shadow.radius = 6;
scene.add(key, key.target);
const fill = new THREE.DirectionalLight(0xe8f0ff, 0.75);
fill.position.set(3, 1, 2);
scene.add(fill);
const rim = new THREE.DirectionalLight(0xfff5df, 1.0);
rim.position.set(0.5, 3, 4);
scene.add(rim);
const geomObjects = new Map();
const skinObjects = new Map();
const sizeObserver = new ResizeObserver(() => {
  if (disposed) return;
  const rect = canvas.parentElement.getBoundingClientRect();
  if (rect.width <= 0 || rect.height <= 0) return;
  renderer.setSize(rect.width, rect.height, false);
  const previousAspect = camera.aspect;
  camera.aspect = rect.width / rect.height;
  camera.updateProjectionMatrix();
  if (showcase && ready && model && Math.abs(Math.log(camera.aspect / previousAspect)) > .12) resetCamera();
  renderRequested = true;
});
sizeObserver.observe(canvas.parentElement);

window.__viewer = {
  get ready() { return ready && presentedGeneration === generation; }, get assetId() { return session?.asset?.id; },
  get sessionId() { return session?.id; }, get state() { return latestState; },
  get connection() { return connection; },
  get model() { return model; }, scene, camera, controls, renderer,
  get direct() { return directController; }, get directMode() { return directMode; },
};

function stopDirectGesture(keyboardPulse = false) {
  clearTimeout(directStopTimer); directStopTimer = null;
  const gesture = directGesture;
  const control = gesture?.control || directPulseControl;
  directGesture = null;
  directPulseControl = null;
  if (!control) return;
  editing.delete(control.name);
  if (control.kind !== 'position') {
    const stop = () => {
      directPulseControl = null;
      queueControl({ [control.name]: 0 }); flushControls();
    };
    if (keyboardPulse && control.kind === 'velocity') {
      directPulseControl = control;
      flushControls();
      directStopTimer = setTimeout(stop, 150);
    } else stop();
  }
}

function directNeutralTargets() {
  return Object.fromEntries((model?.controls || []).filter((control) => control.kind !== 'position').map((control) => [control.name, 0]));
}

function directHandles() {
  if (!ready || !model?.native_controls || !latestState) return [];
  return (model.controls || []).flatMap((control) => {
    const joint = model.joints.find((entry) => entry.id === control.joint_id);
    const state = latestState.joints.find((entry) => entry.id === control.joint_id);
    if (!joint || !state?.origin || !state.axis) return [];
    const isPosition = control.kind === 'position';
    const bounds = isPosition ? control.range : joint.limited ? joint.range : [state.value - Math.PI * 4, state.value + Math.PI * 4];
    const axis = new THREE.Vector3().fromArray(state.axis).normalize();
    const description = control.kind === 'force' ? 'Hold to press the shutter. Release to let the spring return it.'
      : control.kind === 'velocity' ? 'Drag to turn this part. Its motor stops when you release.'
      : desiredAssetId === 'ladder' ? motionHint(latestState.paused) : 'Drag the handle to move this part through its original physical drive.';
    return [{
      id: control.name, label: control.label, kind: joint.type,
      origin: new THREE.Vector3().fromArray(state.origin), axis,
      objects: (control.geom_ids || []).map((id) => geomObjects.get(String(id))).filter(Boolean),
      value: state.value, min: bounds[0], max: bounds[1], unit: joint.unit,
      axisLabel: `World axis (${axis.toArray().map((value) => value.toFixed(2)).join(', ')})`,
      description, coupled: desiredAssetId === 'ladder', disabled: latestState.paused || connection !== 'connected',
    }];
  });
}

async function setupDirectControls(activeGeneration) {
  if (!directMode) return;
  directModulePromise ||= import('./direct-manipulation.js');
  const { createDirectManipulation } = await directModulePromise;
  if (disposed || activeGeneration !== generation) return;
  directController?.dispose();
  directController = createDirectManipulation({
    scene, camera, canvas, orbit: controls, host: $('viewer'), getHandles: directHandles,
    getPickObjects: () => content ? [content] : [],
    onDirty: () => { renderRequested = true; },
    onDragStart(handle, detail = {}) {
      stopDirectGesture();
      const control = model?.controls.find((entry) => entry.name === handle.id);
      if (!control || !ready) return;
      if (showcase) queueControl({}, {demo:false, paused:false});
      directGesture = { control, lastValue: handle.value, lastTime: performance.now(), source: detail.source };
      editing.add(control.name);
      if (control.kind === 'force') {
        queueControl({ [control.name]: control.range[1] }); flushControls();
      }
    },
    onChange(id, value, detail = {}) {
      const control = model?.controls.find((entry) => entry.name === id);
      if (!control || !ready || !Number.isFinite(value)) return;
      if (control.kind === 'position') {
        queueControl({ [control.name]: value });
      } else if (control.kind === 'velocity' && directGesture?.control.name === control.name) {
        const now = performance.now(), elapsed = Math.max(Number.isFinite(detail.dt) ? detail.dt : (now - directGesture.lastTime) / 1000, 1 / 120);
        const speed = THREE.MathUtils.clamp((value - directGesture.lastValue) / elapsed, ...control.range);
        directGesture.lastValue = value; directGesture.lastTime = now;
        queueControl({ [control.name]: speed });
        clearTimeout(directStopTimer);
        directStopTimer = setTimeout(() => {
          if (directGesture?.control.name === control.name) { queueControl({ [control.name]: 0 }); flushControls(); }
        }, 150);
      }
    },
    onDragEnd(handle, detail = {}) {
      stopDirectGesture(directGesture?.source === 'keyboard' && !detail.cancelled);
    },
  });
}

function notify(message, error = false, duration = 4500) {
  if (disposed) return;
  clearTimeout(notificationTimer);
  dom.notification.textContent = message;
  dom.notification.classList.toggle('error', error);
  dom.notification.hidden = false;
  if (error) { window.__physagViewerBoot?.fail(message); postToParent('physag-viewer-error', { message }); }
  if (duration) notificationTimer = setTimeout(() => { dom.notification.hidden = true; }, duration);
}

async function api(path, options = {}) {
  if (disposed) throw new DOMException('Viewer closed', 'AbortError');
  const { timeoutMs = 30000, ...requestOptions } = options;
  const controller = new AbortController();
  // Let a small creation request finish so its returned session can be released.
  const creatingSession = path === '/api/sessions' && requestOptions.method === 'POST';
  requests.set(controller, creatingSession);
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(path, { ...requestOptions, keepalive: creatingSession || requestOptions.keepalive, signal: controller.signal });
    let data;
    try { data = await response.json(); } catch {
      throw Object.assign(new Error(`Unexpected viewer response (${response.status})`), { status: response.status, reconnect: response.status >= 500 });
    }
    if (!response.ok) {
      const expired = response.status === 404 && /^\/api\/sessions\/[^/]+\//.test(path);
      const message = expired ? 'The simulation session expired. Reconnecting…' : (typeof data.error === 'string' ? data.error : (data.error?.message || data.detail || `Request failed (${response.status})`));
      throw Object.assign(new Error(message), { status: response.status, reconnect: expired || response.status >= 500 });
    }
    return data;
  } catch (error) {
    if (error.name === 'AbortError' || error instanceof TypeError) {
      throw Object.assign(new Error(error.name === 'AbortError' ? 'The viewer took too long to respond. Reconnecting…' : 'The viewer is temporarily unavailable. Reconnecting…'), { reconnect: true });
    }
    throw error;
  } finally { clearTimeout(timer); requests.delete(controller); }
}

function setConnection(status, label) {
  connection = status;
  $('app').dataset.connection = status;
  dom['engine-status'].classList.toggle('error', status === 'reconnecting' || status === 'error');
  dom['engine-label'].textContent = label;
}

function rememberState() {
  if (recoverySnapshot || !latestState || renderedAssetId !== desiredAssetId) return;
  const states = model?.native_controls ? latestState.controls : latestState.joints;
  recoverySnapshot = {
    native: Boolean(model?.native_controls),
    values: Object.fromEntries((states || []).map((joint) => [joint.name, joint.value])),
    targets: Object.fromEntries((states || []).map((joint) => [joint.name, joint.target ?? joint.value])),
    mode: latestState.mode, paused: latestState.paused,
  };
}

function scheduleReconnect(immediate = false) {
  if (disposed || suspended || connection !== 'reconnecting' || reconnectTimer || reconnectInFlight) return;
  const delay = immediate ? 0 : Math.min(1000 * 2 ** Math.min(reconnectAttempt++, 4), 15000);
  reconnectTimer = setTimeout(() => { reconnectTimer = null; reconnect(); }, delay);
}

function reconnectAfter(error) {
  if (disposed) return;
  if (directMode) stopDirectGesture();
  rememberState();
  if (error.status === 404) session = null;
  ready = false;
  clearTimeout(controlTimer); controlTimer = null;
  setLoading(false);
  dom['reset-pose'].disabled = true;
  const firstFailure = connection !== 'reconnecting';
  setConnection('reconnecting', 'Reconnecting…');
  if (latestState?.mode === 'physics') dom['simulation-label'].textContent = 'Waiting for connection';
  if (firstFailure) notify(`${error.message} Your view will recover automatically.`, true, 0);
  scheduleReconnect();
}

function connected(recovered = false) {
  if (disposed) return;
  ready = true; recoverySnapshot = null; reconnectAttempt = 0;
  clearTimeout(reconnectTimer); reconnectTimer = null;
  lastSessionCheck = Date.now();
  setConnection('connected', 'Live controls');
  if (recovered) notify('Reconnected. Your view and joint settings have been restored.', false, 4500);
  else if (dom.notification.classList.contains('error')) dom.notification.hidden = true;
  if (suspended) queueControl({}, { paused: true });
  flushControls();
}

function presentReady(activeGeneration = generation) {
  if (disposed || activeGeneration !== generation || !ready || !content) return;
  const rect = canvas.parentElement.getBoundingClientRect();
  if (rect.width <= 0 || rect.height <= 0) return;
  renderer.setSize(rect.width, rect.height, false);
  camera.aspect = rect.width / rect.height; camera.updateProjectionMatrix();
  controls.update(); directController?.update();
  renderer.render(scene, camera); renderRequested = false;
  presentedGeneration = activeGeneration;
  setLoading(false); window.__physagViewerBoot?.complete();
  postToParent('physag-viewer-ready', { assetId: session?.asset?.id || desiredAssetId });
}

async function reconnect() {
  if (disposed || suspended || reconnectInFlight || connection !== 'reconnecting') return;
  reconnectInFlight = true;
  const activeGeneration = generation;
  try {
    await api('/api/health', { timeoutMs: 5000 });
    const listing = await api('/api/assets', { timeoutMs: 10000 });
    if (activeGeneration !== generation) return;
    assets = listing.assets || [];
    updateOptions(desiredAssetId);
    if (!desiredAssetId) desiredAssetId = assets.find((asset) => asset.id === query.get('asset'))?.id || assets.find((asset) => asset.id === 'camera')?.id || assets[0]?.id;
    if (!desiredAssetId) { setLoading(false); setConnection('connected', 'Ready to import'); dom.notification.hidden = true; window.__physagViewerBoot?.complete(); return; }
    if (session) {
      try {
        const state = await api(`/api/sessions/${encodeURIComponent(session.id)}/state`);
        if (activeGeneration !== generation) return;
        updateState(state); connected(true); presentReady(activeGeneration); return;
      } catch (error) { if (error.status !== 404) throw error; session = null; }
    }
    await loadAsset(desiredAssetId, { recovering: true });
  } catch (error) {
    if (activeGeneration === generation) {
      if (error.reconnect) reconnectAfter(error);
      else { setConnection('error', 'Could not restore asset'); notify(error.message, true, 0); }
    }
  } finally {
    reconnectInFlight = false;
    scheduleReconnect();
  }
}

async function restoreSession(created, activeGeneration) {
  if (!recoverySnapshot) return created.state;
  const saved = recoverySnapshot;
  const targets = { ...saved.targets, ...pendingTargets };
  const options = { mode: saved.mode, paused: saved.paused, ...pendingOptions };
  if (suspended) options.paused = true;
  pendingTargets = {}; pendingOptions = {};
  const path = `/api/sessions/${encodeURIComponent(created.id)}/control`;
  try {
    if (saved.native) {
      // Native actuators resume through the solver; never overwrite coupled qpos.
      const restoredTargets = { ...(options.reset ? {} : targets), ...(directMode ? directNeutralTargets() : {}) };
      return await api(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ actuators: restoredTargets, ...options, mode: 'physics' }) });
    }
    // Restore the observed pose before resuming a previously running simulation.
    // Simulation time and velocity restart with the new server session.
    let state = await api(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ mode: 'pose', paused: options.mode === 'physics' ? true : options.paused, targets: options.reset ? {} : (options.mode === 'physics' ? saved.values : targets), reset: options.reset }) });
    if (activeGeneration !== generation) return null;
    if (options.mode === 'physics') {
      state = await api(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ targets: options.reset ? {} : targets, ...options }) });
    }
    return state;
  } catch (error) {
    if (activeGeneration === generation) {
      pendingTargets = { ...targets, ...pendingTargets }; pendingOptions = { ...options, ...pendingOptions };
    }
    throw error;
  }
}

function deleteSession(id) {
  ownedSessions.delete(id);
  if (id) fetch(`/api/sessions/${encodeURIComponent(id)}`, { method: 'DELETE', keepalive: true }).catch(() => {});
}

function setLoading(value, label = 'Loading asset') {
  dom['loading-overlay'].hidden = !value;
  dom['loading-label'].textContent = label;
  dom['reset-pose'].disabled = value || !session;
}

function disposeGroup(group) {
  if (!group) return;
  const geometries = new Set();
  const mats = new Set();
  group.traverse((child) => {
    if (child.geometry) geometries.add(child.geometry);
    if (child.material) (Array.isArray(child.material) ? child.material : [child.material]).forEach((m) => mats.add(m));
  });
  geometries.forEach((g) => g.dispose());
  mats.forEach((m) => m.dispose());
  scene.remove(group);
}

function clearContent() {
  disposeGroup(content); disposeGroup(ground); disposeGroup(grid);
  textures.forEach((texture) => texture.dispose());
  content = null; ground = null; grid = null; materials = []; textures = [];
  geomObjects.clear();
  skinObjects.clear();
}

async function resourceData(url, kind) {
  if (disposed) throw new DOMException('Viewer closed', 'AbortError');
  const controller = new AbortController();
  requests.set(controller, false);
  const timer = setTimeout(() => controller.abort(), 30000);
  try {
    const response = await fetch(url, { signal: controller.signal });
    if (!response.ok) throw Object.assign(new Error(`Could not load model data (${response.status})`), { reconnect: response.status >= 500 });
    return await response[kind]();
  } finally { clearTimeout(timer); requests.delete(controller); }
}

async function loadGeometry(mesh) {
  const geometry = new THREE.BufferGeometry();
  if (mesh.url) {
    let values;
    try {
      values = new Float32Array(await resourceData(mesh.url, 'arrayBuffer'));
    } catch (error) {
      geometry.dispose();
      if (error instanceof TypeError || ['AbortError', 'TimeoutError'].includes(error.name)) throw Object.assign(new Error('Model transfer was interrupted. Reconnecting…'), { reconnect: true });
      throw error;
    }
    const buffer = new THREE.InterleavedBuffer(values, mesh.stride || 8);
    geometry.setAttribute('position', new THREE.InterleavedBufferAttribute(buffer, 3, 0));
    geometry.setAttribute('normal', new THREE.InterleavedBufferAttribute(buffer, 3, 3));
    geometry.setAttribute('uv', new THREE.InterleavedBufferAttribute(buffer, 2, 6));
  } else {
    geometry.setAttribute('position', new THREE.Float32BufferAttribute(mesh.vertices || [], 3));
    if (mesh.normals?.length) geometry.setAttribute('normal', new THREE.Float32BufferAttribute(mesh.normals, 3));
    if (mesh.uvs?.length) geometry.setAttribute('uv', new THREE.Float32BufferAttribute(mesh.uvs, 2));
    if (mesh.indices?.length) geometry.setIndex(mesh.indices);
    if (!mesh.normals?.length) geometry.computeVertexNormals();
  }
  geometry.computeBoundingSphere();
  return geometry;
}

function makePrimitive(geom, material, meshGeometries) {
  const s = geom.size || [0.05, 0.05, 0.05];
  let geometry;
  if (geom.type === 'mesh') geometry = meshGeometries.get(String(geom.mesh_id));
  else if (geom.type === 'box') geometry = new THREE.BoxGeometry(s[0] * 2, s[1] * 2, s[2] * 2);
  else if (geom.type === 'sphere' || geom.type === 'ellipsoid') {
    geometry = new THREE.SphereGeometry(geom.type === 'sphere' ? s[0] : 1, 40, 24);
    if (geom.type === 'ellipsoid') geometry.scale(s[0], s[1], s[2]);
  } else if (geom.type === 'cylinder') {
    geometry = new THREE.CylinderGeometry(s[0], s[0], s[1] * 2, 40);
    geometry.rotateX(Math.PI / 2);
  } else if (geom.type === 'capsule') {
    const group = new THREE.Group();
    const shaft = new THREE.CylinderGeometry(s[0], s[0], s[1] * 2, 32);
    shaft.rotateX(Math.PI / 2);
    group.add(new THREE.Mesh(shaft, material));
    for (const sign of [-1, 1]) {
      const cap = new THREE.Mesh(new THREE.SphereGeometry(s[0], 32, 20), material);
      cap.position.z = sign * s[1]; group.add(cap);
    }
    return group;
  } else if (geom.type === 'plane') return null;
  if (!geometry) return null;
  return new THREE.Mesh(geometry, material);
}

async function buildModel(data, activeGeneration) {
  const meshResults = await Promise.allSettled((data.meshes || []).map(async (mesh) => [String(mesh.id), await loadGeometry(mesh)]));
  const meshEntries = meshResults.filter((result) => result.status === 'fulfilled').map((result) => result.value);
  const failedMesh = meshResults.find((result) => result.status === 'rejected');
  if (failedMesh) { meshEntries.forEach(([, geometry]) => geometry.dispose()); throw failedMesh.reason; }
  if (activeGeneration !== generation) { meshEntries.forEach(([, g]) => g.dispose()); return null; }
  const textureMap = new Map();
  const localTextures = [];
  let sourceMaterials = null;
  if (data.source_materials_url) {
    try {
      const { loadSourceMaterials } = await import('./source-materials.js');
      sourceMaterials = await loadSourceMaterials(await resourceData(data.source_materials_url, 'arrayBuffer'));
      for (const geom of [...data.geoms || [], ...data.skins || []]) {
        if (!sourceMaterials.get(geom.source_material, geom.source_material_index)) throw new Error(`Missing source material: ${geom.source_material || geom.name}`);
      }
      if (activeGeneration !== generation) {
        sourceMaterials.dispose(); meshEntries.forEach(([, geometry]) => geometry.dispose()); return null;
      }
      localTextures.push(...sourceMaterials.textures);
    } catch (error) {
      sourceMaterials?.dispose(); meshEntries.forEach(([, geometry]) => geometry.dispose()); throw error;
    }
  }
  let textureFailure;
  await Promise.all((sourceMaterials ? [] : data.textures || []).map(async (texture) => {
    let objectUrl;
    try {
      let blob;
      try {
        blob = await resourceData(texture.url, 'blob');
      } catch (error) {
        if (error instanceof TypeError || ['AbortError', 'TimeoutError'].includes(error.name)) throw Object.assign(new Error('Texture transfer was interrupted. Reconnecting…'), { reconnect: true });
        throw error;
      }
      objectUrl = URL.createObjectURL(blob);
      const tex = await new THREE.TextureLoader().loadAsync(objectUrl);
      // MuJoCo compiles OBJ UVs with V already flipped into image-row space.
      // Flipping the image again samples unrelated islands in the texture atlas.
      tex.flipY = false;
      tex.colorSpace = texture.role === 'metallic_roughness' ? THREE.NoColorSpace : THREE.SRGBColorSpace;
      tex.wrapS = tex.wrapT = THREE.RepeatWrapping;
      tex.anisotropy = Math.min(renderer.capabilities.getMaxAnisotropy(), 8);
      localTextures.push(tex); textureMap.set(String(texture.id), tex);
    } catch (error) {
      // A missing optional texture is tolerable; a network outage must retry,
      // otherwise it can leave the asset permanently stripped of its materials.
      if (error.reconnect) textureFailure ||= error;
    } finally { if (objectUrl) URL.revokeObjectURL(objectUrl); }
  }));
  if (textureFailure) { meshEntries.forEach(([, geometry]) => geometry.dispose()); localTextures.forEach((texture) => texture.dispose()); throw textureFailure; }
  if (activeGeneration !== generation) {
    meshEntries.forEach(([, g]) => g.dispose());
    if (sourceMaterials) sourceMaterials.dispose();
    else localTextures.forEach((t) => t.dispose());
    return null;
  }
  const meshGeometries = new Map(meshEntries), group = new THREE.Group(), objects = new Map(), localSkins = new Map(), localMaterials = [];
  for (const geom of data.geoms || []) {
    if (geom.type === 'plane') continue;
    const rgba = geom.rgba || [0.72, 0.75, 0.69, 1];
    if (rgba[3] === 0) continue;
    const sourceTexture = textureMap.get(String(geom.texture_id));
    const metallicRoughnessMap = textureMap.get(String(geom.metallic_roughness_texture_id));
    let map = sourceTexture;
    if (sourceTexture && geom.texrepeat) {
      map = sourceTexture.clone(); map.repeat.set(geom.texrepeat[0], geom.texrepeat[1]);
      map.needsUpdate = true; localTextures.push(map);
    }
    const material = sourceMaterials?.get(geom.source_material, geom.source_material_index) || new THREE.MeshStandardMaterial({
      color: new THREE.Color(rgba[0], rgba[1], rgba[2]), map,
      roughness: geom.roughness ?? Math.max(0.2, Math.min(0.92, 0.68 - (geom.shininess || 0) * 0.35)),
      metalness: geom.metalness ?? Math.max(0, Math.min(0.55, (geom.reflectance || 0) * 0.7)),
      roughnessMap: metallicRoughnessMap || null, metalnessMap: metallicRoughnessMap || null,
      transparent: rgba[3] < 0.99, opacity: rgba[3], side: THREE.DoubleSide, wireframe,
    });
    material.wireframe = wireframe;
    localMaterials.push(material);
    const object = makePrimitive(geom, material, meshGeometries);
    if (!object) continue;
    if (sourceMaterials && geom.source_uv_channel > 0) {
      // The supplied MJCF exporter bakes this source UV set into its single UV
      // stream. Expose it under the original channel; retain source map settings.
      object.traverse(child => {
        if (child.geometry?.attributes.uv) child.geometry.setAttribute(`uv${geom.source_uv_channel}`, child.geometry.attributes.uv);
      });
    }
    object.name = geom.name || `geom_${geom.id}`;
    object.traverse((child) => { if (child.isMesh) {
      // Standard shadow maps cannot transmit light through physical glass.
      child.castShadow = !(material.transmission > 0);
      child.receiveShadow = !(material.transmission > 0);
    } });
    objects.set(String(geom.id), object); group.add(object);
  }
  // MuJoCo computes these vertices in world space, including the phone's seams.
  // Keep them at identity so a body transform is never applied a second time.
  for (const skin of data.skins || []) {
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.Float32BufferAttribute(skin.positions, 3).setUsage(THREE.DynamicDrawUsage));
    geometry.setAttribute('normal', new THREE.Float32BufferAttribute(skin.normals, 3).setUsage(THREE.DynamicDrawUsage));
    geometry.setIndex(skin.indices);
    const rgba = skin.rgba || [0.04, 0.04, 0.04, 1];
    const material = sourceMaterials?.get(skin.source_material, skin.source_material_index) || new THREE.MeshStandardMaterial({ color: new THREE.Color(...rgba.slice(0, 3)), roughness: 0.65, side: THREE.DoubleSide, transparent: rgba[3] < 0.99, opacity: rgba[3], wireframe });
    material.wireframe = wireframe;
    const object = new THREE.Mesh(geometry, material);
    object.name = skin.name || 'Display seam';
    object.castShadow = true; object.receiveShadow = true; object.frustumCulled = false;
    localMaterials.push(material); localSkins.set(String(skin.id), object); group.add(object);
  }
  // Geometries with no visible geom should not stay allocated.
  const usedGeometries = new Set();
  group.traverse((o) => { if (o.geometry) usedGeometries.add(o.geometry); });
  meshEntries.forEach(([, geometry]) => { if (!usedGeometries.has(geometry)) geometry.dispose(); });
  return { group, objects, localSkins, localMaterials, localTextures };
}

function addGround(bounds) {
  const min = new THREE.Vector3(...bounds.min), max = new THREE.Vector3(...bounds.max);
  const center = new THREE.Vector3().addVectors(min, max).multiplyScalar(0.5);
  const span = Math.max(max.x - min.x, max.y - min.y, max.z - min.z, 0.12);
  const groundZ = min.z - span * 0.003;
  ground = new THREE.Mesh(new THREE.PlaneGeometry(span * 30, span * 30), new THREE.ShadowMaterial({ color: 0x34404c, opacity: 0.13 }));
  ground.position.set(center.x, center.y, groundZ); ground.receiveShadow = true; scene.add(ground);
  grid = new THREE.GridHelper(span * 10, 100, 0xc9d3bf, 0xd6dfcc);
  grid.rotation.x = Math.PI / 2; grid.position.set(center.x, center.y, groundZ - span * 0.001);
  grid.material.transparent = true; grid.material.opacity = 0.075; grid.material.depthWrite = false;
  scene.add(grid);
  key.position.set(center.x - span * 2, center.y - span * 2.5, center.z + span * 4);
  key.target.position.copy(center);
  key.shadow.camera.left = -span * 2; key.shadow.camera.right = span * 2;
  key.shadow.camera.top = span * 2; key.shadow.camera.bottom = -span * 2;
  key.shadow.camera.near = span * 0.01; key.shadow.camera.far = span * 12;
  key.shadow.camera.updateProjectionMatrix();
  key.shadow.normalBias = span * 0.001;
  fill.position.set(center.x + span * 2, center.y + span, center.z + span * 2);
  rim.position.set(center.x, center.y + span * 2, center.z + span * 3);
  controls.minDistance = span * 0.25;
  controls.maxDistance = span * 12;
  camera.near = Math.max(0.0001, span * 0.001); camera.far = span * 100;
  camera.updateProjectionMatrix();
}

function resetCamera() {
  if (!model?.bounds) return;
  // Consume the remaining orbit/pan damping before applying a new home view.
  const wasDamping = controls.enableDamping;
  controls.enableDamping = false;
  controls.autoRotate = false;
  controls.update();
  dom['auto-orbit'].setAttribute('aria-pressed', 'false');
  // A folded phone is narrower than its full motion envelope. Use the supplied
  // framing envelope only here, never during incoming simulation updates.
  const framing = model.frame_bounds;
  const currentBounds = !framing && content ? new THREE.Box3().setFromObject(content) : null;
  const min = framing ? new THREE.Vector3(...framing.min) : currentBounds && !currentBounds.isEmpty() ? currentBounds.min : new THREE.Vector3(...model.bounds.min);
  const max = framing ? new THREE.Vector3(...framing.max) : currentBounds && !currentBounds.isEmpty() ? currentBounds.max : new THREE.Vector3(...model.bounds.max);
  const center = new THREE.Vector3().addVectors(min, max).multiplyScalar(0.5);
  const dimension = new THREE.Vector3().subVectors(max, min);
  const radius = Math.max(dimension.length() * 0.5, 0.08);
  const limitingFov = Math.min(THREE.MathUtils.degToRad(camera.fov), 2 * Math.atan(Math.tan(THREE.MathUtils.degToRad(camera.fov / 2)) * camera.aspect));
  const showcaseFit = showcase && camera.aspect > 1.2 && session?.asset?.id === 'camera' ? .82 : 1;
  const distance = radius / Math.sin(limitingFov / 2) * 1.03 * showcaseFit;
  // The existing assets have different front-axis conventions.
  const sourceViews = { camera: [1, 1.4, 0.72], phone: [1, -1.35, 0.85], globe: [1, -1.35, 0.85], ladder: [1, -1.35, 0.85], carousel: [1, -1.35, 0.85] };
  const viewDirection = new THREE.Vector3(...(model.view_direction || sourceViews[session?.asset?.id] || [1, -1.35, 0.85])).normalize();
  controls.target.copy(center);
  camera.position.copy(center).addScaledVector(viewDirection, distance);
  controls.update(); controls.saveState();
  controls.enableDamping = wasDamping;
}

function updateOptions(selectedId) {
  dom['asset-select'].replaceChildren();
  for (const asset of assets) {
    const option = document.createElement('option'); option.value = asset.id;
    option.textContent = assetName(asset);
    dom['asset-select'].append(option);
  }
  if (selectedId) dom['asset-select'].value = selectedId;
  dom['asset-select'].disabled = false;
}

async function loadAsset(assetId, { recovering = false } = {}) {
  if (disposed) return;
  stopDirectGesture();
  directController?.dispose(); directController = null;
  releaseHeldControl?.();
  const activeGeneration = ++generation;
  desiredAssetId = assetId;
  clearTimeout(reconnectTimer); reconnectTimer = null;
  if (!recovering) { pendingTargets = {}; pendingOptions = {}; recoverySnapshot = null; reconnectAttempt = 0; }
  ready = false; controlInFlight = false;
  pollInFlight = false; editing.clear(); clearTimeout(controlTimer); controlTimer = null;
  const previousSession = session;
  session = null;
  deleteSession(previousSession?.id);
  const reuseModel = recovering && content && model && renderedAssetId === assetId;
  setLoading(!recovering || !content, recovering ? 'Restoring asset' : 'Loading asset');
  setConnection('loading', recovering ? 'Restoring connection' : 'Connecting…');
  let created;
  try {
    created = await api('/api/sessions', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ asset_id: assetId }) });
    ownedSessions.add(created.id);
    if (activeGeneration !== generation) { deleteSession(created.id); return; }
    const restoredState = recovering ? await restoreSession(created, activeGeneration) : created.state;
    if (activeGeneration !== generation) { deleteSession(created.id); return; }
    if (reuseModel) {
      session = created;
      updateState(restoredState); connected(true); updateOptions(assetId);
      await setupDirectControls(activeGeneration);
      presentReady(activeGeneration);
      return;
    }
    dom['loading-label'].textContent = 'Preparing the 3D view';
    // A previous Studio version may have cached a descriptor without axis metadata.
    const data = await api(created.model_url, { cache: 'no-store' });
    if (activeGeneration !== generation) { deleteSession(created.id); return; }
    const result = await buildModel(data, activeGeneration);
    if (!result) { deleteSession(created.id); return; }
    clearContent();
    session = created; model = data; renderedAssetId = assetId; latestState = null;
    content = result.group; materials = result.localMaterials; textures = result.localTextures;
    result.objects.forEach((object, id) => geomObjects.set(id, object));
    result.localSkins.forEach((object, id) => skinObjects.set(id, object));
    scene.add(content);
    updateState(restoredState);
    const fallbackBounds = new THREE.Box3().setFromObject(content);
    if (!data.bounds || !Number.isFinite(data.bounds.min?.[0])) data.bounds = { min: fallbackBounds.min.toArray(), max: fallbackBounds.max.toArray() };
    const viewport = canvas.parentElement.getBoundingClientRect();
    camera.aspect = viewport.width / viewport.height; camera.updateProjectionMatrix();
    addGround(data.bounds); resetCamera(); buildJointControls(data.native_controls ? data.controls || [] : data.joints || []);
    updateState(restoredState);
    const asset = created.asset || assets.find((a) => a.id === assetId) || {};
    dom['asset-title'].textContent = assetName(asset);
    updateReference({ ...asset, id: assetId });
    dom['asset-code'].textContent = asset.id || assetId;
    dom['asset-description'].textContent = asset.description || 'Orbit the view to explore its shape and movement.';
    const stats = data.stats || {};
    dom['model-stats'].textContent = `${stats.bodies ?? '—'} parts / ${(data.joints || []).length} joints${Number.isFinite(stats.triangles) ? ` / ${new Intl.NumberFormat('en', { notation: 'compact', maximumFractionDigits: 1 }).format(stats.triangles)} triangles` : ''}`;
    connected(recovering);
    if (directMode && data.native_controls && !recovering) queueControl(directNeutralTargets());
    await setupDirectControls(activeGeneration);
    if (disposed || activeGeneration !== generation) return;
    updateOptions(assetId);
    presentReady(activeGeneration);
    if (!(data.native_controls ? data.controls || [] : data.joints || []).length) notify('This asset has no available controls. Drag to inspect it from any angle.');
  } catch (error) {
    if (activeGeneration !== generation) return;
    if (created?.id) deleteSession(created.id);
    if (error.reconnect) { reconnectAfter(error); return; }
    setLoading(false); setConnection('error', 'Could not load asset');
    notify(error.message, true, 0);
    if (!content) {
      dom['joint-list'].replaceChildren();
      const message = document.createElement('div'); message.className = 'empty-state';
      message.textContent = 'This asset could not be loaded. Choose another asset or import a model.';
      dom['joint-list'].append(message);
    }
    console.error(error);
  }
}

const rotateIcon = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 8V3m0 0h5M5 3l3 4m-3 7a7 7 0 1 0 2-7"/></svg>';
const slideIcon = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 12h18M7 8l-4 4 4 4m10-8 4 4-4 4M9 4h6v16H9z"/></svg>';
const format = (value, digits = 1) => Number.isFinite(value) ? Number(value.toFixed(digits)).toString() : '0';

function buildJointControls(joints) {
  jointViews.clear(); dom['joint-list'].replaceChildren();
  const native = Boolean(model?.native_controls);
  dom['mode-pose'].parentElement.hidden = native;
  $('motion-help').textContent = native ? motionHint(latestState?.paused) : 'Move a slider to explore a joint.';
  dom['joint-count'].textContent = String(joints.length);
  if (!joints.length) {
    const empty = document.createElement('div'); empty.className = 'empty-state';
    empty.innerHTML = '<svg viewBox="0 0 24 24"><path d="m12 3 9 5v8l-9 5-9-5V8l9-5Zm0 0v10m9-5-9 5-9-5m9 5v8"/></svg>No movable joints in this model.<br>Drag the view to inspect its shape.';
    dom['joint-list'].append(empty); return;
  }
  for (const [index, joint] of joints.entries()) {
    const isSlide = native ? joint.unit === 'm' : joint.type === 'slide';
    const isForce = native && joint.kind === 'force';
    const isVelocity = native && joint.kind === 'velocity';
    const angular = native ? /^rad(?:\/s)?$/.test(joint.unit) : !isSlide;
    const multiplier = (angular ? 180 / Math.PI : isSlide ? (native ? 1000 : 100) : 1) * (joint.display_sign || 1);
    const unit = angular ? (isVelocity ? '°/s' : '°') : isSlide ? (native ? 'mm' : 'cm') : (joint.unit || 'N');
    const digits = isForce ? 3 : 1;
    const baseRange = joint.range && (native || joint.limited !== false) ? joint.range : (isSlide ? [-1, 1] : [-Math.PI, Math.PI]);
    const displayRange = baseRange.map((value) => value * multiplier).sort((a, b) => a - b);
    if (displayRange[0] === displayRange[1]) displayRange[1] += isSlide ? 1 : 1;
    const card = document.createElement('div'); card.className = 'joint-card';
    const safeId = `joint-${index}`;
    card.innerHTML = `<div class="joint-top"><label class="joint-title" for="${safeId}"><span class="joint-icon">${isSlide ? slideIcon : rotateIcon}</span><span class="joint-label"></span></label><div class="joint-readout"><span>Current</span><b></b></div></div><div class="joint-input-row"><input class="joint-slider" id="${safeId}" type="range"/><div class="joint-number-wrap"><input class="joint-number" type="number" aria-label=""/><span>${unit}</span></div></div><div class="joint-range"><span></span><span></span></div><div class="joint-meta"></div>`;
    const label = native ? joint.label || joint.name : builtinNames[desiredAssetId] ? (builtinJoints[joint.name] || joint.label || joint.name) : (joint.label || joint.name);
    card.querySelector('.joint-label').textContent = label;
    const slider = card.querySelector('.joint-slider'), number = card.querySelector('.joint-number');
    const current = card.querySelector('.joint-readout b');
    slider.min = number.min = String(displayRange[0]); slider.max = number.max = String(displayRange[1]);
    slider.step = number.step = isForce ? '0.005' : (isSlide ? '0.1' : '0.5');
    number.setAttribute('aria-label', `${label}, in ${unit}`);
    slider.setAttribute('aria-label', label);
    slider.title = native ? `${label} · ${isForce ? 'Applied force' : isVelocity ? 'Rotation speed' : 'Target position'}` : `${label} · ${isSlide ? 'Linear movement' : 'Rotation'}`;
    const rangeLabels = card.querySelectorAll('.joint-range span');
    rangeLabels[0].textContent = `${format(displayRange[0])}${unit}`; rangeLabels[1].textContent = `${format(displayRange[1])}${unit}`;
    card.querySelector('.joint-meta').textContent = `${isSlide ? 'Linear movement' : 'Rotation'} · ${joint.limited === false ? 'Typical display range' : 'Model-defined range'}`;
    const view = { joint, multiplier, unit, digits, slider, number, current, displayRange };
    const states = native ? latestState?.controls : latestState?.joints;
    const initial = states?.find((stateJoint) => stateJoint.name === joint.name)?.target ?? joint.value ?? 0;
    setJointDisplay(view, initial);
    const onInput = (source) => {
      const displayValue = Math.max(displayRange[0], Math.min(displayRange[1], Number(source.value)));
      if (!Number.isFinite(displayValue)) return;
      const rawValue = displayValue / multiplier;
      setJointDisplay(view, rawValue, source === number);
      queueControl({ [joint.name]: rawValue });
    };
    slider.addEventListener('input', () => onInput(slider));
    number.addEventListener('input', () => { if (number.value !== '') onInput(number); });
    for (const input of [slider, number]) {
      input.addEventListener('pointerdown', () => editing.add(joint.name));
      input.addEventListener('focus', () => editing.add(joint.name));
      input.addEventListener('blur', () => { editing.delete(joint.name); if (number.value === '') setJointDisplay(view, (native ? latestState?.controls : latestState?.joints)?.find((j) => j.name === joint.name)?.target ?? 0); });
      input.addEventListener('change', () => { onInput(input); editing.delete(joint.name); flushControls(); });
      input.addEventListener('pointerup', () => { editing.delete(joint.name); });
      input.addEventListener('pointercancel', () => editing.delete(joint.name));
    }
    if (native && isForce && desiredAssetId === 'camera') {
      const press = document.createElement('button');
      press.type = 'button'; press.className = 'button shutter-control';
      press.textContent = 'Hold to press shutter';
      press.setAttribute('aria-label', 'Hold to press the shutter. Release to let go.');
      press.setAttribute('aria-pressed', 'false');
      let held = false;
      const release = () => {
        if (!held) return;
        held = false; releaseHeldControl = null; editing.delete(joint.name);
        press.setAttribute('aria-pressed', 'false');
        setJointDisplay(view, 0); queueControl({ [joint.name]: 0 }); flushControls();
      };
      const hold = () => {
        if (held || !ready) return;
        releaseHeldControl?.(); held = true; releaseHeldControl = release;
        editing.add(joint.name); press.setAttribute('aria-pressed', 'true');
        const force = baseRange[1];
        setJointDisplay(view, force); queueControl({ [joint.name]: force }); flushControls();
      };
      press.addEventListener('pointerdown', (event) => { if (event.button !== 0) return; event.preventDefault(); press.focus({ preventScroll: true }); press.setPointerCapture(event.pointerId); hold(); });
      ['pointerup', 'pointercancel', 'lostpointercapture', 'blur'].forEach((name) => press.addEventListener(name, release));
      press.addEventListener('keydown', (event) => { if (event.key === ' ' || event.key === 'Enter') { event.preventDefault(); hold(); } });
      press.addEventListener('keyup', (event) => { if (event.key === ' ' || event.key === 'Enter') { event.preventDefault(); release(); } });
      card.append(press);
    }
    dom['joint-list'].append(card); jointViews.set(joint.name, view);
  }
}

function setJointDisplay(view, rawValue, preserveNumber = false) {
  const value = rawValue * view.multiplier;
  view.slider.value = String(value);
  if (!preserveNumber) view.number.value = format(value, view.digits);
  view.slider.style.setProperty('--fill', `${Math.max(0, Math.min(100, (value - view.displayRange[0]) / (view.displayRange[1] - view.displayRange[0]) * 100))}%`);
  view.slider.setAttribute('aria-valuetext', `${format(value, view.digits)} ${view.unit}`);
}

function updateState(state) {
  if (disposed || !state) return;
  renderRequested = true;
  renderer.shadowMap.needsUpdate = true;
  latestState = state;
  if (showcase && lastDemoState !== state.demo) {
    lastDemoState = state.demo;
    postToParent('physag-showcase-state', {assetId:desiredAssetId, demo:state.demo === true});
  }
  for (const transform of state.transforms || []) {
    const object = geomObjects.get(String(transform.id));
    if (object) { object.position.fromArray(transform.position); object.quaternion.fromArray(transform.quaternion); }
  }
  for (const skin of state.skins || []) {
    const object = skinObjects.get(String(skin.id));
    if (!object) continue;
    for (const name of ['position', 'normal']) {
      const values = name === 'position' ? skin.positions : skin.normals;
      const attribute = object.geometry.getAttribute(name);
      if (!values || values.length !== attribute.array.length) continue;
      attribute.array.set(values); attribute.needsUpdate = true;
    }
    object.geometry.computeBoundingSphere();
  }
  for (const joint of (model?.native_controls ? state.controls : state.joints) || []) {
    const view = jointViews.get(joint.name);
    if (!view) continue;
    view.current.textContent = `${format(joint.value * view.multiplier, view.digits)}${view.unit}`;
    if (!editing.has(joint.name) && !Object.hasOwn(pendingTargets, joint.name)) setJointDisplay(view, joint.target ?? joint.value);
  }
  const physical = state.mode === 'physics';
  dom['mode-pose'].classList.toggle('selected', !physical); dom['mode-pose'].setAttribute('aria-pressed', String(!physical));
  dom['mode-physics'].classList.toggle('selected', physical); dom['mode-physics'].setAttribute('aria-pressed', String(physical));
  dom['simulation-row'].hidden = !physical;
  dom['pause-simulation'].textContent = state.paused ? 'Resume' : 'Pause';
  dom['simulation-label'].textContent = state.paused ? 'Simulation paused' : 'Simulation running';
  if (model?.native_controls) $('motion-help').textContent = motionHint(state.paused);
  const warning = state.error || (state.warnings || []).join('; ');
  if (warning && warning !== lastWarning) { notify(warning, true, 8500); lastWarning = warning; }
  if (!warning) lastWarning = '';
}

function queueControl(targets = {}, options = {}) {
  if (disposed || !desiredAssetId || (renderedAssetId && renderedAssetId !== desiredAssetId)) return;
  controlEpoch++;
  Object.assign(pendingTargets, targets); Object.assign(pendingOptions, options);
  if (suspended) pendingOptions.paused = true;
  // Send changes throughout a drag, rather than waiting for it to finish.
  if (connection === 'connected' && !controlTimer && !controlInFlight) controlTimer = setTimeout(flushControls, 24);
}

async function flushControls() {
  clearTimeout(controlTimer); controlTimer = null;
  if (disposed || connection !== 'connected' || !ready || controlInFlight || !session || (!Object.keys(pendingTargets).length && !Object.keys(pendingOptions).length)) return;
  if (suspended) pendingOptions.paused = true;
  const activeSessionId = session.id, activeGeneration = generation;
  const targets = pendingTargets, options = pendingOptions;
  pendingTargets = {}; pendingOptions = {}; controlInFlight = true;
  try {
    const state = await api(`/api/sessions/${encodeURIComponent(activeSessionId)}/control`, { method: 'POST', keepalive: suspended, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ [model?.native_controls ? 'actuators' : 'targets']: targets, ...options }) });
    if (activeGeneration === generation) updateState(state);
  } catch (error) {
    if (activeGeneration === generation) {
      if (error.reconnect) {
        pendingTargets = { ...targets, ...pendingTargets }; pendingOptions = { ...options, ...pendingOptions };
        reconnectAfter(error);
      } else notify(error.message, true);
    }
  }
  finally {
    if (activeGeneration === generation) { controlInFlight = false; flushControls(); }
  }
}

const pollTimer = setInterval(async () => {
  if (disposed || suspended || connection !== 'connected' || !ready || !session || pollInFlight || controlInFlight) return;
  const running = latestState?.mode === 'physics' && !latestState.paused;
  if (!running && Date.now() - lastSessionCheck < 5000) return;
  const activeGeneration = generation, activeSessionId = session.id, activeControlEpoch = controlEpoch;
  pollInFlight = true; lastSessionCheck = Date.now();
  try {
    const state = await api(`/api/sessions/${encodeURIComponent(activeSessionId)}/state`);
    if (connection === 'connected' && activeGeneration === generation && activeControlEpoch === controlEpoch) updateState(state);
  } catch (error) {
    if (activeGeneration === generation) {
      if (error.reconnect) reconnectAfter(error);
      else { setConnection('error', 'Simulation unavailable'); ready = false; notify(error.message, true); }
    }
  } finally { if (activeGeneration === generation) pollInFlight = false; }
}, 50);

dom['asset-select'].addEventListener('change', (event) => loadAsset(event.target.value));
dom['reset-camera'].addEventListener('click', resetCamera);
dom['auto-orbit'].addEventListener('click', () => {
  controls.autoRotate = !controls.autoRotate;
  dom['auto-orbit'].setAttribute('aria-pressed', String(controls.autoRotate));
});
dom.wireframe.addEventListener('click', () => {
  wireframe = !wireframe;
  materials.forEach((material) => { material.wireframe = wireframe; });
  dom.wireframe.setAttribute('aria-pressed', String(wireframe));
  renderRequested = true;
});
dom['mode-pose'].addEventListener('click', () => queueControl({}, { mode: 'pose', paused: true }));
dom['mode-physics'].addEventListener('click', () => queueControl({}, { mode: 'physics', paused: false }));
dom['pause-simulation'].addEventListener('click', () => queueControl({}, { paused: !latestState?.paused }));
dom['reset-pose'].addEventListener('click', () => {
  stopDirectGesture();
  pendingTargets = {};
  queueControl(directMode ? directNeutralTargets() : {}, { reset: true });
  notify('Resetting the pose', false, 1800);
});

async function importFile(file) {
  if (disposed || !file) return;
  const extension = file.name.split('.').pop().toLowerCase();
  if (!['xml', 'zip'].includes(extension)) { notify('Choose a MJCF XML file or a ZIP containing the scene and its meshes.', true); return; }
  dom['import-button'].disabled = true;
  setLoading(true, `Importing ${file.name}`);
  try {
    const result = await api('/api/import', { timeoutMs: 180000, method: 'POST', headers: { 'Content-Type': extension === 'zip' ? 'application/zip' : 'application/xml', 'X-Filename': encodeURIComponent(file.name) }, body: file });
    if (disposed) return;
    if (!result.asset?.id) throw new Error('The import did not return an asset');
    assets = assets.filter((asset) => asset.id !== result.asset.id);
    assets.push(result.asset); updateOptions(result.asset.id);
    notify('Asset imported. Opening it now…', false, 2500);
    await loadAsset(result.asset.id);
  } catch (error) {
    if (disposed) return;
    setLoading(false);
    if (error.reconnect) {
      reconnectAfter(error);
      notify('Import interrupted by a lost connection. Please select the file again after reconnecting.', true, 0);
    } else notify(error.message, true, 0);
  }
  finally { dom['import-button'].disabled = false; dom['asset-file'].value = ''; }
}

dom['import-button'].addEventListener('click', () => dom['asset-file'].click());
dom['asset-file'].addEventListener('change', () => importFile(dom['asset-file'].files[0]));
document.addEventListener('dragenter', (event) => {
  if (!event.dataTransfer?.types.includes('Files')) return;
  event.preventDefault(); dragDepth++; dom['drop-overlay'].hidden = false;
});
document.addEventListener('dragover', (event) => { if (event.dataTransfer?.types.includes('Files')) { event.preventDefault(); event.dataTransfer.dropEffect = 'copy'; } });
document.addEventListener('dragleave', (event) => { event.preventDefault(); if (--dragDepth <= 0) { dragDepth = 0; dom['drop-overlay'].hidden = true; } });
document.addEventListener('drop', (event) => { event.preventDefault(); dragDepth = 0; dom['drop-overlay'].hidden = true; importFile(event.dataTransfer?.files[0]); });
document.addEventListener('keydown', (event) => {
  if (event.defaultPrevented) return;
  if (event.key === 'Escape' && embedded) {
    event.preventDefault();
    postToParent('physag-viewer-close');
    return;
  }
  if (event.target.closest('input, select, textarea, button, summary') || event.metaKey || event.ctrlKey || event.altKey) return;
  const k = event.key.toLowerCase();
  if (k === 'h') dom['reset-camera'].click();
  else if (k === 'r') dom['reset-pose'].click();
  else if (k === 'a') dom['auto-orbit'].click();
  else if (k === 'w') dom.wireframe.click();
  else if (event.code === 'Space' && latestState?.mode === 'physics') { event.preventDefault(); dom['pause-simulation'].click(); }
});
function disposeViewer() {
  if (disposed) return;
  stopDirectGesture();
  directController?.dispose(); directController = null;
  releaseHeldControl = null;
  disposed = true; ready = false; generation++;
  clearInterval(pollTimer);
  clearTimeout(controlTimer); clearTimeout(reconnectTimer); clearTimeout(notificationTimer);
  cancelAnimationFrame(animationFrame); animationFrame = 0;
  requests.forEach((creatingSession, controller) => { if (!creatingSession) controller.abort(); });
  for (const id of [...ownedSessions]) deleteSession(id);
  session = null;
  sizeObserver.disconnect(); controls.dispose(); clearContent();
  scene.environment?.dispose(); key.shadow.map?.dispose();
  renderer.renderLists.dispose(); renderer.dispose();
  $('input-photo').onload = null; $('input-photo').onerror = null;
}

window.addEventListener('pagehide', disposeViewer, { once: true });
// A history-restored standalone page needs fresh GPU resources and a new session.
window.addEventListener('pageshow', (event) => { if (event.persisted && disposed) location.reload(); });
window.addEventListener('online', () => { if (connection === 'reconnecting') { clearTimeout(reconnectTimer); reconnectTimer = null; scheduleReconnect(true); } });
window.addEventListener('blur', () => { releaseHeldControl?.(); stopDirectGesture(); });

function updateSuspension() {
  if (disposed) return;
  suspended = document.hidden || (showcase && !parentActive);
  if (suspended) {
    stopDirectGesture();
    releaseHeldControl?.();
    cancelAnimationFrame(animationFrame); animationFrame = 0;
    clearTimeout(reconnectTimer); reconnectTimer = null;
    // Pause the actual solver, not just the rendered view. Resuming is explicit.
    if (session) { queueControl({}, { paused: true }); flushControls(); }
    if (recoverySnapshot) recoverySnapshot.paused = true;
  } else {
    lastSessionCheck = 0; renderRequested = true;
    if (showcase && session) queueControl({}, {paused:false});
    startRendering(); scheduleReconnect(true); flushControls();
  }
}
document.addEventListener('visibilitychange', updateSuspension);

// Only the owning homepage can control the one inline showcase instance.
if (showcase) window.addEventListener('message', event => {
  if (event.origin !== location.origin || event.source !== window.parent) return;
  const message = event.data;
  if (message?.type !== 'physag-showcase-control') return;
  if (message.action === 'select' && Object.hasOwn(builtinNames, message.assetId)) {
    lastDemoState = null;
    loadAsset(message.assetId);
  } else if (message.action === 'visibility' && typeof message.active === 'boolean') {
    parentActive = message.active;
    updateSuspension();
  } else if (message.action === 'demo' && typeof message.enabled === 'boolean' && ready) {
    queueControl({}, {demo:message.enabled, paused:suspended});
    flushControls();
  }
});

function animate() {
  animationFrame = 0;
  if (disposed || suspended) return;
  const changed = controls.update();
  directController?.update();
  if (changed || renderRequested) {
    renderer.render(scene, camera);
    renderRequested = false;
  }
  animationFrame = requestAnimationFrame(animate);
}
function startRendering() {
  if (!disposed && !suspended && !animationFrame) animationFrame = requestAnimationFrame(animate);
}
startRendering();

try {
  const response = await api('/api/assets');
  if (!disposed) {
    assets = response.assets || [];
    updateOptions();
    if (!assets.length) { setLoading(false); dom['engine-label'].textContent = 'Ready to import'; notify('No built-in assets are available. Import a MJCF model to begin.'); window.__physagViewerBoot?.complete(); }
    else {
      const requested = query.get('asset');
      const selected = assets.find((asset) => asset.id === requested);
      await loadAsset(selected?.id || assets.find((asset) => asset.id === 'camera')?.id || assets[0].id);
      if (requested && !selected) notify('The requested asset is unavailable. Showing another object.', true);
    }
  }
} catch (error) {
  if (!disposed) {
    setLoading(false);
    if (error.reconnect) reconnectAfter(error);
    else { setConnection('error', 'Viewer unavailable'); notify(`Could not connect to the viewer: ${error.message}`, true, 0); }
  }
}
