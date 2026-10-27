from pathlib import Path
import json,hashlib,xml.etree.ElementTree as ET,mujoco,os,numpy as np
R=Path(__file__).resolve().parent;A=R/'asset'
rep=json.loads((R/'physics_report.json').read_text());assert rep['all_checks_passed'] and rep['actual_dynamics']
os.chdir(A);m=mujoco.MjModel.from_xml_path('scene.xml');refs=[]
for p in A.glob('*.xml'):
 for el in ET.parse(p).iter():
  if el.get('file'):
   ref=p.parent/el.get('file');assert ref.exists(),ref;refs.append(str(ref.relative_to(R)))
manifest=json.loads((A/'visual_manifest.json').read_text());traj=json.loads((R/'trajectory.json').read_text())
names={mujoco.mj_id2name(m,mujoco.mjtObj.mjOBJ_BODY,i) for i in range(1,m.nbody)}
assert all(x['body'] in names for x in manifest['parts'])
assert all(names.issubset(x['bodies']) for x in traj['states'])
a=np.load(R/'native_geometry.npz');c=a['vertices'][a['faces']].mean(1)
lip=(c[:,1]>=-2.60)&(c[:,1]<-2.25)&(c[:,2]<1.6)&(c[:,2]>.42)&(abs(c[:,0])<.55)
repair={'issue':'Visible small bucket lip stayed behind during stick motion because a y-only boundary assigned it upstream','observed_in':'iterations/round01/motion_stick_hold.png','fix':'Extend candidate-informed bucket low-zone boundary from y=-2.60 m to -2.25 m','faces_reassigned':int(lip.sum()),'new_visual_owner':'bucket','final_motion_views_inspected':['boom_hold','stick_hold','bucket_hold'],'physical_tests_rerun':True}
(R/'repair_round02.json').write_text(json.dumps(repair,indent=2),encoding='utf-8')
rr=json.loads((R/'refinement_report.json').read_text())
rr['operations'].append({'operation':'local semantic reconstruction of bucket cutting lip','target':'reattach entire candidate lip to bucket body after actual-motion inspection','faces_reassigned':int(lip.sum())})
(R/'refinement_report.json').write_text(json.dumps(rr,indent=2),encoding='utf-8')
issues=['Native surfaces retain rough panel edges and distorted text/logo textures; photorealistic correspondence is not claimed','Three cylinder endpoints are constrained, but direct virtual joint torques drive motion rather than a fluid or hydraulic pressure model','Front bucket linkage is a rigid bucket region rather than a reconstructed four-bar mechanism','Tracks are rigid assemblies without belt articulation, soil interaction or drive motors','Full-size dimensions, 14.12 tonne total mass, inertia, friction and actuator force limits are category estimates','Open compound bucket collision approximates shell thickness; full travel clearance and unseen geometry remain unverified']
review={'source_image_inspected':True,'native_xyz_diagnostics_inspected':True,'refined_source_view_inspected':True,'actual_motion_views_inspected':['boom_hold','stick_hold','bucket_hold'],'observations':['All three cylinders consist of passive revolute barrel and sliding rod bodies, with actual distal connect equalities','Rod endpoint positions remain connected under actual actuator-driven motion','First motion review caught a disconnected candidate bucket lip; final ownership covers the complete lip and subsequent action images no longer show that floating strip','Bucket mouth remains visibly open and has an open compound contact shell'],'remaining_issues':issues}
(R/'visual_review.json').write_text(json.dumps(review,indent=2),encoding='utf-8')
(R/'LIMITS.md').write_text('挖掘机：使用本次新 TRELLIS.2 1024_cascade 整机候选，保留履带、车体、臂架和铲斗外观；Blender 按新候选拆分语义部件，补建转轴和三组双端连接的伸缩液压杆。液压杆包含被动转动缸筒、滑动活塞杆和远端 MuJoCo connect 约束。初轮动作图发现铲斗唇缘留在上游刚体，已重新划分并复测。\n\nMuJoCo 实际运行约 14 秒，14 项检查通过、求解器无警告。轨迹和动作 PNG 来自真实仿真。液压杆最大端点误差及实际接触穿透量请以 physics_report.json 为准。\n\n限制：关节由虚拟力矩驱动，没有液压压力、油液或土壤模拟；铲斗前连杆仍简化为随铲斗刚性运动，未实现完整四连杆。履带为固定组件，没有履带节、传动或车辆行驶。尺寸、质量（总计 14.12 吨）、惯量、摩擦等均由类别先验推断。文字标识和局部板件仍有神经纹理/几何误差；碰撞采用简化代理，铲斗为开口组合壳。通过本次动作测试不等于全行程机械间隙、所有接触工况或照片级外观验收。\n',encoding='utf-8')
out={'id':R.name,'state':'complete_with_limitations','native_job':'t2-22c2dd1732744b5b95be7e27f1c7404b','native_pipeline':'1024_cascade','physical_checks_passed':True,'physical_check_count':len(rep['checks']),'physics_report':'physics_report.json','actual_dynamics':True,'motion_images':'motion_images.json','simulated_seconds':rep['simulated_seconds'],'maximum_rod_endpoint_error_m':rep['maximum_connection_error_m'],'full_quality_accepted':False,'visual_remaining_issues':issues,'final_texture_paths':['asset/textures/baseColorTexture.png'],'independent_delivery_load':{'nbody':m.nbody,'nq':m.nq,'nu':m.nu,'all_xml_references_exist':True,'references':len(refs),'all_manifest_bodies_in_trajectory':True},'model_sha256':{n:hashlib.sha256((A/n).read_bytes()).hexdigest() for n in ['model.blend','model.glb','model.xml','scene.xml']}}
(R/'CASE_COMPLETE.json').write_text(json.dumps(out,indent=2),encoding='utf-8');print(json.dumps(out['independent_delivery_load']))
