import base64, importlib.util, json, os, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('reproduce',ROOT/'reproduce.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class PrepareTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.p=Path(self.tmp.name);self.img=self.p/'图片.png';self.img.write_bytes(base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a52sAAAAASUVORK5CYII='))
        self.cfg=json.loads((ROOT/'examples/runtime.windows-ssh.json').read_text(encoding='utf-8'));self.cfg['python']=str(self.p/'python.exe');self.cfg['blender']=str(self.p/'blender.exe');self.cp=self.p/'runtime.json';m.save(self.cp,self.cfg)
    def tearDown(self):self.tmp.cleanup()
    def test_packet_has_only_declared_input_and_method(self):
        out=self.p/'new';r=m.prepare(self.img,self.cp,out);self.assertFalse(r['generation_started']);self.assertEqual(m.sha(self.img),m.load(out/'identity.json')['input_sha256']);self.assertFalse((out/'events.jsonl').exists());self.assertFalse((out/'case_results').exists())
    def test_nonempty_output_rejected(self):
        out=self.p/'new';out.mkdir();(out/'old').write_text('keep')
        with self.assertRaises(ValueError):m.prepare(self.img,self.cp,out)
        self.assertEqual((out/'old').read_text(),'keep')
    def test_native_roots_are_unique(self):
        m.prepare(self.img,self.cp,self.p/'a');m.prepare(self.img,self.cp,self.p/'b');self.assertNotEqual(m.load(self.p/'a/identity.json')['native_job_root'],m.load(self.p/'b/identity.json')['native_job_root'])
    def test_wrong_native_parameters_rejected(self):
        self.cfg['trellis']['defaults']['resolution']=512;m.save(self.cp,self.cfg)
        with self.assertRaises(ValueError):m.prepare(self.img,self.cp,self.p/'bad')
    def test_no_extra_context_or_credentials(self):
        self.cfg['context']='historical advice';m.save(self.cp,self.cfg)
        with self.assertRaises(ValueError):m.config(self.cp)
    def test_no_resume_or_parent_environment(self):
        with patch.dict(os.environ,{'CODEX_THREAD_ID':'parent','CODEX_HOME':'own-login','OPENAI_API_KEY':'test-dummy'}):
            e=m.clean_env();self.assertNotIn('CODEX_THREAD_ID',e);self.assertNotIn('OPENAI_API_KEY',e);self.assertEqual(e['CODEX_HOME'],'own-login')
        m.prepare(self.img,self.cp,self.p/'new');cmd=m.command(self.p/'new',self.cfg);self.assertNotIn('resume',cmd);self.assertIn('features.memories=false',cmd)
    def test_input_or_method_tamper_rejected_before_execution(self):
        out=self.p/'new';m.prepare(self.img,self.cp,out);(out/'input/source.png').write_bytes(b'changed')
        with patch.object(m,'doctor',side_effect=AssertionError('must not start')):
            with self.assertRaises(ValueError):m.run(out)
if __name__=='__main__':unittest.main()
