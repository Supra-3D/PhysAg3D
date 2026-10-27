"""Compare recorded SHA256 lines with a separately deployed runtime/model tree."""
from pathlib import Path
import argparse, hashlib, json
ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--root',type=Path,required=True);ap.add_argument('--manifest',type=Path,required=True);a=ap.parse_args()
root=a.root.resolve();records=[]
for line in a.manifest.read_text(encoding='utf-8-sig').splitlines():
    if not line.strip():continue
    expected,relative=line.split(None,1);relative=relative.strip().removeprefix('*');p=(root/relative).resolve()
    if root not in p.parents:raise ValueError('Manifest path outside root')
    actual=None
    if p.is_file():
        with p.open('rb') as f:actual=hashlib.file_digest(f,'sha256').hexdigest()
    records.append({'file':relative,'match':actual==expected,'actual':actual,'expected':expected})
out={'matched':sum(r['match'] for r in records),'total':len(records),'differences':[r for r in records if not r['match']],'scope':'listed files only; does not test imports, CUDA or quality'}
print(json.dumps(out,indent=2));raise SystemExit(0 if out['matched']==out['total'] else 1)
