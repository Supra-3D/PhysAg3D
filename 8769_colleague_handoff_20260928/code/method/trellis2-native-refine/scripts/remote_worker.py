"""SSH RPC and detached worker for the TRELLIS.2 skill (Python 3.10+)."""
from __future__ import annotations

import base64
import hashlib
import importlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import traceback


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def save_json(path, value):
    path = Path(path)
    tmp = path.with_name(path.name + ".tmp-" + str(os.getpid()))
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def job_path(request):
    root = Path(request["config"]["jobs_root"])
    if not root.is_absolute() or ".." in root.parts or len(root.parts) < 4:
        raise ValueError("jobs_root must be a specific absolute job directory")
    root = root.resolve()
    job_id = request["job_id"]
    if not re.fullmatch(r"t2-[0-9a-f]{32}", job_id):
        raise ValueError("Invalid job id")
    job = root / job_id
    if job.resolve().parent != root:
        raise ValueError("Job resolves outside jobs_root")
    return job


def gpu_inventory():
    result = subprocess.run(
        ["nvidia-smi", "--query-gpu=index,name,memory.free,memory.total", "--format=csv,noheader,nounits"],
        capture_output=True, text=True, timeout=15, check=True)
    values = []
    for line in result.stdout.splitlines():
        index, name, free, total = [x.strip() for x in line.split(",")]
        values.append({"index": index, "name": name, "free_mib": int(free), "total_mib": int(total)})
    return values


def doctor(config):
    checks = {key: Path(config[key]).exists() for key in ("python", "runtime", "model", "dino", "rembg")}
    for name in ("pipeline.json", "texturing_pipeline.json"):
        checks[name] = (Path(config["model"]) / name).is_file()
    sys.path.insert(0, config["runtime"])
    imports, versions = {}, {}
    for name in ("torch", "trimesh", "PIL", "trellis2.pipelines", "o_voxel", "cumesh"):
        try:
            module = importlib.import_module(name)
            imports[name] = "ok"
            versions[name] = getattr(module, "__version__", None)
        except Exception as exc:
            imports[name] = type(exc).__name__ + ": " + str(exc)
    try:
        gpus = gpu_inventory()
    except Exception as exc:
        gpus = []
        checks["gpu_query"] = False
        imports["gpu_query"] = str(exc)
    return {"ok": all(checks.values()) and all(v == "ok" for v in imports.values()),
            "paths": checks, "imports": imports, "versions": versions,
            "python": sys.version, "gpus": gpus, "simulation_ready": False}


def status(request):
    job = job_path(request)
    if not job.exists():
        return {"state": "not_found", "job_id": request["job_id"]}
    request_file = job / "request.json"
    if request_file.exists():
        actual = json.loads(request_file.read_text(encoding="utf-8"))
        if actual["fingerprint"] != request["fingerprint"]:
            raise ValueError("Remote request fingerprint mismatch")
    file = job / "worker_status.json"
    info = json.loads(file.read_text(encoding="utf-8")) if file.exists() else {"state": "preparing_unknown"}
    info.update(job_id=request["job_id"], remote_dir=str(job), simulation_ready=False)
    if info["state"] == "running" and info.get("pid"):
        try:
            cmdline = Path("/proc") / str(info["pid"]) / "cmdline"
            alive = str(job).encode() in cmdline.read_bytes()
        except (FileNotFoundError, ProcessLookupError):
            alive = False
        info["process_alive"] = alive
        if not alive:
            info["state"] = "interrupted_unknown"
    log = job / "worker.log"
    if log.exists():
        with log.open("rb") as stream:
            stream.seek(max(0, log.stat().st_size - 6000))
            info["log_tail"] = stream.read().decode("utf-8", errors="replace")
    return info


def submit(request):
    job = job_path(request)
    if job.exists():
        return status(request)
    job.parent.mkdir(parents=True, exist_ok=True)
    try:
        job.mkdir()
    except FileExistsError:
        return status(request)
    # Exclusive job creation is the submission lock. Partial staging is reported,
    # not automatically relaunched after an ambiguous disconnect.
    manifest = {k: v for k, v in request.items() if k not in ("action", "files")}
    save_json(job / "request.json", manifest)
    (job / "input").mkdir()
    allowed = {"input/source_image.png", "input/mesh_yup.npz", "run_trellis.py", "remote_worker.py"}
    for name, payload in request["files"].items():
        if name not in allowed:
            raise ValueError("Unexpected staged filename")
        content = base64.b64decode(payload["base64"], validate=True)
        if hashlib.sha256(content).hexdigest() != payload["sha256"]:
            raise ValueError("Staged content checksum mismatch: " + name)
        (job / name).write_bytes(content)
    save_json(job / "worker_status.json", {"state": "starting", "created_at": time.time()})
    try:
        with (job / "worker.log").open("ab", buffering=0) as log:
            subprocess.Popen([request["config"]["python"], str(job / "remote_worker.py"), "--worker", str(job)],
                             stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                             start_new_session=True, close_fds=True)
    except Exception as exc:
        save_json(job / "worker_status.json", {"state": "failed", "error": str(exc), "finished_at": time.time()})
        raise
    return status(request)


def worker(job):
    job = Path(job).resolve()
    # Even an accidentally repeated worker command cannot run inference twice.
    with (job / ".worker.lock").open("x") as stream:
        stream.write(str(os.getpid()))
    request = json.loads((job / "request.json").read_text(encoding="utf-8"))
    config, settings = request["config"], request["settings"]
    state = {"state": "running", "pid": os.getpid(), "started_at": time.time(), "simulation_ready": False}
    save_json(job / "worker_status.json", state)
    try:
        argv = [config["python"], str(job / "run_trellis.py"), "--route", settings["route"],
                "--input", str(job / "input"), "--output", str(job / "output")]
        for key in ("runtime", "model", "dino", "rembg"):
            argv += ["--" + key, config[key]]
        for key in ("gpu", "resolution", "steps", "texture_size", "seed", "min_free_gb"):
            argv += ["--" + key.replace("_", "-"), str(settings[key])]
        if request.get("retry_of"):
            argv += ["--retry-of", str(request["retry_of"])]
        env = os.environ.copy()
        env.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", PYTHONDONTWRITEBYTECODE="1", PYTHONUNBUFFERED="1")
        state["argv"] = argv
        save_json(job / "worker_status.json", state)
        result = subprocess.run(argv, env=env, cwd=job, check=False)
        report_file = job / "output" / "run.json"
        report = json.loads(report_file.read_text(encoding="utf-8")) if report_file.exists() else {}
        passed = result.returncode == 0 and report.get("status") == "candidate_generated_pending_independent_validation"
        state.update(state="succeeded" if passed else "failed", exit_code=result.returncode,
                     candidate_status=report.get("status"), error=report.get("error"))
    except Exception as exc:
        traceback.print_exc()
        state.update(state="failed", error=type(exc).__name__ + ": " + str(exc))
    finally:
        state["finished_at"] = time.time()
        save_json(job / "worker_status.json", state)


def list_files(request):
    info = status(request)
    if info["state"] not in ("succeeded", "failed"):
        raise ValueError("Collect only terminal jobs; current state: " + info["state"])
    job = job_path(request)
    files = []
    for path in sorted(job.rglob("*")):
        if path.is_file() and not path.is_symlink() and not path.name.startswith(".") and ".tmp-" not in path.name:
            files.append({"path": path.relative_to(job).as_posix(), "bytes": path.stat().st_size, "sha256": digest(path)})
    return {"job_id": request["job_id"], "state": info["state"], "files": files}


def fetch(request):
    job = job_path(request)
    path = job / request["file"]
    if path.is_symlink() or not path.resolve().is_relative_to(job.resolve()) or not path.is_file():
        raise ValueError("Invalid collection file")
    # stdout is the binary transport; diagnostics go to stderr.
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            sys.stdout.buffer.write(block)


def dispatch(request):
    action = request["action"]
    if action == "doctor":
        return doctor(request["config"])
    if action == "gpus":
        return {"gpus": gpu_inventory()}
    if action == "submit":
        return submit(request)
    if action == "status":
        return status(request)
    if action == "list_files":
        return list_files(request)
    raise ValueError("Unsupported action: " + action)


if __name__ == "__main__" and len(sys.argv) == 3 and sys.argv[1] == "--worker":
    worker(sys.argv[2])
