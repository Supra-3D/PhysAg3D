# From a neural surface to an editable assembly

Use this during observation, candidate inspection and Blender refinement. The reference laptop example demonstrated this workflow on one image; it does not establish a universally reliable segmentation, joint prediction or material recovery algorithm.

## Preserve useful evidence

Keep a case-local plan with the input identity, inferred scale, world/up/front convention, reference camera, semantic bodies, proposed interactions and unknowns. Use existing project formats when available. For a batch, verify the input inventory against the user's request before assigning case names; do not substitute a remembered case list for the actual images.

Save the original image unchanged. A foreground mask or alpha cleanup may be useful, but inspect what the model actually receives, particularly thin spokes, handles, cords, glass and dark surfaces. Record any derivative image and its relationship to the source. This workflow does not perform image enhancement.

Keep the scaffold, raw candidate and refined asset as separate stages. Preserve actual neural provenance when a candidate is adopted, rejected or only partly reused. Reusing a previous candidate is a reuse experiment, not a new inference call.

## Register the candidate

TRELLIS.2 produces normalized geometry without recovered metric scale, joint frames or semantic boundaries. Fit orientation, scale, translation and the reference camera using visible landmarks and silhouette. Record the candidate-to-asset transform; keep source and body transforms distinct. Blender's GLB importer may already convert Y-up to Z-up, so inspect transforms before applying another axis conversion.

Use the scaffold's mechanical relationships to disambiguate pose and proportions. For example, a lid must cover its opening, a wheel axle must reach the hub, and a drawer must fit a cavity. These are modeling constraints, not evidence that the inferred dimensions are measured. If a nonlinear surface deformation changes a mechanical surface, update the affected clearance and collision geometry.

## Refine the defects that are actually visible

| Defect | Useful Blender work | Check after the edit |
| --- | --- | --- |
| Wavy housing, wrong thickness or bowed panel | Lattice/surface deformation, local mesh editing, constrained remeshing or replacement surface | Source silhouette, edge profile, thickness and mating surfaces |
| Fused keyboard, door, lever or wheel | Semantic face assignment plus boundary reconstruction, inner surfaces and separate body frames | No fragments follow the wrong body; both sides remain complete through motion |
| Missing cavity or opening | Boolean subtraction or modeled shell/inner liner, with practical wall thickness | Visible opening and collision cavity both remain usable |
| Tubes, handles, support bars or sealing edges | Curve sweeps with appropriate profiles, bend radius and junctions | Both endpoints connect throughout motion, without self-intersection |
| Molded keys, gaskets, rims or tapered features | Profile lofts, bevels and local surface construction | Profile, spacing and contact clearance agree with the inferred function |
| Folded textile or irregular surface | Preserve useful native geometry; repair holes selectively; use a separate physical representation | Surface continuity, UV quality and deformation binding |
| Blotchy color, wrong semantic color zone or broken seams | Material reassignment, local repaint/projection, UV repair or controlled texture transfer | Matched-light comparison; no baked highlight mistaken for a material property |

Choose operations for the defect; executing every listed operation is not a quality metric. Simple geometry is appropriate for unseen structure or a collision proxy, but visible broad curved surfaces and thin structures need shapes that match their evidence.

## Semantic ownership is more than a coordinate cut

Spatial thresholds and connected components may initialize selections. Inspect each resulting region and repair its boundaries. Assign every retained visible fragment to its intended rigid body or deformable skin. Account for surfaces revealed by opening or rotating a part. After any split, maintain UVs/material slots where valid and rebuild exposed undersides or seams where necessary.

For mechanisms with linked rods, hoses or braces, define how both endpoints remain attached. Parenting a complete rod to one moving link generally does not maintain its other endpoint. Use a supported constraint, computed linkage geometry driven by actual solver state, or explicitly simplify and report that mechanism; detached fragments are not a successful articulation.

Contact geometry should represent functional openings and accessible surfaces. A single convex hull of a hollow cabinet, bowl or frame can fill its useful space. Build compound shell proxies or suitable decomposition rather than letting an attractive visual mesh conceal a solid collision block.

## Keep appearance work coupled to observation

Compare source-matched renders before and after a meaningful edit. Check camera and illumination before painting over an exposure error. Use neutral clay renders to isolate shape and material-preserving renders to assess color and texture. Orthographic versus perspective mismatch can dominate silhouette error.

TRELLIS.2's PBR is a useful appearance hypothesis, not measured reflectance. Preserve distinctive visible colors and details where supported; avoid inventing unreadable text as if recovered. If generated appearance lost information, Blender can rebuild geometry or use justified image projection on known surfaces, but uncertain backsides remain inferred.

A fresh native candidate or controlled texture call can help a diagnosed deficiency. Prefer one well-inspected baseline, then a purposeful revision. Record the stopping condition for additional inference before issuing retries; do not run an unbounded seed search because a draft looks poor.
