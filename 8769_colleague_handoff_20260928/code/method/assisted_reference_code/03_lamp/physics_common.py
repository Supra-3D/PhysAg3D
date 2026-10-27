"""Compile authored rigid mechanisms, then measure actual actuator-driven dynamics."""
from pathlib import Path
import sys,json,math,xml.etree.ElementTree as ET
import numpy as np
import mujoco
ROOT=Path(__file__).resolve().parent
def f(x):return ' '.join('%.10g'%a for a in np.asarray(x).ravel())
def qaxis(axis):
    a=np.array(axis,float);a/=np.linalg.norm(a)
    q=np.r_[1+a[2],np.cross([0,0,1],a)]
    if np.linalg.norm(q)<1e-8:return '0 1 0 0'
    return f(q/np.linalg.norm(q))
def write(root,path):ET.indent(root);ET.ElementTree(root).write(path,encoding='utf-8',xml_declaration=True)
def load_model(root,filename='scene.xml'):
    d=Path(root)/'asset';assets={p.relative_to(d).as_posix():p.read_bytes() for p in d.rglob('*') if p.is_file() and (p.suffix in ['.xml','.obj'] or p.parent.name=='textures')}
    return mujoco.MjModel.from_xml_string((d/filename).read_text(encoding='utf-8'),assets)

def compile_case(root):
    r=Path(root);p=json.loads((r/'asset/visual_manifest.json').read_text());bodies=p['bodies'];L=p['length_scale_m']
    m=ET.Element('mujoco',model=r.name);ET.SubElement(m,'compiler',angle='radian',autolimits='true',balanceinertia='true')
    ET.SubElement(m,'option',timestep='.0005',integrator='implicitfast',iterations='80',gravity='0 0 -9.81')
    defaults=ET.SubElement(m,'default');ET.SubElement(defaults,'geom',friction='.7 .005 .0001',solref='.008 1',solimp='.95 .99 .001')
    assets=ET.SubElement(m,'asset');mats=set();parts={name:[] for name in bodies}
    for part in p['parts']:
        ET.SubElement(assets,'mesh',name=part['name'],file=part['mesh']);parts[part['body']].append(part)
        if part['material'] not in mats:
            args={'name':part['material'],'rgba':f(part['rgba']),'specular':'.25','shininess':str(max(.02,1-part['roughness']))}
            if part.get('texture'):
                ET.SubElement(assets,'texture',name='tex_'+part['material'],type='2d',file=part['texture']);args['texture']='tex_'+part['material']
            ET.SubElement(assets,'material',**args);mats.add(part['material'])
    wb=ET.SubElement(m,'worldbody');elements={};joints=[]
    for name,b in bodies.items():
        par=wb if b['parent'] is None else elements[b['parent']];el=ET.SubElement(par,'body',name=name,pos=f(b['pos']));elements[name]=el
        mass=b['mass'];x,y,z=b['inertia_box'];inertia=mass/12*np.array([y*y+z*z,x*x+z*z,x*x+y*y]);inertia=np.maximum(inertia,1e-10)
        ET.SubElement(el,'inertial',mass=str(mass),pos=f(b['com']),diaginertia=f(inertia))
        if b['kind']=='free':ET.SubElement(el,'freejoint',name='root_free')
        elif b['kind'] in ['hinge','slide']:
            args={'name':name+'_joint','type':b['kind'],'axis':f(b['axis']),
              'damping':str(b.get('damping',max(.002,mass*L*.015))),
              'frictionloss':str(b.get('frictionloss',0)),'stiffness':str(b.get('stiffness',0)),
              'armature':str(b.get('armature',max(1e-7,inertia.min()*.002)))}
            if b['range'] is not None:args['range']=f(b['range'])
            ET.SubElement(el,'joint',**args);joints.append(name)
        for part in parts[name]:ET.SubElement(el,'geom',name='visual_'+part['name'],type='mesh',mesh=part['name'],material=part['material'],contype='0',conaffinity='0',mass='0',group='1')
    for i,g in enumerate(p['collision_proxies']):
        args={'name':'collision_'+g['body']+'_'+str(i),'type':g['type'],'size':f(g['size']),'rgba':'0 0 0 0','group':'3','mass':'0'}
        if 'fromto' in g:args['fromto']=f(g['fromto'])
        else:args['pos']=f(g['pos']);args['quat']=f(g['quat']) if 'quat' in g else qaxis(g.get('axis',[0,0,1]))
        if 'friction' in g:args['friction']=f(g['friction'])
        ET.SubElement(elements[g['body']],'geom',**args)
    if r.name=='02_gramophone':
        contacts=ET.SubElement(m,'contact')
        ET.SubElement(contacts,'exclude',body1='record',body2='tonearm')
    if r.name=='05_sink':
        contacts=ET.SubElement(m,'contact')
        ET.SubElement(contacts,'exclude',body1='spout',body2='lever')
        # Mounted faucet parts share an intentionally interpenetrating bearing
        # region with the simplified rear rim. External objects still collide.
        ET.SubElement(contacts,'exclude',body1='base',body2='lever')
        ET.SubElement(contacts,'exclude',body1='base',body2='spout')
    connections=p.get('connections',[])
    if connections:
        eq=ET.SubElement(m,'equality')
        for c in connections:
            a=np.array(c['anchor_world'])-np.array(bodies[c['body1']]['pivot_world'])
            ET.SubElement(eq,'connect',name=c['name'],body1=c['body1'],body2=c['body2'],anchor=f(a),solref='.003 1',solimp='.99 .999 .001')
    if p.get('contact_exclusions'):
        contacts=m.find('contact')
        if contacts is None:contacts=ET.SubElement(m,'contact')
        for a,b in p['contact_exclusions']:ET.SubElement(contacts,'exclude',body1=a,body2=b)
    actuator=ET.SubElement(m,'actuator')
    actuator_names=[]
    for name in joints:
        if not bodies[name].get('actuated',True):continue
        actuator_names.append(name)
        b=bodies[name];mass=b['mass'];box=np.array(b['inertia_box']);inertia=mass*(box**2).sum()/12
        kp=b.get('kp',max(.3,mass*9.81*L*8) if b['kind']=='hinge' else max(300,mass*10000))
        kv=b.get('kv',2*.9*np.sqrt(kp*(inertia if b['kind']=='hinge' else mass)))
        force=b.get('force_limit',max(1,kp*2));args={'name':name+'_control','joint':name+'_joint','kp':str(kp),'kv':str(kv),'forcerange':f([-force,force])}
        if b['range'] is not None:args['ctrlrange']=f(b['range'])
        ET.SubElement(actuator,'position',**args);b['compiled_control']={'kp':kp,'kv':kv,'force_limit':force}
    keys=ET.SubElement(m,'keyframe');qpos=([0,0,0,1,0,0,0] if next(iter(bodies.values()))['kind']=='free' else [])+[0]*len(joints)
    ET.SubElement(keys,'key',name='home',qpos=f(qpos),ctrl=f([0]*len(actuator_names)))
    write(m,r/'asset/model.xml')
    scene=ET.Element('mujoco',model=r.name+'_scene');ET.SubElement(scene,'include',file='model.xml');wb=ET.SubElement(scene,'worldbody')
    ET.SubElement(wb,'geom',name='floor',type='plane',size=f([L*3,L*3,.1]),rgba='.15 .19 .18 1',friction='.8 .005 .0001')
    write(scene,r/'asset/scene.xml')
    (r/'physical_properties.json').write_text(json.dumps({'bodies':bodies,'collision_proxies':p['collision_proxies'],
      'source':'inferred category values and box inertia approximations','units':'SI','no_physical_ground_truth':True},indent=2),encoding='utf-8')

def validate_case(root):
    r=Path(root);p=json.loads((r/'asset/visual_manifest.json').read_text());m=load_model(r);d=mujoco.MjData(m)
    mujoco.mj_resetDataKeyframe(m,d,0);mujoco.mj_forward(m,d)
    controls=p['controls'];states=[];nextframe=0;max_connection_error=0.;minimum_contact=0.;finite=True;max_force=0.;records=[];baseline=None
    phases=[('settle',{},1.0)]
    for c in controls:
        phases.extend([(c['body']+'_move',{c['body']:c['target']},1.6),(c['body']+'_hold',{c['body']:c['target']},.35),(c['body']+'_return',{},1.3)])
    if not controls:phases.append(('contact_rest',{},2.0))
    for label,targets,duration in phases:
        start=d.ctrl.copy();goal=np.zeros(m.nu)
        for name,target in targets.items():goal[m.actuator(name+'_control').id]=target
        for step in range(round(duration/m.opt.timestep)):
            t=min(1,step*m.opt.timestep/(duration*.75));u=t*t*(3-2*t);d.ctrl[:]=start+(goal-start)*u;mujoco.mj_step(m,d)
            finite=finite and bool(np.isfinite(d.qpos).all() and np.isfinite(d.qvel).all())
            if step%10==0:
                for c in p.get('connections',[]):
                    ia=m.body(c['body1']).id;ib=m.body(c['body2']).id
                    aw=np.array(c['anchor_world']);aa=aw-np.array(p['bodies'][c['body1']]['pivot_world']);ab=aw-np.array(p['bodies'][c['body2']]['pivot_world'])
                    pa=d.xpos[ia]+d.xmat[ia].reshape(3,3)@aa;pb=d.xpos[ib]+d.xmat[ib].reshape(3,3)@ab
                    max_connection_error=max(max_connection_error,float(np.linalg.norm(pa-pb)))
            if d.ncon:minimum_contact=min(minimum_contact,float(min(c.dist for c in d.contact[:d.ncon])))
            if m.nu:max_force=max(max_force,float(np.abs(d.actuator_force).max()))
            if d.time>=nextframe:
                states.append({'time':float(d.time),'phase':label,'qpos':d.qpos.tolist(),
                  'bodies':{mujoco.mj_id2name(m,mujoco.mjtObj.mjOBJ_BODY,i):{'pos':d.xpos[i].tolist(),'quat':d.xquat[i].tolist()} for i in range(1,m.nbody)}});nextframe+=1/8
        actual={c['body']:float(d.joint(c['body']+'_joint').qpos[0]) for c in controls};records.append({'phase':label,'targets':targets,'actual':actual})
        if label=='settle':baseline=d.qpos.copy()
    checks={'model_loads':True,'finite_dynamics':finite,'positive_mass_inertia':bool((m.body_mass[1:]>0).all() and (m.body_inertia[1:]>0).all()),
      'bounded_penetration':minimum_contact>-max(.002,p['length_scale_m']*.008)}
    warnings={str(i):int(w.number) for i,w in enumerate(d.warning) if w.number}
    checks['no_solver_warnings']=not warnings
    if p.get('connections'):checks['rod_endpoint_connections']=max_connection_error<.008
    rec={a['phase']:a for a in records}
    for c in controls:
        b=c['body'];target=c['target'];tol=c.get('tolerance',max(.05,abs(target)*.12))
        checks[b+'_reaches_target']=abs(rec[b+'_hold']['actual'][b]-target)<tol
        checks[b+'_returns']=abs(rec[b+'_return']['actual'][b])<tol
    report={'engine':'MuJoCo','version':mujoco.__version__,'checks':checks,'all_checks_passed':all(checks.values()),'nbody':m.nbody,'nq':m.nq,'nv':m.nv,'nu':m.nu,
      'mass_kg':float(m.body_mass.sum()),'simulated_seconds':float(d.time),'minimum_contact_distance_m':minimum_contact,'phases':records,'actual_dynamics':True,'solver_warnings':warnings,'maximum_connection_error_m':max_connection_error,'max_actuator_force':max_force,
      'limits':['Physical values uncalibrated','Collision proxies simplified','Motion travel test is not complete mechanical clearance validation','Controllers represent virtual applied interaction']}
    (r/'physics_report.json').write_text(json.dumps(report,indent=2),encoding='utf-8');(r/'actualphysics_report.json').write_text(json.dumps(report,indent=2),encoding='utf-8');(r/'trajectory.json').write_text(json.dumps({'fps':8,'states':states}),encoding='utf-8')
    print(r.name,'physics',checks,flush=True)
if __name__=='__main__':
    r=ROOT;compile_case(r);validate_case(r)
