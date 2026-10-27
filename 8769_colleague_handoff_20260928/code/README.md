> Handoff correction: keep this code directory unchanged. Edit the sibling config/runtime.windows-ssh.json. Run from the handoff root using python code/reproduce.py. Keep runtime, virtual environments and outputs outside code/. The full instructions are in START_HERE.zh-CN.md at the handoff root.

# 8769 whole-object native then Blender refinement

**Release candidate, not a reproducibility-certified release.** This directory contains an explicitly assisted 8769 protocol, native generation client, Blender/MuJoCo code references, local viewer, and a new portable launcher. No model weights, credentials, conversation history, old meshes or benchmark results are bundled.

The released method is the complete protocol and toolchain, **not a deterministic image-to-articulation network**. The reasoning model authors per-case Blender and simulator code. Historical code-only references are explicitly part of this assisted variant. They must not be omitted while attributing the same historical results to the remaining code.

Read [中文说明](README.zh-CN.md), [context-independence audit](docs/CONTEXT_AUDIT.zh-CN.md), and [reproduction protocol](docs/REPRODUCTION.zh-CN.md) before interpreting results.

## Target environment

Reference target: a **fresh Windows 11 controller** with Python 3.12, Blender 5.2.1, compatible Codex CLI and the recipient's own ChatGPT account, plus an independently deployed **Linux TRELLIS.2 backend**. The two OS environments may be separate machines. Native settings: `1024_cascade`, 24 steps, 2048 texture, seed 42. Historical reasoning model: `gpt-6-astra`, effort `high`; availability and CLI compatibility must be checked by the recipient. No automatic model, authentication or permission fallback.

The local Linux profile is an experimental portability path. **Neither target has been independently validated end to end for this new adapter.** The historical frozen API adapter has Windows-specific preflight requirements and is not the entry point below.

```text
python reproduce.py verify
# From code/: edit ../config/runtime.windows-ssh.json; leave the protected example unchanged.
python reproduce.py doctor --config ../config/runtime.windows-ssh.json
python reproduce.py doctor --config ../config/runtime.windows-ssh.json --native
python reproduce.py prepare --image INPUT.png --config ../config/runtime.windows-ssh.json --out C:/experiments/case001
python reproduce.py plan C:/experiments/case001
# Only the next command starts generation and uses your own model-service quota:
python reproduce.py run C:/experiments/case001
```

`prepare` copies only the declared method, the supplied image and validated runtime configuration into a new empty case. It records input/prompt/method hashes and allocates a unique native jobs root. `run` rejects changed prepared inputs and refuses to reuse an attempted run. Execution completion is **not** a physical or visual pass. Inspect the generated `delivery.json`, `.blend`, GLB, simulator evidence and actual moving surfaces.

Do not mount the historical source archive, results gallery, host workspace, old conversations, old assets or unrelated user state into the clean evaluation guest. A new directory and disabled memory alone are not an isolation certificate.

## Source layout

- `method/trellis2-native-refine/`: original 8769 skill and native tools; deployment profiles sanitized.
- `method/WORKER_PROMPT.md`: full declared generation/refinement/validation instructions.
- `method/assisted_reference_code/`: historical code examples, **not executable case solutions for new images**. Some original hardcoded locations were replaced by explicit invalid placeholders; adapt only general techniques inside the new run.
- `method/delivery_tools/`: packages existing animated GLBs; does not create articulation.
- `reproduce.py`: new portable, single-case controller. It does not implement the historical batch retry/resume policy.
- `provenance/`: source modifications and recorded upstream file fingerprints.
- `checksums.json`: package identity, not a generation-quality certificate.

No first-party public license has been chosen. Third-party notices and input/model licensing must be resolved before publishing. Historical assets are provided separately for the author's review, not silently relicensed by this package.
