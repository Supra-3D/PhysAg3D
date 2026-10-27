import * as T from 'three';
import { GLTFLoader } from './vendor/GLTFLoader.js';
import { createSoftControls, createRecordedSoftControls } from './soft-manipulation.js';
import { surfaceAction } from './soft-profiles.js';
import { resourceURL, readResource, siteRoot } from './resource-urls.js';
import { createNativeControls } from './native-controls.js';

const unitScale = new T.Vector3(1, 1, 1);
const gltfToWorld = new T.Matrix4().makeRotationX(Math.PI / 2);
const pretty = value => String(value || '').replace(/[_-]+/g, ' ').replace(/\b\w/g, x => x.toUpperCase());
const compose = (p, q) => new T.Matrix4().compose(new T.Vector3(...p), new T.Quaternion(q[1], q[2], q[3], q[0]), unitScale);
const depth = object => { let n = 0; while (object.parent) { n++; object = object.parent; } return n; };

export async function createGalleryAdapter(item, { signal, onProgress = () => {} } = {}) {
  const metadataUrl = item.metadata_url ? resourceURL(item.metadata_url) : null;
  async function bytes(url, hash) {
    return readResource(url, { base: metadataUrl || siteRoot, signal, hash, onProgress });
  }
  const metadata = item.metadata || (metadataUrl ? JSON.parse(new TextDecoder().decode(await bytes(metadataUrl))) : {});
  const resources = item.resources || {};
  const source = key => resources[key] || metadata.files?.[key];
  const hashFor = key => metadata.hashes?.[key] || metadata.hashes?.[key + '_sha256'] || (key === 'recorded_skin' ? metadata.hashes?.skin_sha256 : null);
  const jsonResource = async key => JSON.parse(new TextDecoder().decode(await bytes(source(key), hashFor(key))));
  const assetUrl = resourceURL(item.asset_url || source('asset'), metadataUrl || siteRoot);
  onProgress('Loading the 3D model');
  const assetHash = item.asset_sha256 || metadata.hashes?.asset || metadata.hashes?.asset_glb_sha256;
  const buffer = await bytes(assetUrl, assetHash);
  const gltf = await new GLTFLoader().parseAsync(buffer, new URL('.', assetUrl).href);
  const group = new T.Group(); group.rotation.x = Math.PI / 2; group.add(gltf.scene);
  const native = createNativeControls(item, gltf);
  const materials = new Set(), textures = new Set();
  let hasMorphTargets = false;
  gltf.scene.traverse(object => {
    if (!object.isMesh) return;
    hasMorphTargets ||= Boolean(object.geometry.morphAttributes.position?.length);
    const surfaceMaterials = Array.isArray(object.material) ? object.material : [object.material];
    // Match the native viewer: ordinary shadow maps cannot transmit glass.
    const transmissive = surfaceMaterials.some(material => material.transmission > 0);
    object.castShadow = !transmissive; object.receiveShadow = !transmissive;
    for (const material of surfaceMaterials) {
      materials.add(material);
      for (const value of Object.values(material)) if (value?.isTexture) textures.add(value);
    }
  });
  let disposed = false;
  const graph = metadata.kinematics || { bodies: [], bindings: [], controls: [] };
  let trajectory = null, skinData = [], approximateData = [];
  // Keep recorded flex points only as independent surface-shape data. No rigid
  // recording or GLB animation is played or exposed as a draggable timeline.
  const skinSource = source('recorded_skin') ? 'recorded_skin' : source('skin') ? 'skin' : null;
  try {
    if (signal?.aborted) throw new DOMException('Loading cancelled', 'AbortError');
    onProgress('Preparing object interaction');
    if (source('trajectory') && skinSource) {
      trajectory = await jsonResource('trajectory');
      if (!Array.isArray(trajectory.states) || trajectory.states.length < 2) throw new Error('The surface shape data is incomplete.');
      skinData = await jsonResource(skinSource);
    }
    if (metadata.approximate_soft?.available && source('approximate_soft')) approximateData = (await jsonResource('approximate_soft')).regions || [];
    const rest = [];
    group.updateMatrixWorld(true);
    gltf.scene.traverse(object => {
      rest.push({ object, auto: object.matrixAutoUpdate, matrix: object.matrix.clone(), morphs: object.morphTargetInfluences?.slice(),
        positions: object.isMesh && (skinData.length || approximateData.length) ? object.geometry.attributes.position.array.slice() : null,
        normals: object.isMesh && (skinData.length || approximateData.length) ? object.geometry.attributes.normal?.array.slice() : null });
    });
    async function node(binding) {
      const object = Number.isInteger(binding.node_index) ? await gltf.parser.getDependency('node', binding.node_index) : gltf.scene.getObjectByName(binding.node);
      if (!object) throw new Error('A required moving part is missing from this model.');
      return object;
    }
    const bindings = await Promise.all((graph.bindings || []).map(async b => ({ ...b, object: await node(b), offset: b.rest_offset ? new T.Matrix4().fromArray(b.rest_offset) : new T.Matrix4() })));
    bindings.sort((a, b) => depth(a.object) - depth(b.object));
    const skinBindings = await Promise.all(skinData.map(async b => {
      const object = await node(b), count = object.geometry?.attributes.position.count;
      if (!object.isMesh || count !== b.indices.length || count !== b.weights.length) throw new Error('The recorded surface does not match the model.');
      if (b.indices.some((row, i) => row.length !== b.weights[i].length)) throw new Error('The recorded surface weights are incomplete.');
      object.frustumCulled = false; return { ...b, object };
    }));
    const approximateBindings = await Promise.all(approximateData.map(async b => {
      const object = await node(b), count = object.geometry?.attributes.position.count;
      if (!object.isMesh || count !== b.rest_positions.length || count !== b.vertex_deltas.length || ![...b.rest_positions, ...b.vertex_deltas].every(p => p.length === 3 && p.every(Number.isFinite))) throw new Error('The deformation data does not match the model.');
      object.frustumCulled = false; return { ...b, object };
    }));
    const controls = native ? native.controls : (graph.controls || []).map(c => ({ ...c, label: c.label || pretty(c.name), range: c.limits || [-Math.PI, Math.PI], value: c.reference || 0, unit: c.type === 'hinge' ? 'rad' : 'm' }));
    const regions = [...new Set(approximateBindings.map(b => b.region))].map(name => ({ name, label: pretty(name), range: [0, 1], unit: '%', value: 0 }));
    const values = new Map(controls.map(c => [c.name, c.value])), amounts = new Map();
    const local = new Map((graph.bodies || []).map(b => [b.id, compose(b.position, b.quaternion_wxyz)]));
    const bodies = new Map((graph.bodies || []).map(b => [b.id, b]));
    let jointWorlds = new Map();
    const mode = controls.length || regions.length ? 'joints' : 'static';
    let softControls = [];
    const softHeld = new Set(), softReleased = new Set();
    const modes = [{ id: mode, label: controls.length ? 'Joint controls' : regions.length ? 'Approximate deformation' : '3D view' }];

    function restore() {
      for (const row of rest) {
        const o = row.object; o.matrixAutoUpdate = row.auto; o.matrix.copy(row.matrix); o.matrix.decompose(o.position, o.quaternion, o.scale); o.matrixWorldNeedsUpdate = true;
        if (row.morphs) o.morphTargetInfluences.splice(0, row.morphs.length, ...row.morphs);
        if (row.positions) { o.geometry.attributes.position.array.set(row.positions); o.geometry.attributes.position.needsUpdate = true; }
        if (row.normals) { o.geometry.attributes.normal.array.set(row.normals); o.geometry.attributes.normal.needsUpdate = true; }
        if (o.geometry) { o.geometry.boundingBox = null; o.geometry.boundingSphere = null; }
      }
      group.updateMatrixWorld(true);
    }
    function setBody(binding, bodyWorld) {
      const target = bodyWorld.clone().multiply(gltfToWorld).multiply(binding.offset), object = binding.object;
      object.parent?.updateWorldMatrix(true, false);
      if (object.parent) target.premultiply(object.parent.matrixWorld.clone().invert());
      object.matrixAutoUpdate = false; object.matrix.copy(target); object.matrixWorldNeedsUpdate = true; object.updateMatrixWorld(true);
    }
    function changedSurface(object) {
      object.geometry.attributes.position.needsUpdate = true; object.geometry.computeVertexNormals();
      object.geometry.boundingBox = null; object.geometry.boundingSphere = null;
    }
    function applyJoints() {
      if (native) {
        for (const [name, value] of values) native.setValue(name, value);
        group.updateMatrixWorld(true);
        return;
      }
      const worlds = new Map([[0, new T.Matrix4()]]);
      const visiting = new Set();
      function solve(id) {
        if (worlds.has(id)) return worlds.get(id);
        const body = bodies.get(id);
        if (!body || visiting.has(id)) throw new Error('The joint hierarchy is incomplete.');
        visiting.add(id); const matrix = local.get(id).clone(), j = body.joint;
        if (j) {
          const delta = (values.get(j.name) ?? j.reference) - j.reference;
          if (j.type === 'hinge') { const p = j.position; matrix.multiply(new T.Matrix4().makeTranslation(...p)).multiply(new T.Matrix4().makeRotationAxis(new T.Vector3(...j.axis).normalize(), delta)).multiply(new T.Matrix4().makeTranslation(-p[0], -p[1], -p[2])); }
          else if (j.type === 'slide') matrix.multiply(new T.Matrix4().makeTranslation(...j.axis.map(x => x * delta)));
        }
        const world = solve(body.parent).clone().multiply(matrix); worlds.set(id, world); visiting.delete(id); return world;
      }
      for (const binding of bindings) setBody(binding, solve(binding.body));
      for (const control of controls) solve(control.body);
      jointWorlds = worlds;
      for (const b of approximateBindings) {
        const amount = amounts.get(b.region) || 0, p = b.object.geometry.attributes.position;
        for (let i = 0; i < p.count; i++) p.setXYZ(i, ...b.rest_positions[i].map((v, k) => v + amount * b.vertex_deltas[i][k]));
        changedSurface(b.object);
      }
      group.updateMatrixWorld(true);
    }
    function reset() {
      softHeld.clear(); softReleased.clear(); softControls.forEach(control => control.reset());
      amounts.clear(); controls.forEach(c => values.set(c.name, c.reference || 0)); restore(); native?.reset();
      if (mode === 'joints') applyJoints();
    }
    reset();
    // Relative morph targets can make the default geometry box accumulate
    // every target's extent. Frame the evaluated surface at each sample instead.
    const bounds = new T.Box3().setFromObject(group, hasMorphTargets), frameBounds = bounds.clone();
    // Include only the independent joints' extents in the initial framing.
    if (controls.length && controls.length < 30) {
      for (const c of controls) for (const value of [c.range[0], (c.range[0] + c.range[1]) / 2, c.range[1]]) {
        values.set(c.name, value); applyJoints(); frameBounds.expandByObject(group, hasMorphTargets); values.set(c.name, c.reference || 0);
      }
    }
    reset();
    softControls = [...createSoftControls(item, gltf), ...createRecordedSoftControls(skinBindings, trajectory)];
    const softById = new Map(softControls.map(control => [control.descriptor.id, control]));
    // Descriptors cache object ownership; getHandles only reads current small
    // transforms and never traverses vertex buffers.
    const rootCenterLocal = group.worldToLocal(bounds.getCenter(new T.Vector3()));
    function descendsFrom(id, ancestor) {
      const seen = new Set();
      while (id && !seen.has(id)) {
        if (id === ancestor) return true;
        seen.add(id); id = bodies.get(id)?.parent;
      }
      return false;
    }
    const jointHandles = (native ? [] : controls).map(control => {
      const joint = bodies.get(control.body)?.joint || control;
      const objects = [...new Set(bindings.filter(b => descendsFrom(b.body, control.body)).map(b => b.object))];
      const ownObjects = bindings.filter(b => b.body === control.body).map(b => b.object);
      return {
        id: 'joint:' + control.name, label: control.label, kind: control.type, objects,
        min: control.range[0], max: control.range[1], unit: control.unit,
        axisLabel: control.type === 'hinge' ? 'Rotation axis' : 'Translation axis',
        description: 'Drag this part along its declared joint. This is a geometric joint control, not a live physics simulation.',
        axisSource: 'declared_joint', coupled: false,
        selectionDepth: ownObjects.length ? Math.max(...ownObjects.map(depth)) : 0,
        getValue: () => values.get(control.name) ?? control.reference ?? 0,
        pose: () => {
          const world = jointWorlds.get(control.body);
          if (!world || !joint.axis || !joint.position) return { origin: null, axis: null, disabled: true };
          return { origin: new T.Vector3(...joint.position).applyMatrix4(world), axis: new T.Vector3(...joint.axis).transformDirection(world) };
        },
      };
    });
    const surfaceGeometry = approximateBindings.map(binding => {
      let weight = 0, px = 0, py = 0, pz = 0, dx = 0, dy = 0, dz = 0;
      for (let i = 0; i < binding.vertex_deltas.length; i++) {
        const p = binding.rest_positions[i], d = binding.vertex_deltas[i], w = Math.hypot(...d);
        if (w <= 1e-12) continue;
        weight += w; px += p[0] * w; py += p[1] * w; pz += p[2] * w;
        dx += d[0] * w; dy += d[1] * w; dz += d[2] * w;
      }
      return { binding, weight, center: new T.Vector3(px, py, pz).divideScalar(weight || 1), delta: new T.Vector3(dx, dy, dz).divideScalar(weight || 1) };
    });
    const surfaceHandles = regions.map(region => {
      const pieces = surfaceGeometry.filter(x => x.binding.region === region.name), objects = pieces.map(x => x.binding.object);
      const action = surfaceAction(region.name);
      return {
        id: 'surface:' + region.name, label: action.label, kind: 'surface', objects,
        interaction: 'soft', action: action.action, pressAmount: 0.18,
        hint: action.action === 'pull' ? 'Hold and pull. Release to let it settle.' : 'Hold to press. Drag to adjust, then release.',
        min: 0, max: 1, unit: '%', axisLabel: 'Deformation direction', axisSource: 'authored_vertex_deltas',
        description: action.action === 'pull' ? 'Hold and pull. Release to let it settle.' : 'Hold to press. Drag to adjust, then release.',
        coupled: false, selectionDepth: objects.length ? Math.max(...objects.map(depth)) : 0,
        getValue: () => amounts.get(region.name) || 0,
        pose: () => {
          const origin = new T.Vector3(), direction = new T.Vector3();
          let weight = 0, directionWeight = 0;
          for (const piece of pieces) {
            const world = piece.binding.object.matrixWorld;
            const center = piece.center.clone().addScaledVector(piece.delta, amounts.get(region.name) || 0).applyMatrix4(world);
            const delta = piece.delta.clone().applyMatrix3(new T.Matrix3().setFromMatrix4(world));
            origin.addScaledVector(center, piece.weight); direction.addScaledVector(delta, piece.weight);
            weight += piece.weight; directionWeight += delta.length() * piece.weight;
          }
          return { origin: weight ? origin.divideScalar(weight) : group.localToWorld(rootCenterLocal.clone()),
            axis: directionWeight > 1e-12 && direction.length() / directionWeight > 0.35 ? direction.normalize() : null };
        },
      };
    });
    function directDescriptors() {
      if (disposed) return [];
      const joints = native ? native.getHandles().map(handle => ({
        ...handle, pose: () => ({ origin: handle.origin, axis: handle.axis }), getValue: () => handle.value,
      })) : jointHandles;
      return [...joints, ...surfaceHandles, ...softControls.map(control => control.descriptor)];
    }
    function getHandles() {
      return directDescriptors().map(({ pose, getValue, ...descriptor }) => {
        const spatial = pose();
        return { ...descriptor, ...spatial, value: getValue(),
          disabled: Boolean(descriptor.disabled || spatial.disabled) };
      });
    }
    function setDirectValue(id, value) {
      if (!Number.isFinite(value) || !directDescriptors().some(handle => handle.id === id)) return false;
      if (native && id.startsWith('native:')) {
        native.setValue(id, value);
        for (const [name, current] of Object.entries(native.values)) values.set(name, current);
        group.updateMatrixWorld(true);
      } else if (softById.has(id)) {
        softById.get(id).set(value); group.updateMatrixWorld(true);
      } else if (id.startsWith('joint:')) {
        const name = id.slice(6), control = controls.find(c => c.name === name);
        values.set(name, control.limited === false ? value : T.MathUtils.clamp(value, ...control.range)); applyJoints();
      } else if (id.startsWith('surface:')) {
        amounts.set(id.slice(8), T.MathUtils.clamp(value, 0, 1)); applyJoints();
      } else return false;
      return true;
    }
    function beginDirectInteraction(id, detail = {}) {
      if (native && id.startsWith('native:')) return native.beginInteraction?.(id, detail) ?? false;
      const descriptor = directDescriptors().find(handle => handle.id === id);
      if (!descriptor || descriptor.interaction !== 'soft') return false;
      softReleased.delete(id); softHeld.add(id);
      softById.get(id)?.begin(detail);
      return true;
    }
    function endDirectInteraction(id) {
      if (native && id.startsWith('native:')) return native.endInteraction?.(id) ?? false;
      const descriptor = directDescriptors().find(handle => handle.id === id);
      if (!descriptor || descriptor.interaction !== 'soft') return false;
      softHeld.delete(id); softReleased.add(id); return true;
    }
    function clearDirectInteraction() {
      if (native) for (const control of native.controls) native.endInteraction(control.name);
      const ids = new Set([...softHeld, ...softReleased]);
      softHeld.clear(); softReleased.clear();
      for (const id of ids) setDirectValue(id, 0);
    }
    const softSurfaceCount = surfaceHandles.length + softControls.length;
    const hasRigidMotion = Boolean(controls.length);
    return {
      group, materials: [...materials], textures: [...textures], controls, regions, modes, metadata,
      getHandles, setDirectValue, beginDirectInteraction, endDirectInteraction,
      directMetadata: { declaredJoints: native ? native.controls.length : jointHandles.length, authoredSurfaces: surfaceHandles.length,
        softSurfaces: softSurfaceCount, hasRigidMotion,
        softSources: [...surfaceHandles.map(handle => ({ id: handle.id, source: 'authored_vertex_deltas' })), ...softControls.map(control => ({ id: control.descriptor.id, ...control.audit }))],
        softResponse: 'Visual interpolation with smooth release; no new force or material solver.',
        playbackAvailable: false },
      bounds, frameBounds, clips: [], frameCount: 0, partial: false, presets: [],
      get mode() { return mode; }, playing: false, time: 0, frame: 0, duration: 0,
      get label() { return softSurfaceCount && (mode === 'static' || softHeld.size || softReleased.size || [...amounts.values()].some(x => x > 0)) ? 'Soft interaction' : modes[0].label; },
      get values() { return native ? native.values : Object.fromEntries(values); }, get amounts() { return Object.fromEntries(amounts); },
      setMode(value) { if (value === mode) reset(); },
      setJoint(name, value) { const c = controls.find(c => c.name === name); if (!c || !Number.isFinite(value)) return; values.set(name, c.limited === false ? value : T.MathUtils.clamp(value, ...c.range)); applyJoints(); },
      setAmount(name, value) { if (!regions.some(region => region.name === name) || !Number.isFinite(value)) return; amounts.set(name, T.MathUtils.clamp(value, 0, 1)); applyJoints(); },
      // Compatibility with older callers cannot restart a saved recording.
      setClip() { return false; }, seek() { return false; }, seekFrame() { return false; }, toggle() { return false; },
      pause() { clearDirectInteraction(); }, reset,
      update(dt) {
        if (disposed) return false;
        let changed = Boolean(native?.update(dt));
        if (changed) { for (const [name, value] of Object.entries(native.values)) values.set(name, value); group.updateMatrixWorld(true); }
        for (const id of [...softReleased]) {
          const descriptor = directDescriptors().find(handle => handle.id === id);
          if (!descriptor) { softReleased.delete(id); continue; }
          const next = descriptor.getValue() * Math.exp(-Math.max(0, Math.min(dt, .1)) * 10);
          setDirectValue(id, next < .001 ? 0 : next); changed = true;
          if (next < .001) softReleased.delete(id);
        }
        return changed;
      },
      dispose() { softHeld.clear(); softReleased.clear(); softById.clear(); softControls = []; disposed = true; },
    };
  } catch (error) {
    group.traverse(o => o.geometry?.dispose()); materials.forEach(m => m.dispose()); textures.forEach(t => { t.source?.data?.close?.(); t.dispose(); });
    throw error;
  }
}
