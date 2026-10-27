"""Reusable Blender scene, detailed primitives, neural regions and body-local export."""
from pathlib import Path
import json,math,shutil
import numpy as np
import bpy
from mathutils import Vector,Matrix

class Builder:
    def __init__(self,root):
        self.root=Path(root);self.plan=json.loads((self.root/'asset_plan.json').read_text(encoding='utf-8'))
        self.camera=json.loads((self.root/'camera.json').read_text());a=np.load(self.root/'native_geometry.npz')
        self.normals=np.load(self.root/'native_normals.npy') if (self.root/'native_normals.npy').exists() else None
        self.v=a['vertices'];self.f=a['faces'];self.uv=a['uv'];self.color=a['face_colors'];self.c=self.v[self.f].mean(1)
        self.lo=self.v.min(0);self.hi=self.v.max(0);self.ext=self.hi-self.lo;self.L=float(self.ext.max())
        self.bodies={};self.proxies=[];self.operations=[];self.regions={};self.controls=[];self.limitations=[]
        bpy.ops.wm.read_factory_settings(use_empty=True)
        scene=bpy.context.scene;scene.unit_settings.system='METRIC';scene.render.engine='CYCLES';scene.cycles.samples=24;scene.cycles.use_denoising=True;scene.render.threads_mode='FIXED';scene.render.threads=4
        scene.render.resolution_x=scene.render.resolution_y=1024;scene.render.resolution_percentage=100;scene.render.film_transparent=True
        scene.render.image_settings.file_format='PNG';scene.view_settings.view_transform='AgX'
        world=bpy.data.worlds.new('studio');world.use_nodes=True;world.node_tree.nodes['Background'].inputs[0].default_value=(.3,.3,.3,1)
        world.node_tree.nodes['Background'].inputs[1].default_value=.45;scene.world=world
        target=(self.lo+self.hi)/2
        for name,vec,power,size in [('key',(-1.4,-2,2.5),300,2),('fill',(1.4,-.7,1.1),130,1.6),('rim',(0,2,2),180,1.4)]:
            data=bpy.data.lights.new(name,'AREA');data.energy=power*self.L*self.L;data.shape='DISK';data.size=size*self.L
            ob=bpy.data.objects.new(name,data);scene.collection.objects.link(ob);ob.location=target+np.array(vec)*self.L
            ob.rotation_euler=(Vector(target)-ob.location).to_track_quat('-Z','Y').to_euler()
        data=bpy.data.cameras.new('reference_camera');ob=bpy.data.objects.new('reference_camera',data);scene.collection.objects.link(ob);scene.camera=ob
        self.set_camera(self.camera)
        self.neural=self.material('TRELLIS_native_PBR',(1,1,1),0,.5)
        n=self.neural.node_tree.nodes;link=self.neural.node_tree.links;bs=n.get('Principled BSDF')
        tex=n.new('ShaderNodeTexImage');tex.image=bpy.data.images.load(str(self.root/'asset/baseColorTexture.png'));link.new(tex.outputs['Color'],bs.inputs['Base Color'])
        self.neural['texture']='baseColorTexture.png'
        mrpath=self.root/'asset/metallicRoughnessTexture.png'
        if mrpath.exists():
            mr=n.new('ShaderNodeTexImage');mr.image=bpy.data.images.load(str(mrpath));mr.image.colorspace_settings.name='Non-Color'
            split=n.new('ShaderNodeSeparateColor');link.new(mr.outputs['Color'],split.inputs['Color']);link.new(split.outputs['Green'],bs.inputs['Roughness']);link.new(split.outputs['Blue'],bs.inputs['Metallic'])
    def set_camera(self,c):
        ob=bpy.context.scene.camera;ob.location=c['location'];right=np.array(c['right']);up=np.array(c['up']);eye=np.cross(right,up)
        ob.rotation_euler=Matrix(np.column_stack([right,up,eye]).tolist()).to_euler();ob.data.type=c.get('type','ORTHO');ob.data.lens=c.get('lens_mm',50);ob.data.sensor_width=c.get('sensor_width_mm',36);ob.data.ortho_scale=c['ortho_scale']
        ob.data.shift_x=c['shift_x'];ob.data.shift_y=c['shift_y'];ob.data.clip_end=max(100,20*self.L);ob.data.clip_start=self.L*.001
    def material(self,name,color,metal=0,rough=.5):
        m=bpy.data.materials.new(name);m.use_nodes=True;bs=m.node_tree.nodes.get('Principled BSDF')
        bs.inputs['Base Color'].default_value=(*color,1);bs.inputs['Metallic'].default_value=metal;bs.inputs['Roughness'].default_value=rough;m.diffuse_color=(*color,1);return m
    def variant(self,name,metal,rough):
        m=self.neural.copy();m.name=name;bs=m.node_tree.nodes.get('Principled BSDF')
        for k,v in [('Metallic',metal),('Roughness',rough)]:
            for link in list(bs.inputs[k].links):m.node_tree.links.remove(link)
            bs.inputs[k].default_value=v
        return m
    def body(self,name,pivot=(0,0,0),parent=None,mass=1,kind='fixed',axis=(0,0,1),limits=None,**extra):
        pivot=np.array(pivot,float);ob=bpy.data.objects.new('body_'+name,None);bpy.context.collection.objects.link(ob)
        if parent:
            ob.parent=bpy.data.objects['body_'+parent];pos=pivot-np.array(self.bodies[parent]['pivot_world'])
        else:pos=pivot
        ob.location=pos
        self.bodies[name]={'name':name,'parent':parent,'pos':pos.tolist(),'pivot_world':pivot.tolist(),'mass':mass,'kind':kind,'axis':list(axis),'range':limits,**extra}
        return ob
    def mesh(self,name,vertices,faces,owner,mat,uv=None,world=True):
        vertices=np.asarray(vertices)
        if world:vertices=vertices-np.array(self.bodies[owner]['pivot_world'])
        mesh=bpy.data.meshes.new(name);mesh.from_pydata(vertices.tolist(),[],np.asarray(faces).tolist());mesh.update()
        ob=bpy.data.objects.new(name,mesh);bpy.context.collection.objects.link(ob);ob.parent=bpy.data.objects['body_'+owner];ob['body']=owner;mesh.materials.append(mat)
        if uv is not None:
            layer=mesh.uv_layers.new(name='NativeAtlas')
            for loop in mesh.loops:layer.data[loop.index].uv=uv[loop.vertex_index]
        for face in mesh.polygons:face.use_smooth=True
        return ob
    def native(self,name,mask,owner,mat=None,vertices=None):
        faces=self.f[mask]
        if len(faces)==0:return None
        used,inv=np.unique(faces.ravel(),return_inverse=True);v=self.v if vertices is None else vertices
        ob=self.mesh(name,v[used],inv.reshape(-1,3),owner,mat or self.neural,self.uv[used])
        if self.normals is not None:ob.data.normals_split_custom_set_from_vertices(self.normals[used].tolist())
        ob['native_faces']=len(faces);self.regions[name]={'faces':len(faces),'body':owner,'original_uv_retained':True}
        return ob
    def box(self,name,size,pos,owner,mat,bevel=.003,collision=False):
        bpy.ops.mesh.primitive_cube_add(size=1,location=pos);ob=bpy.context.object;ob.name=name;ob.dimensions=size
        bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
        ob.parent=bpy.data.objects['body_'+owner];ob.location=np.array(pos)-self.bodies[owner]['pivot_world'];ob['body']=owner;ob.data.materials.append(mat)
        if bevel:
            mod=ob.modifiers.new('edge_bevel','BEVEL');mod.width=min(bevel,min(size)*.22);mod.segments=3;bpy.ops.object.modifier_apply(modifier=mod.name)
            mod=ob.modifiers.new('weighted_normals','WEIGHTED_NORMAL')
        if collision:self.proxy(owner,'box',pos,np.array(size)/2)
        return ob
    def cylinder(self,name,radius,depth,pos,axis,owner,mat,vertices=48,collision=False):
        bpy.ops.mesh.primitive_cylinder_add(vertices=vertices,radius=radius,depth=depth,location=pos);ob=bpy.context.object;ob.name=name
        ob.rotation_euler=Vector(axis).to_track_quat('Z','Y').to_euler();bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
        ob.parent=bpy.data.objects['body_'+owner];ob.location=np.array(pos)-self.bodies[owner]['pivot_world'];ob['body']=owner;ob.data.materials.append(mat)
        for p in ob.data.polygons:p.use_smooth=len(p.vertices)==4
        if collision:self.proxy(owner,'cylinder',pos,[radius,depth/2],axis=axis)
        return ob
    def sweep(self,name,points,radius,owner,mat,cyclic=False):
        data=bpy.data.curves.new(name,'CURVE');data.dimensions='3D';data.resolution_u=10;data.bevel_depth=radius;data.bevel_resolution=3;data.use_fill_caps=True
        spline=data.splines.new('BEZIER');spline.bezier_points.add(len(points)-1)
        for p,co in zip(spline.bezier_points,points):p.co=np.array(co)-self.bodies[owner]['pivot_world'];p.handle_left_type=p.handle_right_type='AUTO'
        spline.use_cyclic_u=cyclic;ob=bpy.data.objects.new(name,data);bpy.context.collection.objects.link(ob);ob.parent=bpy.data.objects['body_'+owner];ob['body']=owner;data.materials.append(mat)
        copy=ob.copy();copy.data=data.copy();copy.name=name+'_editable_curve';copy.hide_render=True;copy.hide_viewport=True;copy['staging_only']=True;bpy.context.collection.objects.link(copy)
        bpy.ops.object.select_all(action='DESELECT');ob.select_set(True);bpy.context.view_layer.objects.active=ob;bpy.ops.object.convert(target='MESH');ob.select_set(False)
        self.operations.append({'operation':'curve profile sweep','target':name});return ob
    def proxy(self,owner,typ,pos,size,axis=(0,0,1),**extras):
        self.proxies.append({'body':owner,'type':typ,'pos':(np.array(pos)-self.bodies[owner]['pivot_world']).tolist(),'size':np.asarray(size).tolist(),'axis':list(axis),**extras})
    def capsule(self,owner,a,b,radius):
        self.proxies.append({'body':owner,'type':'capsule','fromto':np.r_[np.array(a)-self.bodies[owner]['pivot_world'],np.array(b)-self.bodies[owner]['pivot_world']].tolist(),'size':[radius]})
    def render(self,name,res=1024):
        bpy.context.scene.render.resolution_x=bpy.context.scene.render.resolution_y=res;bpy.context.scene.render.filepath=str(self.root/'renders'/name);bpy.ops.render.render(write_still=True)
    def raw(self):
        self.body('raw',mass=1);ob=self.native('raw_neural',np.ones(len(self.f),bool),'raw');self.render('native.png')
        bpy.ops.wm.save_as_mainfile(filepath=str(self.root/'asset/native.blend'))
        bpy.data.objects.remove(ob,do_unlink=True);bpy.data.objects.remove(bpy.data.objects['body_raw'],do_unlink=True);self.bodies={};self.regions={}
    def export(self):
        out=self.root/'asset';(out/'meshes').mkdir(exist_ok=True);(out/'textures').mkdir(exist_ok=True);parts=[];deps=bpy.context.evaluated_depsgraph_get();bounds={}
        for ob in sorted(bpy.context.scene.objects,key=lambda x:x.name):
            if ob.type!='MESH' or ob.get('staging_only') or not ob.get('body'):continue
            owner=ob['body'];root=bpy.data.objects['body_'+owner];ev=ob.evaluated_get(deps);m=ev.to_mesh();m.calc_loop_triangles();T=root.matrix_world.inverted()@ob.matrix_world
            verts=np.array([T@v.co for v in m.vertices]);bounds.setdefault(owner,[]).extend([verts.min(0),verts.max(0)])
            layer=m.uv_layers.active
            for mi,mat in enumerate(m.materials):
                tris=[t for t in m.loop_triangles if t.material_index==mi]
                if not tris:continue
                name=ob.name+('_mat'+str(mi) if len(m.materials)>1 else '');lines=['v %.9g %.9g %.9g'%tuple(v) for v in verts]
                for loop in m.loops:lines.append('vt %.9g %.9g'%tuple(layer.data[loop.index].uv if layer else (0,0)))
                for t in tris:lines.append('f '+' '.join('%d/%d'%(m.loops[i].vertex_index+1,i+1) for i in t.loops))
                (out/'meshes'/(name+'.obj')).write_text('\n'.join(lines)+'\n',encoding='utf-8')
                bs=mat.node_tree.nodes.get('Principled BSDF');part={'name':name,'body':owner,'mesh':'meshes/'+name+'.obj','material':mat.name,
                  'rgba':list(bs.inputs['Base Color'].default_value),'roughness':float(bs.inputs['Roughness'].default_value),'metallic':float(bs.inputs['Metallic'].default_value)}
                if mat.get('texture'):
                    tex=mat['texture'];shutil.copy2(out/tex,out/'textures'/tex);part['texture']='textures/'+tex;part['rgba']=[1,1,1,1]
                parts.append(part)
            ev.to_mesh_clear()
        for owner,body in self.bodies.items():
            a=np.array(bounds.get(owner,[[0,0,0],[self.L*.01]*3]));lo=a.min(0);hi=a.max(0);body['com']=((lo+hi)/2).tolist();body['inertia_box']=np.maximum(hi-lo,self.L*.001).tolist()
            if not any(p['body']==owner for p in self.proxies):self.proxy(owner,'box',(lo+hi)/2+body['pivot_world'],np.maximum((hi-lo)/2,self.L*.001))
        manifest={'parts':parts,'bodies':self.bodies,'collision_proxies':self.proxies,'controls':self.controls,'length_scale_m':self.L}
        (out/'visual_manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8');bpy.context.scene['body_definitions']=json.dumps(self.bodies)
        bpy.ops.object.select_all(action='DESELECT')
        for ob in bpy.context.scene.objects:
            if ob.type=='EMPTY' or ob.type=='MESH' and ob.get('body') and not ob.get('staging_only'):ob.select_set(True)
        bpy.ops.export_scene.gltf(filepath=str(out/'model.glb'),use_selection=True,export_format='GLB');bpy.ops.file.pack_all();bpy.ops.wm.save_as_mainfile(filepath=str(out/'model.blend'))
        self.render('refined.png')
        clay=self.material('inspection_clay',(.45,.45,.45),0,.65);bpy.context.view_layer.material_override=clay;self.render('refined_clay.png');bpy.context.view_layer.material_override=None
        for name,delta in [('back',(1.5,2.4,1.2)),('side',(-2.8,.05,.9))]:
            cam=bpy.context.scene.camera;target=(self.lo+self.hi)/2;cam.location=target+np.array(delta)*self.L;cam.rotation_euler=(Vector(target)-cam.location).to_track_quat('-Z','Y').to_euler();cam.data.ortho_scale=self.L*1.3;cam.data.shift_x=cam.data.shift_y=0
            self.render(name+'.png',640)
        self.set_camera(self.camera)
        report={'native_regions':self.regions,'native_faces_retained':sum(a['faces'] for a in self.regions.values()),'candidate_faces':len(self.f),
          'operations':self.operations,'limitations':self.limitations,'physics_parameters':'category priors; not measured','geometry_source':'new native job generated from this case input'}
        (self.root/'refinement_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
