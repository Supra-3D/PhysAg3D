from pathlib import Path
import sys,json,math
import bpy,numpy as np
from mathutils import Matrix,Vector,Quaternion
from mathutils.kdtree import KDTree

ROOT=Path(__file__).resolve().parent
r=ROOT
c=json.loads((r/'camera.json').read_text())
def camera():
    ob=bpy.context.scene.camera;ob.location=c['location'];right=np.array(c['right']);up=np.array(c['up']);eye=np.cross(right,up)
    ob.rotation_euler=Matrix(np.column_stack([right,up,eye]).tolist()).to_euler();ob.data.type='ORTHO';ob.data.ortho_scale=c['ortho_scale'];ob.data.shift_x=c['shift_x'];ob.data.shift_y=c['shift_y']
def render(name,size=640):
    sc=bpy.context.scene;sc.render.resolution_x=sc.render.resolution_y=size;sc.render.resolution_percentage=100;sc.cycles.samples=16
    sc.render.filepath=str(r/'renders'/name);bpy.ops.render.render(write_still=True)
for name in ['native','model']:
    bpy.ops.wm.open_mainfile(filepath=str(r/'asset'/(name+'.blend')));camera()
    render('native.png' if name=='native' else 'refined.png',1024)
    if name=='model':bpy.ops.wm.save_as_mainfile(filepath=str(r/'asset/model.blend'))
trajectory=json.loads((r/'trajectory.json').read_text())['states'];phases=[]
if r.name=='07_cushion':wanted=['settle','hold','recover']
else:wanted=['settle']+list(dict.fromkeys(s['phase'] for s in trajectory if s['phase'].endswith('_hold')))
selected=[next(s for s in reversed(trajectory) if s['phase']==phase) for phase in wanted]
roots={ob.name[5:]:ob for ob in list(bpy.context.scene.objects) if ob.name.startswith('body_')}
for ob in roots.values():
    world=ob.matrix_world.copy();ob.parent=None;ob.matrix_world=world
if r.name=='07_cushion':
    a=np.load(r/'asset/soft_binding.npz');tree=KDTree(len(a['vertices']))
    for i,p in enumerate(a['vertices']):tree.insert(p,i)
    tree.balance();mesh_maps=[]
    for ob in bpy.context.scene.objects:
        if ob.type=='MESH' and not ob.get('staging_only'):
            ids=np.array([tree.find(ob.matrix_world@v.co)[1] for v in ob.data.vertices]);mesh_maps.append((ob,ids))
    bpy.ops.mesh.primitive_uv_sphere_add(segments=32,ring_count=16,radius=.07);sphere=bpy.context.object;sphere.name='test_fixture_indenter'
    mat=bpy.data.materials.new('fixture_blue');mat.diffuse_color=(.03,.32,.8,1);sphere.data.materials.append(mat)
for s in selected:
    if 'nodes' in s:
        vv=np.einsum('ni,nij->nj',a['weights'],np.array(s['nodes'])[a['node_ids']])
        for ob,ids in mesh_maps:
            inv=ob.matrix_world.inverted()
            for v,p in zip(ob.data.vertices,vv[ids]):v.co=inv@Vector(p)
            ob.data.update()
        sphere.location=s['indenter'];sphere.hide_render=s['phase'] in ['settle','recover']
    else:
        for name,pose in s['bodies'].items():
            if name in roots:
                ob=roots[name];ob.location=pose['pos'];ob.rotation_mode='QUATERNION';ob.rotation_quaternion=Quaternion(pose['quat'])
    camera();render('motion_'+s['phase']+'.png');phases.append({'phase':s['phase'],'simulation_time':s['time'],'file':'renders/motion_'+s['phase']+'.png'})
    if 'nodes' in s:
        cam=bpy.context.scene.camera;cam.location=(.7,-.95,.8);target=Vector((0,0,.09));cam.rotation_euler=(target-cam.location).to_track_quat('-Z','Y').to_euler();cam.data.ortho_scale=.88;cam.data.shift_x=cam.data.shift_y=0
        render('contact_'+s['phase']+'.png');phases.append({'phase':'contact_'+s['phase'],'simulation_time':s['time'],'file':'renders/contact_'+s['phase']+'.png'})
(r/'motion_images.json').write_text(json.dumps(phases,indent=2),encoding='utf-8')
