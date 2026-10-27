# Inference operations and portable execution

The TRELLIS.2 scripts manage inference and previews. They do not implement semantic segmentation, automatic joints, Blender refinement or a universal sim-ready solver. The [API execution process](api-execution.md) authors the per-case modeling and simulation code, using the TRELLIS.2 client as a tool.

Read the active `server.json` profile, run `doctor`, and use actual paths and available GPU capacity. Profiles contain deployment paths, not credentials. For another machine, copy/configure a profile and pass `--config`; do not assume the historical SSH alias, weights or runtime paths exist there. Preserve SSH host verification and use the user's existing authentication. Do not modify installed weights or interrupt unrelated GPU jobs.

## Command templates

Resolve `SKILL_DIR`, a local Python with the client dependencies, the input image and case directory for the current environment. The placeholders below are shell variables, not literal deployment paths. `--config` is a global option placed before the subcommand.

```bash
python "$SKILL_DIR/scripts/trellis2_tool.py" --config "$PROFILE" doctor
python "$SKILL_DIR/scripts/trellis2_tool.py" --config "$PROFILE" submit \
  --route native --image "$CASE/input/source.png" \
  --resolution 1024 --steps 24 --texture-size 2048 --seed 42 \
  --receipt "$CASE/native-job.json"
python "$SKILL_DIR/scripts/trellis2_tool.py" status --receipt "$CASE/native-job.json"
python "$SKILL_DIR/scripts/trellis2_tool.py" collect \
  --receipt "$CASE/native-job.json" --out "$CASE/native-result"
python "$SKILL_DIR/scripts/trellis2_tool.py" inspect \
  --mesh "$CASE/native-result/output/candidate_yup.glb" --out "$CASE/native-inspection.json"
```

Use equivalent argument arrays/PowerShell syntax on Windows. Commands return JSON; read job state as well as the process exit code. Before relying on an unfamiliar deployed revision, inspect its `--help` and `doctor` output.

The native baseline is 1024 resolution, 24 steps, 2048 texture and seed 42 on both desktop and server. `references/inference-defaults.json` supplies these route defaults to the client; explicit CLI flags take precedence. The transport profile still supplies host paths, GPU-memory requirements and defaults for other routes. Its legacy values do not override the shared native baseline. The `texture` route is unchanged. Do not lower native quality for a deployment smoke test during an ordinary asset request. **The current native 1024 request maps to `pipeline_type="1024_cascade"`**, unlike the earlier direct-1024 run. It is the same modeling approach with a changed inference path, not a bitwise reproduction. Check `native_pipeline_type` in the terminal report. Explicit 512 selects the 512 path and must be recorded as a fallback. This switch performs no image enhancement.

`--gpu auto|INDEX` and `--min-free-gb` can select available capacity. Automatic selection is not an exclusive reservation or cluster scheduler. Use the deployment's scheduler where applicable and limit concurrent submissions to genuinely available capacity.

`--mask PATH` accepts a grayscale foreground mask matching the EXIF-oriented image; white keeps, black removes, and it multiplies existing alpha. Preserve the complete object. A mask does not protect a Blender region in 3D. `native` takes an image and rejects `--mesh`; it does not accept text prompts, structural constraints, joint annotations or a Blender mesh.

## Candidate files and frames

Collected native output includes `candidate_yup.glb`, `native_raw.npz`, `condition_processed.png` and `run.json`, plus request/worker records and collection hashes. The GLB is Y-up and needs inferred metric registration. The raw NPZ remains in the pipeline's internal frame; do not apply the GLB transform to it without checking the exporter convention.

Inspect the processed condition and material-preserving renders of the actual candidate. The preview helper can produce generic views in a disposable Blender process:

```bash
blender --background --python "$SKILL_DIR/scripts/render_preview.py" -- \
  --mesh "$CASE/native-result/output/candidate_yup.glb" --out "$CASE/native-views"
```

The helper clears its process's scene. Its generic views do not recover the source camera. `inspect` analyzes the indexed render mesh; UV seams can duplicate vertices and create apparent component/boundary counts. Diagnose a separately welded physical mesh with a documented tolerance before repairing all such boundaries.

If a later refinement needs only material generation, `texture` accepts a staged UV mesh NPZ in Y-up metres with `vertices: N x 3`, `faces: F x 3`, `uv: N x 2`. UV seams must already be split appropriately. Read the actual tool help and preservation gate before use. The texture route preserves geometry/UV and cannot add shape; its numeric resolution is separate from native cascade selection. Maintain any body ownership and soft binding separately.

## Recovery without duplicate inference

- Preserve the receipt before submission. A matching existing receipt refers to the same request; changed input/settings need a new receipt.
- After transport loss, query the same receipt and inspect status/process evidence. `starting`, `running`, `preparing_unknown` and `interrupted_unknown` are not success or permission to duplicate work.
- Terminal `succeeded` establishes static candidate generation, not simulation readiness. Terminal `failed` can still be collected for diagnostics.
- For a justified retry, use a new receipt with `--retry-of` pointing to the previous receipt and record the reason. Do not assume that an SSH timeout means CUDA failure.
- After a terminal OOM, wait for suitable capacity or use a documented 512 fallback. Import/path errors require diagnosis of the exact environment, not blind reinstallations or repeated model calls.
- A poor visual candidate calls for inspection and Blender refinement first. Another seed is a purposeful additional experiment with a stated limit, not an automatic retry loop.

Existing jobs retain their submitted runner; updating the installed script does not change those jobs. Preserve the actual runner/config fingerprints. A directory name resembling a commit hash is not proof of its Git revision.
