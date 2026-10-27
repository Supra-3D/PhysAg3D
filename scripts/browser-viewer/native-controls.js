import * as T from 'three';

// The five demo profiles use delivered MJCF scenes and parameters.json.
// Additional gallery profiles document their own source below.
// glTF uses (x,z,-y) for an MJCF (x,y,z) vector; the
// enclosing gallery group applies Rx(pi/2), as for every other source GLB.
// These are independent geometric controls, not a replacement dynamics solver.
const axis = (x, y, z) => [x, z, -y];
const hinge = (name, label, node, direction, range, options = {}) => ({
  name, label, node, axis: direction, range, type: 'hinge', unit: 'rad', reference: 0, ...options,
});
const slide = (name, label, node, direction, range, options = {}) => ({
  name, label, node, axis: direction, range, type: 'slide', unit: 'm', reference: 0, ...options,
});

// Closed-loop rear-frame limit: beyond this angle the two rigid side links
// cannot reach their rear attachment. MJCF's nominal +0.025 limit can only be
// reached by violating its compliant equality constraint.
export const LADDER_CLOSURE_MAX = 0.001278605259077129;
const PROFILES = {
  camera: [
    hinge('screen_hinge', 'Fold display', 'Screen_hinge', axis(0, 0, 1), [-0.06, 2.868261652], { reference: 0.0006716795572224155 }),
    hinge('mode_dial', 'Mode dial', 'Mode_dial_axis', axis(0, 0, 1), [-Math.PI, Math.PI], { limited: false }),
    hinge('focus_ring', 'Focus ring', 'Focus_ring_axis', axis(0, 1, 0), [-Math.PI, Math.PI], { limited: false }),
    slide('lens_extension', 'Extend lens', 'Lens_extension_axis', axis(0, 1, 0), [0, 0.012], { reference: 1.669632132581385e-6 }),
    hinge('secondary_dial', 'Secondary dial', 'Secondary_dial_axis', axis(0, 0, 1), [-Math.PI, Math.PI], { limited: false }),
    slide('shutter_press', 'Press shutter', 'Shutter_press_axis', axis(0, 0, -1), [0, 0.0013], { springReturn: true }),
  ],
  phone: [
    hinge('outer_fold', 'Outer fold', 'body_outer', axis(0, 0, -1), [0, Math.PI], { reference: Math.PI, morph: 'outer | continuous black display fold' }),
    hinge('camera_fold', 'Camera-side fold', 'body_camera', axis(0, 0, -1), [0, Math.PI], { reference: Math.PI, morph: 'camera | continuous black display fold' }),
  ],
  globe: [
    hinge('body_globe_joint', 'Rotate globe', 'body_globe', axis(0, 0.4949999887686625, 0.8688929802449921), [-Math.PI, Math.PI], { limited: false }),
  ],
  ladder: [
    hinge('front_joint', 'Front-frame tilt', 'body_front', axis(1, 0, 0), [-0.02, 0.3]),
    hinge('rear_joint', 'Fold rear frame', 'body_rear', axis(1, 0, 0), [-0.61, LADDER_CLOSURE_MAX], { coupled: true }),
  ],
  carousel: [
    hinge('carousel_bearing', 'Rotate carousel', 'Rotor', axis(0, 0, 1), [-Math.PI, Math.PI], { limited: false }),
  ],
};

// These assets have independent rigid parts even though their catalog entries
// contain no kinematics graph. Read their coordinates, not a playback clock.
function galleryProfile(item, scene) {
  const caseId = item.source?.case_id || item.id?.match(/img_\d{3}$/)?.[0];
  if (caseId === 'img_130') {
    const lid = findNode(scene, 'body_lid'), data = lid?.userData;
    if (!data?.hinge_axis_local || !data?.hinge_limits_deg) throw new Error('The laptop hinge metadata is missing.');
    return [hinge('laptop_lid', 'Open display', 'body_lid', data.hinge_axis_local,
      data.hinge_limits_deg.map(T.MathUtils.degToRad), {
        reference: T.MathUtils.degToRad(data.source_opening_estimate_deg), source: 'delivered_glb_joint_metadata',
      })];
  }
  if (caseId === 'img_123') {
    // Each delivered translation is exactly collinear with +Z; the door's
    // quaternion track is exactly about +Y. Extents are the recorded extrema,
    // not invented dynamics limits. Every drawer and door stays independent.
    return [
      ...[0.2795747817, 0.2645740062, 0.2495732456, 0.2345724851].map((travel, i) =>
        slide('cabinet_drawer_' + (i + 1), 'Pull drawer ' + (i + 1), 'body_drawer_' + (i + 1), [0, 0, 1], [0, travel], { source: 'delivered_glb_rigid_axis' })),
      hinge('cabinet_door', 'Open wardrobe door', 'body_tall_door', [0, 1, 0], [0, T.MathUtils.degToRad(59.5668984)], { source: 'delivered_glb_rigid_axis' }),
    ];
  }
  if (caseId === 'img_027') {
    // The supplied refinement is static but retains separate meshes and local
    // pivots. These authored geometric controls are not claimed as MJCF joints.
    // Limit the cover to its supplied open pose and the tonearm to the record.
    const cover = findNode(scene, 'record_player__cover_root_surface_0');
    if (!cover) throw new Error('The record player cover is missing.');
    const opening = 2 * Math.atan2(-cover.quaternion.x, cover.quaternion.w);
    const source = 'authored_from_separate_mesh_pivots';
    return [
      hinge('record_cover', 'Open cover', 'record_player__cover_root_surface_0', [-1, 0, 0], [0, opening], { reference: opening, source }),
      hinge('record_arm', 'Move tonearm', 'record_player__arm_root_surface_0', [0, -1, 0], [0, .7], { source }),
      hinge('record_disc', 'Rotate record', 'record_player__disc_root_surface_0', [0, 1, 0], [-Math.PI, Math.PI], { limited: false, source }),
      ...['front', 'rear'].map(side => hinge('record_' + side + '_knob', 'Turn ' + side + ' knob',
        'record_player__' + side + '_knob_root_surface_0', [0, 1, 0], [-Math.PI, Math.PI], { limited: false, source })),
    ];
  }
  return null;
}

// Exact planar two-link inverse kinematics from the ladder MJCF body positions
// and <connect anchor="0 0.166 0.0285">. Returned angles are relative joint
// coordinates, independent of the front frame's overall tilt.
export function solveLadderClosure(rearAngle) {
  const q = T.MathUtils.clamp(rearAngle, -0.61, LADDER_CLOSURE_MAX);
  const a = [0.177, 0.0485], b = [0.166, 0.0285];
  const c = Math.cos(q), s = Math.sin(q);
  const dy = 0.614 + c * 0.098 - s * -0.312 - 0.369;
  const dz = 1.285 + s * 0.098 + c * -0.312 - 0.896;
  const d = Math.hypot(dy, dz), l1 = Math.hypot(...a), l2 = Math.hypot(...b);
  const shoulder = Math.atan2(dz, dy) + Math.acos(T.MathUtils.clamp((l1 * l1 + d * d - l2 * l2) / (2 * l1 * d), -1, 1));
  const first = shoulder - Math.atan2(a[1], a[0]);
  const second = Math.atan2(dz - l1 * Math.sin(shoulder), dy - l1 * Math.cos(shoulder)) - Math.atan2(b[1], b[0]) - first;
  return { rear: q, first, second };
}

const findNode = (scene, name) => scene.getObjectByName(name) || scene.getObjectByName(T.PropertyBinding.sanitizeNodeName(name));
const depth = object => { let value = 0; while (object.parent) { value++; object = object.parent; } return value; };
const controlName = value => String(value).replace(/^(?:native|joint):/, '');

export function createNativeControls(item, gltf) {
  const profile = PROFILES[item.native_asset_id] || galleryProfile(item, gltf.scene);
  if (!profile) return null;
  const scene = gltf.scene;
  const controls = profile.map(({ node, axis: direction, morph, ...control }) => ({ source: 'delivered_mjcf', ...control, range: [...control.range] }));
  const values = new Map(controls.map(control => [control.name, control.reference]));
  const held = new Set(), released = new Set();
  const bindings = profile.map(control => {
    const object = findNode(scene, control.node);
    if (!object) throw new Error(`The ${item.native_asset_id || item.id} asset is missing its ${control.node} joint node.`);
    const direction = new T.Vector3(...control.axis).normalize();
    const position = object.position.clone();
    if (control.type === 'slide') position.addScaledVector(direction, -control.reference);
    const morphs = [];
    if (control.morph) {
      const fold = findNode(scene, control.morph);
      if (!fold) throw new Error(`The phone asset is missing its ${control.morph} surface.`);
      fold.traverse(part => {
        if (part.morphTargetInfluences?.length === 13) morphs.push(part);
      });
      if (!morphs.length) throw new Error('The phone fold surface does not contain the 13 delivered angle targets.');
    }
    return { control, object, direction, position, morphs };
  });
  const ladder = item.native_asset_id === 'ladder' ? ['body_left_A', 'body_left_B', 'body_right_A', 'body_right_B'].map(name => {
    const object = findNode(scene, name);
    if (!object) throw new Error(`The ladder is missing its ${name} linkage.`);
    return object;
  }) : null;

  function apply() {
    for (const binding of bindings) {
      const { control, object, direction, position, morphs } = binding;
      const value = values.get(control.name);
      object.position.copy(position);
      if (control.type === 'hinge') object.quaternion.setFromAxisAngle(direction, value);
      else object.position.addScaledVector(direction, value);
      // Each phone seam uses its own hinge angle. The original GLB has 13
      // authored shapes at 15-degree intervals, independently for both folds.
      if (morphs.length) {
        const phase = T.MathUtils.clamp(value / (Math.PI / 12), 0, 12);
        const first = Math.floor(phase), second = Math.min(12, first + 1), blend = phase - first;
        for (const mesh of morphs) {
          mesh.morphTargetInfluences.fill(0);
          mesh.morphTargetInfluences[first] = 1 - blend;
          mesh.morphTargetInfluences[second] += blend;
        }
      }
    }
    if (ladder) {
      const q = solveLadderClosure(values.get('rear_joint'));
      values.set('rear_joint', q.rear);
      for (let i = 0; i < ladder.length; i++) ladder[i].quaternion.setFromAxisAngle(new T.Vector3(1, 0, 0), i % 2 ? q.second : q.first);
    }
    scene.updateWorldMatrix(true, true);
  }

  function setValue(name, value) {
    name = controlName(name);
    const control = controls.find(row => row.name === name);
    if (!control || !Number.isFinite(value)) return false;
    values.set(name, control.limited === false ? value : T.MathUtils.clamp(value, ...control.range));
    if (control.springReturn && !held.has(name)) released.add(name);
    apply();
    return true;
  }

  function getHandles() {
    scene.updateWorldMatrix(true, true);
    return bindings.map(({ control, object, direction }) => {
      const matrix = object.parent?.matrixWorld || new T.Matrix4();
      const origin = object.position.clone().applyMatrix4(matrix);
      const description = control.springReturn
        ? 'Press along the shutter axis; release to return. Browser geometric control with a visual return spring.'
        : control.coupled
          ? 'Fold this frame; the two side stays follow their declared closed linkage.'
          : 'Drag this part along its rotation or sliding axis.';
      return {
        id: 'native:' + control.name, name: control.name, label: control.label,
        kind: control.type, min: control.range[0], max: control.range[1],
        limited: control.limited !== false, value: values.get(control.name),
        unit: control.unit, origin, axis: direction.clone().transformDirection(matrix),
        objects: [object], selectionDepth: depth(object), coupled: Boolean(control.coupled),
        axisLabel: control.type === 'hinge' ? 'Rotation axis' : 'Translation axis',
        axisSource: control.source || 'delivered_mjcf', description,
        hint: control.springReturn ? 'Drag to press; release to return.' : undefined,
        springReturn: Boolean(control.springReturn),
      };
    });
  }

  function reset() {
    held.clear(); released.clear();
    for (const control of controls) values.set(control.name, control.reference);
    apply();
  }
  function beginInteraction(id) {
    const name = controlName(id), control = controls.find(row => row.name === name);
    if (!control) return false;
    held.add(name); released.delete(name); return true;
  }
  function endInteraction(id) {
    const name = controlName(id), control = controls.find(row => row.name === name);
    if (!control) return false;
    held.delete(name);
    if (control.springReturn) released.add(name);
    return true;
  }
  function update(dt) {
    if (!released.size || !Number.isFinite(dt) || dt <= 0) return false;
    for (const name of [...released]) {
      const control = controls.find(row => row.name === name);
      const value = control.reference + (values.get(name) - control.reference) * Math.exp(-24 * Math.min(dt, 0.1));
      if (Math.abs(value - control.reference) < 1e-7) { values.set(name, control.reference); released.delete(name); }
      else values.set(name, value);
    }
    apply(); return true;
  }

  reset();
  return {
    controls, getHandles, setValue, reset, update, beginInteraction, endInteraction,
    get values() { return Object.fromEntries(values); },
    get active() { return held.size > 0 || released.size > 0; },
    source: [...new Set(controls.map(control => control.source))].join('; '),
    simulation: false,
  };
}
