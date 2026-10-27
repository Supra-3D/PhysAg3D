from pathlib import Path
import sys,json,hashlib,datetime
import mujoco
ROOT=Path(__file__).resolve().parents[2];cid=sys.argv[1];r=ROOT/'cases'/cid
sys.path.insert(0,str(r));from physics_common import load_model
p=json.loads((r/'physics_report.json').read_text());ref=json.loads((r/'refinement_report.json').read_text());cavity=json.loads((r/'cavity_test_report.json').read_text()) if (r/'cavity_test_report.json').exists() else None
limitations={
'01_vending':['商品图案、细字仍然模糊；生成颜色比原图偏浅','柜体隐蔽内衬、维修门铰链为推断，未模拟出货、付款、电气或冷却','门切割边缘仍有少量神经网格不规则；主体固定在演示基座上','外部球为空腔探针，硬接触采用 priority=1、solref=.002 1；参数未经材料标定'],
'04_fridge':['柜体和上门保留新神经网格；下门错误凸条通过重建圆角薄壳修正，保留神经把手','单图无法确定内部搁板布局；内部表面、厚度和铰链偏移为推断','材质比原图偏白；柜口内缘仍有少量神经切边不规则；不宣称原图未见侧面/背面的真实恢复','固定基座；没有冷却、电路、密封条压缩或可移动内容物'],
'02_gramophone':['盒体、盒盖、唱臂和摇柄保留新神经几何与纹理；唱片和圆形标签重新建模，盒盖补133个孔边面','材质比原图偏浅、金属感不足；盖上缘和铰链附近仍有少量裂缝/不规则切边，不能视作完整外观验收通过','唱片、唱臂和摇柄使用独立虚拟操纵，未建立齿轮联动或发声模型；唱片/唱臂接触作为唱针轴承近似被排除','固定基座，质量和摩擦为类别先验；未测试搬运/跌落','摇柄轴位置由单图推断；动作图中杆段部分被箱壁遮挡，未验证完整摇柄扫掠体接触','实际闭合角1.3487 rad，距推断目标1.3723 rad尚差0.0236 rad，处于本次0.045 rad目标容差内；前缘仍有可见缝隙，是近闭合而非密封闭合或产品工程验证']}
driver=(ROOT/'cases/01_vending/refine_new_candidates.py').read_text(encoding='utf-8')
driver=driver.replace("ROOT=Path(__file__).resolve().parents[2]\nCID=sys.argv[sys.argv.index('--')+1]\nsys.path.insert(0,str(ROOT/'cases'/CID))", "CASE_ROOT=Path(__file__).resolve().parent\nROOT=CASE_ROOT.parents[1]\nCID="+repr(cid)+"\nsys.path.insert(0,str(CASE_ROOT))")
driver=driver.replace("B=Builder(ROOT/'cases'/CID)","B=Builder(CASE_ROOT)")
(r/'build_refined.py').write_text(driver,encoding='utf-8')
m=load_model(r);d=mujoco.MjData(m);mujoco.mj_forward(m,d)
for _ in range(10):mujoco.mj_step(m,d)
manifest=json.loads((r/'asset/visual_manifest.json').read_text());parts=manifest['parts']
files=[r/'asset/model.blend',r/'asset/model.glb',r/'asset/model.xml',r/'asset/scene.xml',r/'asset/visual_manifest.json',r/'physics_report.json',r/'trajectory.json',r/'camera.json',r/'input/source.png',r/'build_refined.py',r/'blender_common.py',r/'physics_common.py']
files += [x for x in [r/'refine_fridge.py',r/'native_normals.npy',r/'native_geometry.npz',r/'asset_plan.json',r/'candidate_partition.json',r/'refinement_report.json'] if x.is_file()]
files += list((r/'asset/meshes').glob('*.obj'))+list((r/'asset/textures').glob('*'))
if cavity:files += [r/'cavity_test_report.json',r/'cavity_test_trajectory.json',r/'asset/cavity_test.xml']
for fp in files:
    if not fp.is_file():raise FileNotFoundError(fp)
hashes={x.relative_to(r).as_posix():hashlib.sha256(x.read_bytes()).hexdigest() for x in files}
validation={'fresh_process_scene_loaded':True,'mujoco_version':mujoco.__version__,'part_mesh_references_exist':all((r/'asset'/x['mesh']).is_file() for x in parts),'body_names_bound':all(m.body(x).id>=0 for x in manifest['bodies']),'nbody':m.nbody,'nu':m.nu,'files_sha256':hashes}
(r/'FINAL_ASSET_BINDING.json').write_text(json.dumps(validation,indent=2),encoding='utf-8')
result={'id':cid,'state':'completed_experimental','frozen_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'new_native_inference_used':True,'native_faces_retained':ref['native_faces_retained'],'candidate_faces':ref['candidate_faces'],'physics_checks_passed':bool(p['all_checks_passed']),'physics_checks':p['checks'],'cavity_test_passed':cavity['passed'] if cavity else None,'visual_acceptance':'partial','fully_validated_sim_ready':False,'actual_mujoco_motion':True,'motion_images':json.loads((r/'motion_images.json').read_text()),'appearance_and_scope_limitations':limitations[cid],'final_asset_binding_sha256':hashlib.sha256((r/'FINAL_ASSET_BINDING.json').read_bytes()).hexdigest()}
(r/'CASE_COMPLETE.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
md=f"# {json.loads((r/'asset_plan.json').read_text(encoding='utf-8'))['title']}：整机生成后精修\n\n本轮重新调用 TRELLIS.2 1024 级联；保留原始候选、单图输入和可调整草模。Blender 对实际新候选重新配准、拆分与修复。\n\n实际 MuJoCo 检查：{'已执行项目全部通过' if p['all_checks_passed'] else '存在失败项目，见 physics_report.json'}。空腔测试：{cavity['passed'] if cavity else '未执行独立外部探针测试'}。完整外观验收未通过；物理数值属于可编辑类别先验。\n\n"
md+='\n'.join('- '+x for x in limitations[cid])
md+='\n\n文件：asset/model.blend 为编辑主文件，asset/model.glb 为静态可视资产；asset/scene.xml 与 model.xml、meshes、textures 一起组成 MuJoCo 资产。trajectory.json 是真实求解记录，其回放不是实时仿真。build_refined.py 是该例独立精修入口。\n'
(r/'README.md').write_text(md,encoding='utf-8');print(json.dumps({k:result[k] for k in ['id','state','physics_checks_passed','cavity_test_passed','native_faces_retained']},ensure_ascii=False))
