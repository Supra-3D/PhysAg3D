# Validate the geometry, interaction and delivered files

Use this before final export and after a change that affects the tested behavior. Choose tests for the inferred function, rather than counting physical fields or successful commands.

## Keep several outcomes separate

| Evidence | What it establishes |
| --- | --- |
| Native job succeeded with collected hashes | A static neural candidate was generated and retrieved |
| Simulator compiled and loaded | The files and supported parameters are accepted |
| Finite dynamics, positive mass/inertia, no reported instability | Numerical behavior in the tested conditions |
| Contact, travel/return and clearance checks | Specific interactions in the measured range |
| Inspected renders of actual motion/deformation | Visible ownership, attachment and surface behavior |
| Source-matched comparison | Appearance/shape agreement from the inspected views |

None of these alone establishes full physical realism or complete sim readiness. Keep failed and unevaluated checks visible in the report.

## Rigid mechanics

Export consistent SI units, body-local meshes, transforms, joint axes/ranges, mass/inertia, friction and passive response. Identify virtual actuators used to demonstrate manipulation; a virtual motor is not evidence that the real object contains a motor. Distinguish a fixed-base demo from a freely movable asset.

Run actual simulator steps for rest, representative actuation, hold and return. Record engine/version, duration, controls, solver warnings, finite states, penetration, tracking and return errors. Check the exported visible mesh and collision proxies against the function:

- A closing lid/door covers its opening without crossing the frame or contents.
- A drawer has a real usable cavity and clears its cabinet through the tested travel.
- Buttons/keys visibly move as separate parts and return under the modeled mechanism.
- Wheels rotate about their hubs; spokes, tyres and connected supports belong to the right bodies.
- Rods and moving links remain connected at both endpoints.
- A bowl, sink or storage opening admits a suitable external probe into the physical cavity.

Inspect intermediate poses and useful combined movements, not only endpoints. Do not hide a faulty assembly by changing tolerances, weakening gravity, reducing mass or excluding contact merely to obtain a pass. If a contact exclusion is a justified mechanical approximation, state its purpose and resulting limitation.

## Visual validation

Keep the source image, untouched candidate and refined result in a comparison with matched generated-view camera, pose and illumination. Inspect neutral clay and material-preserving renders where they answer different questions. A silhouette score is not a photorealism score, and improving framing does not improve the mesh itself.

Check proportions, distinctive colors, semantic details, exposed interiors, floating debris, seams and thin structures. Describe missing detail or uncertain texture rather than silently omitting it from the comparison. Keep the original source image's lighting; do not recolor it to make a generated result appear closer.

For deformation, use the checks and recorded skin mapping in [soft assets](soft-assets.md). Every motion render must use actual simulated body transforms or deformable nodes. Label a saved trajectory as replay; only call a viewer live when its controls affect a running solver.

## Iteration and delivery

Classify a failed check before editing: geometry, body/frame ownership, solver/contact setup, skin binding, or camera/material. Fix the responsible layer and rerun affected checks. A code/format repair is not a visual refinement; if meshes did not change, do not imply that shape quality improved.

Package the final Blender file, simulator model, all referenced meshes/textures, scale/frame conventions, editable assumptions, inference/refinement provenance, and reports/trajectory or video. Load the model from the delivered package in a fresh process so missing absolute-path dependencies are found. Verify any viewer bindings against that exact package, including a non-rest pose or deforming skin.

State the passed subset and remaining failures per case. Complete a useful bounded iteration within the requested resources, and report unresolved problems honestly if further progress needs another experiment. Do not relabel a static or merely loadable fallback as a fully interactive success.
