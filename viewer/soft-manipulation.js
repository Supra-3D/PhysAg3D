import * as T from 'three';
import { LOCAL_SOFT_PROFILES, MORPH_SOFT_PROFILES, SKIN_SOFT_PROFILES } from './soft-profiles.js';

const clamp = value => T.MathUtils.clamp(value, 0, 1);
const vector = value => value?.isVector3 ? value.clone() : Array.isArray(value) ? new T.Vector3(...value) : null;
const within = (object, root) => { for (let o = object; o; o = o.parent) if (o === root) return true; return false; };
const hintFor = action => action === 'pull' ? 'Hold and drag the fabric. Release to let it settle.' : 'Hold to press. Drag to adjust, then release.';

function controller(id, profile, objects, source, pose, apply, onBegin = () => {}, onReset = () => {}) {
  let amount = 0;
  return {
    descriptor: { id, label: profile.label, kind: 'surface', interaction: 'soft', action: profile.action,
      objects, min: 0, max: 1, unit: '%', axisLabel: '', axisSource: source,
      hint: hintFor(profile.action), description: hintFor(profile.action), pressAmount: 0.18,
      coupled: objects.length > 1, selectionDepth: 100,
      acceptsHit: hit => objects.some(object => within(hit.object, object)),
      getValue: () => amount, pose,
    },
    set(value) { amount = clamp(value); apply(amount); },
    begin(detail) { onBegin(detail); amount = 0; },
    reset() { amount = 0; onReset(); apply(0); },
    source,
  };
}

function meshPose(objects) {
  const local = objects.map(object => {
    object.geometry.computeBoundingBox();
    return { object, center: object.geometry.boundingBox.getCenter(new T.Vector3()) };
  });
  return () => ({ origin: local.reduce((p, row) => p.add(row.center.clone().applyMatrix4(row.object.matrixWorld)), new T.Vector3()).divideScalar(local.length || 1), axis: null });
}

function localCushion(scene, profile) {
  const objects = profile.meshes.map(name => scene.getObjectByName(name)).filter(o => o?.isMesh);
  if (objects.length !== profile.meshes.length) return null; // Fail closed on a changed source mesh.
  const rows = objects.map(object => ({ object, positions: object.geometry.attributes.position.array.slice(), normals: object.geometry.attributes.normal?.array.slice(), affected: [] }));
  let contact = new T.Vector3(...profile.center), normal = new T.Vector3(...profile.normal), anchor = objects[0];
  const restore = () => {
    for (const row of rows) {
      const p = row.object.geometry.attributes.position, n = row.object.geometry.attributes.normal;
      for (const hit of row.affected) for (let k = 0; k < 3; k++) { p.array[hit.i * 3 + k] = row.positions[hit.i * 3 + k]; if (n) n.array[hit.i * 3 + k] = row.normals[hit.i * 3 + k]; }
      if (row.affected.length) { p.needsUpdate = true; if (n) n.needsUpdate = true; }
    }
  };
  function prepare(detail = {}) {
    restore();
    const hitObject = objects.find(o => detail.object && within(detail.object, o));
    const worldPoint = vector(detail.point), worldNormal = vector(detail.normal);
    anchor = hitObject || objects[0];
    if (worldPoint && hitObject) contact = anchor.worldToLocal(worldPoint.clone());
    else contact = new T.Vector3(...profile.center);
    if (worldNormal && hitObject) normal = worldNormal.transformDirection(anchor.matrixWorld.clone().invert());
    else normal = new T.Vector3(...profile.normal);
    const centerWorld = contact.clone().applyMatrix4(anchor.matrixWorld);
    const inwardWorld = normal.clone().transformDirection(anchor.matrixWorld).negate();
    for (const row of rows) {
      const inverse = row.object.matrixWorld.clone().invert();
      const center = centerWorld.clone().applyMatrix4(inverse);
      const scale = new T.Vector3().setFromMatrixScale(row.object.matrixWorld);
      const radius = profile.radius / Math.max(scale.x, scale.y, scale.z, 1e-8), radiusSq = radius * radius;
      row.direction = inwardWorld.clone().transformDirection(inverse).multiplyScalar(profile.depth / Math.max(scale.x, scale.y, scale.z, 1e-8));
      row.affected = [];
      const p = row.positions;
      for (let i = 0; i < p.length / 3; i++) {
        const dx = p[3 * i] - center.x, dy = p[3 * i + 1] - center.y, dz = p[3 * i + 2] - center.z;
        const q = 1 - (dx * dx + dy * dy + dz * dz) / radiusSq;
        if (q <= 0) continue;
        const gradient = -6 * q * q / radiusSq;
        row.affected.push({ i, weight: q * q * q, gx: gradient * dx, gy: gradient * dy, gz: gradient * dz });
      }
    }
  }
  function apply(amount) {
    for (const row of rows) {
      const p = row.object.geometry.attributes.position, n = row.object.geometry.attributes.normal, d = row.direction;
      for (const hit of row.affected) {
        const i = hit.i * 3, a = amount * hit.weight;
        p.array[i] = row.positions[i] + d.x * a; p.array[i + 1] = row.positions[i + 1] + d.y * a; p.array[i + 2] = row.positions[i + 2] + d.z * a;
        if (n) {
          const nx = row.normals[i], ny = row.normals[i + 1], nz = row.normals[i + 2];
          // Exact inverse-transpose of this smooth local displacement Jacobian.
          const k = amount * (nx * d.x + ny * d.y + nz * d.z) / Math.max(.2, 1 + amount * (hit.gx * d.x + hit.gy * d.y + hit.gz * d.z));
          const x = nx - hit.gx * k, y = ny - hit.gy * k, z = nz - hit.gz * k, length = Math.hypot(x, y, z) || 1;
          n.array[i] = x / length; n.array[i + 1] = y / length; n.array[i + 2] = z / length;
        }
      }
      p.needsUpdate = true; if (n) n.needsUpdate = true;
      // Pressure only moves inward; retaining rest bounds avoids an O(vertices)
      // bounds scan each pointer move and safely contains the small depression.
    }
  }
  prepare();
  const result = controller('soft:cushion', profile, objects, profile.source,
    () => ({ origin: contact.clone().applyMatrix4(anchor.matrixWorld), axis: normal.clone().transformDirection(anchor.matrixWorld).negate() }), apply, prepare,
    () => { restore(); prepare(); });
  result.audit = { source: profile.source, meshes: profile.meshes, excludedMeshes: profile.excludedMeshes, radius: profile.radius, maximumDepth: profile.depth };
  return result;
}

function morphControls(gltf, profile) {
  const objects = [];
  gltf.scene.traverse(object => { if (object.isMesh && object.geometry.morphAttributes.position?.length) objects.push(object); });
  const result = [];
  for (const [index, object] of objects.entries()) {
    const original = object.morphTargetInfluences.slice(), targets = object.geometry.morphAttributes.position;
    const track = gltf.animations.flatMap(a => a.tracks).find(t => {
      const parsed = T.PropertyBinding.parseTrackName(t.name);
      return parsed.propertyName === 'morphTargetInfluences' && T.PropertyBinding.findNode(gltf.scene, parsed.nodeName) === object;
    });
    if (!track) continue;
    // Pick a supplied shape with the greatest actual sampled surface change,
    // rather than treating one-hot frame weights as deformation magnitude.
    const count = object.geometry.attributes.position.count, stride = Math.max(1, Math.floor(count / 64));
    const samples = []; for (let i = 0; i < count; i += stride) samples.push(i);
    const targetSamples = targets.map(target => samples.map(i => new T.Vector3().fromBufferAttribute(target, i)));
    const basePositions = samples.map(i => new T.Vector3().fromBufferAttribute(object.geometry.attributes.position, i));
    const times = [...track.times], sampleStride = Math.max(1, Math.floor(times.length / 128));
    const interpolant = track.createInterpolant(); let best = -1, peak = original.slice(), peakTime = 0;
    for (let i = 0; i < times.length; i += sampleStride) {
      const weights = Array.from(interpolant.evaluate(times[i])); let score = 0;
      for (let s = 0; s < samples.length; s++) {
        const delta = new T.Vector3();
        for (let k = 0; k < weights.length; k++) if (Math.abs(weights[k] - original[k]) > 1e-7) {
          const position = targetSamples[k][s];
          delta.addScaledVector(position, weights[k] - original[k]);
          if (!object.geometry.morphTargetsRelative) delta.addScaledVector(basePositions[s], original[k] - weights[k]);
        }
        score += delta.lengthSq();
      }
      if (score > best) { best = score; peak = weights; peakTime = times[i]; }
    }
    if (best < 1e-12) continue;
    let baseline = original.slice();
    const label = /strap/i.test(object.name) ? { label: 'Pull strap', action: 'pull' } : profile;
    const control = controller('soft:morph:' + index, label, [object], 'original_morph_shapes', meshPose([object]),
      amount => { for (let i = 0; i < baseline.length; i++) object.morphTargetInfluences[i] = baseline[i] + (peak[i] - baseline[i]) * amount; },
      () => { baseline = object.morphTargetInfluences.slice(); }, () => { baseline = original.slice(); });
    control.audit = { source: control.source, mesh: object.name, peakTime, targets: targets.length, sourceAnimation: gltf.animations[0]?.name, rigidTracksApplied: false };
    result.push(control);
  }
  return result;
}

function skinControls(gltf, profile) {
  const objects = []; gltf.scene.traverse(object => { if (object.isSkinnedMesh && profile.mesh.test(object.name)) objects.push(object); });
  if (!objects.length) return [];
  const bones = [...new Set(objects.flatMap(object => object.skeleton.bones))];
  const initial = new Map(bones.map(b => [b, { position: b.position.clone(), quaternion: b.quaternion.clone(), scale: b.scale.clone() }]));
  const tracks = gltf.animations.flatMap(a => a.tracks).map(track => {
    const parsed = T.PropertyBinding.parseTrackName(track.name), object = T.PropertyBinding.findNode(gltf.scene, parsed.nodeName);
    return { track, property: parsed.propertyName, object, interpolate: track.createInterpolant() };
  }).filter(row => initial.has(row.object) && ['position', 'quaternion', 'scale'].includes(row.property));
  if (!tracks.length) return [];
  const times = [...new Set(tracks.flatMap(row => Array.from(row.track.times)))].sort((a, b) => a - b);
  const stride = Math.max(1, Math.floor(times.length / 48)); let scoreBest = -1, peakTime = 0;
  function stateAt(time) {
    const state = new Map([...initial].map(([bone, pose]) => [bone, { position: pose.position.clone(), quaternion: pose.quaternion.clone(), scale: pose.scale.clone() }]));
    for (const row of tracks) state.get(row.object)[row.property].fromArray(row.interpolate.evaluate(time));
    return state;
  }
  for (let i = 0; i < times.length; i += stride) {
    let score = 0;
    for (const [bone, pose] of stateAt(times[i])) { const rest = initial.get(bone); score += pose.position.distanceToSquared(rest.position) + .002 * (1 - Math.abs(pose.quaternion.dot(rest.quaternion))); }
    if (score > scoreBest) { scoreBest = score; peakTime = times[i]; }
  }
  if (scoreBest < 1e-12) return [];
  const peak = stateAt(peakTime); let baseline = initial;
  const control = controller('soft:skin', profile, objects, 'original_skinned_shapes', meshPose(objects),
    amount => {
      for (const bone of bones) {
        const a = baseline.get(bone), b = peak.get(bone);
        bone.position.lerpVectors(a.position, b.position, amount); bone.quaternion.slerpQuaternions(a.quaternion, b.quaternion, amount); bone.scale.lerpVectors(a.scale, b.scale, amount);
        bone.updateMatrix();
      }
      gltf.scene.updateMatrixWorld(true); objects.forEach(o => { o.skeleton.update(); o.frustumCulled = false; });
    }, () => { baseline = new Map(bones.map(b => [b, { position: b.position.clone(), quaternion: b.quaternion.clone(), scale: b.scale.clone() }])); }, () => { baseline = initial; });
  control.audit = { source: control.source, meshes: objects.map(o => o.name), peakTime, bones: bones.length, rigidTracksApplied: false };
  return [control];
}

export function createSoftControls(item, gltf) {
  const controllers = [];
  if (LOCAL_SOFT_PROFILES[item.id]) { const local = localCushion(gltf.scene, LOCAL_SOFT_PROFILES[item.id]); if (local) controllers.push(local); }
  if (MORPH_SOFT_PROFILES[item.id]) controllers.push(...morphControls(gltf, MORPH_SOFT_PROFILES[item.id]));
  if (SKIN_SOFT_PROFILES[item.id]) controllers.push(...skinControls(gltf, SKIN_SOFT_PROFILES[item.id]));
  return controllers;
}

// Recorded flex points are projected through their original verified skin
// mapping. Only the surface is blended, never the recorder's rigid bodies.
export function createRecordedSoftControls(skinBindings, trajectory) {
  if (!trajectory || !skinBindings.length) return [];
  return skinBindings.map((binding, index) => {
    const object = binding.object, initial = object.geometry.attributes.position.array.slice();
    const normal = object.geometry.attributes.normal?.array.slice();
    const first = trajectory.states[0].flex?.[binding.flex]; if (!first) return null;
    let best = -1, peakFrame = 0;
    for (let frame = 0; frame < trajectory.states.length; frame++) {
      const points = trajectory.states[frame].flex?.[binding.flex]; if (!points) continue;
      let score = 0; for (let i = 0; i < points.length; i++) for (let k = 0; k < 3; k++) score += (points[i][k] - first[i][k]) ** 2;
      if (score > best) { best = score; peakFrame = frame; }
    }
    if (best < 1e-12) return null;
    const peak = initial.slice(), inverse = object.matrixWorld.clone().invert(), point = new T.Vector3(), physical = trajectory.states[peakFrame].flex[binding.flex];
    for (let i = 0; i < binding.indices.length; i++) {
      point.set(0, 0, 0);
      for (let k = 0; k < binding.indices[i].length; k++) point.addScaledVector(new T.Vector3(...physical[binding.indices[i][k]]), binding.weights[i][k]);
      point.applyMatrix4(inverse); peak[i * 3] = point.x; peak[i * 3 + 1] = point.y; peak[i * 3 + 2] = point.z;
    }
    let baseline = initial.slice();
    const result = controller('soft:recorded:' + index, { label: 'Press cushion', action: 'press' }, [object], 'original_recorded_skin', meshPose([object]), amount => {
      const positions = object.geometry.attributes.position;
      for (let i = 0; i < positions.array.length; i++) positions.array[i] = baseline[i] + (peak[i] - baseline[i]) * amount;
      positions.needsUpdate = true;
      if (amount === 0 && normal) { object.geometry.attributes.normal.array.set(normal); object.geometry.attributes.normal.needsUpdate = true; }
      else object.geometry.computeVertexNormals();
      object.frustumCulled = false;
    }, () => { baseline = object.geometry.attributes.position.array.slice(); }, () => { baseline = initial.slice(); });
    result.audit = { source: result.source, mesh: object.name, peakFrame, rigidTracksApplied: false };
    return result;
  }).filter(Boolean);
}
