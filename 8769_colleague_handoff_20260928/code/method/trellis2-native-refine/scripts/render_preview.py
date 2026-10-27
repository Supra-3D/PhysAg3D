"""Run with Blender --background --python THIS_FILE -- --mesh model.glb --out views."""
import argparse
import json
import math
from pathlib import Path
import sys

import bpy
from mathutils import Vector


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mesh", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--size", type=int, default=512)
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:])
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=False)
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    bpy.ops.import_scene.gltf(filepath=str(Path(args.mesh).resolve()))
    objects = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    points = [obj.matrix_world @ Vector(corner) for obj in objects for corner in obj.bound_box]
    if not points:
        raise ValueError("No imported mesh")
    low = Vector([min(p[i] for p in points) for i in range(3)])
    high = Vector([max(p[i] for p in points) for i in range(3)])
    center = (low + high) / 2
    radius = max((p - center).length for p in points)
    if radius <= 0:
        raise ValueError("Zero-size mesh")
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = 16
    scene.cycles.use_denoising = True
    scene.render.resolution_x = scene.render.resolution_y = args.size
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    world = bpy.data.worlds.new("PreviewWorld")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs[0].default_value = (0.3, 0.3, 0.3, 1)
    world.node_tree.nodes["Background"].inputs[1].default_value = 0.5
    scene.world = world
    for index, offset in enumerate(((2, -3, 4), (-3, -1, 2), (1, 3, 3))):
        data = bpy.data.lights.new("PreviewLight" + str(index), "AREA")
        data.energy = 450 * radius * radius
        data.shape = "DISK"
        data.size = 3 * radius
        obj = bpy.data.objects.new(data.name, data)
        scene.collection.objects.link(obj)
        obj.location = center + Vector(offset) * radius
        obj.rotation_euler = (center - obj.location).to_track_quat("-Z", "Y").to_euler()
    camera_data = bpy.data.cameras.new("PreviewCamera")
    camera_data.type = "ORTHO"
    camera_data.ortho_scale = 2.3 * radius
    camera_data.clip_start = max(radius / 1000, 0.000001)
    camera_data.clip_end = radius * 100
    camera = bpy.data.objects.new("PreviewCamera", camera_data)
    scene.collection.objects.link(camera)
    scene.camera = camera
    views = []
    for index, degrees in enumerate((0, 90, 180, 270)):
        angle = math.radians(degrees)
        camera.location = center + Vector((math.sin(angle), -math.cos(angle), 0.35)) * radius * 4
        camera.rotation_euler = (center - camera.location).to_track_quat("-Z", "Y").to_euler()
        filename = "view_" + str(index) + ".png"
        scene.render.filepath = str(out / filename)
        bpy.ops.render.render(write_still=True)
        views.append({"file": filename, "azimuth_degrees": degrees,
                      "camera_world": list(camera.location), "target_world": list(center)})
    (out / "views.json").write_text(json.dumps({"source": str(Path(args.mesh).resolve()),
        "renderer": bpy.app.version_string, "frame": "Blender Z-up after glTF import",
        "appearance_review": "requires image inspection", "views": views}, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
