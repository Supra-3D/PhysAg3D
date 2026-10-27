"""Native image-to-3D or geometry-locked texturing adapter for the local skill.

This adapter never edits the installed TRELLIS.2 checkout or model config.
Mesh inputs and GLB outputs are Y-up. Physics packages remain Z-up metres.
"""
from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import os
from pathlib import Path
import sys
import time
import traceback

PIPELINE_CACHE = {}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--route", choices=["texture", "native"], required=True)
    ap.add_argument("--input", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--runtime", type=Path, required=True)
    ap.add_argument("--model", type=Path, required=True)
    ap.add_argument("--dino", type=Path, required=True)
    ap.add_argument("--rembg", default="ZhengPeng7/BiRefNet")
    ap.add_argument("--gpu", default="1")
    ap.add_argument("--resolution", type=int, choices=[512, 1024], default=512)
    ap.add_argument("--texture-size", type=int, default=1024)
    ap.add_argument("--steps", type=int, default=12)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--min-free-gb", type=float, default=28)
    ap.add_argument("--retry-of", default=None)
    args = ap.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    report = {"schema": "trellis2-skill-candidate-v1", "status": "running", "route": args.route,
              "args": {k: str(v) if isinstance(v, Path) else v for k, v in vars(args).items()},
              "fully_compiled_simulation_asset": False}
    report["runner_sha256"] = sha(__file__)
    (args.output / "runner_source.py").write_bytes(Path(__file__).read_bytes())
    mesh_input = args.input / "mesh_yup.npz"
    report["input_mesh_sha256"] = sha(mesh_input) if args.route == "texture" else None
    report["model_reused_within_process"] = False
    report["compatibility_adapter"] = (
        "preserve input UV; copy vertex normals before upstream in-place rotation"
        if args.route == "texture" else None)
    inference_started = None
    started = time.perf_counter()
    try:
        print(f"Starting {args.route}: {args.input}; output={args.output}", flush=True)
        os.environ["CUDA_VISIBLE_DEVICES"] = args.gpu
        os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")
        os.environ.setdefault("OPENCV_IO_ENABLE_OPENEXR", "1")
        os.environ.setdefault("ATTN_BACKEND", "flash_attn")
        sys.path.insert(0, str(args.runtime))
        import numpy as np
        import torch
        import trimesh
        from PIL import Image
        from trellis2.pipelines import Trellis2ImageTo3DPipeline, Trellis2TexturingPipeline
        free, total = torch.cuda.mem_get_info()
        report.update(device=torch.cuda.get_device_name(0), torch_version=torch.__version__,
                      free_memory_bytes_at_launch=free, total_memory_bytes=total)
        if free < args.min_free_gb * 1024 ** 3:
            raise RuntimeError("Insufficient free GPU memory; other jobs are not interrupted")
        # Make a run-local config pointing to existing weight files. Never edit vendor data.
        config_name = "texturing_pipeline.json" if args.route == "texture" else "pipeline.json"
        config = json.loads((args.model / config_name).read_text())
        for key, value in config["args"]["models"].items():
            config["args"]["models"][key] = str(args.model / value)
        config["args"]["image_cond_model"]["args"]["model_name"] = str(args.dino)
        config["args"]["rembg_model"]["args"]["model_name"] = args.rembg
        write_json(args.output / "pipeline.json", config)
        source = args.input / "source_image.png"
        report["source_sha256"] = sha(source)
        report["runtime_source_hashes"] = {
            name: sha(args.runtime / "trellis2" / "pipelines" / name)
            for name in ["base.py", "trellis2_texturing.py", "trellis2_image_to_3d.py"]}
        report["original_config_sha256"] = sha(args.model / config_name)
        report["effective_config_sha256"] = sha(args.output / "pipeline.json")
        report["weight_files"] = {key: {
            "prefix": value,
            "safetensors_bytes": Path(value + ".safetensors").stat().st_size,
            "config_sha256": sha(value + ".json")
        } for key, value in config["args"]["models"].items()}
        image = Image.open(source)
        t = time.perf_counter()
        cache_key = (args.route, str(args.model.resolve()), str(args.dino.resolve()), args.rembg)
        if cache_key in PIPELINE_CACHE:
            pipeline = PIPELINE_CACHE[cache_key]
            report["model_reused_within_process"] = True
        elif args.route == "texture":
            class WritableNormalMesh(trimesh.Trimesh):
                @property
                def vertex_normals(self):
                    # Upstream postprocess rotates normals in place; trimesh may
                    # expose a read-only cache. A private copy changes no normal.
                    return super().vertex_normals.copy()

            class PreserveUVTexturing(Trellis2TexturingPipeline):
                def preprocess_mesh(self, mesh):
                    normalized = super().preprocess_mesh(mesh)
                    # The pinned upstream method otherwise drops input UVs. Reuse them
                    # when present, preserving soft-skin texcoords without rewrapping.
                    uv = getattr(mesh.visual, "uv", None)
                    if uv is not None:
                        normalized.visual = trimesh.visual.TextureVisuals(uv=np.asarray(uv).copy())
                    return normalized

                def postprocess_mesh(self, mesh, pbr_voxel, resolution=1024, texture_size=1024):
                    compatible = WritableNormalMesh(vertices=mesh.vertices.copy(), faces=mesh.faces.copy(),
                                                    process=False, visual=mesh.visual.copy())
                    return super().postprocess_mesh(compatible, pbr_voxel, resolution, texture_size)
            pipeline = PreserveUVTexturing.from_pretrained(str(args.output))
            report["compatibility_adapter"] = "preserve input UV; copy vertex normals before upstream in-place rotation"
        else:
            pipeline = Trellis2ImageTo3DPipeline.from_pretrained(str(args.output))
        PIPELINE_CACHE[cache_key] = pipeline
        pipeline.cuda()
        report["model_load_seconds"] = time.perf_counter() - t
        # Preprocess once and save actual condition, so A/B can be audited.
        processed = pipeline.preprocess_image(image)
        processed.save(args.output / "condition_processed.png")
        report["processed_condition_sha256"] = sha(args.output / "condition_processed.png")
        report["processed_condition_size"] = list(processed.size)
        torch.cuda.reset_peak_memory_stats()
        t = time.perf_counter()
        inference_started = t
        print(f"Model ready; condition={processed.size}; starting {args.route} inference", flush=True)
        if args.route == "texture":
            data = np.load(args.input / "mesh_yup.npz", allow_pickle=False)
            mesh = trimesh.Trimesh(vertices=data["vertices"].copy(), faces=data["faces"].copy(), process=False)
            if "uv" in data:
                mesh.visual = trimesh.visual.TextureVisuals(uv=data["uv"].copy())
            reference_vertices = mesh.vertices.copy()
            center = (reference_vertices.min(axis=0) + reference_vertices.max(axis=0)) / 2
            scale = 0.99999 / np.ptp(reference_vertices, axis=0).max()
            report["normalization"] = {"center_input_yup": center.tolist(), "scale": float(scale),
                                       "world_frame": "Y-up, metres", "uv_preserved": "uv" in data}
            output = pipeline.run(mesh, processed, seed=args.seed, preprocess_image=False,
                                  resolution=args.resolution, texture_size=args.texture_size,
                                  tex_slat_sampler_params={"steps": args.steps})
            output.vertices = np.asarray(output.vertices) / scale + center
            # Save unsnapped output for independent geometric audit.
            output.export(str(args.output / "candidate_yup.glb"))
            payload = {"vertices": np.asarray(output.vertices), "faces": np.asarray(output.faces),
                       "uv": np.asarray(output.visual.uv)}
            output.visual.material.baseColorTexture.save(args.output / "basecolor.png")
            output.visual.material.metallicRoughnessTexture.save(args.output / "metallic_roughness.png")
            if "uv" in data:
                same_faces = np.array_equal(output.faces, data["faces"])
                same_uv = np.allclose(output.visual.uv, data["uv"], rtol=0, atol=1e-7)
                error = float(np.max(np.abs(output.vertices - reference_vertices))) if len(output.vertices) == len(reference_vertices) else float("inf")
                report["uv_adapter_gate"] = {"same_faces": same_faces, "same_uv": same_uv,
                                            "max_coordinate_error_m": error, "tolerance_m": 1e-6}
                if not (same_faces and same_uv and error <= 1e-6):
                    raise RuntimeError("UV-preserving texture output failed fixed-geometry contract")
                if "source_vertex_index" in data:
                    indices = np.asarray(data["source_vertex_index"])
                    if indices.shape != (len(output.vertices),) or indices.dtype.kind not in "iu" or indices.min() < 0:
                        raise RuntimeError("UV-to-source vertex mapping is invalid")
                    payload["source_vertex_index"] = indices.copy()
                    report["source_vertex_index_preserved"] = True
                if "face_owner" in data and "source_face_index" in data:
                    # Identity comes from a verified pre-texturing face/corner
                    # map, never from post-hoc nearest-neighbour owner guesses.
                    face_owner = np.asarray(data["face_owner"])
                    source_face_index = np.asarray(data["source_face_index"])
                    if face_owner.shape != (len(output.faces),) or source_face_index.shape != face_owner.shape:
                        raise RuntimeError("UV compatibility identity arrays have invalid shapes")
                    if not np.array_equal(np.sort(source_face_index), np.arange(len(output.faces))):
                        raise RuntimeError("UV compatibility source face identity is not bijective")
                    payload["face_owner"] = face_owner.copy()
                    payload["source_face_index"] = source_face_index.copy()
                    report["identity_preservation"] = {"source": "pre-texturing UV-compatibility mapped faces",
                        "same_face_indices_and_uv_gate": True, "posthoc_geometry_guess": False,
                        "source_face_bijection": True}
            np.savez_compressed(args.output / "candidate_yup.npz", **payload)
        else:
            pipeline_type = "1024_cascade" if args.resolution == 1024 else "512"
            report["native_pipeline_type"] = pipeline_type
            results = pipeline.run(processed, seed=args.seed, preprocess_image=False,
                                   pipeline_type=pipeline_type, num_samples=1,
                                   sparse_structure_sampler_params={"steps": args.steps},
                                   shape_slat_sampler_params={"steps": args.steps},
                                   tex_slat_sampler_params={"steps": args.steps})
            mesh = results[0]
            np.savez_compressed(args.output / "native_raw.npz",
                                vertices=mesh.vertices.cpu().numpy(), faces=mesh.faces.cpu().numpy())
            import o_voxel
            kwargs = dict(vertices=mesh.vertices, faces=mesh.faces, attr_volume=mesh.attrs,
                          coords=mesh.coords, attr_layout=mesh.layout, voxel_size=mesh.voxel_size,
                          aabb=[[-0.5]*3, [0.5]*3], decimation_target=200000,
                          texture_size=args.texture_size, remesh=False, verbose=True)
            report["export_signature"] = str(inspect.signature(o_voxel.postprocess.to_glb))
            output = o_voxel.postprocess.to_glb(**kwargs)
            output.export(str(args.output / "candidate_yup.glb"))
            report["native_scale"] = "unit-normalized, not measured metres; uncompiled appearance candidate"
        torch.cuda.synchronize()
        report["inference_and_export_wall_seconds"] = time.perf_counter() - t
        report["vertices"] = len(output.vertices)
        report["faces"] = len(output.faces)
        report["bounds"] = output.bounds.tolist()
        report["max_memory_allocated_bytes"] = torch.cuda.max_memory_allocated()
        report["max_memory_reserved_bytes"] = torch.cuda.max_memory_reserved()
        report["status"] = "candidate_generated_pending_independent_validation"
        report["output_files"] = {p.name: {"sha256": sha(p), "bytes": p.stat().st_size}
                                  for p in args.output.iterdir() if p.is_file()}
    except Exception as exc:
        report["status"] = "failed"
        report["error_type"] = type(exc).__name__
        report["error"] = str(exc)
        report["traceback"] = traceback.format_exc()
        traceback.print_exc()
    finally:
        if inference_started is not None:
            report["inference_elapsed_including_failure_seconds"] = time.perf_counter() - inference_started
        try:
            if "torch" in locals() and torch.cuda.is_initialized():
                report["max_memory_allocated_bytes"] = torch.cuda.max_memory_allocated()
                report["max_memory_reserved_bytes"] = torch.cuda.max_memory_reserved()
        except Exception:
            pass
        report["total_wall_seconds"] = time.perf_counter() - started
        write_json(args.output / "run.json", report)
        print(json.dumps({k: report.get(k) for k in ["status", "route", "error", "total_wall_seconds"]}), flush=True)
    return 1 if report["status"] == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
