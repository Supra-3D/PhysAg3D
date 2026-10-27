"""Compile the authored body graph and exercise actual MuJoCo dynamics."""
import json
import math
from pathlib import Path
import xml.etree.ElementTree as ET

import imageio.v2 as imageio
import mujoco
import numpy as np
import trimesh

ROOT=Path(__file__).resolve().parent
P=json.loads((ROOT/"parameters.json").read_text(encoding="utf-8"))


def f(values):return " ".join("%.10g"%v for v in values)


def box_inertia(mass,dims):
    x,y,z=dims; return [mass*(y*y+z*z)/12,mass*(x*x+z*z)/12,mass*(x*x+y*y)/12]


def compile_asset():
    manifest=json.loads((ROOT/"asset/visual_manifest.json").read_text(encoding="utf-8")); bodies=manifest["bodies"]
    mj=ET.Element("mujoco",model="physxverse_laptop_skill")
    ET.SubElement(mj,"compiler",angle="radian",autolimits="true",balanceinertia="true")
    ET.SubElement(mj,"option",timestep="0.0005",integrator="implicitfast",gravity="0 0 -9.81",iterations="60")
    defaults=ET.SubElement(mj,"default")
    ET.SubElement(defaults,"geom",friction="0.7 0.005 0.0001",solref="0.008 1",solimp="0.95 0.99 0.001")
    asset=ET.SubElement(mj,"asset"); materials={}; bodyparts={name:[] for name in bodies}
    for part in manifest["parts"]:
        ET.SubElement(asset,"mesh",name=part["name"],file=part["mesh"])
        matname=part["material"]
        if matname not in materials:
            args={"name":matname,"rgba":f(part["rgba"]),"specular":str(.25),"shininess":str(max(.02,1-part["roughness"]))}
            if part.get("texture"):
                texname="tex_"+matname; ET.SubElement(asset,"texture",name=texname,type="2d",file=part["texture"]); args["texture"]=texname
            ET.SubElement(asset,"material",**args); materials[matname]=True
        bodyparts[part["body"]].append(part)
    world=ET.SubElement(mj,"worldbody"); elements={}; key_order=[]
    for name,body in bodies.items():
        parent=world if name=="base" else elements[body["parent"]]
        element=ET.SubElement(parent,"body",name=name,pos=f(body["pos"])); elements[name]=element
        if body["kind"]=="free":ET.SubElement(element,"freejoint",name="root_free")
        elif body["kind"]=="hinge":
            ET.SubElement(element,"joint",name="lid_hinge",type="hinge",axis=f(body["axis"]),range=f(np.deg2rad(body["range"])),
                          damping="0.15",frictionloss="0.08",armature="0.00005")
        elif body["kind"]=="key":
            ET.SubElement(element,"joint",name=name+"_press",type="slide",axis=f(body["axis"]),range=f(body["range"]),
                          damping="0.12",stiffness=str(body["stiffness"]),springref="0",armature="0.0001")
            key_order.append(name)
        mass=body["mass"]
        if name in ("base","lid"):
            com=body["com"]; inertia=box_inertia(mass,body["inertia_box"])
        else:
            bounds=np.array([trimesh.load(ROOT/"asset"/part["mesh"],force="mesh",process=False).bounds for part in bodyparts[name]])
            low=bounds[:,0].min(axis=0); high=bounds[:,1].max(axis=0); com=((low+high)/2).tolist()
            inertia=box_inertia(mass,np.maximum(high-low,.001))
        ET.SubElement(element,"inertial",pos=f(com),mass=str(mass),diaginertia=f(inertia))
        for part in bodyparts[name]:
            ET.SubElement(element,"geom",name="visual_"+part["name"],type="mesh",mesh=part["name"],material=part["material"],
                          contype="0",conaffinity="0",group="1",mass="0")
        if name=="base":
            ET.SubElement(element,"geom",name="base_collision",type="box",pos="0 0 0.010",size=f([.18,P["depth_m"]/2,.008]),rgba="0 0 0 0",group="3",mass="0")
            for i,(x,y) in enumerate(( (x,y) for x in(-.145,.145) for y in(-P["depth_m"]/2+.022,P["depth_m"]/2-.022) )):
                ET.SubElement(element,"geom",name="foot_collision_%d"%i,type="box",pos=f([x,y,.001]),size=".0155 .005 .001",rgba="0 0 0 0",group="3",mass="0",friction="1.0 .005 .0001")
        elif name=="lid":
            ET.SubElement(element,"geom",name="lid_collision",type="box",pos=f([0,-P["lid_height_m"]/2,0]),
                          size=f([P["lid_width_m"]/2,P["lid_height_m"]/2,.0054]),rgba="0 0 0 0",group="3",mass="0")
        else:
            ET.SubElement(element,"geom",name=name+"_collision",type="box",pos=f(com),size=f(np.maximum((high-low)/2,.0004)),rgba="0 0 0 0",group="3",mass="0")
    contacts=ET.SubElement(mj,"contact")
    ET.SubElement(contacts,"pair",geom1="base_collision",geom2="lid_collision")
    actuators=ET.SubElement(mj,"actuator")
    ET.SubElement(actuators,"position",name="lid_control",joint="lid_hinge",kp="35",kv="1.4",ctrlrange=f(np.deg2rad([0,145])),forcerange="-1.8 1.8")
    for name in key_order:
        kp=8000 if name=="trackpad" else 4000
        ET.SubElement(actuators,"position",name=name+"_control",joint=name+"_press",kp=str(kp),kv="0.1",ctrlrange=f(bodies[name]["range"]),forcerange="-4 4")
    keys=ET.SubElement(mj,"keyframe")
    qpos=[0,0,0,1,0,0,0,math.radians(P["opening_deg"])]+[0]*len(key_order)
    ctrl=[math.radians(P["opening_deg"])]+[0]*len(key_order)
    ET.SubElement(keys,"key",name="home",qpos=f(qpos),ctrl=f(ctrl))
    ET.indent(mj); ET.ElementTree(mj).write(ROOT/"asset/laptop.xml",encoding="utf-8",xml_declaration=True)
    scene=ET.Element("mujoco",model="Laptop interaction scene"); ET.SubElement(scene,"include",file="laptop.xml")
    visual=ET.SubElement(scene,"visual"); ET.SubElement(visual,"global",offwidth="960",offheight="720")
    ET.SubElement(visual,"headlight",ambient="0.3 0.3 0.3",diffuse="0.6 0.6 0.6",specular="0.3 0.3 0.3")
    assets=ET.SubElement(scene,"asset"); ET.SubElement(assets,"material",name="floor_mat",rgba=".16 .18 .21 1",specular=".1",shininess=".1")
    world=ET.SubElement(scene,"worldbody"); ET.SubElement(world,"geom",name="floor",type="plane",size="2 2 .1",material="floor_mat")
    ET.SubElement(world,"light",pos="-.4 -.7 1.4",dir="0.2 0.3 -1",diffuse=".7 .7 .7",castshadow="true")
    eye=np.array([-.65,-.86,.62]); target=np.array([0,0,.115]); forward=target-eye; forward/=np.linalg.norm(forward)
    right=np.cross(forward,[0,0,1]);right/=np.linalg.norm(right);up=np.cross(right,forward)
    ET.SubElement(world,"camera",name="overview",pos=f(eye),xyaxes=f(np.r_[right,up]),fovy="35")
    ET.indent(scene); ET.ElementTree(scene).write(ROOT/"asset/scene.xml",encoding="utf-8",xml_declaration=True)
    return bodies


def load_model():
    # Python reads the Unicode workspace paths; MuJoCo receives an in-memory VFS.
    directory=ROOT/"asset"
    files={p.relative_to(directory).as_posix():p.read_bytes() for p in directory.rglob("*")
           if p.is_file() and (p.suffix.lower() in (".xml",".obj") or p.suffix.lower()==".png" and p.parent.name=="textures")}
    return mujoco.MjModel.from_xml_string((directory/"scene.xml").read_text(encoding="utf-8"),assets=files)


def simulate():
    model=load_model(); data=mujoco.MjData(model)
    mujoco.mj_resetDataKeyframe(model,data,0); mujoco.mj_forward(model,data)
    joint=model.joint("lid_hinge"); angle_index=int(joint.qposadr[0]); hinge_act=model.actuator("lid_control").id
    records=[]; snapshots=[]; contact_min=0.; max_base_tilt=0.; finite=True; max_force=0.
    qmin=np.full(model.nq,np.inf);qmax=np.full(model.nq,-np.inf)
    # Targets are actuator controls. qpos is set only by the initial keyframe.
    phases=[("settle",P["opening_deg"],.8,{}), ("close",1,1.5,{}),("closed_hold",1,.5,{}),
            ("open",135,1.8,{}),("open_hold",135,.5,{}),
            ("press_W",135,.4,{"key_w":-.0015}),("release_W",135,.4,{}),
            ("press_space",135,.4,{"key_space":-.0015}),("release_space",135,.4,{}),
            ("click_trackpad",135,.4,{"trackpad":-.0008}),("release_trackpad",135,.4,{}),
            ("return",P["opening_deg"],1.5,{}),("returned_hold",P["opening_deg"],.5,{})]
    next_frame=0;states=[]
    for label,degrees,duration,press in phases:
        initial=data.ctrl[hinge_act]; target=math.radians(degrees)
        for step in range(round(duration/model.opt.timestep)):
            u=min(1,(step*model.opt.timestep)/max(duration*.8,.01)); smooth=u*u*(3-2*u)
            data.ctrl[:]=0; data.ctrl[hinge_act]=initial+(target-initial)*smooth
            for name,val in press.items():data.ctrl[model.actuator(name+"_control").id]=val
            mujoco.mj_step(model,data)
            finite=finite and np.isfinite(data.qpos).all() and np.isfinite(data.qvel).all()
            qmin=np.minimum(qmin,data.qpos);qmax=np.maximum(qmax,data.qpos)
            max_force=max(max_force,float(abs(data.actuator_force[hinge_act])))
            if data.ncon:contact_min=min(contact_min,float(min(c.dist for c in data.contact[:data.ncon])))
            base_rotation=data.xmat[model.body("base").id].reshape(3,3)
            max_base_tilt=max(max_base_tilt,float(np.rad2deg(np.arccos(np.clip(base_rotation[2,2],-1,1)))))
            if data.time>=next_frame:
                states.append({"time":float(data.time),"phase":label,"qpos":data.qpos.tolist(),
                               "bodies":{mujoco.mj_id2name(model,mujoco.mjtObj.mjOBJ_BODY,i):{"pos":data.xpos[i].tolist(),"quat_wxyz":data.xquat[i].tolist()} for i in range(1,model.nbody)}})
                next_frame+=1/24
        records.append({"phase":label,"target_deg":degrees,"angle_deg":float(np.rad2deg(data.qpos[angle_index])),
                        "base_z":float(data.qpos[2]),"hinge_force_Nm":float(data.actuator_force[hinge_act]),
                        "W_displacement_m":float(data.qpos[model.joint("key_w_press").qposadr[0]]),
                        "space_displacement_m":float(data.qpos[model.joint("key_space_press").qposadr[0]]),
                        "trackpad_displacement_m":float(data.qpos[model.joint("trackpad_press").qposadr[0]])})
    phase={r["phase"]:r for r in records}
    warnings={str(i):int(w.number) for i,w in enumerate(data.warning) if w.number}
    checks={"model_loads":True,"finite_dynamics":bool(finite),"no_solver_warnings":not warnings,"positive_mass_and_inertia":bool((model.body_mass[1:]>0).all() and (model.body_inertia[1:]>0).all()),
            "lid_close_reached":abs(phase["closed_hold"]["angle_deg"]-1)<2,
            "lid_open_reached":abs(phase["open_hold"]["angle_deg"]-135)<2,
            "lid_return_reached":abs(phase["returned_hold"]["angle_deg"]-P["opening_deg"])<2,
            "lid_limits":bool(qmin[angle_index]>=-.005 and qmax[angle_index]<=math.radians(145)+.005),
            "W_press_and_release":phase["press_W"]["W_displacement_m"]<-.0011 and abs(phase["release_W"]["W_displacement_m"])<.0001,
            "space_press_and_release":phase["press_space"]["space_displacement_m"]<-.0008 and abs(phase["release_space"]["space_displacement_m"])<.0001,
            "trackpad_press_and_release":phase["click_trackpad"]["trackpad_displacement_m"]<-.0005 and abs(phase["release_trackpad"]["trackpad_displacement_m"])<.0001,
            "base_stable":max_base_tilt<8 and abs(phase["returned_hold"]["base_z"])<.005,
            "bounded_penetration":contact_min>-.001,
            "actuator_torque_bound":max_force<=1.80001}
    report={"engine":"MuJoCo","version":mujoco.__version__,"dt":model.opt.timestep,"simulated_seconds":float(data.time),
            "nq":model.nq,"nv":model.nv,"nbody":model.nbody,"actuators":model.nu,"checks":checks,"all_checks_passed":all(checks.values()),
            "phases":records,"minimum_contact_distance_m":contact_min,"max_base_tilt_deg":max_base_tilt,
            "maximum_hinge_actuator_torque_Nm":max_force,"physical_truth_verified":False,
            "control_method":"Smooth actuator target changes followed by mj_step; no scripted qpos animation",
            "visualization":"Actual MuJoCo body transforms replayed in Blender; rendering itself is not a live simulation","solver_warnings":warnings,
            "limitations":["Dimensions and physical parameters are image/category inferences","Virtual hinge actuator represents user-applied opening torque, not a powered real laptop hinge",
                           "Primitive collision proxies approximate visible surfaces","Adjacent parent-child contacts use MuJoCo's default filtering",
                           "Full Blender PBR is approximated by MuJoCo material and texture support"]}
    (ROOT/"physics_report.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    (ROOT/"trajectory.json").write_text(json.dumps({"fps":24,"states":states}),encoding="utf-8")
    print(json.dumps({"checks":checks,"all_passed":all(checks.values()),"minimum_contact_distance_m":contact_min,"max_base_tilt_deg":max_base_tilt}))


if __name__=="__main__":compile_asset();simulate()
