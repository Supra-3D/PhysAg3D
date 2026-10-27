from pathlib import Path
import hashlib,json,shutil
import numpy as np
from scipy.optimize import least_squares

ROOT=Path(__file__).resolve().parent
SOURCE=ROOT/'input/source.png'

def project(p,return_points=False):
    az,el,distance,cx,cy,depth,opening,focal=p
    hinge_y=depth/2-.009;hinge_z=.027;h=depth-.010
    t=np.deg2rad(opening)
    points=np.array([[-.18,-depth/2,.018],[.18,-depth/2,.018],[-.18,depth/2,.018],[.18,depth/2,.018],
                     [-.178,hinge_y,hinge_z],[.178,hinge_y,hinge_z],
                     [-.178,hinge_y-h*np.cos(t),hinge_z+h*np.sin(t)],[.178,hinge_y-h*np.cos(t),hinge_z+h*np.sin(t)]])
    az,el=np.deg2rad([az,el]);target=np.array([0,0,.115]);eye=target+distance*np.array([np.cos(el)*np.cos(az),np.cos(el)*np.sin(az),np.sin(el)])
    forward=(target-eye)/distance;right=np.cross(forward,[0,0,1]);right/=np.linalg.norm(right);up=np.cross(right,forward)
    d=points-eye
    xy=np.column_stack([focal*(d@right)/(d@forward)+cx,-focal*(d@up)/(d@forward)+cy])
    return (xy,eye,target) if return_points else xy

def main():
    for name in ['input','asset','renders','provenance']: (ROOT/name).mkdir(exist_ok=True)
    expected='67d784912d80a59fb3932ad36dbfd2d16d0dbf0e9d15a6789d2bc52f8b2832ae'
    assert hashlib.sha256(SOURCE.read_bytes()).hexdigest()==expected
    # The packaged reference image is already at its canonical location.
    obs=np.array([[434,842],[805,630],[195,673],[587,547],[198,653],[574,529],[170,355],[557,291]])
    initial=[-130,25,1.1,512,525,.23,110,1600]
    lower=[-165,10,.6,400,400,.19,80,700];upper=[-95,60,3,650,650,.30,140,4000]
    fit=least_squares(lambda p:(project(p)-obs).ravel(),initial,bounds=(lower,upper),max_nfev=6000,x_scale='jac')
    xy,eye,target=project(fit.x,True);az,el,dist,cx,cy,depth,angle,focal=fit.x
    p={'width_m':.36,'depth_m':depth,'lid_width_m':.356,'lid_height_m':depth-.010,'base_height_m':.016,'base_center_z':.010,
       'hinge_y':depth/2-.009,'hinge_z':.027,'opening_deg':angle,
       'camera':{'location':eye.tolist(),'target':target.tolist(),'focal_pixels':focal,'cx':cx,'cy':cy,'resolution':1024},
       'fit':{'rms_pixels':float(np.sqrt(np.mean((xy-obs)**2))),'landmarks':obs.tolist(),'projected':xy.tolist()},
       'closure':{'front_gap_m':.001,'side_gap_m':.002,'constraint':'lid height = base depth - 10mm; hinge inset = 9mm'}}
    (ROOT/'parameters.json').write_text(json.dumps(p,indent=2),encoding='utf-8')
    plan={'input':{'asset_id':'6f4a0b64512f412aa46403796201ac1c','view':'000.png','sha256':expected},
          'execution':'Current GPT-6 executes trellis2-native-refine; no external LLM API call',
          'reused':'Input and generic runtime/export infrastructure only; previous final geometry is not the visual source',
          'stages':['Adjustable Blender scaffold with closure and clearance','Whole-image native TRELLIS.2 geometry/PBR candidate','Blender refinement and semantic articulation','Comparable rendering and MuJoCo validation'],
          'neural_call':{'route':'native','resolution':1024,'texture_size':2048,'steps':24,'seed':42,'target':'whole laptop geometry and PBR, including keyboard and chassis',
                         'allowed':'visual surface and provisional dimensions','preserve':'coherent base/lid assembly, closeable lid, independent key/trackpad ownership after integration'},
          'physical_truth_verified':False,'mass_prior_kg':{'base':1.35,'lid':.48},
          'acceptance':['Source camera and visible details','Native candidate detail retained where useful','Closure coverage and clearance','Lid, keys and touchpad motion','Improved rendering with contact shadows and reflections']}
    (ROOT/'asset_plan.json').write_text(json.dumps(plan,indent=2),encoding='utf-8')
    skill=Path(r'C:\HISTORICAL_REFERENCE_NOT_EXECUTABLE\.codex\skills\trellis2-native-refine')
    for pth in [skill/'SKILL.md',skill/'references/workflow.md']:
        if pth.exists():shutil.copy2(pth,ROOT/'provenance'/pth.name)
    print(json.dumps({'fit_rms':p['fit']['rms_pixels'],'depth':depth,'lid_height':depth-.010,'angle':angle,'focal':focal}))

if __name__=='__main__':main()
