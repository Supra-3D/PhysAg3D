"""Local Blender loft, sweep and region-edit helpers used on the native candidate."""
import math
import bpy
import numpy as np

def ring(width,depth,radius,segments=6):
    r=min(radius,width*.49,depth*.49);points=[]
    for cx,cy,start in [(width/2-r,depth/2-r,0),(-width/2+r,depth/2-r,90),(-width/2+r,-depth/2+r,180),(width/2-r,-depth/2+r,270)]:
        for angle in np.linspace(start,start+90,segments+1):
            a=math.radians(angle);points.append((cx+r*math.cos(a),cy+r*math.sin(a)))
    return points

def loft(name,sections,mat,owner,center=(0,0,0),segments=6):
    # Explicit corresponding cross-sections: (width, depth, radius, local_z).
    vertices=[]
    for width,depth,radius,z in sections:vertices.extend((x,y,z) for x,y in ring(width,depth,radius,segments))
    n=len(vertices)//len(sections);faces=[tuple(reversed(range(n)))]
    for j in range(len(sections)-1):
        for i in range(n):faces.append((j*n+i,j*n+(i+1)%n,(j+1)*n+(i+1)%n,(j+1)*n+i))
    faces.append(tuple(range((len(sections)-1)*n,len(sections)*n)))
    mesh=bpy.data.meshes.new(name);mesh.from_pydata(vertices,[],faces);mesh.update()
    obj=bpy.data.objects.new(name,mesh);bpy.context.collection.objects.link(obj)
    obj.parent=bpy.data.objects['body_'+owner];obj.location=center;obj['body']=owner;obj['refinement']='section loft'
    obj.data.materials.append(mat)
    for p in mesh.polygons:p.use_smooth=(len(p.vertices)==4)
    uv=mesh.uv_layers.new(name='SurfaceUV')
    w,d,_,_=sections[0]
    for loop in mesh.loops:
        v=mesh.vertices[loop.vertex_index].co;uv.data[loop.index].uv=(v.x/w+.5,v.y/d+.5)
    return obj

def sweep_rim(name,width,depth,radius,tube,mat,owner,center):
    data=bpy.data.curves.new(name,'CURVE');data.dimensions='3D';data.resolution_u=2
    points=ring(width,depth,radius,16);spline=data.splines.new('POLY');spline.points.add(len(points)-1)
    for p,(x,y) in zip(spline.points,points):p.co=(x,y,0,1)
    spline.use_cyclic_u=True;data.bevel_depth=tube;data.bevel_resolution=3;data.use_fill_caps=True
    obj=bpy.data.objects.new(name,data);bpy.context.collection.objects.link(obj)
    obj.parent=bpy.data.objects['body_'+owner];obj.location=center;obj['body']=owner;obj['refinement']='curve profile sweep'
    data.materials.append(mat)
    # Keep the editable curve source in a hidden collection, export an evaluated mesh.
    editable=obj.copy();editable.data=data.copy();editable.name=name+'_curve_source';bpy.context.collection.objects.link(editable)
    editable.hide_render=True;editable.hide_viewport=True;editable['staging_only']=True
    bpy.ops.object.select_all(action='DESELECT');obj.select_set(True);bpy.context.view_layer.objects.active=obj;bpy.ops.object.convert(target='MESH')
    bpy.ops.object.mode_set(mode='EDIT');bpy.ops.mesh.select_all(action='SELECT');bpy.ops.uv.smart_project(island_margin=.02);bpy.ops.object.mode_set(mode='OBJECT')
    obj.select_set(False)
    return obj

def difference(obj,cutter):
    bpy.ops.object.select_all(action='DESELECT');obj.select_set(True);bpy.context.view_layer.objects.active=obj
    modifier=obj.modifiers.new('local_recess','BOOLEAN');modifier.operation='DIFFERENCE';modifier.solver='EXACT';modifier.object=cutter
    bpy.ops.object.modifier_apply(modifier=modifier.name)
    cutter.hide_render=True;cutter.hide_viewport=True;cutter['staging_only']=True
    obj['refinement']='Boolean difference'
    return obj
