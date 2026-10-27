import numpy as np,math,json
import bpy

def build(B):
    h=B.hi[2];c=B.c;v=B.v
    roof=v[v[:,2]>.98*h];low=np.quantile(roof,.01,axis=0);high=np.quantile(roof,.99,axis=0)
    xl,xr=float(low[0]),float(high[0]);yf,yb=float(low[1]),float(high[1]);width=xr-xl;depth=yb-yf
    door=(c[:,1]<yf-.005)&(c[:,2]>.018*h)
    bins=np.linspace(.55*h,.80*h,81);hist,_=np.histogram(c[door,2],bins);smooth=np.convolve(hist,np.ones(5)/5,mode='same');j=int(np.argmin(smooth[5:-5]))+5;split=float((bins[j]+bins[j+1])/2)
    upper=door&(c[:,2]>split);lower=door&~upper
    ivory=B.material('inferred_ivory_liner',(.61,.625,.565),.01,.58);steel=B.material('steel_hinge',(.29,.30,.29),.7,.28);gasket=B.material('door_gasket',(.37,.38,.35),0,.75)
    B.body('base',mass=45,kind='fixed')
    # Remove any accidental native face spanning the functional openings.
    in_opening=(c[:,0]>xl+.035)&(c[:,0]<xr-.035)&(c[:,1]<yf+.008)&(c[:,2]>.035)&(c[:,2]<h-.035)&(np.abs(c[:,2]-split)>.020)
    B.native('native_outer_cabinet',~door&~in_opening,'base')
    parts=[]
    for name,mask,mass in [('upper_door',upper,4.0),('lower_door',lower,9.0)]:
        p=c[mask]
        if len(p)<100:raise ValueError('Fresh refrigerator door partition too small: '+name)
        xy=p[:,:2];center=xy.mean(0);cov=(xy-center).T@(xy-center);ev,U=np.linalg.eigh(cov);direction=U[:,-1]
        if direction[0]<0:direction=-direction
        theta=float(math.atan2(direction[1],direction[0]));normal=np.array([-direction[1],direction[0]])
        # Plane through robust median, evaluated at actual cabinet right edge.
        normal_offset=float(np.median(xy@normal));hy=float((normal_offset-normal[0]*(xr+.003))/normal[1]);fit_pivot=np.array([xr+.003,hy,0.]);pivot=np.array([xr+.010,yf-.026,0.])
        delta=xy-fit_pivot[:2];proj=delta@direction;ext=np.quantile(proj,[.003,.997]);z0,z1=np.quantile(p[:,2],[.003,.997]);target_width=width+.008;factor=target_width/max(.05,-ext[0])
        modified=v.copy();allp=(v[:,:2]-fit_pivot[:2])@direction;alln=(v[:,:2]-fit_pivot[:2])@normal
        modified[:,:2]=pivot[:2]+np.outer(allp*factor,direction)+np.outer(alln,normal)
        original_z=[float(z0),float(z1)];new_z0=.04 if name=='lower_door' else z0;new_z1=h-.023 if name=='upper_door' else z1
        modified[:,2]=new_z0+(v[:,2]-z0)*(new_z1-new_z0)/(z1-z0);z0,z1=new_z0,new_z1
        if name=='lower_door':
            interior=(allp<-.035)&(allp>-target_width+.035)&(v[:,2]>original_z[0]+.02)&(v[:,2]<original_z[1]-.025)
            preserve_handle=(v[:,2]>original_z[1]-.22)&(allp<-target_width*.42)
            owned=np.zeros(len(v),bool);owned[np.unique(B.f[mask])]=True;flatten=interior&~preserve_handle&owned;plane_n=float(np.median(alln[flatten]));corrected=np.clip(alln,plane_n-.008,plane_n+.008)
            modified[flatten,:2]=pivot[:2]+np.outer(allp[flatten]*factor,direction)+np.outer(corrected[flatten],normal)
        B.body(name,pivot,parent='base',mass=mass,kind='hinge',axis=[0,0,1],limits=[-theta,1.60-theta],frictionloss=.16,kp=300,kv=24,force_limit=60)
        if name=='lower_door':
            face_u=(c[:,:2]-fit_pivot[:2])@direction;face_n=(c[:,:2]-fit_pivot[:2])@normal
            handle=mask&(c[:,2]>original_z[1]-.20)&(face_u<-target_width*.38)&(face_u>-target_width*.93)&(face_n<-.005)&(B.color.mean(1)<.65)
            if handle.sum()<30:raise ValueError('Native lower-door handle isolation failed')
            B.native('native_lower_handle',handle,name,vertices=modified)
            front_material=B.material('reconstructed_lower_door_enamel',(.60,.615,.555),.04,.38)
            panel_center=pivot[:2]-direction*(target_width/2)-normal*.004
            panel=B.box('rebuilt_lower_door_rounded_shell',(target_width,.038,z1-z0),[*panel_center,(z0+z1)/2],name,front_material,bevel=.011);panel.rotation_euler[2]=theta
            B.proxy(name,'box',[*panel_center,(z0+z1)/2],[target_width/2-.004,.019,(z1-z0)/2-.004],quat=[math.cos(theta/2),0,0,math.sin(theta/2)])
            B.operations.append({'operation':'replace spurious native ribbed lower front with beveled thin shell, retain native handle','target':'lower_door','handle_faces':int(handle.sum())})
        else:B.native('native_'+name,mask,name,vertices=modified)
        thickness=.017;centerxy=pivot[:2]-direction*(target_width/2)+normal*.013
        ob=B.box(name+'_inner_liner',(target_width-.020,thickness,z1-z0-.035),[*centerxy,(z0+z1)/2],name,ivory,bevel=.005)
        ob.rotation_euler[2]=theta
        B.proxy(name,'box',[*centerxy,(z0+z1)/2],[(target_width-.024)/2,thickness/2,(z1-z0-.038)/2],quat=[math.cos(theta/2),0,0,math.sin(theta/2)])
        for z in [z0+.032,z1-.032]:B.cylinder(name+'_hinge_'+str(round(z,3)),.009,.034,[*pivot[:2],z],[0,0,1],name,steel)
        pts=[]
        for a,z in [(-target_width+.018,z0+.018),(-.018,z0+.018),(-.018,z1-.018),(-target_width+.018,z1-.018)]:pts.append([*(pivot[:2]+direction*a+normal*.018),z])
        poly=bpy.data.curves.new(name+'_gasket_path','CURVE');poly.dimensions='3D';poly.bevel_depth=.0025;poly.bevel_resolution=3;poly.use_fill_caps=True;line=poly.splines.new('POLY');line.points.add(len(pts)-1)
        for pp,xyz in zip(line.points,pts):pp.co=(*((np.array(xyz)-pivot).tolist()),1)
        line.use_cyclic_u=True;ob=bpy.data.objects.new(name+'_gasket',poly);bpy.context.collection.objects.link(ob);ob.parent=bpy.data.objects['body_'+name];ob['body']=name;poly.materials.append(gasket);bpy.ops.object.select_all(action='DESELECT');ob.select_set(True);bpy.context.view_layer.objects.active=ob;bpy.ops.object.convert(target='MESH')
        B.controls.append({'body':name,'label':'冷冻门闭合' if name=='upper_door' else '冷藏门闭合','target':-theta,'tolerance':.045})
        parts.append({'name':name,'faces':int(mask.sum()),'pivot':pivot.tolist(),'candidate_fitted_pivot':fit_pivot.tolist(),'hinge_exterior_translation':(pivot-fit_pivot).tolist(),'source_angle_rad':theta,'width_registration_factor':factor,'height_range':[float(z0),float(z1)],'candidate_height_range':original_z})
    for x in [xl+.013,xr-.013]:B.box('liner_side_'+str(round(x,3)),(.018,depth-.015,h-.035),[x,(yf+yb)/2+.01,h/2],'base',ivory,collision=True)
    B.box('liner_back',(width-.026,.018,h-.035),[(xl+xr)/2,yb-.010,h/2],'base',ivory,collision=True)
    for z in [.023,split,h-.022]:B.box('liner_horizontal_'+str(round(z,3)),(width-.04,depth-.035,.018),[(xl+xr)/2,(yf+yb)/2+.014,z],'base',ivory,collision=True)
    B.box('upper_front_cut_edge_trim',(width-.025,.022,.024),[(xl+xr)/2,yf+.002,h-.032],'base',ivory)
    for z in [split*.34,split*.66]:B.box('shelf_'+str(round(z,3)),(width-.065,depth-.08,.008),[(xl+xr)/2,(yf+yb)/2+.035,z],'base',ivory,collision=True)
    B.operations += [{'operation':'new candidate roof and door-plane registration','target':'separate upper/lower door ownership and correct closure width'}, {'operation':'local mesh removal plus wall extrusion','target':'cabinet real interior openings and inner liners'}, {'operation':'curved profile sweep','target':'door perimeter gaskets'}, {'operation':'cylindrical pivot assembly','target':'independent right-side hinges'}]
    B.limitations += ['Fixed-base demonstration; whole-object free manipulation not tested','Internal shelves and wall thickness are inferred','No gasket compression, cooling, wiring, thermodynamics or contents','Single-view novel interior has no appearance ground truth']
    (B.root/'candidate_partition.json').write_text(json.dumps({'candidate_bounds':[B.lo.tolist(),B.hi.tolist()],'roof_bounds':[low.tolist(),high.tolist()],'front_y':yf,'horizontal_split_z':split,'doors':parts,'front_fill_faces_removed':int((~door&in_opening).sum())},indent=2),encoding='utf-8')
