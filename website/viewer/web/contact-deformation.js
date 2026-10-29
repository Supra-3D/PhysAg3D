import * as T from 'three';

const vector = value => value?.isVector3 ? value.clone() : Array.isArray(value) ? new T.Vector3(...value) : null;
const triangle = (object, detail) => {
  if (detail.face) return [detail.face.a, detail.face.b, detail.face.c];
  if (!Number.isInteger(detail.faceIndex)) return null;
  const index = object.geometry.index, start = detail.faceIndex * 3;
  if (start < 0 || start + 2 >= (index?.count || object.geometry.attributes.position.count)) return null;
  return [0, 1, 2].map(k => index ? index.getX(start + k) : start + k);
};
const worldVertex = (object, index) => object.getVertexPosition(index, new T.Vector3()).applyMatrix4(object.matrixWorld);
function skinMatrix(object, index) {
  const result = new T.Matrix4();
  if (!object.isSkinnedMesh) return result;
  const indices = object.geometry.attributes.skinIndex, weights = object.geometry.attributes.skinWeight;
  result.elements.fill(0);
  for (let k = 0; k < 4; k++) {
    const weight = weights.getComponent(index, k), offset = indices.getComponent(index, k) * 16;
    for (let j = 0; j < 16; j++) result.elements[j] += weight * object.skeleton.boneMatrices[offset + j];
  }
  return result.premultiply(object.bindMatrixInverse).multiply(object.bindMatrix);
}
function copyAttribute(attribute) {
  if (!attribute) return null;
  const array = new Float32Array(attribute.count * 3);
  for (let i = 0; i < attribute.count; i++) { array[i * 3] = attribute.getX(i); array[i * 3 + 1] = attribute.getY(i); array[i * 3 + 2] = attribute.getZ(i); }
  return new T.BufferAttribute(array, 3);
}
function invalidate(object) {
  object.geometry.boundingBox = null; object.geometry.boundingSphere = null;
  if (object.isSkinnedMesh) { object.boundingBox = null; object.boundingSphere = null; }
}

// Work at the actual contact in evaluated world space, then invert the exact
// per-vertex skin mapping. Original shapes, bones and rigid parts stay intact.
export function createContactControl(id, profile, objects, source) {
  let amount = 0, active = false, center = null, lastContact = null, normal = new T.Vector3(0, 0, 1);
  const defaultCenter = objects[0].worldToLocal(new T.Box3().setFromObject(objects[0], true).getCenter(new T.Vector3()));
  const rows = objects.map(object => {
    const eligible = new Float32Array(object.geometry.attributes.position.count).fill(1);
    if (profile.bones && object.isSkinnedMesh) {
      const indices = object.geometry.attributes.skinIndex, weights = object.geometry.attributes.skinWeight;
      for (let i = 0; i < eligible.length; i++) {
        let softWeight = 0;
        for (let k = 0; k < 4; k++) if (profile.bones.test(object.skeleton.bones[indices.getComponent(i, k)]?.name || '')) softWeight += weights.getComponent(i, k);
        eligible[i] = T.MathUtils.smoothstep(softWeight, .05, .95);
      }
    }
    return { object, eligible, originalGeometry: null, affected: [] };
  });
  function privateGeometry(row) {
    if (row.originalGeometry) return;
    const original = row.object.geometry, geometry = new T.BufferGeometry();
    // Share read-only UVs, indices and potentially hundreds of authored shapes.
    geometry.name = original.name; geometry.setIndex(original.index);
    for (const [name, attribute] of Object.entries(original.attributes)) geometry.setAttribute(name, name === 'position' || name === 'normal' ? copyAttribute(attribute) : attribute);
    geometry.morphAttributes = original.morphAttributes; geometry.morphTargetsRelative = original.morphTargetsRelative;
    geometry.groups = original.groups.map(group => ({ ...group })); geometry.drawRange = { ...original.drawRange };
    row.originalGeometry = original; row.object.geometry = geometry;
  }
  function restore() {
    if (!active) return;
    for (const row of rows) {
      const object = row.object, geometry = object.geometry;
      geometry.attributes.position.array.set(row.baseline); geometry.attributes.position.needsUpdate = true;
      if (row.normals) { geometry.attributes.normal.array.set(row.normals); geometry.attributes.normal.needsUpdate = true; }
      else geometry.deleteAttribute('normal');
      if (row.morphs) object.morphTargetInfluences.splice(0, row.morphs.length, ...row.morphs);
      object.frustumCulled = row.frustumCulled; invalidate(object); row.affected = [];
    }
    active = false;
  }
  function acceptsHit(hit) {
    const row = rows.find(row => row.object === hit.object);
    if (!row) return false;
    const face = triangle(row.object, hit);
    if (!face) return !profile.bones;
    const bary = T.Triangle.getBarycoord(hit.point, ...face.map(index => worldVertex(row.object, index)), new T.Vector3());
    return bary && face.reduce((sum, index, k) => sum + row.eligible[index] * bary.getComponent(k), 0) > .75;
  }
  function prepare(detail = lastContact || {}) {
    const hitRow = rows.find(row => row.object === detail.object), face = hitRow && triangle(hitRow.object, detail);
    let point = vector(detail.point), bary = null;
    // Re-grabbing during spring-back follows the same material triangle.
    if (active && face && point) bary = T.Triangle.getBarycoord(point, ...face.map(i => worldVertex(hitRow.object, i)), new T.Vector3());
    restore(); amount = 0;
    for (const row of rows) { privateGeometry(row); row.object.updateWorldMatrix(true, false); row.object.skeleton?.update(); }
    const anchor = hitRow || rows.find(row => row.eligible.some(value => value > .75)) || rows[0];
    if (bary) point = face.reduce((p, index, k) => p.addScaledVector(worldVertex(anchor.object, index), bary.getComponent(k)), new T.Vector3());
    const box = new T.Box3().setFromObject(anchor.object, true), size = box.getSize(new T.Vector3());
    if (!point || !hitRow) {
      const desired = profile.center ? new T.Vector3(...profile.center).applyMatrix4(anchor.object.matrixWorld) : box.getCenter(new T.Vector3());
      let nearest = Infinity;
      for (let i = 0; i < anchor.eligible.length; i++) if (anchor.eligible[i] > .75) {
        const p = worldVertex(anchor.object, i), distance = p.distanceToSquared(desired);
        if (distance < nearest) { nearest = distance; point = p; }
      }
    }
    center = point || box.getCenter(new T.Vector3());
    normal = vector(detail.normal) || (profile.normal ? new T.Vector3(...profile.normal).applyNormalMatrix(new T.Matrix3().getNormalMatrix(anchor.object.matrixWorld)) : new T.Vector3(0, 0, 1));
    normal.normalize();
    lastContact = { ...detail, point: center.clone(), normal: normal.clone() };
    const extent = Math.max(size.x, size.y, size.z, 1e-6);
    let radius = profile.radius || extent * (profile.action === 'pull' ? .22 : .18);
    // Include the picked face even when a source surface has coarse triangles.
    if (face) for (const index of face) radius = Math.max(radius, worldVertex(anchor.object, index).distanceTo(center) * 2.2);
    const depth = profile.depth || radius * (profile.action === 'pull' ? .35 : .20);
    const direction = normal.clone().multiplyScalar((profile.action === 'pull' ? 1 : -1) * depth);
    for (const row of rows) {
      const object = row.object, geometry = object.geometry, positions = geometry.attributes.position;
      row.baseline = positions.array.slice(); row.normals = geometry.attributes.normal?.array.slice();
      row.morphs = object.morphTargetInfluences?.slice(); row.frustumCulled = object.frustumCulled;
      row.evaluated = row.baseline.slice(); row.affected = [];
      const point = new T.Vector3(), inverseWorld = object.matrixWorld.clone().invert();
      for (let i = 0; i < positions.count; i++) {
        // Bake only the current morph pose, before skinning. Zeroing its weights
        // avoids double application for absolute, relative and one-hot shapes.
        T.Mesh.prototype.getVertexPosition.call(object, i, point);
        point.toArray(row.evaluated, i * 3);
        if (object.isSkinnedMesh) object.applyBoneTransform(i, point);
        point.applyMatrix4(object.matrixWorld);
        const q = 1 - point.distanceToSquared(center) / (radius * radius);
        if (q <= 0 || row.eligible[i] === 0) continue;
        const inverse = object.isSkinnedMesh ? skinMatrix(object, i).invert().multiply(inverseWorld) : inverseWorld;
        const delta = direction.clone().applyMatrix3(new T.Matrix3().setFromMatrix4(inverse));
        row.affected.push({ index: i * 3, weight: q * q * q * row.eligible[i], delta });
      }
      positions.array.set(row.evaluated);
      row.poseNormals = row.normals?.slice();
      if (row.poseNormals && row.morphs && geometry.morphAttributes.normal?.length) {
        const baseWeight = geometry.morphTargetsRelative ? 1 : 1 - row.morphs.reduce((a, b) => a + b, 0);
        for (let i = 0; i < row.poseNormals.length; i++) row.poseNormals[i] *= baseWeight;
        geometry.morphAttributes.normal.forEach((target, k) => {
          if (!row.morphs[k]) return;
          for (let i = 0; i < target.count; i++) for (let component = 0; component < 3; component++) row.poseNormals[i * 3 + component] += target.getComponent(i, component) * row.morphs[k];
        });
      }
      const moved = new Set(row.affected.map(hit => hit.index / 3));
      row.changedNormals = new Uint8Array(positions.count);
      const count = geometry.index?.count || positions.count;
      for (let start = 0; start < count; start += 3) {
        const indices = [0, 1, 2].map(k => geometry.index ? geometry.index.getX(start + k) : start + k);
        if (indices.some(index => moved.has(index))) for (const index of indices) row.changedNormals[index] = 1;
      }
      if (row.morphs) object.morphTargetInfluences.fill(0);
      object.frustumCulled = false; positions.needsUpdate = true; invalidate(object);
    }
    active = true;
  }
  function set(value) {
    amount = T.MathUtils.clamp(value, 0, 1);
    if (amount === 0) { restore(); return; }
    if (!active) prepare();
    amount = T.MathUtils.clamp(value, 0, 1);
    for (const row of rows) {
      const geometry = row.object.geometry, positions = geometry.attributes.position;
      for (const hit of row.affected) {
        const i = hit.index, a = amount * hit.weight;
        positions.array[i] = row.evaluated[i] + hit.delta.x * a;
        positions.array[i + 1] = row.evaluated[i + 1] + hit.delta.y * a;
        positions.array[i + 2] = row.evaluated[i + 2] + hit.delta.z * a;
      }
      positions.needsUpdate = true; geometry.computeVertexNormals();
      // Preserve authored shading outside the changed triangles.
      if (row.poseNormals) for (let i = 0; i < row.changedNormals.length; i++) if (!row.changedNormals[i]) {
        geometry.attributes.normal.array.set(row.poseNormals.subarray(i * 3, i * 3 + 3), i * 3);
      }
      invalidate(row.object);
    }
  }
  const hint = profile.action === 'pull' ? 'Hold and drag the fabric. Release to let it settle.' : 'Hold to press. Drag to adjust, then release.';
  return {
    source,
    descriptor: { id, label: profile.label, kind: 'surface', interaction: 'soft', action: profile.action,
      objects, min: 0, max: 1, unit: '%', axisLabel: '', axisSource: source, hint, description: hint,
      pressAmount: .18, coupled: false, selectionDepth: 100, acceptsHit, getValue: () => amount,
      pose: () => ({ origin: center?.clone() || objects[0].localToWorld(defaultCenter.clone()), axis: center ? normal.clone().multiplyScalar(profile.action === 'pull' ? 1 : -1) : null }),
    },
    begin: prepare, set,
    reset() { restore(); amount = 0; center = null; lastContact = null; },
    dispose() { restore(); for (const row of rows) if (row.originalGeometry) { const geometry = row.object.geometry; row.object.geometry = row.originalGeometry; geometry.dispose(); } },
    audit: { source, interaction: 'contact_centered_visual_deformation', meshes: objects.map(object => object.name), rigidTransformsApplied: false, skinWeightMask: Boolean(profile.bones) },
  };
}
