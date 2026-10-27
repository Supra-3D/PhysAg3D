"""Render the final asset and a playback of measured MuJoCo body transforms."""
import argparse
import json
from pathlib import Path
import sys
import bpy
from mathutils import Vector

ROOT=Path(__file__).resolve().parent


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--mode",choices=["views","motion"],required=True)
    args=parser.parse_args(sys.argv[sys.argv.index("--")+1:])
    bpy.ops.wm.open_mainfile(filepath=str(ROOT/"asset/laptop.blend"))
    scene=bpy.context.scene;scene.cycles.samples=12;cam=scene.camera
    if args.mode=="views":
        for name,pos in [("rear",(.50,.72,.43)),("side",(-.75,.05,.25)),("front",(0,-.90,.45))]:
            cam.location=pos;cam.rotation_euler=(Vector((0,0,.12))-cam.location).to_track_quat("-Z","Y").to_euler()
            cam.data.shift_x=cam.data.shift_y=0;cam.data.lens=48
            scene.render.resolution_x=scene.render.resolution_y=720
            scene.render.filepath=str(ROOT/"renders"/(name+".png"));bpy.ops.render.render(write_still=True)
        return
    data=json.loads((ROOT/"trajectory.json").read_text(encoding="utf-8"));states=data["states"]
    selected={0,len(states)-1}
    for phase in dict.fromkeys(s['phase'] for s in states):
        ids=[i for i,s in enumerate(states) if s['phase']==phase];selected.add(ids[-1])
        if phase in ('close','open'):selected.add(ids[len(ids)//2])
    root_objects={ob.name[5:]:ob for ob in bpy.data.objects if ob.name.startswith("body_")}
    for ob in root_objects.values():
        matrix=ob.matrix_world.copy();ob.parent=None;ob.matrix_world=matrix;ob.rotation_mode="QUATERNION"
    cam.location=(-.63,-.80,.52);cam.rotation_euler=(Vector((0,0,.115))-cam.location).to_track_quat("-Z","Y").to_euler()
    cam.data.shift_x=cam.data.shift_y=0;cam.data.lens=48
    scene.render.resolution_x=640;scene.render.resolution_y=512;scene.render.resolution_percentage=100;scene.cycles.samples=8
    scene.render.fps=data['fps'];scene.frame_start=1;scene.frame_end=len(states)
    out=ROOT/"renders/motion_frames";out.mkdir(exist_ok=True)
    for i,state in enumerate(states):
        scene.frame_set(i+1)
        for name,transform in state["bodies"].items():
            if name not in root_objects:continue
            ob=root_objects[name];ob.location=transform["pos"];ob.rotation_quaternion=transform["quat_wxyz"]
            ob.keyframe_insert(data_path="location",frame=i+1);ob.keyframe_insert(data_path="rotation_quaternion",frame=i+1)
        bpy.context.view_layer.update()
        if i in selected:
            scene.render.filepath=str(out/("%04d.png"%i));bpy.ops.render.render(write_still=True)
    scene.frame_set(1);bpy.ops.wm.save_as_mainfile(filepath=str(ROOT/"asset/laptop_simulation_playback.blend"))
    (ROOT/"renders/motion_index.json").write_text(json.dumps({"fps":data['fps'],"frames":[{"frame":i,"time":states[i]["time"],"phase":states[i]["phase"]} for i in sorted(selected)],"source":"Actual MuJoCo world body transforms; all recorded states keyframed in blend, selected stills rendered"},indent=2),encoding="utf-8")


if __name__=="__main__":main()
