# Authorized asset construction task

Generate and DELIVER the single-image interactive asset in the supplied case directory. This is a new single-image run of the **8769 whole-object native then Blender refinement** method. The execution follows the assisted 8769 subscription route already used for the appearance20 batch. This is an explicitly assisted experiment, `strict_isolation=false`; do not claim independent inference or a strictly isolated guest. Work autonomously through delivery, not just a plan.

## Authority and scope

- Use the frozen `trellis2-native-refine/SKILL.md` modeling route and its workflow/operations/validation references. For this separately labelled assisted run, the parent controller uses the local Codex ChatGPT subscription route already used by the 8769 appearance20 batch. This is a run configuration, not a claim that the user explicitly requested a particular billing method. You are the asset reasoning process for this case; do not launch `run_api.py`, read credential files, invoke another GPT API, or recursively spawn another LLM/agent. The copied skill's API-execution adapter is not used in this run; its modeling, Blender refinement and validation requirements still apply.
- Your only object observation is the attached `input/source.png`. Read `runtime.json` for runtime locations. All physical dimensions, materials and hidden geometry are editable estimates, not recovered ground truth. Do not browse source dataset models, annotation corpora, other image views, historical case outputs, workspace conversations, memories or sibling run outputs. Name/category metadata are identification, not physics truth.
- `method/assisted_reference_code` contains explicitly declared historical CODE ONLY. You may read and adapt its general Blender segmentation/material retention/body-local export/MuJoCo/render techniques. Do not run the archived scripts in place: they contain hardcoded old paths/face masks. Derive the new object's geometry, masks and pivots from its image and fresh candidate. Record which reference algorithms you adopted. No old meshes, states, renders or case solutions may replace this new output.
- Write only inside your own case directory; treat method/runtime files as read-only. Use the declared SSH/TRELLIS deployment and the separate per-run jobs root in `method/server.json`. Always pass `runtime.json`'s `profile` value via the native client's `--config`; never rely on the copied skill's historical default profile. Never interrupt unrelated GPU jobs, modify installed weights/skills, start other batches, or change the controller. Shell commands must respect actual approval/sandbox decisions. If execution is denied, record the precise blocker and retain outputs; never bypass protection or mislabel a denial as modeling failure.

## Fixed execution and quality policy

1. Inspect the attached source. Record observed parts, seams, material/texture cues, plausible interactions, scale/physics assumptions and source-camera hypothesis in `asset_plan.json`.
2. Create and save `scaffold.blend` via Blender with meaningful approximate moving parts, attachment/closure/thickness constraints BEFORE native submission. Provisional scaffold surfaces are not the final visible object.
3. Call the frozen native client using the explicit runtime profile and parameters: `--route native --resolution 1024 --steps 24 --texture-size 2048 --seed 42 --gpu <runtime.gpu>`. Input is the original image unchanged. Save `native-job.json` and collect to `native-result`. Check existing receipt/status before any retry; transport loss is not permission to duplicate inference. A poor candidate should first be inspected/refined, not replaced with a white blockout. Do not downgrade resolution for speed. No old native candidate may be reused.
4. Inspect and render the actual untouched `native-result/output/candidate_yup.glb`, its condition image and multiple views. Do not confuse raw/GLB/Blender frames. Save native renders and observations. Retain native PBR textures and useful fine surface details.
5. Build the detailed Blender assembly: infer semantic surface ownership, correct pivots and connected body hierarchy; repair only necessary gaps/thickness/hidden moving surfaces. Avoid broad remeshing or replacing the detailed textured object with primitives. Preserve observed colors, material identity and useful surface details rather than indiscriminately increasing metallicness or gloss. A visible native surface MUST actually be bound to and move with its actuator or deformation field. A moving invisible scaffold behind a static native shell is a failure. Verify against real rendered states. Object orbit/turntable alone is not an interaction.
6. Construct actual physical mechanics and tests with the local external Python's MuJoCo (not Blender embedded Python). Store body-local visual/collision meshes, MJCF dependencies, units, masses/inertias/friction/limits/compliance assumptions. For soft materials read `references/soft-assets.md`; do not force every object into a rigid-only pipeline. Use real soft loading and surface binding where warranted; if impossible within budget, report that exact missing behavior.
7. Bounded review: at most TWO physics/visual acceptance passes, and at most TWO repair rounds. Fix concrete errors, retain prior candidates, stop acceptance-driven repair after the limit. Choose the best visually faithful, functional candidate and deliver it even if physics fails. A simulator trajectory is optional on failure. If animation is kinematic/parameterized instead of simulated, label it `kinematic_parameter_animation` everywhere; never call it physics-passed or live simulation. No fabricated trajectories, measurements, QA screenshots or passed checks.
8. Deliver the interactive page and a real rendered motion video. Prefer recorded simulator-driven states when available. Otherwise export an honest GLB animation showing actual part/soft-surface motion, not just camera motion. Native preservation plus functional motion are required for claiming an interactive result. Show input/native/refined comparison, auto-play, pause/scrub controls and camera orbit. All assets should load locally without external CDN dependencies.

## Practical delivery tools (optional generic infrastructure)

- Local Python includes numpy, scipy, trimesh, PIL, mujoco, imageio and imageio_ffmpeg. Query `imageio_ffmpeg.get_ffmpeg_exe()` for video encoding (ffmpeg is not on PATH). Blender is 5.2.1: inspect current RNA/export options instead of assuming deprecated 4.x properties. Use separate Blender processes, `--background --threads 4 --python ...`. Save authoring scripts and .blend. Limit CPU render concurrency; for an informative video 240 frames at 24 fps, 768–960 px is sufficient, but not a mandatory quality downgrade. Use physically readable studio light and material-rendered frames; workbench/white clay is not the final appearance video.
- The frozen `delivery_tools/make_viewer.py CASE_DIR` builds a local Three.js page from `delivery.json` and an ANIMATED GLB. It does not generate geometry or interactions. The page automatically plays embedded clips sequentially, supports clip selection and scrubbing. Export actual moving nodes/morph targets in GLB (multiple named clips or one combined demonstration are supported). Ensure animation tracks exist and bind to rendered meshes. Copying static GLB and calling this packager does not create interaction.
- A custom page is allowed if soft binding/replay needs it. Keep dependencies inside `presentation/`. Do not bake massive base64 assets into HTML. Video must be a nonempty readable MP4 with real visible motion and material appearance. Inspect at least start/middle/end output frames. Camera and lights should allow comparison across states.

## Artifact contract

Update `progress.json` after each meaningful stage with `stage`, `message`, `updated_at`, and errors if any. Preserve code, source image, raw native, Blender asset, simulator dependencies, renders, video and tests.

On completion write `delivery.json` (relative paths inside CASE_DIR):
```
{
  "title": "descriptive object name",
  "status": "delivered_with_limitations",
  "input": "input/source.png",
  "model": "asset/refined.glb",
  "blend": "asset/refined.blend",
  "simulator": "physics/scene.xml",
  "video": "media/motion.mp4",
  "native_render": "renders/native.png",
  "refined_render": "renders/refined.png",
  "page": "presentation/index.html",
  "motion_kind": "simulated_replay OR kinematic_parameter_animation OR static_only",
  "interaction_status": "bound_motion_verified OR partial OR static_only",
  "physics_status": "passed OR failed OR partial OR not_tested",
  "physics_report": "physics/report.json",
  "visible_motion_evidence": ["renders/motion_start.png", "renders/motion_mid.png"],
  "native_preservation_evidence": "native_preservation.json",
  "repair_rounds": 0,
  "acceptance_passes": 0,
  "limitations": ["actual limitations, no invented successes"],
  "reference_code_used": ["declared historical code paths and adapted techniques"]
}
```
Use actual values; null for unavailable paths. `status` may be `delivered`, `delivered_with_limitations`, `native_only`, `blocked`, `failed`. `blocked` must include `blocker` and precise reason. Do not make `delivery.json` terminal until files are written and verified. If there is an execution blocker or budget exhaustion, deliver best available partial files explicitly, not a success record. A valid source image or static native preview is not a finished interactive asset.

Aim to finish this one case within the assigned active-time budget (see runtime.json), reserving time for video, preview and honest validation. Model-capacity errors are retried by the controller with your own session/intermediate outputs; they are not grounds to discard work or start unrelated cases.
