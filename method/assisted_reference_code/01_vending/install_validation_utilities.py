from pathlib import Path
import json
ROOT=Path(__file__).resolve().parents[2];OLD=ROOT.parent/'trellis2_skill_batch8_20260908'
for cid in ['01_vending','02_gramophone','04_fridge','05_sink']:
    r=ROOT/'cases'/cid
    s=(OLD/'render_validation.py').read_text(encoding='utf-8').replace('ROOT=Path(__file__).resolve().parent','ROOT=Path(__file__).resolve().parents[2]')
    s=s.replace("sc.cycles.samples=16","sc.cycles.samples=20")
    (r/'render_validation.py').write_text(s,encoding='utf-8')
    s=(r/'physics_common.py').read_text(encoding='utf-8')
    s=s.replace("'bounded_penetration':minimum_contact>-max(.002,p['length_scale_m']*.008)","'bounded_penetration':minimum_contact>-max(.002,p['length_scale_m']*.003), 'no_solver_warnings':sum(int(w.number) for w in d.warning)==0")
    s=s.replace("'actual_dynamics':True,","'actual_dynamics':True,'solver_warning_counts':[int(w.number) for w in d.warning], 'max_actuator_force':max_force, 'fixed_base_demo':next(iter(p['bodies'].values()))['kind']=='fixed',")
    (r/'physics_common.py').write_text(s,encoding='utf-8')
print('Case-local physics and actual-trajectory rendering utilities ready')
