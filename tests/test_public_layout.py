"""Integrity checks for the public repository layout; no inference or services."""
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('public_layout_execute', ROOT / 'execute.py')
execute = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(execute)


class PublicLayoutTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        manifest = json.loads((ROOT / 'checksums.json').read_text(encoding='utf-8'))
        for name in [*manifest, 'checksums.json']:
            target = self.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / name, target)

    def tearDown(self):
        self.temp.cleanup()

    def verify(self):
        with patch.object(execute, 'ROOT', self.root):
            return execute.verify()

    def test_git_and_editable_config_do_not_break_source_verification(self):
        for name in ['.git/HEAD', '.venv/pyvenv.cfg', 'config/runtime.local.json', 'inputs/example.png']:
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b'local user data')
        self.assertTrue(self.verify()['ok'])

    def test_changed_method_is_rejected(self):
        path = self.root / 'method/WORKER_PROMPT.md'
        path.write_bytes(path.read_bytes() + b'changed')
        report = self.verify()
        self.assertFalse(report['ok'])
        self.assertIn('method/WORKER_PROMPT.md', report['mismatch'])

    def test_missing_source_is_rejected(self):
        (self.root / 'execute.py').unlink()
        report = self.verify()
        self.assertFalse(report['ok'])
        self.assertIn('execute.py', report['mismatch'])

    def test_extra_method_file_is_rejected(self):
        (self.root / 'method/unexpected.py').write_text('unexpected', encoding='utf-8')
        report = self.verify()
        self.assertFalse(report['ok'])
        self.assertIn('method/unexpected.py', report['extra'])


if __name__ == '__main__':
    unittest.main()
