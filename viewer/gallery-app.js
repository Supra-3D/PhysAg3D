import * as T from 'three';
import { OrbitControls } from './vendor/OrbitControls.js';
import { RoomEnvironment } from './vendor/RoomEnvironment.js';
import { createGalleryAdapter } from './gallery-adapter.js';
import { resourceURL, readResource } from './resource-urls.js';

const $ = id => document.getElementById(id);
const query = new URLSearchParams(location.search), embedded = query.get('embed') === '1';
const directMode = true;
const directModule = await import('./direct-manipulation.js');
let directController = null;
document.body.classList.add('gallery-studio');
if (directMode) document.body.classList.add('direct-mode', 'direct-gallery');
if (embedded) document.body.classList.add('embedded');
const post = (type, detail = {}) => { if (embedded && parent !== window) parent.postMessage({ type, ...detail }, location.origin); };
let catalog = [], item = null, adapter = null, ready = false, disposed = false, generation = 0, request = null;
let raf = 0, lastTime = 0, dirty = true, wireframe = false, ground = null, notificationTimer;
const canvas = $('scene'), renderer = new T.WebGLRenderer({ canvas, antialias: true, alpha: true, preserveDrawingBuffer: true });
renderer.setPixelRatio(Math.min(devicePixelRatio || 1, 2));
renderer.outputColorSpace = T.SRGBColorSpace;
renderer.toneMapping = T.ACESFilmicToneMapping;
renderer.toneMappingExposure = 0.94;
renderer.setClearColor(0xeff2eb, 0);
const scene = new T.Scene(), studio = new RoomEnvironment(), pmrem = new T.PMREMGenerator(renderer);
const environment = pmrem.fromScene(studio, 0.04);
scene.environment = environment.texture; scene.environmentIntensity = 0.7;
studio.dispose(); pmrem.dispose();
const camera = new T.PerspectiveCamera(36, 1, 0.001, 1000); camera.up.set(0, 0, 1);
const orbit = new OrbitControls(camera, canvas);
orbit.enableDamping = true; orbit.dampingFactor = 0.08; orbit.autoRotateSpeed = 1.25;
orbit.maxPolarAngle = Math.PI * 0.93; orbit.screenSpacePanning = true;
orbit.addEventListener('change', () => { dirty = true; });
scene.add(new T.HemisphereLight(0xffffff, 0x9ca6b0, 1));
for (const [color, power, position] of [[0xffffff, 2.2, [-2.5, -3.5, 5]], [0xe8f0ff, 0.75, [3, 1, 2]], [0xfff5df, 1, [0.5, 3, 4]]]) {
  const light = new T.DirectionalLight(color, power); light.position.set(...position); scene.add(light);
}
const resize = new ResizeObserver(() => {
  if (disposed) return;
  const rect = canvas.parentElement.getBoundingClientRect();
  if (rect.width <= 0 || rect.height <= 0) return;
  renderer.setSize(rect.width, rect.height, false); camera.aspect = rect.width / rect.height; camera.updateProjectionMatrix(); dirty = true;
});
resize.observe(canvas.parentElement);
canvas.setAttribute('aria-label', 'Drag a moving part to manipulate it. Drag blank space to orbit; scroll to zoom.');
directController = directModule.createDirectManipulation({
  scene, camera, canvas, orbit, host: $('viewer'), getHandles: () => adapter?.getHandles() || [],
  getPickObjects: () => adapter ? [adapter.group] : [],
  onChange(id, value) { adapter?.setDirectValue(id, value); refreshUi(); dirty = true; },
  onDragStart(handle, detail) { adapter?.pause(); adapter?.beginDirectInteraction?.(handle.id, detail); dirty = true; },
  onDragEnd(handle, detail) { adapter?.endDirectInteraction?.(handle.id, detail); dirty = true; },
  onDirty() { dirty = true; },
});
window.__viewer = {
  get ready() { return ready; }, get assetId() { return item?.id; }, get galleryId() { return item?.id; },
  runtime: 'browser',
  get direct() { return directController; }, directMode,
  get adapter() { return adapter; }, get model() { return adapter?.metadata; },
  get state() { return adapter ? { mode: adapter.mode, playing: adapter.playing, time: adapter.time, frame: adapter.frame, controls: adapter.values, amounts: adapter.amounts } : null; },
  scene, camera, controls: orbit, renderer,
};

function notify(message, error = false) {
  if (disposed) return;
  clearTimeout(notificationTimer); $('notification').textContent = message; $('notification').hidden = false;
  $('notification').classList.toggle('error', error);
  notificationTimer = setTimeout(() => { $('notification').hidden = true; }, 6000);
  if (error) { window.__physagViewerBoot?.fail(message); post('physag-viewer-error', { message }); }
}
function destroyAsset(value) {
  if (!value) return;
  value.dispose(); scene.remove(value.group);
  const geometries = new Set(); value.group.traverse(o => { if (o.geometry) geometries.add(o.geometry); });
  geometries.forEach(g => g.dispose()); value.materials.forEach(m => m.dispose());
  value.textures.forEach(t => { t.source?.data?.close?.(); t.dispose(); });
}
function removeGround() { if (ground) { scene.remove(ground); ground.geometry.dispose(); ground.material.dispose(); ground = null; } }
function resetCamera() {
  if (!adapter) return;
  const bounds = adapter.frameBounds.isEmpty() ? adapter.bounds : adapter.frameBounds;
  const center = bounds.getCenter(new T.Vector3()), size = bounds.getSize(new T.Vector3());
  const span = Math.max(size.length(), 0.001), radius = span / 2;
  const fov = Math.min(T.MathUtils.degToRad(camera.fov), 2 * Math.atan(Math.tan(T.MathUtils.degToRad(camera.fov / 2)) * camera.aspect));
  const distance = radius / Math.sin(fov / 2) * 1.05;
  orbit.enableDamping = false; orbit.autoRotate = false; orbit.update();
  $('auto-orbit').setAttribute('aria-pressed', 'false');
  orbit.target.copy(center); camera.position.copy(center).addScaledVector(new T.Vector3(1, -1.35, 0.85).normalize(), distance);
  camera.near = Math.max(0.00001, span * 0.001); camera.far = span * 100;
  orbit.minDistance = span * 0.08; orbit.maxDistance = span * 12;
  camera.updateProjectionMatrix(); orbit.update(); orbit.saveState(); orbit.enableDamping = true; dirty = true;
}
function setupGround() {
  removeGround();
  const bounds = adapter.frameBounds, size = bounds.getSize(new T.Vector3()), center = bounds.getCenter(new T.Vector3());
  const span = Math.max(size.length(), 0.01);
  ground = new T.Mesh(new T.PlaneGeometry(span * 3, span * 3), new T.ShaderMaterial({
    transparent: true, depthWrite: false,
    vertexShader: 'varying vec2 vUv; void main(){ vUv=uv; gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.0); }',
    fragmentShader: 'varying vec2 vUv; void main(){ float fade=1.0-smoothstep(0.0,0.48,distance(vUv,vec2(0.5))); gl_FragColor=vec4(0.39,0.44,0.41,fade*fade*0.07); }',
  }));
  ground.position.set(center.x, center.y, bounds.min.z - span * 0.01); scene.add(ground);
}
function prepareInteraction() {
  const handles = adapter.getHandles();
  const softHandles = handles.filter(handle => handle.interaction === 'soft');
  const hasJoints = handles.some(handle => handle.interaction !== 'soft');
  const pullOnly = softHandles.length > 0 && softHandles.every(handle => handle.action === 'pull');
  $('reset-pose').disabled = false;
  $('reset-pose').hidden = handles.length === 0;
  $('asset-description').textContent = softHandles.length
    ? hasJoints ? 'Drag a moving part, or press and drag a soft area.'
      : pullOnly ? 'Hold a soft area and drag to pull it. Release to let it settle.'
        : 'Press a soft area and drag to shape it. Release to let it spring back.'
    : hasJoints ? 'Drag a moving part to explore the object.'
      : 'Drag to rotate the object. Scroll or pinch to zoom.';
  directController.refresh();
  refreshUi();
}
function refreshUi() {
  if (adapter) $('engine-label').textContent = adapter.label;
}
async function loadAsset(id) {
  if (disposed) return;
  const selected = catalog.find(a => a.id === id);
  if (!selected) throw new Error('This Gallery asset is not available in the local catalogue.');
  const token = ++generation; request?.abort(); request = new AbortController(); ready = false;
  const previous = adapter; adapter = null; directController?.refresh(); destroyAsset(previous); removeGround(); dirty = true;
  item = selected; $('asset-select').value = id;
  $('asset-code').textContent = selected.source?.case_id || selected.id;
  $('asset-title').textContent = selected.name; $('asset-description').textContent = selected.description || 'Inspect the original shape and its available motion.';
  $('loading-overlay').hidden = false; $('engine-status').classList.remove('error'); $('engine-label').textContent = 'Loading…';
  $('reset-pose').disabled = true;
  $('input-reference').hidden = true; const photo = $('input-photo');
  photo.onload = () => { if (!disposed && item === selected) $('input-reference').hidden = false; };
  photo.onerror = () => { $('input-reference').hidden = true; }; photo.alt = 'Input photograph of ' + selected.name.toLowerCase(); photo.src = resourceURL(selected.input_url);
  try {
    const result = await createGalleryAdapter(selected, { signal: request.signal, onProgress: text => {
      if (token !== generation) return;
      $('loading-label').textContent = text; $('viewer-boot-label').textContent = text;
      post('physag-viewer-progress', { message: text });
    } });
    if (disposed || token !== generation) { destroyAsset(result); return; }
    adapter = result; scene.add(adapter.group); adapter.materials.forEach(m => { m.wireframe = wireframe; });
    const rect = canvas.parentElement.getBoundingClientRect();
    renderer.setSize(rect.width, rect.height, false); camera.aspect = rect.width / rect.height; camera.updateProjectionMatrix();
    setupGround(); resetCamera(); ready = true; prepareInteraction(); directController?.update();
    $('model-stats').textContent = selected.native_asset_id ? 'Joint controls' : adapter.label;
    // Publish readiness only after the correct model, layout and controls have a frame.
    renderer.render(scene, camera); dirty = false;
    $('loading-overlay').hidden = true; window.__physagViewerBoot?.complete();
    const url = new URL(location.href); url.searchParams.set('gallery', id); history.replaceState(null, '', url);
    post('physag-viewer-ready', { assetId: id, gallery: true });
  } catch (error) {
    if (disposed || token !== generation || error.name === 'AbortError') return;
    ready = false;
    $('loading-overlay').hidden = true; $('engine-status').classList.add('error'); $('engine-label').textContent = 'Unavailable';
    notify(error.message, true);
  }
}
$('asset-select').addEventListener('change', event => { loadAsset(event.target.value).catch(error => notify(error.message, true)); });
$('reset-pose').addEventListener('click', () => { adapter?.reset(); directController?.refresh(); refreshUi(); dirty = true; });
$('reset-camera').addEventListener('click', resetCamera);
$('auto-orbit').addEventListener('click', () => { orbit.autoRotate = !orbit.autoRotate; $('auto-orbit').setAttribute('aria-pressed', String(orbit.autoRotate)); dirty = true; });
$('wireframe').addEventListener('click', () => { wireframe = !wireframe; adapter?.materials.forEach(m => { m.wireframe = wireframe; }); $('wireframe').setAttribute('aria-pressed', String(wireframe)); dirty = true; });
document.addEventListener('keydown', event => {
  if (event.defaultPrevented) return;
  if (event.key === 'Escape' && embedded) { event.preventDefault(); post('physag-viewer-close'); return; }
  if (/^(INPUT|SELECT|TEXTAREA)$/.test(event.target.tagName)) return;
  const shortcuts = { h: 'reset-camera', a: 'auto-orbit', w: 'wireframe', r: 'reset-pose' };
  const target = shortcuts[event.key.toLowerCase()]; if (target) { event.preventDefault(); if (!$(target).disabled && !$(target).hidden) $(target).click(); }
});
function animate(now) {
  if (disposed || document.hidden) { raf = 0; return; }
  const dt = lastTime ? Math.min((now - lastTime) / 1000, 0.1) : 0; lastTime = now;
  try { if (adapter?.update(dt)) dirty = true; } catch (error) { adapter?.pause(); notify(error.message, true); }
  orbit.update();
  directController?.update();
  if (dirty || orbit.autoRotate) { renderer.render(scene, camera); dirty = false; }
  raf = requestAnimationFrame(animate);
}
document.addEventListener('visibilitychange', () => {
  adapter?.pause(); orbit.autoRotate = false; $('auto-orbit').setAttribute('aria-pressed', 'false'); refreshUi();
  if (document.hidden) { cancelAnimationFrame(raf); raf = 0; } else if (!raf && !disposed) { lastTime = 0; dirty = true; raf = requestAnimationFrame(animate); }
});
function dispose() {
  if (disposed) return; disposed = true; ready = false; generation++; request?.abort();
  clearTimeout(notificationTimer); cancelAnimationFrame(raf); resize.disconnect(); directController?.dispose(); orbit.dispose(); destroyAsset(adapter); adapter = null;
  removeGround(); environment.dispose(); renderer.dispose(); renderer.forceContextLoss();
}
window.addEventListener('pagehide', dispose, { once: true });
window.addEventListener('message', event => { if (event.origin === location.origin && event.source === parent && event.data?.type === 'physag-viewer-dispose') dispose(); });
raf = requestAnimationFrame(animate);
request = new AbortController();
try {
  const data = JSON.parse(new TextDecoder().decode(await readResource('assets/gallery-models/catalog.json', { signal: request.signal })));
  catalog = data.assets || [];
  if (query.get('collection') === 'demo') {
    catalog = ['camera', 'phone', 'globe', 'ladder', 'carousel']
      .map(name => catalog.find(asset => asset.native_asset_id === name)).filter(Boolean);
  }
  $('asset-select').replaceChildren(...catalog.map(a => new Option(a.name, a.id))); $('asset-select').disabled = false;
  const requested = query.get('gallery') || catalog.find(a => a.native_asset_id === query.get('asset'))?.id || catalog[0]?.id;
  await loadAsset(catalog.some(asset => asset.id === requested) ? requested : catalog[0]?.id);
} catch (error) { if (!disposed && error.name !== 'AbortError') { $('loading-overlay').hidden = true; notify(error.message, true); } }
