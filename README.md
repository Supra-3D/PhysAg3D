# PhysAg3D

**Bridging 3D Generative and Agentic Models for High-Fidelity and Physically-Interactive Assets**

[Project website](https://supra-3d.github.io/PhysAg3D/) · [中文说明](README.zh-CN.md)

PhysAg3D combines single-image 3D generation with agent-directed Blender refinement and MuJoCo evaluation. The repository includes the task protocol, generation tools, code references, a single-case launcher, and sample images.

## Repository layout

```text
PhysAg3D/
├── reproduce.py                 # Verify, prepare, inspect, and launch a case
├── verify_external.py           # Check an external runtime or model installation
├── method/                      # Task instructions, generation tools, and references
├── config/                      # Editable runtime configuration templates
├── examples/                    # Reference configuration profiles
├── inputs/                      # 34 sample images
├── tests/                       # Offline launcher tests
├── docs/                        # Setup, validation, and result documentation
├── provenance/                  # Recorded external runtime/model fingerprints
├── licenses/                    # Third-party license texts
├── checksums.json               # Source integrity manifest
└── requirements.observed.txt    # Observed Python dependency versions
```

## Environment

The reference setup uses a Windows controller with Python 3.12, Blender 5.2.1, and a compatible Codex CLI, connected to a Linux NVIDIA GPU host running TRELLIS.2. The configured native inference requires at least 28 GiB of free GPU memory. TRELLIS.2, DINOv3, BiRefNet, and their weights must be installed separately.

The launcher retains its configured reasoning model (`gpt-6-astra`, `high`) and native settings (resolution 1024, 24 steps, texture size 2048, seed 42). `doctor` checks the CLI flags and tool dependencies; access to the configured model must also be available. The dependency file records observed versions and is not a validated clean-install lockfile.

## Quick start

Run these PowerShell commands from the repository root:

```powershell
python -m venv .venv
$python = (Resolve-Path .venv/Scripts/python.exe).Path
& $python -m pip install -r requirements.observed.txt
Copy-Item config/runtime.windows-ssh.json config/runtime.local.json
```

Edit `config/runtime.local.json` with your Python, Blender, Codex CLI, SSH host, model directories, and writable remote job directory. `python` must point to the environment created above. Use your own account and SSH configuration; credentials are not part of the runtime JSON.

```powershell
& $python reproduce.py verify
& $python reproduce.py doctor --config config/runtime.local.json
& $python reproduce.py doctor --config config/runtime.local.json --native
& $python reproduce.py prepare --image inputs/glossy_18_e53271e2.png --config config/runtime.local.json --out ../runs/example01
& $python reproduce.py plan ../runs/example01
& $python reproduce.py run ../runs/example01
```

Only `run` starts generation and uses model-service quota. Each case must use a new directory outside this repository. Prepared inputs and method files are checked before execution, and an attempted case is not automatically retried or resumed.

The main launcher uses the configured ChatGPT subscription route. The optional API-key adapter in `method/trellis2-native-refine/scripts/run_api.py` is a separate execution route; its configuration is documented alongside that tool.

## Results and validation

Inspect `delivery.json` for the actual output paths and status. Outputs may include an editable Blender file, GLB, MJCF scene and dependencies, motion video, comparison renders, and a local preview page. Process completion alone does not establish visual or physical correctness.

The declared method includes code references in `method/assisted_reference_code/`. They illustrate modeling techniques and contain case-specific assumptions; the worker adapts them to each new image and candidate. Model weights and pre-generated assets are not bundled. Independent end-to-end reproduction remains to be validated.

Source checksums cover the declared source files and directories. Local configuration, input images, Git metadata, and virtual environments are outside that scope.

- [Detailed setup](docs/REPRODUCTION.zh-CN.md)
- [Validation scope](docs/VALIDATION.zh-CN.md)
- [Result checklist](docs/RESULTS.zh-CN.md)
- [Third-party notices](THIRD_PARTY_NOTICES.md)
