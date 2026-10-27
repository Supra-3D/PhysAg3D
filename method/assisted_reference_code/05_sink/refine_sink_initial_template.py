import numpy as np,json,math

def build(B):
    c=B.c;v=B.v;h=B.hi[2];zrim=h*.50
    # Use new candidate's broad slab height; the faucet is a thin tall feature.
    zz=np.linspace(h*.32,h*.68,121);hist,_=np.histogram(c[:,2],zz);zrim=float(zz[np.argmax(hist)])
    bowl=c[:,2]<zrim-.012;bp=v[v[:,2]<zrim-.01];lo=np.quantile(bp,.003,axis=0);hi=np.quantile(bp,.997,axis=0)
    spout=c[:,2]>zrim+.075
    foot=c[(c[:,2]>zrim+.018)&(c[:,2]<zrim+.075)];faucet_xy=np.median(foot[:,:2],axis=0)
    lever=(c[:,2]>zrim+.006)&(c[:,2]<zrim+.073)&(c[:,0]>faucet_xy[0]+.009)&(c[:,1]>faucet_xy[1]-.045)
    pivot=[*faucet_xy,zrim+.032];lp=[faucet_xy[0]+.022,faucet_xy[1],zrim+.030]
    B.body('base',mass=13,kind='fixed');B.body('spout',pivot,parent='base',mass=.8,kind='hinge',axis=[0,0,1],limits=[-.7,.7],frictionloss=.018,kp=16,kv=1.2,force_limit=8)
    B.body('lever',lp,parent='base',mass=.13,kind='hinge',axis=[1,0,0],limits=[-.2,.55],frictionloss=.006,kp=4,kv=.3,force_limit=3)
    B.native('native_double_basin',~spout&~lever,'base');B.native('native_swivel_spout',spout,'spout',B.variant('satin_faucet',.5,.32));B.native('native_valve_lever',lever,'lever')
    steel=B.material('bearing_steel',(.44,.45,.43),.65,.3)
    B.cylinder('swivel_bearing',.016,.03,pivot,[0,0,1],'base',steel)
    B.cylinder('valve_pivot',.010,.026,lp,[1,0,0],'base',steel)
    # Geometry-informed compound wall colliders preserve both open bowls.
    width=hi[0]-lo[0];mid=(lo[0]+hi[0])/2;depth=hi[1]-lo[1];yc=(lo[1]+hi[1])/2;floor=float(lo[2]+.012);rim=zrim-.010;halfwidth=width/4-.017
    centers=[]
    for i,x in enumerate([mid-width/4,mid+width/4]):
        centers.append([x,yc,floor+.12])
        B.proxy('base','box',[x,yc,floor],[halfwidth-.006,depth/2-.021,.008])
        for side in [-1,1]:
            B.proxy('base','box',[x+side*(halfwidth+.006),yc,(floor+rim)/2],[.010,depth/2-.005,(rim-floor)/2])
            B.proxy('base','box',[x,yc+side*(depth/2-.01),(floor+rim)/2],[halfwidth+.008,.012,(rim-floor)/2])
    points=c[spout];pmin=points[np.argmin(points[:,2])];pmax=points[np.argmax(points[:,2])]
    B.capsule('spout',pmin,pmax,.012);B.proxy('lever','box',lp,[.016,.018,.016])
    B.controls += [{'body':'spout','label':'龙头旋转','target':.55,'tolerance':.04},{'body':'lever','label':'阀门转动','target':.35,'tolerance':.035}]
    B.operations += [{'operation':'native UV-preserving semantic split','target':'tall curved faucet and short valve arm'}, {'operation':'compound hollow collision shell','target':'both basin cavities'}, {'operation':'cylindrical bearing construction','target':'faucet swivel and valve hinge'}]
    B.limitations += ['Fixed installed basin; no plumbing or fluid simulation','Contact walls are a conservative box-shell approximation, not exact tapered bowl walls','Faucet bearing surfaces interpenetrate locally by design and have a documented contact exclusion']
    d={'candidate_bounds':[B.lo.tolist(),B.hi.tolist()],'basin_bounds':[lo.tolist(),hi.tolist()],'rim_z':zrim,'floor_z':floor,'faucet_pivot':pivot,'valve_pivot':lp,'probe_drop_centers':centers,'part_faces':{'base':int((~spout&~lever).sum()),'spout':int(spout.sum()),'lever':int(lever.sum())}}
    (B.root/'candidate_partition.json').write_text(json.dumps(d,indent=2),encoding='utf-8')
