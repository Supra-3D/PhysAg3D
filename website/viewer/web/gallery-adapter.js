import * as T from 'three';
import { GLTFLoader } from './vendor/GLTFLoader.js';
import { createSoftControls, createRecordedSoftControls } from './soft-manipulation.js';
import { surfaceAction } from './soft-profiles.js';

const unitScale = new T.Vector3(1, 1, 1);
const gltfToWorld = new T.Matrix4().makeRotationX(Math.PI / 2);
const pretty = value => String(value || '').replace(/[_-]+/g, ' ').replace(/\b\w/g, x => x.toUpperCase());
const compose = (p, q) => new T.Matrix4().compose(new T.Vector3(...p), new T.Quaternion(q[1], q[2], q[3], q[0]), unitScale);
const depth = object => { let n = 0; while (object.parent) { n++; object = object.parent; } return n; };

// This describes an axis in a delivered recording, never an independently
// controllable joint. Inspect keyframe transforms once; do not sample meshes.
function fitRecordedAxis(samples) {
  if (samples.length < 2) return null;
  const first = samples[0], inverse = first.quaternion.clone().invert();
  let best = null, largestRotation = 0, largestTravel = 0;
  for (const sample of samples) {
    if (![...sample.position.toArray(), ...sample.quaternion.toArray()].every(Number.isFinite)) return null;
    const delta = sample.quaternion.clone().multiply(inverse).normalize();
    if (delta.w < 0) delta.set(-delta.x, -delta.y, -delta.z, -delta.w);
    const sine = Math.hypot(delta.x, delta.y, delta.z);
    if (sine > largestRotation) { largestRotation = sine; best = { sample, delta }; }
    largestTravel = Math.max(largestTravel, sample.position.distanceTo(first.position));
  }
  const tolerance = Math.max(0.000002, largestTravel * 0.0002);
  if (largestRotation > 0.0005) {
    const axis = new T.Vector3(best.delta.x, best.delta.y, best.delta.z).normalize();
    const rhs = best.sample.position.clone().sub(first.position.clone().applyQuaternion(best.delta));
    const pivot = rhs.clone().multiplyScalar(0.5)
      .addScaledVector(axis.clone().cross(rhs), 0.5 * best.delta.w / largestRotation)
      .addScaledVector(axis, first.position.dot(axis));
    let error = 0;
    for (const sample of samples) {
      const delta = sample.quaternion.clone().multiply(inverse).normalize();
      if (new T.Vector3(delta.x, delta.y, delta.z).cross(axis).length() > 0.00001) return null;
      const expected = first.position.clone().sub(pivot).applyQuaternion(delta).add(pivot);
      error = Math.max(error, expected.distanceTo(sample.position));
    }
    return error <= tolerance ? { axisKind: 'hinge', pivot, axis, error } : null;
  }
  if (largestTravel < 0.000001) return null;
  const farthest = samples.reduce((a, b) => a.position.distanceToSquared(first.position) > b.position.distanceToSquared(first.position) ? a : b);
  const axis = farthest.position.clone().sub(first.position).normalize();
  let error = 0;
  for (const sample of samples) error = Math.max(error, sample.position.clone().sub(first.position).cross(axis).length());
  return error <= tolerance ? { axisKind: 'slide', pivot: first.position.clone(), axis, error } : null;
}

function uniformWorldScale(object) {
  if (!object) return true;
  const scale = new T.Vector3().setFromMatrixScale(object.matrixWorld);
  const largest = Math.max(scale.x, scale.y, scale.z, 1e-12);
  return Math.max(Math.abs(scale.x - scale.y), Math.abs(scale.x - scale.z)) / largest < 0.0001;
}

export async function createGalleryAdapter(item, { signal, onProgress = () => {} } = {}) {
  const metadataUrl = item.metadata_url ? new URL(item.metadata_url, location.href).href : null;
  async function bytes(url, hash) {
    const resource = new URL(url, metadataUrl || location.href);
    if (resource.origin !== location.origin) throw new Error('The model resource must be served locally.');
    const response = await fetch(resource.href, { signal });
    if (!response.ok) throw new Error('Could not load the model resource (' + response.status + ').');
    const buffer = await response.arrayBuffer();
    if (typeof hash === 'string' && /^[a-f0-9]{64}$/i.test(hash)) {
      const digest = [...new Uint8Array(await crypto.subtle.digest('SHA-256', buffer))].map(x => x.toString(16).padStart(2, '0')).join('');
      if (digest !== hash.toLowerCase()) throw new Error('The model and its motion data do not match.');
    }
    return buffer;
  }
  const metadata = item.metadata || (metadataUrl ? JSON.parse(new TextDecoder().decode(await bytes(metadataUrl))) : {});
  const resources = item.resources || {};
  const source = key => resources[key] || metadata.files?.[key];
  const hashFor = key => metadata.hashes?.[key] || metadata.hashes?.[key + '_sha256'] || (key === 'recorded_skin' ? metadata.hashes?.skin_sha256 : null);
  const jsonResource = async key => JSON.parse(new TextDecoder().decode(await bytes(source(key), hashFor(key))));
  const assetUrl = new URL(item.asset_url || source('asset'), metadataUrl || location.href).href;
  onProgress('Loading the 3D model');
  const assetHash = item.asset_sha256 || metadata.hashes?.asset || metadata.hashes?.asset_glb_sha256;
  const buffer = await bytes(assetUrl, assetHash);
  const gltf = await new GLTFLoader().parseAsync(buffer, new URL('.', assetUrl).href);
  const group = new T.Group(); group.rotation.x = Math.PI / 2; group.add(gltf.scene);
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
  const mixer = gltf.animations.length ? new T.AnimationMixer(gltf.scene) : null;
  const actions = mixer ? gltf.animations.map(clip => {
    const action = mixer.clipAction(clip); action.setLoop(T.LoopOnce, 1); action.clampWhenFinished = true; return action;
  }) : [];
  const graph = metadata.kinematics || { bodies: [], bindings: [], controls: [] };
  let trajectory = null, skinData = [], approximateData = [];
  const manifestBodies = metadata.manifest?.requirements?.bodies || [];
  const hasRecordedSource = source('trajectory') && (metadata.recorded_replay?.available || manifestBodies.length);
  try {
    if (signal?.aborted) throw new DOMException('Loading cancelled', 'AbortError');
    onProgress('Preparing motion controls');
    if (hasRecordedSource) {
      trajectory = await jsonResource('trajectory');
      if (!Array.isArray(trajectory.states) || trajectory.states.length < 2) throw new Error('Recorded motion is missing its frames.');
      if (source('recorded_skin')) skinData = await jsonResource('recorded_skin');
      else if (source('skin')) skinData = await jsonResource('skin');
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
    const replayDefinitions = metadata.recorded_replay?.body_bindings || manifestBodies.map(b => ({ body: b.name, node: b.node }));
    const replayBindings = trajectory ? await Promise.all(replayDefinitions.map(async b => ({ ...b, object: await node(b), offset: b.rest_offset ? new T.Matrix4().fromArray(b.rest_offset) : new T.Matrix4() }))) : [];
    replayBindings.sort((a, b) => depth(a.object) - depth(b.object));
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
    const controls = (graph.controls || []).map(c => ({ ...c, label: c.label || pretty(c.name), range: c.limits || [-Math.PI, Math.PI], value: c.reference || 0, unit: c.type === 'hinge' ? 'rad' : 'm' }));
    const regions = [...new Set(approximateBindings.map(b => b.region))].map(name => ({ name, label: pretty(name), range: [0, 1], unit: '%', value: 0 }));
    const values = new Map(controls.map(c => [c.name, c.value])), amounts = new Map();
    const local = new Map((graph.bodies || []).map(b => [b.id, compose(b.position, b.quaternion_wxyz)]));
    const bodies = new Map((graph.bodies || []).map(b => [b.id, b]));
    let jointWorlds = new Map();
    let mode = controls.length || regions.length ? 'joints' : trajectory ? 'recorded' : actions.length ? 'animation' : 'static';
    let playing = false, time = 0, frame = 0, clip = 0;
    let softControls = [];
    const softHeld = new Set(), softReleased = new Set();
    const modes = [];
    if (controls.length || regions.length) modes.push({ id: 'joints', label: controls.length ? 'Joint controls' : 'Approximate deformation' });
    if (trajectory) modes.push({ id: 'recorded', label: metadata.recorded_replay?.partial ? 'Partial recording' : skinBindings.length ? 'Recorded deformation' : 'Recorded motion' });
    const animationKind = item.original_motion_kind || metadata.original_motion_kind;
    if (actions.length) modes.push({ id: 'animation', label: animationKind === 'kinematic_parameter_animation' ? 'Parameter animation' : 'Original 3D motion' });
    if (!modes.length) modes.push({ id: 'static', label: '3D view' });

    function restore() {
      mixer?.stopAllAction();
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
    function applyRecorded(index) {
      frame = Math.max(0, Math.min(trajectory.states.length - 1, Math.round(index)));
      const state = trajectory.states[frame]; time = state.time;
      for (const b of replayBindings) {
        const pose = state.bodies[b.body];
        if (!pose) throw new Error('A recorded part is missing its position.');
        setBody(b, compose(pose.pos, pose.quat_wxyz));
      }
      group.updateMatrixWorld(true);
      const point = new T.Vector3();
      for (const b of skinBindings) {
        const physical = state.flex?.[b.flex], p = b.object.geometry.attributes.position, inverse = b.object.matrixWorld.clone().invert();
        if (!physical) throw new Error('The recorded surface is missing a frame.');
        for (let v = 0; v < p.count; v++) {
          point.set(0, 0, 0);
          for (let k = 0; k < b.indices[v].length; k++) {
            const xyz = physical[b.indices[v][k]], w = b.weights[v][k];
            if (!xyz || !xyz.every(Number.isFinite) || !Number.isFinite(w)) throw new Error('The recorded surface contains an invalid point.');
            point.x += xyz[0] * w; point.y += xyz[1] * w; point.z += xyz[2] * w;
          }
          point.applyMatrix4(inverse); p.setXYZ(v, point.x, point.y, point.z);
        }
        changedSurface(b.object);
      }
      group.updateMatrixWorld(true);
    }
    function recordedAt(t) {
      let lo = 0, hi = trajectory.states.length;
      while (lo < hi) { const mid = (lo + hi) >> 1; if (trajectory.states[mid].time <= t) lo = mid + 1; else hi = mid; }
      return Math.max(0, lo - 1);
    }
    function applyAnimation(t) {
      const action = actions[clip]; action.enabled = true; action.paused = false; action.play(); action.time = t; mixer.update(0); action.paused = true;
      time = t; group.updateMatrixWorld(true);
    }
    function apply() {
      if (mode === 'joints') applyJoints();
      else if (mode === 'recorded') applyRecorded(frame);
      else if (mode === 'animation') applyAnimation(time);
    }
    function reset() {
      softHeld.clear(); softReleased.clear(); softControls.forEach(control => control.reset());
      playing = false; time = 0; frame = 0; amounts.clear(); controls.forEach(c => values.set(c.name, c.reference || 0)); restore(); apply();
    }
    reset();
    // Relative morph targets can make the default geometry box accumulate
    // every target's extent. Frame the evaluated surface at each sample instead.
    const bounds = new T.Box3().setFromObject(group, hasMorphTargets), frameBounds = bounds.clone();
    // Sample the supplied movement for first-load framing without changing the
    // user's camera when they later operate a control.
    if (trajectory) {
      const samples = new Set([0, trajectory.states.length - 1, ...Object.values(trajectory.presets || {})]);
      for (let i = 0; i < 8; i++) samples.add(Math.round(i * (trajectory.states.length - 1) / 7));
      for (const i of samples) { applyRecorded(i); frameBounds.expandByObject(group, hasMorphTargets); }
      restore();
    }
    if (controls.length && controls.length < 30) {
      for (const c of controls) for (const value of [c.range[0], (c.range[0] + c.range[1]) / 2, c.range[1]]) {
        values.set(c.name, value); applyJoints(); frameBounds.expandByObject(group, hasMorphTargets); values.set(c.name, c.reference || 0);
      }
    }
    if (actions.length) {
      for (let i = 0; i < Math.min(actions.length, 12); i++) { clip = i; restore(); for (let n = 0; n < 5; n++) { applyAnimation(gltf.animations[i].duration * n / 4); frameBounds.expandByObject(group, hasMorphTargets); } }
      clip = 0;
    }
    reset();
    softControls = [...createSoftControls(item, gltf), ...createRecordedSoftControls(skinBindings, trajectory)];
    const softById = new Map(softControls.map(control => [control.descriptor.id, control]));
    // Direct manipulation is an additional view over the existing controls.
    // Descriptors cache object ownership and motion fits; getHandles only reads
    // current small transforms and never traverses vertex buffers.
    const rootCenterLocal = group.worldToLocal(bounds.getCenter(new T.Vector3()));
    const allObjects = [gltf.scene];
    function descendsFrom(id, ancestor) {
      const seen = new Set();
      while (id && !seen.has(id)) {
        if (id === ancestor) return true;
        seen.add(id); id = bodies.get(id)?.parent;
      }
      return false;
    }
    const jointHandles = controls.map(control => {
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
    function replayDescriptor(id, label, objects, pose, fit = null) {
      return {
        id, label, kind: 'replay', objects, min: 0, unit: 's', coupled: true,
        axisLabel: fit ? fit.axisKind === 'hinge' ? 'Recorded rotation axis' : 'Recorded translation axis' : 'Recorded motion',
        axisKind: fit?.axisKind || null, axisSource: fit ? 'recorded_transform_fit' : null,
        fitError: fit?.error ?? null,
        description: fit ? 'This axis describes the saved motion. Dragging scrubs the complete animation; all recorded parts stay synchronized.'
          : 'Drag to scrub the complete saved motion. No independent joint axis is claimed.',
        selectionDepth: fit ? Math.max(...objects.map(depth)) : -1,
        getValue: () => time, pose,
      };
    }
    const fallbackPose = () => ({ origin: group.localToWorld(rootCenterLocal.clone()), axis: null });
    const recordedHandles = trajectory ? [replayDescriptor('recorded:timeline', skinBindings.length ? 'Recorded deformation' : 'Recorded motion', allObjects, fallbackPose)] : [];
    if (trajectory && !skinBindings.length) {
      for (const binding of replayBindings) {
        const samples = trajectory.states.map(state => state.bodies?.[binding.body]).filter(Boolean).map(pose => ({ position: new T.Vector3(...pose.pos), quaternion: new T.Quaternion(pose.quat_wxyz[1], pose.quat_wxyz[2], pose.quat_wxyz[3], pose.quat_wxyz[0]).normalize() }));
        const fit = samples.length === trajectory.states.length ? fitRecordedAxis(samples) : null;
        if (fit) recordedHandles.push(replayDescriptor('recorded:part:' + binding.body, pretty(binding.body), [binding.object], () => ({ origin: fit.pivot.clone(), axis: fit.axis.clone() }), fit));
      }
    }
    const animationHandles = gltf.animations.map((animation, animationIndex) => {
      const entries = [replayDescriptor('animation:' + animationIndex + ':timeline', animationKind === 'kinematic_parameter_animation' ? 'Parameter animation' : 'Recorded motion', allObjects, fallbackPose)];
      // A soft recording has deformation controls, not a claimed rigid hinge.
      if (hasMorphTargets) return entries;
      const nodeTracks = new Map();
      for (const track of animation.tracks) {
        const parsed = T.PropertyBinding.parseTrackName(track.name);
        if (!['position', 'quaternion', 'scale'].includes(parsed.propertyName)) continue;
        const object = T.PropertyBinding.findNode(gltf.scene, parsed.nodeName);
        if (!object) continue;
        if (!nodeTracks.has(object)) nodeTracks.set(object, {});
        const tracks = nodeTracks.get(object);
        if (tracks[parsed.propertyName]) tracks.ambiguous = true;
        tracks[parsed.propertyName] = track;
      }
      let index = 0;
      for (const [object, tracks] of nodeTracks) {
        if (object.isBone || tracks.ambiguous || (!tracks.position && !tracks.quaternion) || !uniformWorldScale(object.parent)) continue;
        const used = [tracks.position, tracks.quaternion, tracks.scale].filter(Boolean);
        if (used.some(track => track.createInterpolant.isInterpolantFactoryMethodGLTFCubicSpline)) continue;
        if (tracks.scale && tracks.scale.values.some((value, i, array) => Math.abs(value - array[i % 3]) > 0.000001)) continue;
        const times = [...new Set(used.flatMap(track => Array.from(track.times)))].sort((a, b) => a - b);
        const position = tracks.position?.createInterpolant(), quaternion = tracks.quaternion?.createInterpolant();
        const samples = times.map(t => ({ position: position ? new T.Vector3().fromArray(position.evaluate(t)) : object.position.clone(),
          quaternion: quaternion ? new T.Quaternion().fromArray(quaternion.evaluate(t)).normalize() : object.quaternion.clone() }));
        const fit = fitRecordedAxis(samples);
        if (!fit) continue;
        entries.push(replayDescriptor('animation:' + animationIndex + ':part:' + index++, pretty(object.name) || 'Recorded part', [object], () => {
          const parentWorld = object.parent?.matrixWorld || new T.Matrix4();
          return { origin: fit.pivot.clone().applyMatrix4(parentWorld), axis: fit.axis.clone().transformDirection(parentWorld) };
        }, fit));
      }
      return entries;
    });
    function directDescriptors() {
      if (disposed) return [];
      if (mode === 'joints') return [...jointHandles, ...surfaceHandles];
      if (mode === 'recorded') {
        const soft = softControls.filter(c => c.source === 'original_recorded_skin').map(c => c.descriptor);
        return soft.length && !hasRigidMotion ? soft : [...recordedHandles, ...soft];
      }
      if (mode === 'animation') {
        const soft = softControls.filter(c => c.source !== 'original_recorded_skin').map(c => c.descriptor);
        return soft.length && !hasRigidMotion ? soft : [...animationHandles[clip], ...soft];
      }
      return softControls.filter(c => c.source === 'browser_local_visual_deformation').map(c => c.descriptor);
    }
    function getHandles() {
      const duration = mode === 'recorded' ? trajectory.states.at(-1).time : mode === 'animation' ? gltf.animations[clip].duration : 0;
      return directDescriptors().map(({ pose, getValue, ...descriptor }) => {
        const spatial = pose();
        return { ...descriptor, ...spatial, value: getValue(), max: descriptor.kind === 'replay' ? duration : descriptor.max,
          disabled: Boolean(descriptor.disabled || spatial.disabled || (descriptor.kind === 'replay' && duration <= 0)) };
      });
    }
    function setDirectValue(id, value) {
      if (!Number.isFinite(value) || !directDescriptors().some(handle => handle.id === id)) return false;
      playing = false;
      if (softById.has(id)) {
        softById.get(id).set(value); group.updateMatrixWorld(true);
      } else if (id.startsWith('joint:')) {
        const name = id.slice(6), control = controls.find(c => c.name === name);
        values.set(name, control.limited === false ? value : T.MathUtils.clamp(value, ...control.range)); applyJoints();
      } else if (id.startsWith('surface:')) {
        amounts.set(id.slice(8), T.MathUtils.clamp(value, 0, 1)); applyJoints();
      } else if (mode === 'recorded') applyRecorded(recordedAt(T.MathUtils.clamp(value, 0, trajectory.states.at(-1).time)));
      else if (mode === 'animation') applyAnimation(T.MathUtils.clamp(value, 0, gltf.animations[clip].duration));
      else return false;
      return true;
    }
    function beginDirectInteraction(id, detail = {}) {
      const descriptor = directDescriptors().find(handle => handle.id === id);
      if (!descriptor || descriptor.interaction !== 'soft') return false;
      playing = false; softReleased.delete(id); softHeld.add(id);
      softById.get(id)?.begin(detail);
      return true;
    }
    function endDirectInteraction(id) {
      const descriptor = directDescriptors().find(handle => handle.id === id);
      if (!descriptor || descriptor.interaction !== 'soft') return false;
      softHeld.delete(id); softReleased.add(id); return true;
    }
    function clearDirectInteraction() {
      const ids = new Set([...softHeld, ...softReleased]);
      softHeld.clear(); softReleased.clear();
      for (const id of ids) setDirectValue(id, 0);
    }
    const softSurfaceCount = surfaceHandles.length + softControls.length;
    const animatedRigidObjects = new Set(gltf.animations.flatMap(animation => animation.tracks).map(track => {
      const parsed = T.PropertyBinding.parseTrackName(track.name);
      const object = T.PropertyBinding.findNode(gltf.scene, parsed.nodeName);
      return ['position', 'quaternion', 'scale'].includes(parsed.propertyName) && object && !object.isBone ? object : null;
    }).filter(Boolean));
    const hasRigidMotion = Boolean(jointHandles.length || animatedRigidObjects.size || (!skinBindings.length && replayBindings.length));
    return {
      group, materials: [...materials], textures: [...textures], controls, regions, modes, metadata,
      getHandles, setDirectValue, beginDirectInteraction, endDirectInteraction,
      directMetadata: { declaredJoints: jointHandles.length, authoredSurfaces: surfaceHandles.length,
        softSurfaces: softSurfaceCount, hasRigidMotion,
        softSources: [...surfaceHandles.map(handle => ({ id: handle.id, source: 'authored_vertex_deltas' })), ...softControls.map(control => ({ id: control.descriptor.id, ...control.audit }))],
        softResponse: 'Visual interpolation with smooth release; no new force or material solver.',
        recordedAxes: recordedHandles.filter(x => x.axisKind).length,
        animationAxes: animationHandles.map(rows => rows.filter(x => x.axisKind).length),
        recordedMotionRemainsCoupled: true, axisFitsSampleMeshes: false },
      bounds, frameBounds, clips: gltf.animations.map((a, i) => ({ id: i, name: a.name || 'Animation ' + (i + 1) })),
      frameCount: trajectory?.states.length || 0, partial: Boolean(metadata.recorded_replay?.partial),
      presets: trajectory ? Object.entries(trajectory.presets || {}).map(([name, index]) => ({ name: pretty(name), index })) : [],
      get mode() { return mode; }, get playing() { return playing; }, get time() { return time; }, get frame() { return frame; },
      get duration() { return mode === 'recorded' ? trajectory.states.at(-1).time : mode === 'animation' ? gltf.animations[clip].duration : 8; },
      get label() { return softSurfaceCount && (mode === 'static' || softHeld.size || softReleased.size) ? 'Soft interaction' : mode === 'joints' && [...amounts.values()].some(x => x > 0) ? 'Soft interaction' : modes.find(x => x.id === mode)?.label || '3D view'; },
      get values() { return Object.fromEntries(values); }, get amounts() { return Object.fromEntries(amounts); },
      setMode(value) { if (!modes.some(m => m.id === value)) return; mode = value; reset(); },
      setJoint(name, value) { const c = controls.find(c => c.name === name); if (!c || !Number.isFinite(value)) return; playing = false; values.set(name, c.limited === false ? value : T.MathUtils.clamp(value, ...c.range)); applyJoints(); },
      setAmount(name, value) { playing = false; amounts.set(name, T.MathUtils.clamp(value, 0, 1)); applyJoints(); },
      setClip(value) { if (!actions[value]) return; clip = value; reset(); },
      seek(value) { clearDirectInteraction(); playing = false; if (mode === 'recorded') applyRecorded(recordedAt(value)); else if (mode === 'animation') applyAnimation(T.MathUtils.clamp(value, 0, gltf.animations[clip].duration)); },
      seekFrame(index) { clearDirectInteraction(); playing = false; applyRecorded(index); },
      toggle() { if (mode === 'static') return; clearDirectInteraction(); if (time >= this.duration) { time = 0; frame = 0; } playing = !playing; },
      pause() { clearDirectInteraction(); playing = false; }, reset,
      update(dt) {
        if (disposed) return false;
        let changed = false;
        for (const id of [...softReleased]) {
          const descriptor = directDescriptors().find(handle => handle.id === id);
          if (!descriptor) { softReleased.delete(id); continue; }
          const next = descriptor.getValue() * Math.exp(-Math.max(0, Math.min(dt, .1)) * 10);
          setDirectValue(id, next < .001 ? 0 : next); changed = true;
          if (next < .001) softReleased.delete(id);
        }
        if (!playing) return changed;
        const next = time + dt;
        if (mode === 'joints') {
          time = next;
          for (const c of controls) values.set(c.name, c.limited === false ? values.get(c.name) + Math.PI / 3 * dt : c.range[0] + (1 - Math.cos(time * Math.PI / 4)) / 2 * (c.range[1] - c.range[0]));
          applyJoints();
        } else if (mode === 'recorded') { const at = Math.min(next, this.duration); applyRecorded(recordedAt(at)); time = at; if (at >= this.duration) playing = false; }
        else if (mode === 'animation') { const at = Math.min(next, this.duration); applyAnimation(at); if (at >= this.duration) playing = false; }
        return true;
      },
      dispose() { softHeld.clear(); softReleased.clear(); softById.clear(); softControls = []; disposed = true; mixer?.stopAllAction(); mixer?.uncacheRoot(gltf.scene); },
    };
  } catch (error) {
    group.traverse(o => o.geometry?.dispose()); materials.forEach(m => m.dispose()); textures.forEach(t => { t.source?.data?.close?.(); t.dispose(); });
    throw error;
  }
}
