from pathlib import Path
import hashlib, json, sys
root=Path(__file__).resolve().parent
manifest=json.loads((root/'package-manifest.json').read_text(encoding='utf-8'))
errors=[]
for item in manifest['files']:
    p=root/item['path']
    if not p.is_file():
        errors.append('Missing: '+item['path']);continue
    h=hashlib.sha256()
    with p.open('rb') as stream:
        for chunk in iter(lambda:stream.read(4*1024*1024),b''):h.update(chunk)
    if p.stat().st_size!=item['bytes'] or h.hexdigest()!=item['sha256']:
        errors.append('Changed: '+item['path'])
if errors:
    print('\n'.join(errors));sys.exit(1)
print('OK: %d files verified.' % len(manifest['files']))
