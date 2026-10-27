"""Offline tests of actual submit construction. No RPC, GPU, model or receipt writes."""
import argparse
import ast
import copy
import importlib.util
import json
from pathlib import Path
import sys
import unittest
from unittest import mock

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location('native_defaults_client', HERE / 'trellis2_tool.py')
CLIENT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CLIENT)


class InferenceDefaultsTests(unittest.TestCase):
    def setUp(self):
        self.config = json.loads((HERE.parent / 'references/server.json').read_text(encoding='utf-8'))
        self.receipt = HERE / '__offline_nonexistent__' / 'receipt.json'
        self.image = HERE / '__offline_nonexistent__' / 'image.png'
        self.mesh = HERE / '__offline_nonexistent__' / 'mesh.npz'
        if self.receipt.exists():
            raise AssertionError('Offline sentinel receipt must not exist')
        self.requests = []
        self.write_records = []

    def invoke(self, route='native', **overrides):
        config_before = copy.deepcopy(self.config)
        values = dict(route=route, image=str(self.image), mask=None,
                      mesh=str(self.mesh) if route == 'texture' else None,
                      resolution=None, steps=None, texture_size=None, seed=None,
                      min_free_gb=None, gpu='auto', receipt=str(self.receipt), retry_of=None)
        values.update(overrides)

        def fake_rpc(request, destination=None):
            if request['action'] == 'gpus':
                return {'gpus': [{'index': '0', 'free_mib': 131072}]}
            if request['action'] == 'submit':
                self.requests.append(request)
                return {'state': 'offline_mock_not_submitted'}
            raise AssertionError('Unexpected RPC action: ' + request['action'])

        def fake_write(path, value, **kwargs):
            self.write_records.append((str(path), copy.deepcopy(value), kwargs))

        real_read_bytes = Path.read_bytes

        def read_fixture_or_source(path):
            return b'offline-mesh-fixture' if path == self.mesh else real_read_bytes(path)

        with mock.patch.object(CLIENT, 'rpc', side_effect=fake_rpc), \
                mock.patch.object(CLIENT, 'write_json', side_effect=fake_write), \
                mock.patch.object(CLIENT, 'prepare_image', return_value=(b'offline-image-fixture', [8, 8])), \
                mock.patch.object(CLIENT, 'sha_file', return_value='0' * 64), \
                mock.patch.object(CLIENT, 'check_texture_mesh'), \
                mock.patch.object(Path, 'read_bytes', autospec=True, side_effect=read_fixture_or_source):
            response = CLIENT.submit(argparse.Namespace(**values), self.config)
        self.assertEqual(response['state'], 'offline_mock_not_submitted')
        self.assertEqual(len(self.requests), 1)
        self.assertEqual(len(self.write_records), 1)
        self.assertEqual(self.config, config_before, 'Broker profile must not be mutated')
        self.assertEqual(self.requests[0]['config'], config_before)
        self.assertFalse(self.receipt.exists(), 'Receipt writes must stay intercepted')
        return self.requests[0]

    def test_native_omitted_cli_uses_quality_baseline(self):
        request = self.invoke()
        self.assertEqual(request['settings'], dict(resolution=1024, steps=24, texture_size=2048,
                         seed=42, min_free_gb=self.config['defaults']['min_free_gb'],
                         route='native', gpu='0'))

    def test_texture_keeps_profile_defaults(self):
        request = self.invoke(route='texture')
        self.assertEqual(request['settings'], {**self.config['defaults'], 'route': 'texture', 'gpu': '0'})

    def test_explicit_cli_wins_for_every_parameter(self):
        request = self.invoke(resolution=512, steps=7, texture_size=4096, seed=9, min_free_gb=32)
        self.assertEqual(request['settings'], dict(resolution=512, steps=7, texture_size=4096,
                         seed=9, min_free_gb=32, route='native', gpu='0'))

    def test_memory_gate_remains_from_selected_profile(self):
        self.config['defaults']['min_free_gb'] = 60
        request = self.invoke()
        self.assertEqual(request['settings']['min_free_gb'], 60)
        self.assertEqual(request['settings']['steps'], 24)

    def test_sidecar_contains_only_native_quality_defaults(self):
        data = json.loads((HERE.parent / 'references/inference-defaults.json').read_text(encoding='utf-8'))
        self.assertEqual(data, {'native': {'resolution': 1024, 'steps': 24, 'texture_size': 2048, 'seed': 42}})

    def test_actual_runner_maps_1024_to_cascade(self):
        tree = ast.parse((HERE / 'run_trellis.py').read_text(encoding='utf-8'))
        statement = next(n for n in ast.walk(tree) if isinstance(n, ast.Assign)
                         and any(isinstance(t, ast.Name) and t.id == 'pipeline_type' for t in n.targets))
        scope = {'args': argparse.Namespace(resolution=self.invoke()['settings']['resolution'])}
        exec(compile(ast.Module(body=[statement], type_ignores=[]), 'runner_pipeline_selection_only', 'exec'), scope)
        self.assertEqual(scope['pipeline_type'], '1024_cascade')

    def test_changed_request_rejects_old_receipt_before_rpc(self):
        real_exists = Path.exists
        real_read_json = CLIENT.read_json

        def exists(path):
            return path == self.receipt or real_exists(path)

        def read_json(path):
            if Path(path) == self.receipt:
                return {'fingerprint': 'old-low-quality-request'}
            return real_read_json(path)

        values = dict(route='native', image=str(self.image), mask=None, mesh=None,
                      resolution=None, steps=None, texture_size=None, seed=None,
                      min_free_gb=None, gpu='auto', receipt=str(self.receipt), retry_of=None)
        with mock.patch.object(CLIENT, 'rpc') as rpc, \
                mock.patch.object(CLIENT, 'write_json') as write, \
                mock.patch.object(CLIENT, 'prepare_image', return_value=(b'fixture', [8, 8])), \
                mock.patch.object(CLIENT, 'sha_file', return_value='0' * 64), \
                mock.patch.object(CLIENT, 'read_json', side_effect=read_json), \
                mock.patch.object(Path, 'exists', autospec=True, side_effect=exists):
            with self.assertRaisesRegex(ValueError, 'Receipt belongs to a different request'):
                CLIENT.submit(argparse.Namespace(**values), self.config)
            rpc.assert_not_called()
            write.assert_not_called()


if __name__ == '__main__':
    unittest.main(verbosity=2)
