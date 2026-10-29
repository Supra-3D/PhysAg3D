import { LOCAL_SOFT_PROFILES, MORPH_SOFT_PROFILES, SKIN_SOFT_PROFILES, surfaceAction } from './soft-profiles.js';
import { createContactControl } from './contact-deformation.js';

export function createSoftControls(item, gltf) {
  const controls = [], local = LOCAL_SOFT_PROFILES[item.id], morph = MORPH_SOFT_PROFILES[item.id], skin = SKIN_SOFT_PROFILES[item.id];
  if (local) {
    const objects = local.meshes.map(name => gltf.scene.getObjectByName(name)).filter(object => object?.isMesh);
    if (objects.length === local.meshes.length) controls.push(createContactControl('soft:cushion', local, objects, local.source));
  }
  if (morph) {
    const objects = [];
    gltf.scene.traverse(object => { if (object.isMesh && object.geometry.morphAttributes.position?.length) objects.push(object); });
    objects.forEach((object, index) => {
      const profile = /strap/i.test(object.name) ? { ...morph, label: 'Pull strap', action: 'pull' } : morph;
      controls.push(createContactControl('soft:morph:' + index, profile, [object], 'original_morph_shapes'));
    });
  }
  if (skin) {
    const objects = [];
    gltf.scene.traverse(object => { if (object.isSkinnedMesh && skin.mesh.test(object.name)) objects.push(object); });
    if (objects.length) controls.push(createContactControl('soft:skin', skin, objects, 'original_skinned_shapes'));
  }
  return controls;
}

export function createRecordedSoftControls(skinBindings, trajectory) {
  if (!trajectory || !skinBindings.length) return [];
  return skinBindings.flatMap((binding, index) => trajectory.states[0].flex?.[binding.flex]
    ? [createContactControl('soft:recorded:' + index, { label: 'Press cushion', action: 'press' }, [binding.object], 'original_recorded_skin')]
    : []);
}

export function createAuthoredSoftControls(bindings) {
  return [...new Set(bindings.map(binding => binding.region))].map(region =>
    createContactControl('surface:' + region, surfaceAction(region), [...new Set(bindings.filter(binding => binding.region === region).map(binding => binding.object))], 'authored_vertex_deltas'));
}
