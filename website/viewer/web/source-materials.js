import { GLTFLoader } from './vendor/GLTFLoader.js';

const materialKey = (name) => name.toLowerCase().replace(/[^a-z0-9]/g, '');

// Let the bundled glTF loader interpret the complete material, including its
// extensions, texture color spaces, samplers and UV transforms. The source
// meshes/animations are discarded: MuJoCo still supplies geometry and motion.
export async function loadSourceMaterials(bytes) {
  const gltf = await new GLTFLoader().parseAsync(bytes, '');
  const definitions = await gltf.parser.getDependencies('material');
  const materials = definitions.slice();
  const textures = new Set(), geometries = new Set(), sceneMaterials = new Set();
  const byName = new Map();
  gltf.scenes.forEach((scene) => scene.traverse((object) => {
    if (object.geometry) geometries.add(object.geometry);
    if (object.material) (Array.isArray(object.material) ? object.material : [object.material]).forEach((m) => {
      sceneMaterials.add(m);
      // Use GLTFLoader's finalized material, including its derivative-tangent
      // normal-map convention. These native meshes, like their source meshes,
      // provide normals and UVs but no explicit tangents or vertex colors.
      const index = gltf.parser.associations.get(m)?.materials;
      if (Number.isInteger(index)) materials[index] = m;
    });
  }));
  materials.forEach((material, index) => {
    byName.set(materialKey(gltf.parser.json.materials[index].name || ''), material);
    Object.values(material).forEach((value) => { if (value?.isTexture) textures.add(value); });
  });
  geometries.forEach((geometry) => geometry.dispose());
  new Set([...definitions, ...sceneMaterials]).forEach((material) => { if (!materials.includes(material)) material.dispose(); });
  return {
    materials, textures: [...textures],
    get(name, index) { return Number.isInteger(index) ? materials[index] : byName.get(materialKey(name || '')); },
    dispose() {
      materials.forEach((material) => material.dispose());
      textures.forEach((texture) => texture.dispose());
    },
  };
}
