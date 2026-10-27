// UI-only profiles. Original GLB, recorded states, and authored deltas stay intact.
// This allowlist identifies delivered soft meshes; it never infers softness from
// metallicFactor (the lounge upholstery and steel share the same PBR material).
export const LOCAL_SOFT_PROFILES = {
  'studio-img_001': {
    label: 'Press cushion', action: 'press',
    meshes: ['upholstery_skin_surface_0'],
    excludedMeshes: ['support_native_surface_0', 'upholstery_underside_closure'],
    radius: 0.20, depth: 0.036,
    // glTF coordinates, on the middle of the seat; real hits replace this point.
    center: [0, 0.44, 0.18], normal: [0, 1, 0],
    source: 'browser_local_visual_deformation',
  },
};

export const MORPH_SOFT_PROFILES = {
  'studio-img_009': { label: 'Press cushion', action: 'press' },
  'studio-img_019': { label: 'Press cushion', action: 'press' },
  'extra-img_097': { label: 'Press cushion', action: 'press' },
  'extra-img_102': { label: 'Press mattress', action: 'press' },
  'extra-img_103': { label: 'Press slippers', action: 'press' },
  'extra-img_104': { label: 'Press pillow', action: 'press' },
  'extra-img_117': { label: 'Press drumhead', action: 'press' },
  'extra-img_127': { label: 'Press cushion', action: 'press' },
  'extra-img_176': { label: 'Press mattress', action: 'press' },
  'extra-img_179': { label: 'Press fabric seat', action: 'press' },
  'extra-img_189': { label: 'Pull fabric', action: 'pull' },
  'extra-img_194': { label: 'Press padding', action: 'press' },
  'extra-img_231': { label: 'Press cushion', action: 'press', split: true },
  'extra-img_233': { label: 'Pull strap', action: 'pull' },
  'extra-img_247': { label: 'Press cushion', action: 'press' },
};

// Only skeletons bound to these visible soft parts are interpolated. Rigid
// animation channels, tool/probe transforms, and other scene nodes are untouched.
export const SKIN_SOFT_PROFILES = {
  'extra-img_086': { label: 'Press woven seat', action: 'press', mesh: /woven_seat/i },
  'extra-img_093': { label: 'Bend hose', action: 'pull', mesh: /hose/i },
  'extra-img_096': { label: 'Press bedding', action: 'press', mesh: /upholstery_and_bedding/i },
  'extra-img_100': { label: 'Press pillow', action: 'press', mesh: /pillow/i },
  'extra-img_101': { label: 'Press cushion', action: 'press', mesh: /seat.cushion/i },
  'extra-img_111': { label: 'Pull fabric', action: 'pull', mesh: /puffer_outer_surface|seam_gap_backing/i },
  'extra-img_114': { label: 'Press cushion', action: 'press', mesh: /upholstery/i },
  'extra-img_119': { label: 'Pull blanket', action: 'pull', mesh: /blanket/i },
  'extra-img_122': { label: 'Pull curtains', action: 'pull', mesh: /curtain/i },
  'extra-img_124': { label: 'Press cushion', action: 'press', mesh: /cushion/i },
  'extra-img_125': { label: 'Press padding', action: 'press', mesh: /chaise_surface/i },
  'extra-img_132': { label: 'Press lining', action: 'press', mesh: /bound_padding/i },
  'extra-img_153': { label: 'Pull canopy', action: 'pull', mesh: /canopy/i },
  'extra-img_173': { label: 'Pull canopy', action: 'pull', mesh: /canopy_textile|roof_gap_backing|roof_inner_liner/i },
  'extra-img_187': { label: 'Press fabric seat', action: 'press', mesh: /deforming_sling/i },
  'extra-img_190': { label: 'Pull fabric', action: 'pull', mesh: /textile/i },
  'extra-img_191': { label: 'Pull cord', action: 'pull', mesh: /cord/i },
  'extra-img_202': { label: 'Press flexible wall', action: 'press', mesh: /soft_wall|wall_liner/i },
  'extra-img_223': { label: 'Pull pleats', action: 'pull', mesh: /gussets_and_dividers/i },
  'extra-img_232': { label: 'Pull net', action: 'pull', mesh: /native_net/i },
  'extra-img_239': { label: 'Press flexible wall', action: 'press', mesh: /bellows/i },
};

export function surfaceAction(name) {
  if (/fabric|ribbon|cloth|cable|cord/i.test(name)) return { label: /cable|cord/i.test(name) ? 'Bend cable' : 'Pull fabric', action: 'pull' };
  if (/tire|tread/i.test(name)) return { label: 'Press tire', action: 'press' };
  if (/seal/i.test(name)) return { label: 'Press seal', action: 'press' };
  if (/grip/i.test(name)) return { label: 'Press grip', action: 'press' };
  if (/cover/i.test(name)) return { label: 'Press cover', action: 'press' };
  return { label: 'Press cushion', action: 'press' };
}
