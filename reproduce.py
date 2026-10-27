"""Portable preparation and launch utilities for PhysAg3D.

No model call occurs in verify, prepare, plan, or doctor. Run explicitly launches
the configured Codex subscription worker; no API credentials are accepted here.
"""
from pathlib import Path, PurePosixPath
import argparse, hashlib, importlib.metadata, json, os, platform, re, shutil
import subprocess, sys, uuid
from datetime import datetime, timezone

ROOT=Path(__file__).resolve().parent
LABEL='PhysAg3D'
FLAGS=['--ignore-user-config','--skip-git-repo-check','--approve-for-me']
def load(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def save(p,d):Path(p).write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def digest_files(base):
    return {p.relative_to(base).as_posix():sha(p) for p in sorted(base.rglob('*')) if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc'}
def verify():
    expected=load(ROOT/'checksums.json');actual={}
    # Check the declared source roots; Git metadata, user config and inputs are separate.
    for name in sorted({PurePosixPath(n).parts[0] for n in expected}):
        path=ROOT/name
        if path.is_dir():
            actual.update({name+'/'+n:h for n,h in digest_files(path).items()})
        elif path.is_file():
            actual[name]=sha(path)
    bad=[n for n in expected if expected[n]!=actual.get(n)];extra=sorted(set(actual)-set(expected))
    return {'ok':not bad and not extra,'files':len(expected),'mismatch':bad,'extra':extra,'scope':'file identity, not generation quality'}
def config(p):
    d=load(p)
    allowed={'python','blender','codex','model','reasoning_effort','gpu','trellis','max_case_active_seconds'}
    unknown=set(d)-allowed
    if unknown:raise ValueError('Unknown configuration keys: '+','.join(sorted(unknown)))
    if d.get('model')!='gpt-6-astra' or d.get('reasoning_effort')!='high':
        raise ValueError('Historical assisted protocol requires gpt-6-astra/high. A substitute is a separately labelled experiment.')
    for key in ['python','blender']:
        if not Path(d[key]).is_absolute():raise ValueError(key+' must be an absolute target-machine path')
    t=d['trellis'];allowed_t={'profile','transport','ssh_host','known_hosts','python','runtime','model','dino','rembg','jobs_root','defaults'}
    if set(t)-allowed_t:raise ValueError('Unknown TRELLIS profile keys')
    for key in ['python','runtime','model','dino','rembg','jobs_root']:
        if not isinstance(t.get(key),str) or not t[key].startswith('/') or '..' in PurePosixPath(t[key]).parts:
            raise ValueError('TRELLIS '+key+' requires an absolute Linux path without ..')
    if t.get('transport') not in ['ssh','local']:raise ValueError('transport must be ssh or local')
    if t['transport']=='ssh' and (not t.get('ssh_host') or t['ssh_host'].startswith('-')):raise ValueError('Supply your own SSH host alias')
    fixed={'resolution':1024,'steps':24,'texture_size':2048,'seed':42}
    if any(t.get('defaults',{}).get(k)!=v for k,v in fixed.items()):raise ValueError('Native settings must be 1024/24/2048/42')
    if not isinstance(d.get('max_case_active_seconds',10800),int) or d.get('max_case_active_seconds',10800)<=0:raise ValueError('Invalid time budget')
    return d
def prepare(image,cfg,out):
    check=verify()
    if not check['ok']:raise ValueError('Release checksum mismatch')
    image=Path(image).resolve(strict=True);out=Path(out).resolve()
    if not image.is_file():raise ValueError('Image is not a file')
    if out.exists() and (not out.is_dir() or any(out.iterdir())):raise ValueError('Use a new empty output directory; no resume or overwrite')
    if out==ROOT or ROOT in out.parents:raise ValueError('Put the case outside the code release and evaluation directories')
    d=config(cfg);run_id='native_refine_'+uuid.uuid4().hex
    out.mkdir(parents=True,exist_ok=True);(out/'input').mkdir()
    img=out/'input'/('source'+image.suffix.lower());shutil.copy2(image,img)
    shutil.copytree(ROOT/'method',out/'method')
    t=dict(d['trellis']);t['jobs_root']=str(PurePosixPath(t['jobs_root'])/run_id)
    t['profile']=run_id;save(out/'method/server.json',t)
    # Both copies point only at this run; no accidental historical default path.
    save(out/'method/trellis2-native-refine/references/server.json',t)
    rt={'case_id':out.name,'source':str(img),'method_dir':str(out/'method'),'profile':str(out/'method/server.json'),'python':d['python'],'blender':d['blender'],'gpu':d.get('gpu','auto'),'max_case_active_seconds':d.get('max_case_active_seconds',10800),'max_physics_acceptance_passes':2,'max_repairs':2,'auth':'local_Codex_ChatGPT_subscription_no_API_keys','assistance':'Frozen declared code-only historical references are part of the method. No conversation history or old outputs supplied.','strict_isolation':False}
    save(out/'runtime.json',rt)
    # Config is explicitly validated to exclude credentials and arbitrary context.
    save(out/'launch_config.json',d)
    prompt=(out/'method/WORKER_PROMPT.md').read_text(encoding='utf-8').replace('`input/source.png`','`input/'+img.name+'`')
    prompt+='\n\nRuntime directory: '+str(out)+'\nRead runtime.json now. The attached original image is the complete object evidence. Finish this case.\n'
    (out/'prompt.md').write_text(prompt,encoding='utf-8')
    immutable=digest_files(out)
    identity={'release':LABEL,'created_at':datetime.now(timezone.utc).isoformat(),'native_job_root':t['jobs_root'],'input_sha256':sha(img),'prompt_sha256':sha(out/'prompt.md'),'immutable_files':immutable,'strict_isolation':False,'isolation_scope':'Capsule preparation only. Run inside a separately verified clean machine/guest to test context independence.','auth':'local_ChatGPT_subscription','model':d['model'],'reasoning_effort':d['reasoning_effort'],'fresh_session':True,'historical_templates_declared':True,'generation_started':False}
    save(out/'identity.json',identity)
    return {'prepared':str(out),'input_sha256':identity['input_sha256'],'generation_started':False,'strict_isolation':False}
def clean_env():
    # Preserve the recipient's own login location, not desktop session linkage.
    return {k:v for k,v in os.environ.items() if not re.search(r'API_KEY|ACCESS_TOKEN|AUTH_TOKEN|SECRET|PASSWORD|OPENAI_BASE_URL',k,re.I) and not (k.startswith('CODEX_') and k!='CODEX_HOME')}
def cli(config):return config.get('codex') or shutil.which('codex')
def command(case,d):
    rt=load(case/'runtime.json')
    return [cli(d) or 'codex','exec',*FLAGS,'-C',str(case),'-m',d['model'],'-c','forced_login_method="chatgpt"','-c','model_provider="openai"','-c','model_reasoning_effort="high"','-c','features.memories=false','-c','features.multi_agent=false','-c','web_search="disabled"','--json','-o',str(case/'last_message.txt'),'--image',rt['source'],'-']
def doctor(d,native=False):
    checks={'python_exists':Path(d['python']).is_file(),'blender_exists':Path(d['blender']).is_file(),'codex_exists':bool(cli(d))}
    details={}
    if cli(d):
        p=subprocess.run([cli(d),'exec','--help'],capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=30,env=clean_env())
        missing=[x for x in FLAGS if x not in p.stdout+p.stderr]
        checks['codex_flags']=p.returncode==0 and not missing;details['missing_flags']=missing
    if checks['python_exists']:
        code='import json,sys,importlib.metadata as m; import numpy,scipy,trimesh,PIL,mujoco,imageio,imageio_ffmpeg; print(json.dumps({"python":sys.version,"packages":{n:m.version(n) for n in ["numpy","scipy","trimesh","Pillow","mujoco","imageio","imageio-ffmpeg"]}}))'
        p=subprocess.run([d['python'],'-X','utf8','-c',code],capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=30,env=clean_env())
        checks['python_imports']=p.returncode==0
        if p.returncode==0:details['python']=json.loads(p.stdout)
    if checks['blender_exists']:
        p=subprocess.run([d['blender'],'--version'],capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=30,env=clean_env());checks['blender_runs']=p.returncode==0;details['blender']=p.stdout.splitlines()[:1]
    if native:
        # Read-only deployment doctor using a temporary explicit profile.
        import tempfile
        with tempfile.TemporaryDirectory(prefix='native-refine-doctor-') as temp:
            profile=Path(temp)/'profile.json';save(profile,d['trellis'])
            p=subprocess.run([d['python'],str(ROOT/'method/trellis2-native-refine/scripts/trellis2_tool.py'),'--config',str(profile),'doctor'],capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=120,env=clean_env())
            try:details['native']=json.loads(p.stdout)
            except ValueError:details['native']={'ok':False,'diagnostic':'Doctor did not return JSON; check your deployment.'}
            checks['native_doctor']=p.returncode==0 and details['native'].get('ok') is True
    return {'checks':checks,'details':details,'ok':all(checks.values()),'model_called':False,'quality_verified':False,'os':platform.platform()}
def run(case):
    if not verify()['ok']:raise ValueError('Release checksum mismatch')
    identity=load(case/'identity.json')
    if (case/'execution.json').exists():raise ValueError('Run already attempted. This adapter does not silently retry or resume.')
    changed=[n for n,h in identity['immutable_files'].items() if not (case/n).is_file() or sha(case/n)!=h]
    if changed:raise ValueError('Prepared input/method/config/prompt changed: '+','.join(changed))
    d=load(case/'launch_config.json');pre=doctor(d,True);save(case/'preflight.json',pre)
    if not pre['ok']:raise ValueError('Preflight failed. Do not remove flags or bypass permissions to continue.')
    login=subprocess.run([cli(d),'login','status'],capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=30,env=clean_env())
    if login.returncode or 'chatgpt' not in (login.stdout+login.stderr).lower():raise ValueError('Historical route requires your own ChatGPT login. No automatic API fallback.')
    rt=load(case/'runtime.json');cmd=command(case,d);record={'started_at':datetime.now(timezone.utc).isoformat(),'command':cmd,'model_called':False,'asset_acceptance':'not_checked','state':'starting'};save(case/'execution.json',record)
    with (case/'events.jsonl').open('w',encoding='utf-8') as log,(case/'stderr.log').open('w',encoding='utf-8') as err:
        p=subprocess.Popen(cmd,cwd=case,env=clean_env(),stdin=subprocess.PIPE,stdout=log,stderr=err,text=True,encoding='utf-8',start_new_session=os.name!='nt')
        record.update(model_called=True,pid=p.pid,state='running');save(case/'execution.json',record)
        p.stdin.write((case/'prompt.md').read_text(encoding='utf-8'));p.stdin.close()
        try:code=p.wait(timeout=rt['max_case_active_seconds'])
        except subprocess.TimeoutExpired:
            if os.name=='nt':subprocess.run(['taskkill','/PID',str(p.pid),'/T','/F'],capture_output=True)
            else:
                import signal
                os.killpg(p.pid,signal.SIGTERM)
            p.wait(timeout=30);record['state']='controller_timeout';code=124
        record.update(exit_code=code,finished_at=datetime.now(timezone.utc).isoformat())
        if record['state']=='running':record['state']='executor_completed' if code==0 else 'executor_failed'
        record['asset_acceptance']='Read and independently check delivery.json and actual motion/physics. Executor completion is not asset success.'
        save(case/'execution.json',record)
    return record
def main():
    ap=argparse.ArgumentParser(description=__doc__);s=ap.add_subparsers(dest='action',required=True)
    s.add_parser('verify')
    p=s.add_parser('prepare');p.add_argument('--image',required=True);p.add_argument('--config',required=True);p.add_argument('--out',required=True)
    p=s.add_parser('doctor');p.add_argument('--config',required=True);p.add_argument('--native',action='store_true')
    for n in ['plan','run']:
        p=s.add_parser(n);p.add_argument('case',type=Path)
    a=ap.parse_args()
    if a.action=='verify':r=verify()
    elif a.action=='prepare':r=prepare(a.image,a.config,a.out)
    elif a.action=='doctor':r=doctor(config(a.config),a.native)
    elif a.action=='plan':
        case=a.case.resolve();r={'command':command(case,load(case/'launch_config.json')),'prompt_file':str(case/'prompt.md'),'model_called':False}
    else:r=run(a.case.resolve())
    print(json.dumps(r,ensure_ascii=False,indent=2));return 0 if r.get('ok',True) else 2
if __name__=='__main__':
    try:sys.exit(main())
    except (ValueError,OSError,subprocess.SubprocessError) as e:
        print(json.dumps({'error':type(e).__name__,'message':str(e)},ensure_ascii=False),file=sys.stderr);sys.exit(2)
