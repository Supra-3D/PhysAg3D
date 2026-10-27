---
name: trellis2-native-refine
description: Generate a single-image interactive asset using whole-object TRELLIS.2 geometry and PBR, then Blender refinement, semantic part reconstruction and physical validation. Use for an explicit single-image native-generation-then-refinement workflow; trellis2-assets is the separate Blender-primary route.
---

# Whole-object generation, Blender refinement and interaction

## GPT execution for new asset runs

The user requests API-key execution for GPT-6 asset reasoning. Before starting a new generation, read [API execution](references/api-execution.md) and use `scripts/run_api.py`; it attaches the image and runs this full workflow under the configured API key. The desktop conversation only launches/reports the run; it does not substitute its own modeling decisions or code. Once already inside the API runner, execute the workflow below directly, without recursively launching it. Missing API access must not silently fall back to subscription execution. This change does not restart or convert existing runs, and does not affect ordinary questions about assets.

API authentication does not change the modeling route, Blender tool choices, autonomous repair loop or acceptance criteria below. Do not introduce deployment-test quality reductions into normal asset runs.

## Modeling route

Turn one object image into an editable, physically testable asset. GPT observes the image, directs the modeling and evaluates results; TRELLIS.2 supplies a whole-object static candidate; Blender reshapes and reconstructs that candidate into an assembly. The user normally supplies only an image. Infer editable category priors rather than requesting a detailed parameter questionnaire.

This skill deliberately permits the main visible surfaces to come from TRELLIS.2. There is no required Blender/neural face ratio. Blender remains responsible for the final part boundaries, mechanical fit, physical regions and integration. Retaining many neural triangles does not establish fidelity, and merely importing or slicing a candidate does not complete this workflow.

## Execute the full refinement loop

1. **Observe and plan.** Inspect the actual input. Record visible parts, material cues, intended interactions, approximate scale, unknown hidden structures and a reference camera hypothesis. Keep inferred dimensions and physics editable, with units and rationale. Do not read the source asset's 3D model or physical annotations in a single-image test.
2. **Build a provisional Blender scaffold.** Save an adjustable blockout and meaningful closure, cavity, attachment or joint constraints before neural inference. The scaffold establishes a structural hypothesis; its surfaces need not be retained. Check that its proposed interaction is geometrically plausible.
3. **Generate a whole-object candidate.** Submit the original image through `native` with the shared baseline `--resolution 1024 --steps 24 --texture-size 2048 --seed 42`; 1024 selects `1024_cascade`. The same native defaults are applied by the client from `references/inference-defaults.json` when flags are omitted. Do not upscale or enhance the image. Preserve input hashes, preprocessing, settings, receipt, logs and raw candidate. Read [operations](references/operations.md) before the first inference call. A documented 512 fallback is allowed for a concrete execution limitation, not an unreported substitution.
4. **Inspect before editing.** Render the candidate from the source view and informative other views. Check silhouette, fused parts, filled cavities, missing thin members, material/UV artifacts and the visibility of surfaces needed during motion. Keep this inspection and the untouched candidate available for comparison.
5. **Refine in Blender.** Register the candidate to the editable scaffold, then repair proportions, separate semantic parts, restore functional openings and thickness, build hidden moving surfaces, and correct materials. Use curve lofts, sweeps, Booleans, surface deformation and local mesh editing wherever useful. Read [workflow](references/workflow.md) for defect-driven choices. Revise the scaffold if image evidence warrants it; do not force a mechanism to fit an accidental neural shape.
6. **Construct and test physics.** Export body-local visual geometry separately from collision geometry, define actual mechanics and simulate representative interactions. For deformable parts read [soft assets](references/soft-assets.md) before choosing the physical mesh and skin binding. Read [validation](references/validation.md) before final export and verification.
7. **Use the evidence to iterate.** Compare input, raw native candidate and refined asset under matched camera/lighting. Inspect actual simulated poses for detached pieces, bad closure, penetration and visible deformation. Fix the concrete failure in geometry, assembly, physics or rendering; re-export and rerun affected checks. Do not stop at a successful GLB export or MJCF load.

The API-authenticated execution process authors and runs case-specific Blender and simulator code, with TRELLIS.2 as a tool. A laptop script is an example of case-specific modeling, not a general segmentation or articulation algorithm.

## Deliver an inspectable result

Keep the original input, editable scaffold, untouched neural candidate, final Blender asset, simulator file with all dependencies, editable physical assumptions, refinement decisions and validation evidence. Include a source-view comparison and representative motion/deformation results. Separate `candidate_generated`, `simulator_loaded`, `interaction_tested` and the actual passed/failed checks.

State what was adopted from TRELLIS.2, what Blender rebuilt, and which behaviors remain unsupported or failed. A static GLB does not carry MuJoCo physics; a recorded animation is not a live simulator. Do not label unmeasured physical values as recovered truth, or describe an unfinished prototype as a fully validated sim-ready asset.
