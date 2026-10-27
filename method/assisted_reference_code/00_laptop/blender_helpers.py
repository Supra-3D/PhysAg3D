"""Shared scene/mesh export helpers; no previous asset geometry is loaded."""
import json,math
from pathlib import Path
import bpy
import numpy as np
from mathutils import Vector
ROOT=Path(__file__).resolve().parent
P=json.loads((ROOT/"parameters.json").read_text(encoding="utf-8"))
BODIES={}
def material(name,color,metal=0,rough=.5):
    m=bpy.data.materials.new(name); m.use_nodes=True
    bs=m.node_tree.nodes.get("Principled BSDF")
    bs.inputs["Base Color"].default_value=(*color,1)
    bs.inputs["Metallic"].default_value=metal; bs.inputs["Roughness"].default_value=rough
    m.diffuse_color=(*color,1)
    return m

def body(name,pos=(0,0,0),kind="fixed",parent="base",**extra):
    ob=bpy.data.objects.new("body_"+name,None); bpy.context.collection.objects.link(ob)
    if name!="base": ob.parent=bpy.data.objects["body_"+parent]
    ob.location=pos
    BODIES[name]={"name":name,"parent":None if name=="base" else parent,"pos":list(pos),"kind":kind,**extra}
    return ob

def rounded(name,dims,center,mat,owner="base",radius=.001,segments=5):
    w,d,h=dims; r=min(radius,w*.49,d*.49)
    ring=[]
    for cx,cy,start in ((w/2-r,d/2-r,0),(-w/2+r,d/2-r,90),(-w/2+r,-d/2+r,180),(w/2-r,-d/2+r,270)):
        for t in np.linspace(start,start+90,segments+1):
            t=math.radians(t); ring.append((cx+r*math.cos(t),cy+r*math.sin(t)))
    n=len(ring); verts=[(x,y,z) for z in (-h/2,h/2) for x,y in ring]
    faces=[tuple(reversed(range(n))),tuple(range(n,2*n))]
    faces += [(i,(i+1)%n,(i+1)%n+n,i+n) for i in range(n)]
    mesh=bpy.data.meshes.new(name); mesh.from_pydata(verts,[],faces); mesh.update()
    ob=bpy.data.objects.new(name,mesh); bpy.context.collection.objects.link(ob)
    ob.parent=bpy.data.objects["body_"+owner]; ob.location=center; ob["body"]=owner
    ob.data.materials.append(mat)
    # A small bevel catches light without replacing the explicitly rounded outline.
    bevel=ob.modifiers.new("edge_highlights","BEVEL"); bevel.width=min(.00035,h*.18); bevel.segments=2
    bevel.affect="EDGES"
    bpy.context.view_layer.objects.active=ob; ob.select_set(True)
    bpy.ops.object.modifier_apply(modifier=bevel.name)
    bpy.ops.object.mode_set(mode="EDIT"); bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=math.radians(66),island_margin=.018)
    bpy.ops.object.mode_set(mode="OBJECT"); ob.select_set(False)
    return ob

def setup_scene():
    bpy.ops.object.select_all(action="SELECT"); bpy.ops.object.delete(use_global=False)
    scene=bpy.context.scene; scene.unit_settings.system="METRIC"; scene.unit_settings.scale_length=1
    scene.render.engine="CYCLES"; scene.cycles.device="CPU"; scene.cycles.samples=32; scene.cycles.use_denoising=True
    scene.render.resolution_x=scene.render.resolution_y=1024; scene.render.resolution_percentage=100
    scene.render.image_settings.file_format="PNG"; scene.render.film_transparent=True
    scene.view_settings.view_transform="AgX"
    world=bpy.data.worlds.new("studio"); world.use_nodes=True
    world.node_tree.nodes["Background"].inputs[0].default_value=(.30,.30,.30,1)
    world.node_tree.nodes["Background"].inputs[1].default_value=.55; scene.world=world
    for name,pos,energy,size in [("key",(-.7,-.9,1.3),70,1.0),("fill",(.7,-.4,.7),35,.8),("rim",(0,1.1,1.0),50,.7)]:
        light=bpy.data.lights.new(name,"AREA"); light.energy=energy; light.shape="DISK"; light.size=size
        ob=bpy.data.objects.new(name,light); scene.collection.objects.link(ob); ob.location=pos
        ob.rotation_euler=(Vector((0,0,.10))-ob.location).to_track_quat("-Z","Y").to_euler()
    camdata=bpy.data.cameras.new("source_camera"); cam=bpy.data.objects.new("source_camera",camdata)
    scene.collection.objects.link(cam); c=P["camera"]; cam.location=c["location"]
    cam.rotation_euler=(Vector(c["target"])-cam.location).to_track_quat("-Z","Y").to_euler()
    camdata.type="PERSP"; camdata.sensor_fit="HORIZONTAL"; camdata.sensor_width=36
    camdata.lens=c["focal_pixels"]*36/1024; camdata.shift_x=(512-c["cx"])/1024; camdata.shift_y=(c["cy"]-512)/1024
    camdata.clip_start=.01; camdata.clip_end=20; scene.camera=cam

def export_assets():
    directory=ROOT/"asset/meshes"; directory.mkdir(parents=True,exist_ok=True)
    textures=ROOT/"asset/textures"; textures.mkdir(exist_ok=True)
    records=[]; deps=bpy.context.evaluated_depsgraph_get()
    for ob in sorted(bpy.context.scene.objects,key=lambda o:o.name):
        if ob.type!="MESH" or ob.get("staging_only") or ob.get("replaced"):continue
        owner=ob.get("body"); root=bpy.data.objects["body_"+owner]
        ev=ob.evaluated_get(deps); mesh=ev.to_mesh(); mesh.calc_loop_triangles()
        transform=root.matrix_world.inverted()@ob.matrix_world
        vertices=[transform@v.co for v in mesh.vertices]; layer=mesh.uv_layers.active
        for mi,mat in enumerate(mesh.materials):
            triangles=[t for t in mesh.loop_triangles if t.material_index==mi]
            if not triangles:continue
            name=ob.name+("_mat%d"%mi if len(mesh.materials)>1 else "")
            filename=name+".obj"; lines=[]
            for v in vertices:lines.append("v %.9g %.9g %.9g"%tuple(v))
            for loop in mesh.loops:
                xy=layer.data[loop.index].uv if layer else (0,0); lines.append("vt %.9g %.9g"%tuple(xy))
            for tri in triangles:lines.append("f "+" ".join("%d/%d"%(mesh.loops[i].vertex_index+1,i+1) for i in tri.loops))
            (directory/filename).write_text("\n".join(lines)+"\n",encoding="utf-8")
            bs=mat.node_tree.nodes.get("Principled BSDF")
            record={"name":name,"body":owner,"mesh":"meshes/"+filename,"material":mat.name,
                    "rgba":list(bs.inputs["Base Color"].default_value),"roughness":float(bs.inputs["Roughness"].default_value),
                    "metallic":float(bs.inputs["Metallic"].default_value)}
            if mat.get("mujoco_texture"):
                import shutil
                tex=ROOT/"asset"/Path(mat["mujoco_texture"]).name
                shutil.copy2(tex,textures/tex.name); record["texture"]="textures/"+tex.name; record["rgba"]=[1,1,1,1]
            records.append(record)
        ev.to_mesh_clear()
    (ROOT/"asset/visual_manifest.json").write_text(json.dumps({"frame":"Z-up metres, body local","parts":records,
       "bodies":json.loads(bpy.context.scene["body_definitions"])},indent=2),encoding="utf-8")
    bpy.ops.object.select_all(action="DESELECT")
    for ob in bpy.context.scene.objects:
        if ob.type=="EMPTY" or ob.type=="MESH" and not ob.get("staging_only") and not ob.get("replaced"):ob.select_set(True)
    bpy.ops.export_scene.gltf(filepath=str(ROOT/"asset/laptop.glb"),use_selection=True,export_format="GLB")
