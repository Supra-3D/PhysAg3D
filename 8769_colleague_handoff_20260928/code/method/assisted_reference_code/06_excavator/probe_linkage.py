from pathlib import Path
import mujoco,numpy as np,json
xml="""<mujoco><compiler angle="radian"/><option timestep="0.0005" integrator="implicitfast"/><worldbody><body name="arm" pos="0 0 1"><joint name="arm_h" axis="1 0 0"/><geom type="capsule" fromto="0 0 0 0 0 1" size=".03" mass="2" contype="0" conaffinity="0"/></body><body name="barrel" pos="0 1 1"><joint name="barrel_h" axis="1 0 0" damping=".1"/><geom type="capsule" fromto="0 0 0 0 -.5 .5" size=".03" mass="1" contype="0" conaffinity="0"/><body name="rod"><joint name="extension" type="slide" axis="0 -.707106781 .707106781" damping=".1"/><geom type="capsule" fromto="0 -.3 .3 0 -1 1" size=".015" mass=".3" contype="0" conaffinity="0"/></body></body></worldbody><equality><connect body1="rod" body2="arm" anchor="0 -1 1" solref=".003 1" solimp=".99 .999 .001"/></equality><actuator><position name="drive" joint="arm_h" kp="200" kv="20"/></actuator></mujoco>"""
m=mujoco.MjModel.from_xml_string(xml);d=mujoco.MjData(m);maximum=0.
for i in range(6000):
 d.ctrl[0]=.2*min(1,i/2000);mujoco.mj_step(m,d)
 ra=d.xpos[m.body('rod').id]+d.xmat[m.body('rod').id].reshape(3,3)@np.array([0,-1,1]);aa=d.xpos[m.body('arm').id]+d.xmat[m.body('arm').id].reshape(3,3)@np.array([0,0,1]);maximum=max(maximum,float(np.linalg.norm(ra-aa)))
r={'constraint':'passive barrel hinge plus rod slide with opposite endpoint connect','maximum_endpoint_error_m':maximum,'final_arm_angle':float(d.joint('arm_h').qpos[0]),'warnings':int(sum(w.number for w in d.warning)),'source_reference':'https://mujoco.readthedocs.io/en/stable/XMLreference.html#equality-connect','valid':maximum<.001 and not any(w.number for w in d.warning)}
assert r['valid'],r
Path(__file__).with_suffix('.json').write_text(json.dumps(r,indent=2));print(json.dumps(r))
