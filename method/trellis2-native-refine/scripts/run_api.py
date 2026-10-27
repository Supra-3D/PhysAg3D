"""Run this asset skill with explicitly API-key-authenticated Codex CLI.

No login/config changes, credential copying, subscription fallback, or retry of
whole asset jobs. --dry-run and --doctor never start a model execution.
"""
import argparse
import base64
import getpass
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from urllib.parse import urlsplit

from asset_prompt import build_asset_prompt


PRIVATE_KEY_ENV = "TRELLIS_ASSET_API_KEY"


def read_env(path):
    values = {}
    for line in Path(path).read_text(encoding="utf-8-sig").splitlines():
        line = line.strip().removeprefix("export ").strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        value = value.strip()
        if value.startswith(("'", '"')):
            quote = value[0]
            end = value.find(quote, 1)
            if end < 0 or value[end + 1:].strip().strip("# "):
                # Accept a conventional trailing comment, never execute dotenv.
                if end < 0 or not value[end + 1:].lstrip().startswith("#"):
                    raise ValueError("Unsupported quoted dotenv value")
            value = value[1:end]
        else:
            value = re.split(r"\s+#", value, maxsplit=1)[0].rstrip()
        values[name.strip()] = value
    return values


def credentials(settings, env_file=None, key_env=None, ask_key=False):
    source_file = env_file or settings.get("env_file")
    data = read_env(source_file) if source_file else {}
    name = key_env or settings.get("key_env", "OPENAI_API_KEY")
    key = os.environ.get(name) or data.get(name, "")
    if ask_key:
        if not sys.stdin.isatty():
            raise ValueError("--ask-key requires your interactive terminal")
        key = getpass.getpass("API key (hidden): ")
    key = key.strip()
    base = (settings.get("base_url") or data.get("OPENAI_BASE_URL")
            or "https://api.openai.com/v1").rstrip("/")
    url = urlsplit(base)
    if (url.scheme != "https" or not url.hostname or url.username
            or url.password or url.query or url.fragment):
        raise ValueError("API base URL must be HTTPS without embedded credentials or query")
    return key, base


def redact(text, key):
    if key:
        text = text.replace(key, "[REDACTED]")
    return re.sub(r"\bsk-[A-Za-z0-9_-]{12,}\b", "[REDACTED]", text)


def make_command(codex, root, image, base, model, effort):
    provider = {"name": "Asset API key", "base_url": base,
                "env_key": PRIVATE_KEY_ENV, "wire_api": "responses",
                "requires_openai_auth": False, "request_max_retries": 1,
                "stream_max_retries": 1}
    # JSON string literals are also valid TOML basic string values.
    table = "{ " + ", ".join(k + " = " + json.dumps(v) for k, v in provider.items()) + " }"
    config = [
        'model_provider="trellis_asset_api"',
        "model_providers.trellis_asset_api=" + table,
        "model_reasoning_effort=" + json.dumps(effort),
        'approval_policy="never"',
        'sandbox_workspace_write.network_access=true',
        'shell_environment_policy.inherit="all"',
        'shell_environment_policy.ignore_default_excludes=false',
        'shell_environment_policy.filters={"*KEY*"="exclude", "*TOKEN*"="exclude", "*SECRET*"="exclude", "*PASSWORD*"="exclude"}',
    ]
    if sys.platform == "win32":
        # --ignore-user-config also skips [windows]. Select the restricted
        # backend explicitly; never downgrade after a failed setup/probe.
        config.append('windows.sandbox="elevated"')
    command = [codex, "exec", "--ignore-user-config", "--ephemeral",
               "--skip-git-repo-check", "--sandbox", "workspace-write",
               "--model", model, "--cd", str(root), "--image", str(image),
               "--json", "--color", "never"]
    for item in config:
        command.extend(["-c", item])
    command.append("-")
    return command


def probe_local_tools(codex, root, skill, image=None, source_key_env=None):
    """No model call: check restricted Windows shell read/write, fail closed."""
    if sys.platform != "win32":
        return {"status": "not_checked_non_windows", "passed": None}
    root = Path(root).resolve()
    shell = shutil.which("powershell.exe") or shutil.which("pwsh.exe")
    if not codex or not shell or not root.is_dir():
        return {"status": "local_dependency_missing", "passed": False}
    marker = "CODEX_ASSET_PROBE_" + uuid.uuid4().hex
    probe = root / ("." + marker + ".txt")
    def literal(value):
        return "'" + str(value).replace("'", "''") + "'"
    script = "$ErrorActionPreference='Stop'; $ProgressPreference='SilentlyContinue'; "
    script += "[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false); $OutputEncoding=[Console]::OutputEncoding; "
    script += "$null=[IO.File]::ReadAllText(" + literal(Path(skill) / "SKILL.md") + "); "
    if image:
        script += "$stream=[IO.File]::OpenRead(" + literal(Path(image).resolve()) + "); $stream.Dispose(); "
    script += "$probePath=" + literal(probe) + "; try { "
    script += "[IO.File]::WriteAllText($probePath," + literal(marker) + "); "
    script += "if ([IO.File]::ReadAllText($probePath) -ne " + literal(marker) + ") { throw 'probe mismatch' }; "
    script += "Write-Output " + literal(marker) + " } finally { if ([IO.File]::Exists($probePath)) { [IO.File]::Delete($probePath) } }"
    # Codex 0.153.0 on Windows takes `sandbox [COMMAND]`, without a `windows`
    # subcommand. Include managed constraints when selecting the built-in profile.
    command = [codex, "sandbox", "--permission-profile", ":workspace",
               "--include-managed-config", "--cd", str(root),
               "-c", 'windows.sandbox="elevated"', "-c", 'approval_policy="never"',
               "--", shell, "-NoProfile", "-NonInteractive", "-EncodedCommand",
               base64.b64encode(script.encode("utf-16-le")).decode("ascii")]
    env = {k: v for k, v in os.environ.items()
           if not re.search(r"KEY|TOKEN|SECRET|PASSWORD", k, re.I)}
    if source_key_env:
        env.pop(source_key_env, None)
    started = time.monotonic()
    try:
        result = subprocess.run(command, cwd=root, env=env, stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                timeout=30, text=True, encoding="utf-8", errors="replace")
        passed = result.returncode == 0 and marker in result.stdout.splitlines()
        status = "passed" if passed else "sandbox_command_failed"
        if not passed and "1385" in result.stdout:
            status = "windows_logon_type_denied_1385"
        return {"status": status, "passed": passed, "exit_code": result.returncode,
                "windows_sandbox": "elevated", "wall_seconds": time.monotonic() - started,
                "diagnostic": redact(result.stdout.replace(marker, "[probe]"), "")[-2000:],
                "scope": "Sandboxed PowerShell startup, skill/input read, and temporary workspace write. No API, Blender or SSH validation."}
    except subprocess.TimeoutExpired:
        return {"status": "sandbox_probe_timeout", "passed": False,
                "wall_seconds": time.monotonic() - started}
    except OSError as exc:
        return {"status": "sandbox_probe_start_failed", "passed": False,
                "error_type": type(exc).__name__, "winerror": getattr(exc, "winerror", None)}


def worker_environment(key, source_key_env=None):
    env = dict(os.environ)
    # Pass only the selected key to model transport; do not persist it or let
    # an inherited Codex credential/base URL select another billing path.
    for name in ("OPENAI_API_KEY", "CODEX_API_KEY", "CODEX_ACCESS_TOKEN", "OPENAI_BASE_URL"):
        env.pop(name, None)
    if source_key_env:
        env.pop(source_key_env, None)
    env[PRIVATE_KEY_ENV] = key
    env["TRELLIS_ASSET_API_EXECUTION"] = "1"
    return env


def probe_dependencies(codex, root, skill, settings, source_key_env=None):
    """Check the actual toolchain in the worker's sandbox, without a model call."""
    if sys.platform != "win32":
        if settings.get("require_dependency_preflight") is True:
            return {"status": "unsupported_dependency_sandbox", "passed": False, "checks": {}}
        return {"status": "not_checked_non_windows", "passed": None, "checks": {}}
    root, skill = Path(root).resolve(), Path(skill).resolve()
    if not codex or not root.is_dir():
        return {"status": "local_dependency_missing", "passed": False, "checks": {}}
    # Extend the filesystem baseline with the same network access as the worker.
    # Managed constraints still apply; no additional filesystem access is requested.
    prefix = [codex, "sandbox", "--permission-profile", "asset_dependency_probe",
              "--include-managed-config", "--cd", str(root),
              "-c", 'permissions.asset_dependency_probe.extends=":workspace"',
              "-c", 'permissions.asset_dependency_probe.network.enabled=true',
              "-c", 'windows.sandbox="elevated"', "-c", 'approval_policy="never"']
    env = {k: v for k, v in os.environ.items()
           if not re.search(r"KEY|TOKEN|SECRET|PASSWORD", k, re.I)}
    if source_key_env:
        env.pop(source_key_env, None)
    checks = {}
    python = settings.get("runtime_python")
    blender = settings.get("runtime_blender")
    marker = "CODEX_ASSET_IMPORTS_" + uuid.uuid4().hex
    imports = "import numpy, scipy, trimesh, PIL, mujoco; print(" + repr(marker) + ")"
    phases = [
        ("python_imports", python, ["-B", "-X", "utf8", "-c", imports], 30),
        ("blender", blender, ["--version"], 30),
        ("trellis", python, ["-B", "-X", "utf8", str(skill / "scripts" / "trellis2_tool.py"),
                            "--config", str(settings.get("trellis_config") or skill / "references" / "server.json"), "doctor"], 75),
    ]
    for phase, executable, arguments, timeout in phases:
        if not isinstance(executable, str) or not Path(executable).is_absolute() or not Path(executable).is_file():
            checks[phase] = {"passed": False, "status": "configured_runtime_missing"}
            continue
        if phase == "trellis" and not checks["python_imports"]["passed"]:
            checks[phase] = {"passed": False, "status": "not_run_python_imports_failed"}
            continue
        started = time.monotonic()
        try:
            result = subprocess.run(prefix + ["--", executable] + arguments, cwd=root, env=env,
                                    stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                    timeout=timeout, text=True, encoding="utf-8", errors="replace")
            valid_output = False
            if phase == "python_imports":
                valid_output = marker in result.stdout.splitlines()
            elif phase == "blender":
                valid_output = bool(re.search(r"(?m)^Blender [0-9]+\.", result.stdout))
            else:
                try:
                    report = json.loads(result.stdout)
                    valid_output = isinstance(report, dict) and report.get("ok") is True
                except (ValueError, TypeError):
                    pass
            passed = result.returncode == 0 and valid_output
            checks[phase] = {"passed": passed, "status": "passed" if passed else "dependency_command_failed",
                             "exit_code": result.returncode,
                             "diagnostic": redact((result.stdout + result.stderr).replace(marker, "[imports]"), "")[-2000:]}
        except subprocess.TimeoutExpired:
            checks[phase] = {"passed": False, "status": "dependency_timeout"}
        except OSError as exc:
            checks[phase] = {"passed": False, "status": "dependency_start_failed",
                             "error_type": type(exc).__name__, "winerror": getattr(exc, "winerror", None)}
        checks[phase]["wall_seconds"] = time.monotonic() - started
    passed = all(check["passed"] for check in checks.values())
    return {"passed": passed, "status": "passed" if passed else "dependency_preflight_failed",
            "windows_sandbox": "elevated", "network_access": True, "checks": checks,
            "scope": "Sandboxed Python imports, Blender version, and TRELLIS doctor. No API or asset generation."}


def dependency_preflight(codex, root, skill, settings, local_preflight, source_key_env=None):
    if local_preflight["passed"] is False:
        return {"passed": False, "status": "not_run_local_preflight_failed", "checks": {}}
    return probe_dependencies(codex, root, skill, settings, source_key_env)


def main(argv=None):
    # Redirected Windows streams may default to CP936 even though diagnostics
    # and worker events are UTF-8. Configure before argparse can report errors.
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="backslashreplace")
    skill = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", type=Path)
    parser.add_argument("--out", type=Path, help="Fresh output directory; existing nonempty paths are rejected")
    parser.add_argument("--config", type=Path, default=skill / "references" / "api-execution.json")
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--key-env")
    parser.add_argument("--ask-key", action="store_true")
    parser.add_argument("--context-file", type=Path, help="Optional task requirements and tool locations, without secrets")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--doctor", action="store_true")
    modes.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    settings = json.loads(args.config.read_text(encoding="utf-8-sig"))
    key, base = credentials(settings, args.env_file, args.key_env, args.ask_key)
    source_key_env = args.key_env or settings.get("key_env", "OPENAI_API_KEY")
    codex = shutil.which("codex")
    model = settings.get("model", "gpt-6-astra")
    effort = settings.get("reasoning_effort", "xhigh")
    if model != "gpt-6-astra":
        raise ValueError("This runner requires the user's requested gpt-6-astra; no automatic model substitution")
    if effort not in ("low", "medium", "high", "xhigh", "max"):
        raise ValueError("Unsupported reasoning effort")
    public = {"skill": skill.name, "model": model, "reasoning_effort": effort,
              "api_base_url": base, "authentication": "api_key",
              "key_present": bool(key), "codex_available": bool(codex),
              "subscription_fallback": False}
    if sys.platform == "win32":
        public["windows_sandbox"] = "elevated"
    if args.doctor:
        public["local_tool_preflight"] = probe_local_tools(codex, Path.cwd(), skill, args.image, source_key_env)
        public["dependency_preflight"] = dependency_preflight(codex, Path.cwd(), skill, settings,
                                                              public["local_tool_preflight"], source_key_env)
        public.update(api_started=False, usage={"input_tokens": 0, "cached_input_tokens": 0, "output_tokens": 0})
        print(json.dumps(public, ensure_ascii=False))
        return 0 if key and codex and public["local_tool_preflight"]["passed"] is not False and public["dependency_preflight"]["passed"] is not False else 2
    if not args.image or not args.out:
        parser.error("--image and --out are required")
    image = args.image.resolve(strict=True)
    root = args.out.resolve()
    if not image.is_file():
        raise ValueError("Input image must be a file")
    if root.exists() and (not root.is_dir() or any(root.iterdir())):
        raise ValueError("Choose a fresh output directory; existing jobs are never overwritten or restarted")
    context = args.context_file.read_text(encoding="utf-8-sig") if args.context_file else ""
    if key and key in context:
        raise ValueError("Context contains the API key; remove all credentials")
    prompt = build_asset_prompt(skill, image, root, settings, context)
    if key and key in prompt:
        raise ValueError("Runtime prompt contains the API key; remove all credentials")
    command = make_command(codex or "codex", root, image, base, model, effort)
    if args.dry_run:
        print(json.dumps({**public, "command": command, "out": str(root),
                          "image": str(image), "prompt": prompt, "started": False}, ensure_ascii=False))
        return 0
    if not key or not codex:
        raise ValueError("API key or Codex CLI missing; no subscription fallback")
    root.mkdir(parents=True, exist_ok=True)
    manifest_path = root / "api_execution.json"
    manifest = {**public, "state": "preflighting", "phase": "local_tool_preflight", "started_at": datetime.now(timezone.utc).isoformat(),
                "input_sha256": hashlib.sha256(image.read_bytes()).hexdigest(),
                "skill_sha256": hashlib.sha256((skill / "SKILL.md").read_bytes()).hexdigest(),
                "usage": {}, "api_started": False, "asset_validation": "see worker reports"}
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (root / "api_prompt.txt").write_text(prompt, encoding="utf-8")
    preflight = probe_local_tools(codex, root, skill, image, source_key_env)
    manifest["local_tool_preflight"] = preflight
    manifest["phase"] = "dependency_preflight"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    dependencies = dependency_preflight(codex, root, skill, settings, preflight, source_key_env)
    manifest["dependency_preflight"] = dependencies
    if preflight["passed"] is False or dependencies["passed"] is False:
        blocked_phase = "local_preflight" if preflight["passed"] is False else "dependency_preflight"
        manifest.update(state="blocked_" + blocked_phase, phase=blocked_phase,
                        finished_at=datetime.now(timezone.utc).isoformat(),
                        api_started=False, usage={"input_tokens": 0, "cached_input_tokens": 0, "output_tokens": 0})
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        print(json.dumps({"manifest": str(manifest_path), "state": manifest["state"],
                          "api_started": False, "local_tool_preflight": preflight,
                          "dependency_preflight": dependencies}, ensure_ascii=False))
        return 2
    manifest.update(state="running", phase="api_execution")
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    failed = False
    process = None
    try:
        process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, env=worker_environment(key, source_key_env),
                                   cwd=root, text=True, encoding="utf-8", errors="replace")
        manifest["api_started"] = True
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        process.stdin.write(prompt)
        process.stdin.close()
        with (root / "api_events.jsonl").open("w", encoding="utf-8") as events:
            for line in process.stdout:
                line = redact(line, key)
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    event = {"type": "runner.log", "text": line.rstrip()}
                events.write(json.dumps(event, ensure_ascii=False) + "\n")
                events.flush()
                if event.get("type") == "turn.completed":
                    for name, value in event.get("usage", {}).items():
                        if isinstance(value, (int, float)):
                            manifest["usage"][name] = manifest["usage"].get(name, 0) + value
                if event.get("type") in ("turn.failed", "error"):
                    failed = True
                item = event.get("item", {})
                if event.get("type") == "item.completed" and item.get("type") == "agent_message":
                    with (root / "api_messages.md").open("a", encoding="utf-8") as messages:
                        messages.write(item.get("text", "") + "\n\n")
                if event.get("type") in ("thread.started", "turn.started", "turn.completed", "turn.failed", "error"):
                    print(json.dumps(event, ensure_ascii=False), flush=True)
        code = process.wait()
        manifest.update(state="failed" if code or failed else "executor_completed", exit_code=code)
    except BaseException:
        manifest["state"] = "interrupted_or_failed"
        if process is not None and process.poll() is None:
            process.terminate()
            process.wait()
        raise
    finally:
        manifest["finished_at"] = datetime.now(timezone.utc).isoformat()
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps({"manifest": str(manifest_path), "state": manifest["state"],
                      "usage": manifest["usage"]}, ensure_ascii=False))
    return 1 if code or failed else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError) as exc:
        # Do not echo exceptions from dotenv/network contents or credentials.
        print(json.dumps({"error": type(exc).__name__, "message": "API runner setup failed; check input paths/configuration. No subscription fallback."}), file=sys.stderr)
        raise SystemExit(2)
