from pathlib import Path
import json,hashlib,xml.etree.ElementTree as ET,mujoco,os
R=Path(__file__).resolve().parent;A=R/'asset'
rep=json.loads((R/'physics_report.json').read_text())
assert rep['all_checks_passed'] and rep['actual_dynamics']
os.chdir(A);m=mujoco.MjModel.from_xml_path('scene.xml');refs=[]
for p in A.glob('*.xml'):
 for el in ET.parse(p).iter():
  if el.get('file'):
   ref=p.parent/el.get('file');assert ref.exists(),ref;refs.append(str(ref.relative_to(R)))
manifest=json.loads((A/'visual_manifest.json').read_text());traj=json.loads((R/'trajectory.json').read_text())
names={mujoco.mj_id2name(m,mujoco.mjtObj.mjOBJ_BODY,i) for i in range(1,m.nbody)}
assert all(x['body'] in names for x in manifest['parts'])
assert all(names.issubset(x['bodies']) for x in traj['states'])
rr=json.loads((R/'refinement_report.json').read_text())
for op in rr['operations']:
 if op['operation']=='thin profile loft and local underside reconstruction':op.update(operation='inward solidify of actual native hood',target='1.5 mm inner thickness following native surface; lamp mouth remains open')
rr['limitations'][-1]='Shade retains neural geometric ridges; its albedo is a source-informed uniform prior. Base retains the neural atlas.'
(R/'refinement_report.json').write_text(json.dumps(rr,indent=2),encoding='utf-8')
issues=['Green shade retains visible neural ridges and faceting; uniform source-inferred albedo replaces its original neural green texture','Stand and yoke are continuous reconstructed curves, with inferred hidden mounting geometry','Pull chain is a rigid visual attachment; no electrical, thermal, fracture or flexible-chain model','Dimensions, mass, inertia, friction and joint resistance are unmeasured priors; simplified shade collision box','Studio shading remains brighter than the source; full photorealistic equivalence is not claimed']
review={'source_image_inspected':True,'native_xyz_diagnostics_inspected':True,'refined_source_view_inspected':True,'actual_motion_views_inspected':['shade_hold'],'observations':['Shade rotates visibly around its two side pins while the U yoke remains fixed','Continuous bent stand remains attached to base and U yoke','Rejected intersecting approximate inner loft; final inner shell follows the actual native hood with inward solidify','Old detached pull-chain residue removed; final short chain follows shade'],'remaining_issues':issues}
(R/'visual_review.json').write_text(json.dumps(review,indent=2),encoding='utf-8')
(R/'LIMITS.md').write_text('台灯：本次新 TRELLIS.2 1024_cascade 整物体候选，保留底座和灯罩主体几何；Blender 重建连续弯杆、U 形支架和转轴。灯罩内壁由原始曲面向内加厚 1.5 mm，绿色材质改为依据原图估计的均匀粗糙玻璃参数。\n\nMuJoCo 实际运行 4.25 秒，7 项检查通过，灯罩达到约 0.302 rad 后回到约 0.00436 rad。动作 PNG 来自记录的真实刚体位姿。\n\n限制：灯罩仍有神经几何的横向起伏和分面；棚拍光照下颜色比原图偏亮。拉链为刚性装饰，没有柔性链、电路、发热或玻璃破碎。尺寸、质量、惯量、摩擦为估计值，灯罩碰撞体为简化代理；本轮通过运动测试，不代表完成所有姿态和接触验证，也不声称达到照片级一致。\n',encoding='utf-8')
out={'id':R.name,'state':'complete_with_limitations','native_job':'t2-2587c21ba3d74d47aee518ed515bb204','native_pipeline':'1024_cascade','physical_checks_passed':True,'physical_check_count':len(rep['checks']),'physics_report':'physics_report.json','actual_dynamics':True,'motion_images':'motion_images.json','simulated_seconds':rep['simulated_seconds'],'full_quality_accepted':False,'visual_remaining_issues':issues,'final_texture_paths':['asset/textures/baseColorTexture.png'],'independent_delivery_load':{'nbody':m.nbody,'nq':m.nq,'nu':m.nu,'all_xml_references_exist':True,'references':len(refs),'all_manifest_bodies_in_trajectory':True},'model_sha256':{n:hashlib.sha256((A/n).read_bytes()).hexdigest() for n in ['model.blend','model.glb','model.xml','scene.xml']}}
(R/'CASE_COMPLETE.json').write_text(json.dumps(out,indent=2),encoding='utf-8');print(json.dumps(out['independent_delivery_load']))
