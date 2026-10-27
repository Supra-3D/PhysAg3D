"""Offline prompt parity and dry-run contract tests; no model or external tools."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import asset_prompt
import run_api


class PromptTests(unittest.TestCase):
    def test_native_route_retains_authorship_and_no_substitution(self):
        prompt = asset_prompt.build_asset_prompt(
            Path('/skills/trellis2-native-refine'), Path('/input.png'), Path('/case'), {}
        )
        for requirement in (
            'Observe it yourself; author case-specific Blender',
            'inspect actual renders and iterate from the evidence yourself',
            'Do not create additional agents or invoke\nanother LLM/API/session',
            'save diagnostics and STOP',
            'Do not substitute a Blender-only asset',
            'Do not read credential files or print environment secrets',
        ):
            self.assertIn(requirement, prompt)
        for test_condition in ('12 steps', '24 steps', '20%', '3 mm', '1.2 mm',
                               'representative deployment test', 'adopted_job'):
            self.assertNotIn(test_condition, prompt)

    def test_host_facts_do_not_change_modeling_requirements(self):
        args = (Path('/skills/trellis2-native-refine'), Path('/input.png'), Path('/case'))
        first = dict(runtime_python='/windows/python.exe', runtime_blender='/windows/blender.exe',
                     transport_hint='Use the configured authenticated SSH transport.')
        second = dict(runtime_python='/linux/python', runtime_blender='/linux/blender',
                      transport_hint='Use the configured managed Unix broker transport.')
        a = asset_prompt.build_asset_prompt(*args, first, context='User requirement: inspect the back.')
        b = asset_prompt.build_asset_prompt(*args, second, context='User requirement: inspect the back.')
        for key in first:
            a = a.replace(first[key], '{' + key + '}')
            b = b.replace(second[key], '{' + key + '}')
        self.assertEqual(a, b)
        self.assertIn('User requirement: inspect the back.', a)

    def test_runtime_configuration_is_not_dumped_into_prompt(self):
        settings = dict(env_file='/private/key.env', key_env='PRIVATE_AUTH',
                        unused_secret='do-not-display', runtime_python='/tools/python',
                        runtime_blender='/tools/blender', transport_hint='Use the active profile.')
        prompt = asset_prompt.build_asset_prompt(Path('/skills/trellis2-native-refine'),
                                                Path('/input.png'), Path('/case'), settings,
                                                writable_dirs=['/api/tmp'])
        self.assertIn('Configured Python: /tools/python', prompt)
        self.assertIn('Configured Blender: /tools/blender', prompt)
        self.assertIn("['/api/tmp']", prompt)
        for secret in ('/private/key.env', 'PRIVATE_AUTH', 'do-not-display'):
            self.assertNotIn(secret, prompt)

    def test_dry_run_outputs_exact_dispatched_prompt_and_reads_context(self):
        selected_key = 'offline-selected-key'
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            skill = root / 'trellis2-native-refine'
            (skill / 'scripts').mkdir(parents=True)
            (skill / 'SKILL.md').write_text('Offline fixture only', encoding='utf-8')
            image, config, context = root / 'image.png', root / 'config.json', root / 'context.txt'
            image.write_bytes(b'offline-fixture')
            config.write_text(json.dumps({'runtime_python': '/tools/python',
                                          'runtime_blender': '/tools/blender',
                                          'transport_hint': 'Use the configured transport.'}), encoding='utf-8')
            context.write_text('\ufeffUser-only context: keep the rear opening.\n中文要求。', encoding='utf-8')
            output = root / 'case'
            argv = ['--config', str(config), '--image', str(image), '--out', str(output),
                    '--context-file', str(context)]
            captured = {}

            class Input(io.StringIO):
                def close(self):
                    captured['prompt'] = self.getvalue()
                    super().close()

            class Process:
                def __init__(self, command, **kwargs):
                    captured['command'] = command
                    self.stdin = Input()
                    self.stdout = iter([json.dumps({'type': 'turn.completed', 'usage': {}}) + '\n'])

                def wait(self):
                    return 0

            with contextlib.ExitStack() as stack:
                stack.enter_context(patch.object(run_api, '__file__', str(skill / 'scripts/run_api.py')))
                stack.enter_context(patch.object(run_api, 'credentials', return_value=(selected_key, 'https://example.test/v1')))
                stack.enter_context(patch.object(run_api.shutil, 'which', return_value='codex'))
                probe = stack.enter_context(patch.object(run_api.subprocess, 'run'))
                for name in ('probe_local_tools', 'probe_dependencies'):
                    if hasattr(run_api, name):
                        stack.enter_context(patch.object(run_api, name, return_value={'passed': True}))
                stdout = io.StringIO()
                with patch.object(run_api.subprocess, 'Popen') as no_launch, contextlib.redirect_stdout(stdout):
                    self.assertEqual(run_api.main(argv + ['--dry-run']), 0)
                    no_launch.assert_not_called()
                dry = json.loads(stdout.getvalue())
                self.assertFalse(output.exists())
                self.assertIn('User-only context: keep the rear opening.\n中文要求。', dry['prompt'])
                self.assertIn('Do not substitute a Blender-only asset', dry['prompt'])
                self.assertNotIn(selected_key, stdout.getvalue())
                with patch.object(run_api.subprocess, 'Popen', Process), contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(run_api.main(argv), 0)
                self.assertEqual(dry['prompt'], captured['prompt'])
                self.assertEqual(dry['command'], captured['command'])
                self.assertEqual((output / 'api_prompt.txt').read_text(encoding='utf-8'), dry['prompt'])
                self.assertIn('--image', captured['command'])
                self.assertEqual(captured['command'][captured['command'].index('--image') + 1], str(image.resolve()))
                probe.assert_not_called()

    def test_dry_run_rejects_secret_or_unreadable_context_without_side_effects(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            image, config, context = root / 'image.png', root / 'config.json', root / 'context.txt'
            image.write_bytes(b'offline-fixture')
            config.write_text('{}', encoding='utf-8')
            context.write_text('never print offline-selected-key', encoding='utf-8')
            argv = ['--config', str(config), '--image', str(image), '--out', str(root / 'case'),
                    '--context-file', str(context), '--dry-run']
            with patch.object(run_api, 'credentials', return_value=('offline-selected-key', 'https://example.test/v1')), \
                    patch.object(run_api.shutil, 'which', return_value='codex'), \
                    patch.object(run_api.subprocess, 'Popen') as launch, \
                    patch.object(run_api.subprocess, 'run') as probe:
                stdout = io.StringIO()
                with contextlib.redirect_stdout(stdout), self.assertRaises(ValueError):
                    run_api.main(argv)
                self.assertEqual(stdout.getvalue(), '')
                context.unlink()
                with contextlib.redirect_stdout(stdout), self.assertRaises(OSError):
                    run_api.main(argv)
                self.assertEqual(stdout.getvalue(), '')
                context.write_text('No credentials in this context.', encoding='utf-8')
                config.write_text(json.dumps({'transport_hint': 'offline-selected-key'}), encoding='utf-8')
                with contextlib.redirect_stdout(stdout), self.assertRaises(ValueError):
                    run_api.main(argv)
                self.assertEqual(stdout.getvalue(), '')
                self.assertFalse((root / 'case').exists())
                launch.assert_not_called()
                probe.assert_not_called()

    def test_dry_run_without_key_still_exposes_offline_prompt(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            image, config = root / 'image.png', root / 'config.json'
            image.write_bytes(b'offline-fixture')
            config.write_text('{}', encoding='utf-8')
            with patch.object(run_api, 'credentials', return_value=('', 'https://example.test/v1')), \
                    patch.object(run_api.shutil, 'which', return_value=None), \
                    patch.object(run_api.subprocess, 'Popen') as launch, \
                    patch.object(run_api.subprocess, 'run') as probe:
                stdout = io.StringIO()
                with contextlib.redirect_stdout(stdout):
                    self.assertEqual(run_api.main(['--config', str(config), '--image', str(image),
                                                   '--out', str(root / 'case'), '--dry-run']), 0)
                report = json.loads(stdout.getvalue())
                self.assertFalse(report['key_present'])
                self.assertFalse(report['started'])
                self.assertTrue(report['prompt'])
                self.assertFalse((root / 'case').exists())
                launch.assert_not_called()
                probe.assert_not_called()


if __name__ == '__main__':
    unittest.main()
