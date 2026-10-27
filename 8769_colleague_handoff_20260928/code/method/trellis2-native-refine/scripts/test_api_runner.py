"""Offline routing, credential handling, and failure-accounting checks."""
import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import tomllib
import unittest
from unittest.mock import patch

import run_api


class RunnerTests(unittest.TestCase):
    def test_cli_reports_unicode_through_legacy_encoded_streams(self):
        diagnostic = "#< CLIXML\n\ufffd \U0001f9ea \u4e2d\u6587"
        with tempfile.TemporaryDirectory() as d:
            config = Path(d) / "settings.json"
            config.write_text('{"model":"gpt-6-astra"}', encoding="utf-8")
            for argument_error in (False, True):
                with self.subTest(argument_error=argument_error):
                    stdout_bytes, stderr_bytes = io.BytesIO(), io.BytesIO()
                    stdout = io.TextIOWrapper(stdout_bytes, encoding="cp936", errors="strict")
                    stderr = io.TextIOWrapper(stderr_bytes, encoding="cp936", errors="strict")
                    try:
                        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr), patch.object(run_api, "credentials", return_value=("offline-test-secret", "https://example.test/v1")), patch.object(run_api.shutil, "which", return_value="codex"), patch.object(run_api, "probe_local_tools", return_value={"passed": True, "diagnostic": diagnostic}), patch.object(run_api, "probe_dependencies", return_value={"passed": True}), patch.object(run_api.subprocess, "Popen") as launch:
                            if argument_error:
                                with self.assertRaises(SystemExit) as error:
                                    run_api.main(["--unknown-\ufffd"])
                                self.assertEqual(error.exception.code, 2)
                            else:
                                self.assertEqual(run_api.main(["--config", str(config), "--doctor"]), 0)
                            launch.assert_not_called()
                        stdout.flush()
                        stderr.flush()
                        if argument_error:
                            self.assertIn("--unknown-\ufffd", stderr_bytes.getvalue().decode("utf-8"))
                        else:
                            report = json.loads(stdout_bytes.getvalue().decode("utf-8"))
                            self.assertEqual(report["local_tool_preflight"]["diagnostic"], diagnostic)
                    finally:
                        stdout.close()
                        stderr.close()

    def test_provider_and_shell_isolation(self):
        command = run_api.make_command("codex", Path("case 中文"), Path("image name.png"),
                                       "https://example.test/v1", "gpt-6-astra", "xhigh")
        config = tomllib.loads("\n".join(command[i + 1] for i, v in enumerate(command) if v == "-c"))
        provider = config["model_providers"][config["model_provider"]]
        self.assertEqual(provider["env_key"], run_api.PRIVATE_KEY_ENV)
        self.assertFalse(provider["requires_openai_auth"])
        self.assertEqual(provider["wire_api"], "responses")
        self.assertEqual(config["shell_environment_policy"]["filters"]["*KEY*"], "exclude")
        self.assertIn("--ignore-user-config", command)
        self.assertNotIn("--dangerously-bypass-approvals-and-sandbox", command)
        if run_api.sys.platform == "win32":
            self.assertEqual(config["windows"]["sandbox"], "elevated")
        with patch.dict(os.environ, {"OPENAI_API_KEY": "unused", "CODEX_API_KEY": "unused", "AUTH_CREDENTIAL": "selected-secret"}):
            env = run_api.worker_environment("selected-secret", "AUTH_CREDENTIAL")
        self.assertEqual(env[run_api.PRIVATE_KEY_ENV], "selected-secret")
        self.assertNotIn("OPENAI_API_KEY", env)
        self.assertNotIn("CODEX_API_KEY", env)
        self.assertNotIn("AUTH_CREDENTIAL", env)
        self.assertEqual(command[-1], "-")

    def test_dotenv_parsing_without_shell_execution(self):
        with tempfile.TemporaryDirectory() as d:
            env = Path(d) / ".env.local"
            env.write_text('export OPENAI_API_KEY="test#literal" # comment\nOPENAI_BASE_URL=https://example.test/v1 # comment\nOTHER=$(do-not-run)\n', encoding="utf-8")
            values = run_api.read_env(env)
            self.assertEqual(values["OPENAI_API_KEY"], "test#literal")
            self.assertEqual(values["OPENAI_BASE_URL"], "https://example.test/v1")
            self.assertEqual(values["OTHER"], "$(do-not-run)")
        with self.assertRaises(ValueError):
            run_api.credentials({"base_url": "https://example.test/v1?key=secret"})

    def test_dry_run_and_missing_key_cannot_start_worker(self):
        with tempfile.TemporaryDirectory() as d, patch.dict(os.environ, {}, clear=True):
            root = Path(d)
            image = root / "source.png"
            image.write_bytes(b"dry-run-only")
            config = root / "settings.json"
            config.write_text('{"model":"gpt-6-astra"}', encoding="utf-8")
            argv = ["--config", str(config), "--image", str(image), "--out", str(root / "out")]
            with patch.object(run_api.subprocess, "Popen") as launch, patch.object(run_api.subprocess, "run") as probe, patch.object(run_api.shutil, "which", return_value="codex"), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(run_api.main(argv + ["--dry-run"]), 0)
                self.assertFalse((root / "out").exists())
                with self.assertRaises(ValueError):
                    run_api.main(argv)
                launch.assert_not_called()
                probe.assert_not_called()

    def test_usage_redaction_and_failed_turn_not_success(self):
        secret = "sk-test-secret-for-offline-check"
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            image = root / "source.png"
            image.write_bytes(b"mock-image")
            config = root / "settings.json"
            config.write_text('{"model":"gpt-6-astra","key_env":"TEST_ASSET_KEY"}', encoding="utf-8")
            for failed in (False, True):
                out = root / ("failed" if failed else "success")
                class Process:
                    def __init__(self, command, **kwargs):
                        self.stdin = io.StringIO()
                        events = [json.dumps({"type": "runner.log", "text": secret}), json.dumps({"type": "turn.completed", "usage": {"input_tokens": 20, "cached_input_tokens": 5, "output_tokens": 3}})]
                        if failed:
                            events.append(json.dumps({"type": "turn.failed", "error": {"message": "probe"}}))
                        self.stdout = iter(x + "\n" for x in events)
                    def wait(self): return 0
                with patch.dict(os.environ, {"TEST_ASSET_KEY": secret}), patch.object(run_api.shutil, "which", return_value="codex"), patch.object(run_api.subprocess, "Popen", Process), patch.object(run_api, "probe_local_tools", return_value={"passed": True, "status": "mock_passed"}), patch.object(run_api, "probe_dependencies", return_value={"passed": True}), contextlib.redirect_stdout(io.StringIO()):
                    code = run_api.main(["--config", str(config), "--image", str(image), "--out", str(out)])
                self.assertEqual(code, int(failed))
                manifest = json.loads((out / "api_execution.json").read_text())
                self.assertEqual(manifest["usage"]["input_tokens"], 20)
                self.assertEqual(manifest["state"], "failed" if failed else "executor_completed")
                prompt = (out / "api_prompt.txt").read_text(encoding="utf-8")
                self.assertEqual("Do not substitute a Blender-only asset" in prompt,
                                 Path(run_api.__file__).resolve().parents[1].name == "trellis2-native-refine")
                for file in out.iterdir():
                    self.assertNotIn(secret, file.read_text(encoding="utf-8"))

    def test_failed_local_probe_stops_before_api(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            image = root / "source.png"
            image.write_bytes(b"mock-image")
            config = root / "settings.json"
            config.write_text('{"model":"gpt-6-astra","key_env":"TEST_ASSET_KEY"}', encoding="utf-8")
            argv = ["--config", str(config), "--image", str(image), "--out", str(root / "out")]
            with patch.dict(os.environ, {"TEST_ASSET_KEY": "offline-test-secret"}), patch.object(run_api.shutil, "which", return_value="codex"), patch.object(run_api, "probe_local_tools", return_value={"passed": False, "status": "windows_logon_type_denied_1385"}) as probe, patch.object(run_api.subprocess, "Popen") as launch, contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(run_api.main(argv + ["--dry-run"]), 0)
                probe.assert_not_called()
                self.assertEqual(run_api.main(argv), 2)
                self.assertEqual(run_api.main(["--config", str(config), "--doctor"]), 2)
                launch.assert_not_called()
            manifest = json.loads((root / "out/api_execution.json").read_text())
            self.assertEqual(manifest["state"], "blocked_local_preflight")
            self.assertFalse(manifest["api_started"])
            self.assertEqual(manifest["usage"]["input_tokens"], 0)

    def test_probe_command_and_failure_modes(self):
        with tempfile.TemporaryDirectory() as d, patch.object(run_api.sys, "platform", "win32"), patch.object(run_api.shutil, "which", return_value="powershell.exe"), patch.dict(os.environ, {"OPENAI_API_KEY": "do-not-pass", "OTHER_SECRET": "do-not-pass", "AUTH_CREDENTIAL": "do-not-pass"}):
            def success(command, **kwargs):
                self.assertEqual(command[1], "sandbox")
                self.assertNotIn("windows", command)
                self.assertIn("--include-managed-config", command)
                self.assertIn('windows.sandbox="elevated"', command)
                self.assertNotIn("OPENAI_API_KEY", kwargs["env"])
                self.assertNotIn("OTHER_SECRET", kwargs["env"])
                self.assertNotIn("AUTH_CREDENTIAL", kwargs["env"])
                script = run_api.base64.b64decode(command[-1]).decode("utf-16-le")
                marker = run_api.re.search(r"CODEX_ASSET_PROBE_[0-9a-f]+", script).group()
                return SimpleNamespace(returncode=0, stdout=marker + "\n")
            with patch.object(run_api.subprocess, "run", side_effect=success):
                self.assertTrue(run_api.probe_local_tools("codex", Path(d), Path(d), source_key_env="AUTH_CREDENTIAL")["passed"])
            for code, output, status in [(1, "CreateProcessWithLogonW failed: 1385", "windows_logon_type_denied_1385"), (0, "no success marker", "sandbox_command_failed")]:
                with patch.object(run_api.subprocess, "run", return_value=SimpleNamespace(returncode=code, stdout=output)):
                    result = run_api.probe_local_tools("codex", Path(d), Path(d))
                    self.assertFalse(result["passed"])
                    self.assertEqual(result["status"], status)
            for exc, status in [(run_api.subprocess.TimeoutExpired("probe", 30), "sandbox_probe_timeout"), (OSError("probe"), "sandbox_probe_start_failed")]:
                with patch.object(run_api.subprocess, "run", side_effect=exc):
                    self.assertEqual(run_api.probe_local_tools("codex", Path(d), Path(d))["status"], status)

    def test_process_start_failure_does_not_claim_api_started(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            image = root / "source.png"
            image.write_bytes(b"mock-image")
            config = root / "settings.json"
            config.write_text('{"key_env":"TEST_ASSET_KEY"}', encoding="utf-8")
            with patch.dict(os.environ, {"TEST_ASSET_KEY": "offline-test-secret"}), patch.object(run_api.shutil, "which", return_value="codex"), patch.object(run_api, "probe_local_tools", return_value={"passed": True}), patch.object(run_api, "probe_dependencies", return_value={"passed": True}), patch.object(run_api.subprocess, "Popen", side_effect=OSError("start failed")):
                with self.assertRaises(OSError):
                    run_api.main(["--config", str(config), "--image", str(image), "--out", str(root / "out")])
            manifest = json.loads((root / "out/api_execution.json").read_text())
            self.assertFalse(manifest["api_started"])
            self.assertEqual(manifest["state"], "interrupted_or_failed")

    def test_unavailable_trellis_stops_api_and_is_reported_by_doctor(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            image, config = root / "image.png", root / "config.json"
            image.write_bytes(b"offline")
            config.write_text('{}', encoding="utf-8")
            dependencies = {"passed": False, "checks": {"python_imports": {"passed": True},
                            "blender": {"passed": True}, "trellis": {"passed": False,
                            "status": "dependency_command_failed", "diagnostic": "Could not resolve hostname"}}}
            with patch.object(run_api, "credentials", return_value=("offline-only", "https://example.test/v1")), patch.object(run_api.shutil, "which", return_value="codex"), patch.object(run_api, "probe_local_tools", return_value={"passed": True}), patch.object(run_api, "probe_dependencies", return_value=dependencies), patch.object(run_api.subprocess, "Popen") as launch:
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(run_api.main(["--config", str(config), "--image", str(image), "--out", str(root / "out")]), 2)
                stdout = io.StringIO()
                with contextlib.redirect_stdout(stdout):
                    self.assertEqual(run_api.main(["--config", str(config), "--doctor"]), 2)
                launch.assert_not_called()
            report = json.loads(stdout.getvalue())
            self.assertEqual(report["dependency_preflight"], dependencies)
            self.assertTrue(report["local_tool_preflight"]["passed"])
            manifest = json.loads((root / "out" / "api_execution.json").read_text())
            self.assertEqual(manifest["state"], "blocked_dependency_preflight")
            self.assertEqual(manifest["phase"], "dependency_preflight")
            self.assertFalse(manifest["api_started"])
            self.assertEqual(manifest["usage"], {"input_tokens": 0, "cached_input_tokens": 0, "output_tokens": 0})

    def test_dependency_checks_use_sandbox_and_validate_actual_outputs(self):
        with tempfile.TemporaryDirectory() as d, patch.object(run_api.sys, "platform", "win32"):
            root = Path(d)
            python, blender = root / "python.exe", root / "blender.exe"
            python.touch()
            blender.touch()
            settings = {"runtime_python": str(python), "runtime_blender": str(blender)}
            def response(command, **kwargs):
                self.assertEqual(command[1], "sandbox")
                self.assertIn("--include-managed-config", command)
                config = tomllib.loads("\n".join(command[i + 1] for i, value in enumerate(command[:command.index("--")]) if value == "-c"))
                self.assertEqual(config["windows"]["sandbox"], "elevated")
                profile = config["permissions"][command[command.index("--permission-profile") + 1]]
                self.assertEqual(profile["extends"], ":workspace")
                self.assertTrue(profile["network"]["enabled"])
                self.assertNotIn("OPENAI_API_KEY", kwargs["env"])
                self.assertNotIn("AUTH_CREDENTIAL", kwargs["env"])
                if command[-1] == "--version":
                    output = "Blender 5.2.1\n"
                elif command[-1] == "doctor":
                    self.assertEqual(command[-2], str(root.resolve() / "references" / "server.json"))
                    output = '{"ok":true}'
                else:
                    self.assertIn("numpy, scipy, trimesh, PIL, mujoco", command[-1])
                    output = run_api.re.search(r"CODEX_ASSET_IMPORTS_[0-9a-f]+", command[-1]).group() + "\n"
                return SimpleNamespace(returncode=0, stdout=output, stderr="")
            with patch.dict(os.environ, {"OPENAI_API_KEY": "never-forward", "AUTH_CREDENTIAL": "never-forward"}), patch.object(run_api.subprocess, "run", side_effect=response) as run:
                self.assertTrue(run_api.probe_dependencies("codex", root, root, settings, "AUTH_CREDENTIAL")["passed"])
                self.assertEqual(run.call_count, 3)
            for bad_output in ('{"ok":false}', '{"ok":"true"}', 'not JSON'):
                def broken(command, **kwargs):
                    if command[-1] == "doctor":
                        return SimpleNamespace(returncode=0, stdout=bad_output, stderr="")
                    return response(command, **kwargs)
                with self.subTest(output=bad_output), patch.dict(os.environ, {}, clear=True), patch.object(run_api.subprocess, "run", side_effect=broken) as run:
                    report = run_api.probe_dependencies("codex", root, root, settings)
                    self.assertFalse(report["passed"])
                    self.assertFalse(report["checks"]["trellis"]["passed"])
                    self.assertEqual(run.call_count, 3)

    def test_dependency_timeout_and_missing_runtime_fail_without_retries(self):
        with tempfile.TemporaryDirectory() as d, patch.object(run_api.sys, "platform", "win32"):
            root = Path(d)
            runtime = root / "runtime.exe"
            runtime.touch()
            settings = {"runtime_python": str(runtime), "runtime_blender": str(runtime)}
            for error, status in [(run_api.subprocess.TimeoutExpired("probe", 30), "dependency_timeout"),
                                  (OSError("blocked"), "dependency_start_failed")]:
                with self.subTest(status=status), patch.object(run_api.subprocess, "run", side_effect=error) as run:
                    report = run_api.probe_dependencies("codex", root, root, settings)
                    self.assertFalse(report["passed"])
                    self.assertEqual(report["checks"]["python_imports"]["status"], status)
                    self.assertEqual(report["checks"]["trellis"]["status"], "not_run_python_imports_failed")
                    self.assertEqual(run.call_count, 2)
            with patch.object(run_api.subprocess, "run") as run:
                self.assertFalse(run_api.probe_dependencies("codex", root, root, {})["passed"])
                run.assert_not_called()

    def test_existing_non_windows_configs_remain_explicitly_unchecked(self):
        with patch.object(run_api.sys, "platform", "linux"), patch.object(run_api.subprocess, "run") as run:
            unchecked = run_api.probe_dependencies("codex", Path.cwd(), Path.cwd(), {})
            self.assertIsNone(unchecked["passed"])
            self.assertEqual(unchecked["status"], "not_checked_non_windows")
            required = run_api.probe_dependencies("codex", Path.cwd(), Path.cwd(), {"require_dependency_preflight": True})
            self.assertFalse(required["passed"])
            self.assertEqual(required["status"], "unsupported_dependency_sandbox")
            run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
