from pathlib import Path
import json,hashlib,shutil
ROOT=Path(__file__).resolve().parents[2]
OLD=ROOT.parent/'trellis2_skill_batch8_20260908'
observations={
'01_vending':{'visible':['Red rectangular cabinet with bevelled perimeter','Three drink rows and right payment strip','Low rectangular delivery flap','Dark bottom strip, four supports and decorative tiled presentation platform'], 'mechanics':['Service door inferred on left front edge','Delivery flap on horizontal top pivot','One independent selection button'],'risks':['Generated printed drinks are appearance only','Service cavity unseen','Do not retain a solid cabinet collision hull across its opening']},
'02_gramophone':{'visible':['Brown fabric-covered carrying case and nearly upright recessed lid','Black circular record with salmon red label','Curved silver tonearm','Right side crank with yellow wooden grip','Front latch and carrying handle'], 'mechanics':['Back-edge lid hinge, closing over case','Record Z-axis spin','Tonearm yaw with pickup kept above record','Right side crank X-axis spin'],'risks':['Lid closure requires enough clearance for tonearm','No transmission or audio inference','Texture-native broken metal arm may need reconstruction']},
'04_fridge':{'visible':['Ivory two-compartment refrigerator','Both left handle doors partially open about right-side hinges','Tall lower compartment and shorter upper compartment','Grey horizontal handles and real dark cavity between door and box'], 'mechanics':['Independent vertical right hinges','Closed pose must cover both openings','Door liners and shelves remain inside closed envelope'],'risks':['Cutting native by depth alone may drag cabinet fragments','Single view cannot reveal hidden door liner','Avoid filled collision hull in cabinet']},
'05_sink':{'visible':['Off-white double basin with thick continuous rim','Tapered bowl walls and open basin bottoms visible','Curved high faucet with curved outlet facing forward','Short side valve lever at faucet base'], 'mechanics':['Swivel spout on vertical bearing','Valve lever pitch','Independent ball drop into both hollow basin collision shells'],'risks':['No water simulation','Both native bowl visual cavities and contact cavities must remain open','Do not use whole-sink convex hull']}}
for cid,obs in observations.items():
    r=ROOT/'cases'/cid
    for sub in ['asset','renders','logs']:(r/sub).mkdir(exist_ok=True)
    p=json.loads((OLD/'cases'/cid/'asset_plan.json').read_text(encoding='utf-8'))
    p['observation']=obs;p['generation_experiment']='new native inference followed by renewed case-specific refinement';p['route']['pipeline_type']='1024_cascade';p['scaffold_policy']='provisional cavity panels, articulated parts and joints; no old final geometry'
    p['provenance']['source_sha256_verified']=hashlib.sha256((r/'input/source.png').read_bytes()).hexdigest()
    (r/'asset_plan.json').write_text(json.dumps(p,ensure_ascii=False,indent=2),encoding='utf-8')
    for name in ['blender_common.py','prepare_native.py','physics_common.py']:
        text=(OLD/name).read_text(encoding='utf-8')
        if name=='prepare_native.py':
            text=text.replace("ROOT=Path(__file__).resolve().parent","ROOT=Path(__file__).resolve().parents[2]")
        elif name=='physics_common.py':
            text=text.replace("ROOT=Path(__file__).resolve().parent","ROOT=Path(__file__).resolve().parents[2]")
        (r/name).write_text(text,encoding='utf-8')
    (r/'SOURCE_REUSE.json').write_text(json.dumps({'reused_source_utilities':['blender_common.py','prepare_native.py','physics_common.py'],'source_directory':str(OLD),'reused_old_final_models':False,'reused_old_native_candidates':False,'new_observation':obs},ensure_ascii=False,indent=2),encoding='utf-8')
print('Four new observed plans and case-local utilities prepared')
