# Soft assets and deforming visual surfaces

Use this when the image depicts a soft object or a rigid object with soft regions. Whole-object native generation can provide the detailed rest surface and PBR, but it does not provide a deformable volume, material constants, attachments or a simulator skin binding.

## Choose a physical interpretation

Infer the representation from the requested interaction and visible structure. A cushion may be an equivalent elastic volume for a press/recovery experiment; a hanging fabric sheet is a shell; a cable is a rod or a chain with bend/stretch response. For a padded rigid object, separate the frame and compliant regions. Do not automatically turn every soft-looking mesh into a tetrahedral solid.

Record the chosen approximation and editable parameters with units: mass/density, material model and its supported elastic parameters, damping, thickness or cross-section, contact settings, and fixed or moving attachments. A single image does not determine these values. An equivalent cushion model does not resolve fabric, stuffing, seams, airflow or plastic deformation unless those mechanisms are actually implemented.

Inspect the installed simulator/version and use its supported facilities. Blender cloth or soft-body modifiers are not automatically translated into MuJoCo flex, material or attachment definitions.

## Construct the simulation mesh and bind the candidate

Keep detailed render geometry separate from the physical discretization. For a volumetric model, create a closed physical boundary and positive-volume tetrahedra appropriate to the chosen solver. Fix inverted or degenerate rest elements. For a shell, preserve the intended open boundaries and thickness; closing it solely to satisfy a volume mesher can change its physics.

Map the detailed rest surface to the simulation representation explicitly, preserving texture coordinates and semantic ownership. A tetrahedral embedding should reconstruct the rest surface accurately and place vertices inside their assigned elements within a scale-aware numerical tolerance. Diagnose the minimum weight, outside-vertex count, weight sums and maximum reconstruction error. Significant negative barycentric weights are extrapolation, even when reconstruction error is almost zero; expand/refine the volume or choose a suitable surface binding instead of silently declaring that mapping valid.

Do not clamp invalid weights without measuring the resulting shape change. If an alternative binding uses offsets from the physical surface, preserve and update those offsets consistently under deformation and check for inversions or detached detail. Remeshing requires rebinding. Moving rigid attachments require both rest-frame and deformed-frame checks.

The visual geometry in MuJoCo, Blender playback and any custom viewer must derive from the same simulated state and the recorded binding. A high-resolution rest mesh displayed over an invisible moving flex is still a static asset. A separately animated squash shape does not demonstrate physical skinning.

## Demonstrate contact-driven deformation

For a cushion/pillow test, place an external collider above the visible surface, let the object settle, press through actual contact, hold, withdraw the collider, and simulate recovery. A controlled indenter may be kinematic; the cushion displacement must come from the solver. Do not impose the cushion's target vertices or precomputed deformation as the test result.

Record the indenter trajectory, contact evidence, compression relative to the settled baseline, recovery error, nodal and visible-surface displacement, minimum signed element-volume ratio or the corresponding shell quality measure, penetration and solver warnings. Inspect the rendered rest, maximum-compression and recovered states, including seams and attachment regions.

Avoid treating finite positions or a single compressing node as proof of good deformation. Check that the visible contact patch actually indents, detail follows the physical surface, and the object returns without permanent numerical distortion when the selected material is elastic. Use a duration and tolerances appropriate to the object and intended demonstration. Preserve failures; modest compression does not validate large deformation, tearing or every possible contact.

Deliver the simulator definition, physical mesh, binding arrays and a runnable way to update the visible skin. The static GLB and Blender rest model alone are not a portable deformable asset.
