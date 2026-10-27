from pathlib import Path
import sys,json,math,numpy as np,bpy
R=Path(__file__).resolve().parent;sys.path.insert(0,str(R))
from blender_common import Builder
from geometry_helpers import tube_between,shell_loft_x
P=json.loads((R/'semantic_parameters.json').read_text());B=Builder(R);c=B.c;col=B.color;h=B.hi[2]
# Selection is based on inspected new-candidate bounds and its green material zone.
shade=(c[:,2]>P['shade_zmin'])&(col[:,1]>col[:,0]*P['green_ratio'])&(col[:,2]<col[:,1]*.88)
base=(c[:,2]<P['base_zmax'])&(np.linalg.norm(c[:,:2]-[0,.124],axis=1)<.142);brass=B.material('brushed_brass',(.17,.14,.045),.45,.48);glass=B.material('source_inferred_olive_glass',(.025,.06,.006),.02,.65);inside=B.material('shade_inner_pale_glass',(.40,.49,.27),.02,.45)
B.body('base',mass=2.5,kind='free');B.body('shade',P['hinge'],parent='base',mass=.3,kind='hinge',axis=[1,0,0],limits=[-.42,.42],frictionloss=.014,kp=16,kv=.8,force_limit=8)
B.native('native_stepped_base',base,'base',B.variant('native_base_brass_response',.30,.50))
hood=B.native('native_curved_green_glass',shade,'shade',glass)
hood.data.materials.append(inside);bpy.context.view_layer.objects.active=hood;hood.select_set(True)
sol=hood.modifiers.new('inner_glass_thickness','SOLIDIFY');sol.thickness=.0015;sol.offset=-1;sol.use_even_offset=True;sol.material_offset=0;sol.material_offset_rim=0
bpy.ops.object.modifier_apply(modifier=sol.name);hood.select_set(False)
# Construct a smooth continuous stand and yoke from observed landmarks.
B.sweep('continuous_curved_brass_stand',P['stand_points'],P['stand_radius'],'base',brass)
for a,b in zip(P['stand_points'][:-1],P['stand_points'][1:]):B.capsule('base',a,b,P['stand_radius'])
B.sweep('continuous_shade_support_yoke',P['yoke_points'],.006,'base',brass)
hinge=np.array(P['hinge']);width=P['shade_width'];depth=P['shade_depth'];height=P['shade_height']
for s in [-1,1]:
 end=hinge+[s*(width/2+.018),0,0];tube_between(B,'shade_hinge_pin_'+str(s),end+[-.017,0,0],end+[.017,0,0],.008,'base',brass)
 B.cylinder('shade_pivot_cap_'+str(s),.010,.008,end+[s*.012,0,0],[1,0,0],'shade',brass)
# A thin inner shell closes genuine missing underside thickness while leaving the lamp mouth open.
# Inner thickness now follows the actual native surface rather than an intersecting approximate ellipse.
# Rim is attached to the moving hood; it does not bridge hood to fixed yoke.
# Pull switch remains a documented rigid visual detail attached to its socket.
chain_top=np.array(P['chain_top']);tube_between(B,'pull_chain',chain_top,chain_top+[0,0,-.105],.0008,'shade',brass);B.cylinder('pull_switch_weight',.0027,.006,chain_top+[0,0,-.108],[0,0,1],'shade',brass)
B.proxy('base','cylinder',P['base_center'],[P['base_radius'],P['base_halfheight']])
B.proxy('shade','box',hinge+[0,0,height*.5],[width*.47,depth*.44,height*.40])
B.controls=[{'body':'shade','label':'shade pitch','target':.30,'tolerance':.035}]
B.operations.extend([{'operation':'material-guided semantic extraction','target':'new native stepped base and green hood'}, {'operation':'curve profile sweeps','target':'smooth bent stand and continuous yoke fitted to source/candidate landmarks'}, {'operation':'inward solidify of actual native hood','target':'1.5 mm inner thickness following native surface; lamp mouth remains open'}, {'operation':'hinge pin and socket construction','target':'coincident X-axis pivots'}])
B.limitations.extend(['Only shade pitch is physically modeled; chain is rigid visual detail','No electrical, thermal or glass fracture simulation','Hidden inner shell, mass, scale and friction are inferred','Shade retains neural geometric ridges; its albedo is a source-informed uniform prior. Base retains the neural atlas.'])
B.operations.append({'operation':'source-informed material repair','target':'olive green shade','decision':'replace overbright neural green albedo by an editable uniform rough-glass prior; native geometry/UV preserved'})
B.export()
