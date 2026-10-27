"""Refine an actual TRELLIS.2 native mesh into an articulated Blender asset."""
import json,math,sys
from pathlib import Path
import bpy
import numpy as np
from mathutils import Vector
ROOT=Path(__file__).resolve().parent;sys.path.insert(0,str(ROOT))
import blender_helpers as H
from refinement_tools import loft,sweep_rim,difference
P=H.P
A=np.load(ROOT/'native_geometry_zup.npz');RAW_V=A['vertices'];F=A['faces'];UV=A['uv'];RAW_C=RAW_V[F].mean(axis=1)
FIT=json.loads((ROOT/'candidate_fit.json').read_text(encoding='utf-8'))
# A measured current-candidate transform into the explicit modeling reference
# frame, not an assumption that a newly generated mesh shares old coordinates.
V=RAW_V.copy();low,high=np.array(FIT['base_bounds']);deck=FIT['deck_z']
V[:,0]=(RAW_V[:,0]-(low[0]+high[0])/2)/(high[0]-low[0])
V[:,1]=(RAW_V[:,1]-low[1])/(high[1]-low[1])*(.3118+.350343)-.350343
V[:,2]=np.where(RAW_V[:,2]<=deck,-.327612+(RAW_V[:,2]-low[2])/(deck-low[2])*.028112,-.2995+RAW_V[:,2]-deck)
C=V[F].mean(axis=1)
LAYOUT=json.loads((ROOT/'key_layout.json').read_text())
REPORT={'source':'actual native job '+json.loads((ROOT/'native-job.json').read_text(encoding='utf-8'))['request']['job_id'],'input_faces':len(F),'native_regions':{},'operations':[],'current_candidate_registration':FIT}


def neural_material():
    m=H.material('TRELLIS_native_PBR',(1,1,1),0,.5);nodes=m.node_tree.nodes;links=m.node_tree.links;bs=nodes.get('Principled BSDF')
    tex=nodes.new('ShaderNodeTexImage');tex.image=bpy.data.images.load(str(ROOT/'asset/baseColorTexture.png'));links.new(tex.outputs['Color'],bs.inputs['Base Color'])
    mr=nodes.new('ShaderNodeTexImage');mr.image=bpy.data.images.load(str(ROOT/'asset/metallicRoughnessTexture.png'));mr.image.colorspace_settings.name='Non-Color'
    split=nodes.new('ShaderNodeSeparateColor');links.new(mr.outputs['Color'],split.inputs['Color']);links.new(split.outputs['Green'],bs.inputs['Roughness']);links.new(split.outputs['Blue'],bs.inputs['Metallic'])
    m['mujoco_texture']=str(ROOT/'asset/baseColorTexture.png')
    return m


def native_region(name,mask,points,material,owner):
    selected=F[mask];used,inverse=np.unique(selected.ravel(),return_inverse=True)
    faces=inverse.reshape(-1,3);vertices=points[used]
    mesh=bpy.data.meshes.new(name);mesh.from_pydata(vertices.tolist(),[],faces.tolist());mesh.update()
    layer=mesh.uv_layers.new(name='NativeAtlas')
    uv=UV[used]
    for loop in mesh.loops:layer.data[loop.index].uv=uv[loop.vertex_index]
    for face in mesh.polygons:face.use_smooth=True
    obj=bpy.data.objects.new(name,mesh);bpy.context.collection.objects.link(obj);obj.parent=bpy.data.objects['body_'+owner];obj['body']=owner
    obj.data.materials.append(material);obj['native_face_count']=len(selected);obj['source_job']=REPORT['source']
    REPORT['native_regions'][name]={'faces':len(selected),'vertices':len(used),'owner':owner,'UV':'original candidate UV retained through region extraction and vertex deformation'}
    return obj


def base_transform(v):
    out=v.copy();out[:,0]*=.36
    out[:,1]=(v[:,1]+.350343)/(.3118+.350343)*P['depth_m']-P['depth_m']/2
    z=v[:,2];out[:,2]=np.maximum(.002,.002+(z+.327612)/.028112*.016)
    upper=z>-.2995;out[upper,2]=.018+(z[upper]+.2995)*.16
    # Continuous deformation avoids folds at piecewise region boundaries.
    return out


def lid_transform(v):
    v=RAW_V
    k,c=FIT['lid_plane_y_equals_k_z_plus_b']
    direction=np.array([0,k,1]);direction/=np.linalg.norm(direction)
    normal=np.array([0,1,-k]);normal/=np.linalg.norm(normal)
    u0,u1=FIT['lid_u_range'];length=v@direction-u0;thick=(v-[0,c,0])@normal
    xmin,xmax=FIT['lid_x_range']
    out=np.zeros_like(v);out[:,0]=(v[:,0]-(xmin+xmax)/2)*(P['lid_width_m']/(xmax-xmin))
    out[:,1]=-np.clip(length/(u1-u0),0,1)*P['lid_height_m']
    out[:,2]=np.clip(thick*.36,-.0065,.0047)
    def smooth(u):
        t=np.clip(u,0,1);return t*t*(3-2*t)
    weight=smooth((.445-np.abs(v[:,0]))/.035)*smooth((length-.022)/.024)*smooth(((u1-u0)-.02-length)/.025)
    # Gradual deformation preserves normals across the rim-to-panel transition.
    target=np.where(thick<0,-.00335+(thick+.0075)*.065,.0037+(thick-.0100)*.065)
    out[:,2]=out[:,2]*(1-weight)+target*weight
    return out


def render(name):
    bpy.context.view_layer.update();bpy.context.scene.render.filepath=str(ROOT/'renders'/name);bpy.ops.render.render(write_still=True)


def main():
    H.setup_scene();scene=bpy.context.scene;scene.cycles.samples=40;scene.render.threads_mode='FIXED';scene.render.threads=4
    # Matched lighting used for candidate and refinement comparisons.
    for ob in scene.objects:
        if ob.type=='LIGHT':ob.data.energy*=.42
    scene.world.node_tree.nodes['Background'].inputs[1].default_value=.32
    scene.view_settings.view_transform='AgX'
    native=neural_material()
    H.body('base',kind='free',mass=1.35,com=[0,0,.010],inertia_box=[.36,P['depth_m'],.018])
    aligned=V.copy();aligned[:,0]*=.36;aligned[:,1]=(V[:,1]+.350343)/(.3118+.350343)*P['depth_m']-P['depth_m']/2;aligned[:,2]=(V[:,2]+.327612)*.36+.002
    baseline=native_region('native_unrepaired',np.ones(len(F),dtype=bool),aligned,native,'base')
    render('native_aligned.png');bpy.ops.file.pack_all();bpy.ops.wm.save_as_mainfile(filepath=str(ROOT/'asset/native_aligned.blend'))
    bpy.data.objects.remove(baseline,do_unlink=True);REPORT['native_regions'].pop('native_unrepaired')
    base_points=base_transform(V)
    # Remove only the fused keyboard/control patches and obsolete hinge connective area.
    keyboard=(np.abs(C[:,0])<.436)&(C[:,1]>-.183)&(C[:,1]<.195)&(C[:,2]>-.302)
    touch=(np.abs(C[:,0])<.145)&(C[:,1]>-.337)&(C[:,1]<-.179)&(C[:,2]>-.305)
    base_mask=(C[:,2]<-.270)&~keyboard&~touch
    base=native_region('native_chassis_refined',base_mask,base_points,native,'base')
    REPORT['operations'].append({'operation':'local mesh region extraction and surface deformation','target':'native chassis','purpose':'retain native case and PBR, straighten bottom/side edges and deck, remove fused controls'})
    lid=H.body('lid',(0,P['hinge_y'],P['hinge_z']),kind='hinge',mass=.48,
               com=[0,-P['lid_height_m']/2,0],inertia_box=[P['lid_width_m'],P['lid_height_m'],.009],axis=[-1,0,0],range=[0,145])
    lid.rotation_euler[0]=-math.radians(P['opening_deg'])
    lid_mask=RAW_C[:,2]>FIT['lid_face_cut_z']
    lid_obj=native_region('native_lid_refined',lid_mask,lid_transform(V),native,'lid')
    REPORT['operations'].append({'operation':'local surface deformation','target':'native lid','purpose':'fit closure coverage, straighten broad display/back panel while preserving native rim, shape and PBR'})

    dark=H.material('graphite_refinement',(.011,.013,.015),.02,.38)
    orange=H.material('source_orange_key',(.88,.235,.10),0,.38)
    red=H.material('source_red_wells',(.42,.018,.007),.10,.4)
    silver=H.material('machined_edge',(.24,.25,.26),.65,.3)
    rubber=H.material('rubber_gasket',(.006,.007,.008),0,.68)
    touchmat=H.material('touchpad_glass',(.038,.040,.043),.18,.28)
    # The native control cutout is rebuilt as a recessed tray with actual Boolean geometry.
    kb_y0=base_transform(np.array([[0,-.181,-.2995]]))[0,1];kb_y1=base_transform(np.array([[0,.190,-.2995]]))[0,1]
    mid=(kb_y0+kb_y1)/2;depth=kb_y1-kb_y0
    tray=loft('keyboard_tray',[(.314,depth+.008,.0025,.0168),(.314,depth+.008,.0025,.0185)],silver,'base',(0,mid,0))
    cutter=H.rounded('keyboard_recess_cutter',(.305,depth,.005),(0,mid,.0206),dark,radius=.0018)
    difference(tray,cutter)
    H.rounded('keyboard_recess_floor',(.305,depth,.0008),(0,mid,.0176),dark,radius=.0018)
    REPORT['operations'].append({'operation':'Boolean difference','target':'keyboard tray','purpose':'real recessed mounting tray in the local native control patch'})
    xs=np.array(LAYOUT['x_centers_native']);ys=np.array(LAYOUT['y_centers_native']);key_count=0
    for row,y in enumerate(ys):
        yhi=.190 if row==0 else (y+ys[row-1])/2
        ylo=-.181 if row==len(ys)-1 else (y+ys[row+1])/2
        for col,x in enumerate(xs):
            if row==5 and 5<=col<=8:continue
            space=row==5 and col==4
            xhi=.43 if col==len(xs)-1 else (x+xs[col+1])/2
            xlo=-.43 if col==0 else (x+xs[col-1])/2
            if space:xhi=(xs[8]+xs[9])/2;x=(xlo+xhi)/2
            pos=base_transform(np.array([[x,y,-.289]]))[0];pos[2]=.02035
            name='key_space' if space else ('key_w' if (row,col)==(3,3) else 'key_%02d_%02d'%(row,col))
            span=5 if space else 1
            H.body(name,pos,kind='key',mass=.0012*span,axis=[0,0,1],range=[-.0015,0],stiffness=500*span)
            width=(xhi-xlo)*.36-.0032;key_depth=(yhi-ylo)*P['depth_m']/(.3118+.350343)-.003
            key_depth=min(key_depth,.0168)
            selected=(C[:,0]>xlo)&(C[:,0]<xhi)&(C[:,1]>ylo)&(C[:,1]<yhi)&(C[:,2]>-.2945)&(C[:,2]<-.274)
            special=(row,col) in {(3,3),(4,2),(4,3),(4,4),(4,12),(4,13),(5,12),(5,13)}
            capmat=orange if special else dark
            # Loft gives a consistent tapered skirt and a shallow dish; retained native top sits above it.
            loft(name+'_skirt',[(width,key_depth,.0013,-.0013),(width,key_depth,.0013,-.0007),
                                (width-.0012,key_depth-.0012,.0016,.0010),(width-.003,key_depth-.003,.0016,.00085)],capmat,name)
            if not space and np.count_nonzero(selected)>20:
                points=base_points-pos
                points[:,0]=np.clip(points[:,0],-width*.49,width*.49)
                points[:,1]=np.clip(points[:,1],-key_depth*.49,key_depth*.49)
                # Smooth inconsistent height while retaining candidate top shape and UV texture.
                points[:,2]=np.clip((V[:,2]+.2945)*.18-.00125,-.00125,.00125)
                native_region(name+'_native_top',selected,points,orange if special else native,name)
            H.rounded(name+'_well',(width+.0015,key_depth+.0015,.0007),(pos[0],pos[1],.0185),red,radius=.0007)
            key_count+=1
    REPORT['operations'].append({'operation':'semantic local mesh extraction, local height edits and section lofts','target':'keyboard','purpose':'regularize fused and inconsistent native keys to an editable image-informed grid; retain local neural top patches, create independent tapered key bodies and restore observed orange keys','key_count':key_count,'layout_inferred':True})
    # A distinct touchpad closes the removed native fused control patch.
    pad_y=base_transform(np.array([[0,-.252,-.2995]]))[0,1]
    H.body('trackpad',(0,pad_y,.0188),kind='key',mass=.018,axis=[0,0,1],range=[-.0008,0],stiffness=1800)
    loft('touchpad_panel',[(.099,.044,.0010,-.00065),(.099,.044,.0010,0),(.0978,.0428,.0011,.00035)],touchmat,'trackpad')
    sweep_rim('touchpad_seam',.1006,.0456,.0015,.00024,dark,'base',(0,pad_y,.0183))
    H.rounded('touchpad_floor',(.112,.060,.0012),(0,pad_y,.0180),silver,radius=.001)
    # Restore controlled hinge geometry in the cut interface; curves remain editable in the blend.
    for x in [-.142,.142]:
        loft('hinge_shroud_'+str(x),[(.022,.017,.0015,.018),(.022,.017,.0015,.029),(.021,.016,.002,.031)],silver,'base',(x,P['hinge_y']-.002,0))
    sweep_rim('display_rim_seal',P['lid_width_m']-.010,P['lid_height_m']-.008,.008,.0004,rubber,'lid',(0,-P['lid_height_m']/2,-.0060))
    REPORT['operations'].append({'operation':'curve profile sweep','target':'display rim and touchpad boundary','purpose':'continuous controlled seal/seam contours fitted to the retained native surfaces'})
    for x in [-.145,.145]:
        for y in [-P['depth_m']/2+.022,P['depth_m']/2-.022]:H.rounded('foot_%s_%s'%(x,y),(.031,.010,.002),(x,y,.001),rubber,radius=.004)
    scene['body_definitions']=json.dumps(H.BODIES);scene['source_image']=str(ROOT/'input/source.png');scene['neural_provenance']=json.dumps(REPORT)
    scene['authorship']='Current Codex applies trellis2-native-refine: newly generated native geometry/PBR + Blender deformation, local editing, lofts, Boolean and sweeps'
    bpy.context.view_layer.update()
    # Inspect actual lid/base vertex bounds at the closed pose, not only parameter formulas.
    lid.rotation_euler[0]=0;bpy.context.view_layer.update()
    lv=np.array([tuple(lid_obj.matrix_world@v.co) for v in lid_obj.data.vertices]);bv=np.array([tuple(base.matrix_world@v.co) for v in base.data.vertices])
    front_gap=float(lv[:,1].min()-bv[:,1].min());side_gap=float((np.ptp(bv[:,0])-np.ptp(lv[:,0]))/2)
    REPORT['closed_geometry']={'front_gap_m':front_gap,'mean_side_gap_m':side_gap,'front_coverage_passed':abs(front_gap)<.003,'side_coverage_passed':abs(side_gap)<.004}
    render('closed.png')
    lid.rotation_euler[0]=-math.radians(P['opening_deg']);bpy.context.view_layer.update()
    H.export_assets();bpy.ops.file.pack_all();bpy.ops.wm.save_as_mainfile(filepath=str(ROOT/'asset/laptop.blend'))
    render('source_final.png')
    REPORT['retained_native_faces']=sum(v['faces'] for v in REPORT['native_regions'].values())
    REPORT['remaining_limitations']=['Single-view physical properties are inferred','Native geometric regions are regularized to mechanical constraints','Some key colors and repaired patches use authored material rather than neural texture','Unknown back/underside features are hypotheses']
    (ROOT/'refinement_report.json').write_text(json.dumps(REPORT,indent=2),encoding='utf-8')
    print(json.dumps({'closed_geometry':REPORT['closed_geometry'],'native_faces_retained':REPORT['retained_native_faces'],'keys':key_count}))


if __name__=='__main__':main()
