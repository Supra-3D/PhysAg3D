# API execution and accounting

The desktop and server runners share `scripts/asset_prompt.py` for the modeling task prompt. Runtime executable paths, transport hints and enforced permission profiles are host adapters; they do not prescribe a different modeling or repair method. `--dry-run` includes the exact prompt and caller-supplied context, after checking for the selected key, without starting a model. Normal runs do not automatically load historical deployment-test context files. Native inference defaults are shared in `references/inference-defaults.json`.

The user requests API-key billing for GPT-6 asset generation. New generation runs
use `scripts/run_api.py`. It starts Codex CLI with a named Responses provider,
`gpt-6-astra`, environment-key auth and no ChatGPT-auth fallback. This retains the
full image/tool/modeling/refinement loop. The desktop task launches the run and
reports its outputs; it should not do the asset reasoning/code generation first.
Ordinary conversation and launch/report orchestration retain their current billing.
An already-started generation is not retroactively converted or automatically restarted.

## Local configuration

`api-execution.json` contains the model, effort, credential-file path, absolute
`runtime_python` / `runtime_blender` executable paths and a preflight requirement,
with no secret. The configured `.env.local` provides `OPENAI_API_KEY` and
`OPENAI_BASE_URL`. Select an endpoint appropriate to your own account. If using
a compatible gateway, usage and backend model identity are determined by that
provider; they are not verified by a model listing. A model listing alone does
not establish successful generation, tool compatibility or output quality.

Resolve the current skill directory and use Python 3.10+ and Codex CLI. Commands
below are templates; use actual paths and a fresh case directory.

```powershell
& $python "$skillDir/scripts/run_api.py" --doctor
& $python "$skillDir/scripts/run_api.py" --image $image --out $newCase --dry-run
& $python "$skillDir/scripts/run_api.py" --image $image --out $newCase --context-file $taskContext
```

The optional context is a UTF-8 file containing the user's additional requirements,
available Blender/Python paths and active TRELLIS SSH profile; never include a key.
The actual image is attached to the API execution via `--image`. Once inside the
worker, execute this skill directly: the launch prompt and `api_execution.json`
identify the active API run. Do not launch another runner recursively.

An optional non-secret `trellis_config` absolute path in the API configuration
selects the same deployment profile for both dependency preflight and the worker
prompt. This avoids testing an unrelated historical SSH profile. A `broker_tcp`
profile can reach an already configured fixed-purpose Unix broker through an
operator-maintained SSH tunnel bound to `127.0.0.1`. The worker does not read SSH
credentials or start the tunnel. `server_config` must contain the exact managed
Unix profile; broker validation, pinned inference code and GPU locks still apply.
The adapter does not provide shell execution or change worker permissions.

Use `--env-file PATH`, `--key-env NAME`, or `--config PATH` for another environment.
`--ask-key` is for the user's own interactive terminal and never echoes the key.
Dotenv is parsed as simple assignments, without shell expansion. A named process
environment key takes precedence over the file's key; endpoint comes from explicit
configuration, then the dotenv file, otherwise the official OpenAI URL.

The launcher does not alter Codex login or global settings, ignores the ordinary
user config for that invocation, and uses the skill's shell/SSH tools rather than
assuming the desktop MCP setup is available. It writes only the fresh case folder.
On Windows it explicitly selects `windows.sandbox="elevated"` because ignoring
user config also skips that setting. Before a model request it probes restricted
PowerShell startup, skill/input reads and a temporary workspace write. The probe
uses the installed 0.153 Windows CLI form `codex sandbox --permission-profile
:workspace --include-managed-config -- COMMAND`; there is no `windows` subcommand
in that build. It does not call a model or read/send API credentials. A failed
probe is recorded as `blocked_local_preflight`, with `api_started=false` and zero
API usage. This initial check does not establish Blender/SSH health.

After the local probe succeeds, `dependency_preflight` runs the actual configured
toolchain before starting the model: Python imports `numpy`, `scipy`, `trimesh`,
`PIL` and `mujoco` (30-second timeout); Blender `--version` (30 seconds); and
`trellis2_tool.py doctor` (75 seconds). The TRELLIS doctor checks the configured
server connection, paths, imports and GPU inventory; it submits no generation job.
Python import failure skips the TRELLIS check. These checks use a temporary
`asset_dependency_probe` permission profile extending `:workspace`, with network
enabled, managed configuration included, the elevated Windows backend and
approval policy `never`. They request no extra filesystem access and change no
global configuration. Network access follows the worker's existing policy; this
is not a new domain allowlist or a guarantee of server access. API credentials are
excluded from the probe environment. No model or asset generation runs.

A failed dependency check records `blocked_dependency_preflight`,
`api_started=false` and zero API usage. Inspect the individual `python_imports`,
`blender` and `trellis` results; shell success alone is insufficient. Passing these
checks does not prove image inference, modeling, full tool-policy compatibility
or physical validation will succeed. The launcher never downgrades or disables a
sandbox after failure.

These local configurations set `require_dependency_preflight=true`, requiring a
supported dependency sandbox. Windows always performs the check. On non-Windows
hosts, older configurations that omit this flag or set it to false retain their
previous execution behavior and report `not_checked_non_windows` with
`passed=null`; that is not successful validation. With the flag true, an unsupported
platform reports `unsupported_dependency_sandbox` and blocks before model use.

The worker uses workspace-write with network enabled and approval policy never;
enforced restrictions still apply. A blocked tool is a reported limitation, not
permission to disable restrictions. Existing nonempty output folders are rejected.

This native-refine method requires an actual whole-object TRELLIS.2 candidate.
If mandatory TRELLIS access or generation fails, preserve the receipt, logs and
usage, report the blocker, and stop this asset run. Do not substitute Blender-only
geometry or present an earlier candidate as a new native generation.

## Results and failure handling

- `--doctor`: key/CLI presence, the local Windows sandbox probe and the subsequent
  dependency preflight in the current directory. Its temporary probe file is removed.
  It can contact the configured TRELLIS server over SSH but makes no model API
  request and submits no generation job. Both probe results are reported.
- `--dry-run`: inspect non-secret arguments; neither probe executes, with no model
  execution, SSH request or output writes.
- `api_execution.json`: configured provider, model, timestamps, input/skill hashes,
  process state and CLI-reported token usage. This is an execution record, not a
  provider invoice. Cached input tokens may be a subset of input tokens; do not
  add them again. Interrupted streams can leave incomplete usage accounting.
- `api_events.jsonl`, `api_messages.md`, `api_prompt.txt`: inspectable execution and
  result evidence. The launcher redacts the supplied key from event output and
  excludes secret environment variables from model-generated shell commands.
- `executor_completed` means the CLI ended, not that the asset passed validation.
  Check MJCF load, actual interactions and matched-view evidence separately.
- Missing/invalid key, model unavailability or a failed run: preserve evidence and
  report the blocker. Do not fall back to Pro/ChatGPT auth, change the model, repeat
  an entire asset job, or duplicate a TRELLIS job automatically.

For Windows error `1385`, sandbox users exist but Windows denies the required
logon type. Have the machine administrator verify the Codex sandbox-user rights
and applicable enterprise policy, and use the approved Codex sandbox setup flow.
Do not automatically grant rights, change groups, remove deny rules or change
authentication. See [Windows sandbox troubleshooting](https://learn.chatgpt.com/docs/windows/windows-sandbox).

Official configuration references checked 2026-09-09:
[custom providers](https://learn.chatgpt.com/docs/config-file/config-advanced),
[non-interactive execution](https://learn.chatgpt.com/docs/non-interactive-mode),
[GPT-6 Astra API model](https://developers.openai.com/api/docs/guides/latest-model).
