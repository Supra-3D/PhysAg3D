#!/usr/bin/env python3
"""Live MuJoCo articulation service and local, offline Three.js viewer.

Source assets are read-only. Each browser session owns its own MjData; only
immutable MjModels and render buffers are shared. No animation clips are used.
"""
from __future__ import annotations

import argparse
import gzip
import io
import json
import math
import mimetypes
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import struct
import tempfile
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlparse
import uuid
import xml.etree.ElementTree as ET
import zipfile

import mujoco
import numpy as np
from PIL import Image

if __package__:
    from .showcase_controller import ShowcaseController
else:
    from showcase_controller import ShowcaseController

ROOT = Path(__file__).resolve().parent
ASSETS = ROOT / "assets"
MAX_UPLOAD = 128 * 1024**2
MAX_EXPANDED = 512 * 1024**2


class BadRequest(ValueError):
    pass


def name_of(model, kind, index):
    return mujoco.mj_id2name(model, kind, index) or f"{kind.name}_{index}"


def json_bytes(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode()


def load_mujoco_model(scene, resource_root):
    """Keep native loading while bridging Windows' narrow-character file I/O.

    MuJoCo 3.12 cannot open a model through a non-ASCII Windows parent path.
    A temporary byte-for-byte copy preserves relative includes and dependencies;
    it is removed as soon as MuJoCo finishes loading the model into memory.
    """
    if os.name != "nt" or str(scene).isascii():
        return mujoco.MjModel.from_xml_path(str(scene))
    with tempfile.TemporaryDirectory(prefix="physag3d-model-") as temporary:
        staging = Path(temporary) / "asset"
        shutil.copytree(resource_root, staging)
        return mujoco.MjModel.from_xml_path(str(staging / scene.relative_to(resource_root)))


def update_skin_vertices(model, data, scene):
    # updateScene uses MuJoCo's current active-skin implementation. The legacy
    # mjv_updateSkin entry point prints a deprecation warning on every frame.
    options = mujoco.MjvOption()
    options.flags[mujoco.mjtVisFlag.mjVIS_SKIN] = True
    mujoco.mjv_updateScene(model, data, options, None, mujoco.MjvCamera(),
                         mujoco.mjtCatBit.mjCAT_ALL, scene)


def original_pbr(scene):
    """Read the same asset's optional visual GLB material metadata, not its animation.

    MJCF retains base color but historical exporters omit the metallic/roughness
    atlas. Preserve it from the companion visual asset when material names match.
    """
    path = scene.parent / "appearance.glb"
    if not path.is_file():
        path = scene.parent.parent / "asset/refined.glb"
    if not path.is_file():
        return {}, {}
    try:
        blob = path.read_bytes()
        if blob[:4] != b"glTF" or len(blob) > MAX_EXPANDED:
            return {}, {}
        size = struct.unpack_from("<I", blob, 12)[0]
        document = json.loads(blob[20:20 + size])
        binary_start = 20 + size + 8
        binary = memoryview(blob)[binary_start:]
        materials, images = {}, {}
        for material_index, material in enumerate(document.get("materials", [])):
            pbr = material.get("pbrMetallicRoughness", {})
            record = {"rgba": pbr.get("baseColorFactor", [1, 1, 1, 1]),
                      "metalness": pbr.get("metallicFactor", 1),
                      "roughness": pbr.get("roughnessFactor", 1)}
            texture = pbr.get("metallicRoughnessTexture")
            if texture:
                source = document["textures"][texture["index"]]["source"]
                image = document["images"][source]
                if "bufferView" in image:
                    view = document["bufferViews"][image["bufferView"]]
                    offset = view.get("byteOffset", 0)
                    identity = f"pbr_{source}"
                    images[identity] = bytes(binary[offset:offset + view["byteLength"]])
                    record["metallic_roughness_texture_id"] = identity
            key = re.sub(r"[^a-z0-9]", "", material.get("name", "").lower())
            if key:
                materials[key] = record
            # The Overview export names its MJCF materials by original GLB index.
            materials[f"releasemat{material_index}"] = record
        return materials, images
    except (ValueError, KeyError, IndexError, struct.error):
        return {}, {}


class Asset:
    def __init__(self, identity, name, scene, description="", scope="", labels=None, imported=False, resource_root=None, native_controls=False):
        self.id, self.name = identity, name
        self.scene = Path(scene).resolve()
        self.resource_root = Path(resource_root).resolve() if resource_root else self.scene.parent
        self.native_controls = native_controls
        self.description, self.scope = description, scope
        self.labels, self.imported = labels or {}, imported
        self.lock = threading.RLock()
        self.model = None
        self.mesh_buffers, self.texture_buffers = {}, {}

    def summary(self):
        return {"id": self.id, "name": self.name, "description": self.description,
                "scope": self.scope, "thumbnail": f"/api/assets/{self.id}/thumbnail",
                "imported": self.imported,
                "joint_count": len(self.joints) if self.model is not None else None}

    def load(self):
        with self.lock:
            if self.model is not None:
                return
            m = load_mujoco_model(self.scene, self.resource_root)
            if m.ngeom > 10000 or m.nmeshface > 5_000_000:
                raise BadRequest("Asset exceeds the limit of 10,000 shapes or 5 million mesh triangles.")
            d = mujoco.MjData(m)
            if m.nkey:
                mujoco.mj_resetDataKeyframe(m, d, 0)
            self.initial_qpos = None
            self.initial_controls = np.zeros(m.nu)
            self.controls = []
            if self.native_controls:
                metadata = json.loads((self.resource_root / "asset.json").read_text(encoding="utf-8"))
                self.initial_qpos = np.asarray(metadata["initial_qpos"], dtype=float)
                if self.initial_qpos.shape != (m.nq,):
                    raise BadRequest("The asset's initial joint state does not match its model.")
                d.qpos[:] = self.initial_qpos
                parameters = json.loads((self.resource_root / "parameters.json").read_text(encoding="utf-8"))
                actuator_types = {a["name"]: a["type"] for a in parameters["actuators"]}
                for a in range(m.nu):
                    name = name_of(m, mujoco.mjtObj.mjOBJ_ACTUATOR, a)
                    j = int(m.actuator_trnid[a, 0])
                    joint_name = name_of(m, mujoco.mjtObj.mjOBJ_JOINT, j)
                    kind = {"position": "position", "velocity": "velocity", "motor": "force"}[actuator_types[name]]
                    slide = int(m.jnt_type[j]) == int(mujoco.mjtJoint.mjJNT_SLIDE)
                    unit = ("m" if slide else "rad") if kind == "position" else (("m/s" if slide else "rad/s") if kind == "velocity" else ("N" if slide else "Nm"))
                    limits = m.actuator_ctrlrange[a].tolist() if m.actuator_ctrllimited[a] else (m.jnt_range[j].tolist() if m.jnt_limited[j] else [-math.tau, math.tau])
                    value = float(d.qpos[m.jnt_qposadr[j]]) if kind == "position" else 0.0
                    self.initial_controls[a] = value
                    self.controls.append({"id": a, "name": name, "label": self.labels.get(joint_name, joint_name.replace("_", " ")),
                                          "kind": kind, "joint": joint_name, "joint_id": j, "range": limits,
                                          "body_id": int(m.jnt_bodyid[j]), "joint_type": "slide" if slide else "hinge",
                                          "limited": bool(m.actuator_ctrllimited[a]), "unit": unit, "value": value})
                profile_path = self.resource_root / "control_profile.json"
                if profile_path.is_file():
                    self.initial_controls[:] = json.loads(profile_path.read_text(encoding="utf-8"))["ctrl"][0]
                if self.id == "camera":
                    # Same initial manual-control setpoints as the supplied demo.reset.
                    for joint_name, actuator_name, rate, gain in (
                        ("mode_dial", "dial_virtual_hand", math.tau / 8, .01),
                        ("secondary_dial", "secondary_dial_virtual_hand", math.tau / 6, .01),
                        ("focus_ring", "focus_virtual_hand", math.tau / 12, .02),
                    ):
                        j = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_JOINT, joint_name)
                        a = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_ACTUATOR, actuator_name)
                        v = int(m.jnt_dofadr[j])
                        self.initial_controls[a] = rate * (1 + m.dof_damping[v] / gain) + m.dof_frictionloss[v] / gain
                    self.initial_controls[mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_ACTUATOR, "screen_virtual_hand")] = 0
                    self.initial_controls[mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_ACTUATOR, "zoom_virtual_hand")] = 0
                for control in self.controls:
                    control["value"] = float(self.initial_controls[control["id"]])
                d.ctrl[:] = self.initial_controls
            mujoco.mj_forward(m, d)
            self.joints = []
            for j in range(m.njnt):
                kind = int(m.jnt_type[j])
                if kind not in (int(mujoco.mjtJoint.mjJNT_HINGE), int(mujoco.mjtJoint.mjJNT_SLIDE)):
                    continue
                hinge = kind == int(mujoco.mjtJoint.mjJNT_HINGE)
                limited = bool(m.jnt_limited[j])
                bounds = m.jnt_range[j].tolist() if limited else ([-math.pi, math.pi] if hinge else [-1, 1])
                name = name_of(m, mujoco.mjtObj.mjOBJ_JOINT, j)
                label = self.labels.get(name, name.replace("_", " "))
                self.joints.append({"id": j, "name": name, "label": label,
                                    "body_id": int(m.jnt_bodyid[j]), "type": "hinge" if hinge else "slide",
                                    "range": bounds, "limited": limited, "unit": "rad" if hinge else "m",
                                    "value": float(d.qpos[m.jnt_qposadr[j]]),
                                    "display_sign": -1 if self.id == "img_069" else 1})
            self.geoms = []
            self.meshes = []
            self.textures = []
            pbr_materials, pbr_images = original_pbr(self.scene)
            used_meshes, used_textures = set(), set()
            all_bounds = []
            framing_corners = {}
            for g in range(m.ngeom):
                kind = int(m.geom_type[g])
                if kind == int(mujoco.mjtGeom.mjGEOM_PLANE):
                    continue
                if self.native_controls and int(m.geom_group[g]) >= 3:
                    continue
                material = int(m.geom_matid[g])
                color = m.geom_rgba[g].copy()
                if material >= 0 and np.allclose(color, [.5, .5, .5, 1]):
                    color = m.mat_rgba[material].copy()
                if color[3] <= 0.001:
                    continue
                names = {2: "sphere", 3: "capsule", 4: "ellipsoid", 5: "cylinder", 6: "box", 7: "mesh"}
                if kind not in names:
                    continue
                texid = -1
                if material >= 0:
                    for role in [1, 8]:
                        if int(m.mat_texid[material, role]) >= 0:
                            texid = int(m.mat_texid[material, role])
                            break
                # Cubemaps are not interchangeable with UV textures.
                if texid >= 0 and int(m.tex_type[texid]) != int(mujoco.mjtTexture.mjTEXTURE_2D):
                    texid = -1
                if texid >= 0:
                    used_textures.add(texid)
                meshid = int(m.geom_dataid[g]) if kind == 7 else -1
                material_name = name_of(m, mujoco.mjtObj.mjOBJ_MATERIAL, material) if material >= 0 else ""
                pbr = pbr_materials.get(re.sub(r"[^a-z0-9]", "", material_name.lower()), {})
                self.geoms.append({"id": g, "name": name_of(m, mujoco.mjtObj.mjOBJ_GEOM, g),
                                   "body_id": int(m.geom_bodyid[g]), "type": names[kind], "mesh_id": meshid,
                                   "size": m.geom_size[g].tolist(), "rgba": color.tolist(), "texture_id": texid,
                                   "texrepeat": m.mat_texrepeat[material].tolist() if material >= 0 else [1, 1],
                                   "reflectance": float(m.mat_reflectance[material]) if material >= 0 else 0,
                                   "shininess": float(m.mat_shininess[material]) if material >= 0 else .3,
                                   **pbr})
                rotation = d.geom_xmat[g].reshape(3, 3)
                if meshid >= 0:
                    used_meshes.add(meshid)
                    start, n = int(m.mesh_vertadr[meshid]), int(m.mesh_vertnum[meshid])
                    points = m.mesh_vert[start:start + n] @ rotation.T + d.geom_xpos[g]
                    all_bounds.extend([points.min(axis=0), points.max(axis=0)])
                    if self.id == "phone":
                        local = m.mesh_vert[start:start + n]
                        low, high = local.min(axis=0), local.max(axis=0)
                        framing_corners[g] = np.array([[x, y, z] for x in (low[0], high[0])
                                                      for y in (low[1], high[1]) for z in (low[2], high[2])])
                else:
                    s = m.geom_size[g]
                    if kind == 2:
                        half = np.repeat(s[0], 3)
                    elif kind in (3, 5):
                        half = np.array([s[0], s[0], s[1] + (s[0] if kind == 3 else 0)])
                    else:
                        half = s
                    if self.id == "phone":
                        framing_corners[g] = np.array([[x, y, z] for x in (-half[0], half[0])
                                                      for y in (-half[1], half[1]) for z in (-half[2], half[2])])
                    half = np.abs(rotation) @ half
                    all_bounds.extend([d.geom_xpos[g] - half, d.geom_xpos[g] + half])
            for meshid in sorted(used_meshes):
                fa, fn = int(m.mesh_faceadr[meshid]), int(m.mesh_facenum[meshid])
                va, na, ta = int(m.mesh_vertadr[meshid]), int(m.mesh_normaladr[meshid]), int(m.mesh_texcoordadr[meshid])
                faces = m.mesh_face[fa:fa + fn].reshape(-1)
                values = np.zeros((len(faces), 8), dtype="<f4")
                values[:, :3] = m.mesh_vert[va + faces]
                normals = m.mesh_facenormal[fa:fa + fn].reshape(-1)
                if na >= 0 and (normals >= 0).all():
                    values[:, 3:6] = m.mesh_normal[na + normals]
                else:
                    triangle = values[:, :3].reshape(-1, 3, 3)
                    normal = np.cross(triangle[:, 1] - triangle[:, 0], triangle[:, 2] - triangle[:, 0])
                    normal /= np.maximum(np.linalg.norm(normal, axis=1, keepdims=True), 1e-12)
                    values[:, 3:6] = np.repeat(normal, 3, axis=0)
                tex = m.mesh_facetexcoord[fa:fa + fn].reshape(-1)
                if ta >= 0 and (tex >= 0).all():
                    values[:, 6:] = m.mesh_texcoord[ta + tex]
                self.mesh_buffers[meshid] = values.tobytes()
                self.meshes.append({"id": meshid, "url": f"/api/assets/{self.id}/meshes/{meshid}.bin",
                                    "vertex_count": len(values), "stride": 8})
            for texid in sorted(used_textures):
                h, w, c = int(m.tex_height[texid]), int(m.tex_width[texid]), int(m.tex_nchannel[texid])
                start = int(m.tex_adr[texid])
                pixels = m.tex_data[start:start + h * w * c].reshape(h, w, c)
                out = io.BytesIO()
                Image.fromarray(pixels.squeeze() if c == 1 else pixels).save(out, format="PNG")
                self.texture_buffers[texid] = out.getvalue()
                self.textures.append({"id": texid, "url": f"/api/assets/{self.id}/textures/{texid}.png"})
            for identity, data in pbr_images.items():
                self.texture_buffers[identity] = data
                self.textures.append({"id": identity, "url": f"/api/assets/{self.id}/textures/{identity}.png",
                                      "role": "metallic_roughness"})
            self.skins = []
            if m.nskin:
                skin_scene = mujoco.MjvScene(m, maxgeom=max(100, m.ngeom + 20))
                update_skin_vertices(m, d, skin_scene)
                for s in range(m.nskin):
                    va, vn = int(m.skin_vertadr[s]), int(m.skin_vertnum[s])
                    fa, fn = int(m.skin_faceadr[s]), int(m.skin_facenum[s])
                    self.skins.append({"id": s, "name": name_of(m, mujoco.mjtObj.mjOBJ_SKIN, s),
                                       "vertex_count": vn, "indices": m.skin_face[fa:fa + fn].reshape(-1).tolist(),
                                       "positions": skin_scene.skinvert[va * 3:(va + vn) * 3].tolist(),
                                       "normals": skin_scene.skinnormal[va * 3:(va + vn) * 3].tolist(),
                                       "rgba": m.skin_rgba[s].tolist()})
            points = np.array(all_bounds) if all_bounds else np.array([[-.1, -.1, 0], [.1, .1, .2]])
            self.bounds = {"min": points.min(axis=0).tolist(), "max": points.max(axis=0).tolist()}
            for control in self.controls:
                # Selection follows the articulated subtree, while all movement
                # still goes through the original actuator and MuJoCo solver.
                descendants = {control["body_id"]}
                for body in range(control["body_id"] + 1, m.nbody):
                    if int(m.body_parentid[body]) in descendants:
                        descendants.add(body)
                control["geom_ids"] = [geom["id"] for geom in self.geoms if geom["body_id"] in descendants]
            self.model = m
            self.descriptor = {"engine": "MuJoCo", "version": mujoco.__version__,
                               "geoms": self.geoms, "meshes": self.meshes, "textures": self.textures,
                               "joints": self.joints, "bounds": self.bounds, "scope": self.scope,
                               "native_controls": self.native_controls, "controls": self.controls, "skins": self.skins,
                               "stats": {"bodies": m.nbody - 1, "joints": len(self.joints),
                                         "triangles": sum(x["vertex_count"] // 3 for x in self.meshes)},
                               "unsupported_joints": m.njnt - len(self.joints)}
            if self.id == "phone" and self.native_controls:
                # Camera framing only: sample a separate MjData, never the live
                # session, so opening either fold remains inside the initial view.
                framing_data = mujoco.MjData(m)
                outer = m.jnt_qposadr[mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_JOINT, "outer_fold")]
                camera = m.jnt_qposadr[mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_JOINT, "camera_fold")]
                envelope = []
                for first in (0, math.pi / 2, math.pi):
                    for second in (0, math.pi / 2, math.pi):
                        framing_data.qpos[:] = self.initial_qpos
                        framing_data.qpos[outer], framing_data.qpos[camera] = first, second
                        mujoco.mj_forward(m, framing_data)
                        for g, corners in framing_corners.items():
                            positions = corners @ framing_data.geom_xmat[g].reshape(3, 3).T + framing_data.geom_xpos[g]
                            envelope.extend((positions.min(axis=0), positions.max(axis=0)))
                envelope = np.asarray(envelope)
                self.descriptor["frame_bounds"] = {"min": envelope.min(axis=0).tolist(), "max": envelope.max(axis=0).tolist()}
            if self.native_controls:
                source = (self.resource_root / "appearance.glb").read_bytes()
                source_json = json.loads(source[20:20 + struct.unpack_from("<I", source, 12)[0]])
                source_materials = source_json["materials"]
                # The supplied camera exporter reordered its materials. This
                # permutation is verified against source colors, texture pixels
                # and the corresponding OBJ/GLB primitives, not inferred by name.
                camera_materials = [6, 11, 13, 1, 7, 3, 16, 4, 10, 0, 2, 15, 5, 12, 17, 14, 20, 19, 22, 21, 18, 9, 8]
                def source_index(name):
                    if self.id == "camera" and re.fullmatch(r"mat_\d+", name):
                        return camera_materials[int(name[4:])]
                    if self.id in {"phone", "carousel"} and re.fullmatch(r"release_mat_\d+", name):
                        return int(name[12:])
                    if self.id == "ladder":
                        if name == "native_PBR_color":
                            return 4
                        if re.fullmatch(r"assisted_\d+", name):
                            return int(name[9:])
                    key = re.sub(r"[^a-z0-9]", "", name.lower())
                    matches = [i for i, mat in enumerate(source_materials)
                               if re.sub(r"[^a-z0-9]", "", mat.get("name", "").lower()) == key]
                    if len(matches) != 1:
                        raise ValueError(f"Source material is ambiguous or missing: {self.id}/{name}")
                    return matches[0]
                self.descriptor["source_materials_url"] = f"/api/assets/{self.id}/appearance.glb"
                for geom in self.geoms:
                    material_id = int(m.geom_matid[geom["id"]])
                    geom["source_material"] = name_of(m, mujoco.mjtObj.mjOBJ_MATERIAL, material_id)
                    index = source_index(geom["source_material"])
                    if self.id == "phone":
                        # The MJCF exporter merges the two leather materials.
                        # Restore their source indices and UV channel semantics.
                        if geom["name"] in {"release_mesh_4_0", "release_mesh_7_0", "release_mesh_10_0"}:
                            index = 3
                        if index in {3, 5}:
                            geom["source_uv_channel"] = 2 if index == 3 else 1
                    if not 0 <= index < len(source_materials):
                        raise ValueError("Source material index is outside the GLB material table.")
                    geom["source_material_index"] = index
                # Both supplied phone skins replace the corresponding GLB OLED
                # seam meshes (18 and 21), which use source material zero.
                if self.id == "phone":
                    for skin in self.skins:
                        if skin["name"] in {"camera_display_seam", "outer_display_seam"}:
                            skin["source_material_index"] = 0


class Session:
    def __init__(self, asset):
        asset.load()
        self.id, self.asset, self.model = uuid.uuid4().hex, asset, asset.model
        self.data = mujoco.MjData(self.model)
        self.lock = threading.RLock()
        self.mode, self.paused, self.error = "physics" if asset.native_controls else "pose", False, None
        self.last_access = self.last_tick = time.monotonic()
        self.targets = {}
        self.actuators = {}
        self.native_targets = {}
        self.demo = False
        self.showcase_controller = ShowcaseController(self.model, asset.resource_root) if asset.native_controls else None
        self.skin_scene = mujoco.MjvScene(self.model, maxgeom=max(100, self.model.ngeom + 20)) if self.model.nskin else None
        m = self.model
        # Detect actual position actuators instead of assuming their order or names.
        for a in range(m.nu):
            j = int(m.actuator_trnid[a, 0])
            if int(m.actuator_trntype[a]) == int(mujoco.mjtTrn.mjTRN_JOINT) and j >= 0:
                if m.actuator_gainprm[a, 0] > 0 and np.isclose(m.actuator_biasprm[a, 1], -m.actuator_gainprm[a, 0]):
                    self.actuators[j] = a
        self.reset()

    def reset(self):
        m, d = self.model, self.data
        self.demo = False
        if m.nkey:
            mujoco.mj_resetDataKeyframe(m, d, 0)
        else:
            mujoco.mj_resetData(m, d)
        if self.asset.initial_qpos is not None:
            d.qpos[:] = self.asset.initial_qpos
        self.native_targets = {control["name"]: float(self.asset.initial_controls[control["id"]])
                               for control in self.asset.controls}
        self.targets = {j["name"]: float(d.qpos[m.jnt_qposadr[j["id"]]]) for j in self.asset.joints}
        self.error = None
        self.last_tick = time.monotonic()
        self.apply_controls()
        mujoco.mj_forward(m, d)

    def apply_controls(self):
        m, d = self.model, self.data
        d.qfrc_applied[:] = 0
        d.ctrl[:] = 0
        if self.asset.native_controls:
            if self.demo:
                values = self.showcase_controller(d.time)
                self.native_targets.update({control["name"]: float(values[control["id"]])
                                            for control in self.asset.controls})
            for control in self.asset.controls:
                d.ctrl[control["id"]] = self.native_targets[control["name"]]
            return
        for joint in self.asset.joints:
            j, name = joint["id"], joint["name"]
            if j in self.actuators:
                a = self.actuators[j]
                ctrl = self.targets[name] * float(m.actuator_gear[a, 0])
                if m.actuator_ctrllimited[a]:
                    ctrl = float(np.clip(ctrl, *m.actuator_ctrlrange[a]))
                d.ctrl[a] = ctrl
            else:
                # An explicit virtual hand for unactuated hinge/slide joints.
                q, v = int(m.jnt_qposadr[j]), int(m.jnt_dofadr[j])
                inertia = max(float(m.dof_M0[v]), 1e-5)
                force = d.qfrc_bias[v] + inertia * (900 * (self.targets[name] - d.qpos[q]) - 60 * d.qvel[v])
                d.qfrc_applied[v] = np.clip(force, -100, 100)

    def control(self, command):
        with self.lock:
            if not isinstance(command, dict):
                raise BadRequest("Control parameters must be an object.")
            if self.asset.native_controls:
                return self.control_native(command)
            if "demo" in command and (not isinstance(command["demo"], bool) or command["demo"]):
                raise BadRequest("Automatic demonstration is only available for the five Overview assets.")
            mode = command.get("mode", self.mode)
            if mode not in ("pose", "physics"):
                raise BadRequest("Unknown control mode.")
            targets = command.get("targets", {})
            if not isinstance(targets, dict):
                raise BadRequest("Joint targets must be an object.")
            joint_by_name = {j["name"]: j for j in self.asset.joints}
            validated = {}
            for name, value in targets.items():
                if name not in joint_by_name:
                    raise BadRequest(f"Unknown joint: {name}")
                if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value):
                    raise BadRequest("Joint positions must be finite numbers.")
                validated[name] = float(np.clip(value, *joint_by_name[name]["range"]))
            if "paused" in command and not isinstance(command["paused"], bool):
                raise BadRequest("The paused parameter must be a boolean.")
            if command.get("reset"):
                self.reset()
            if mode != self.mode:
                self.data.qvel[:] = 0
                self.last_tick = time.monotonic()
            self.mode = mode
            self.paused = command.get("paused", self.paused)
            self.targets.update(validated)
            self.last_access = time.monotonic()
            if self.mode == "pose":
                for joint in self.asset.joints:
                    self.data.qpos[self.model.jnt_qposadr[joint["id"]]] = self.targets[joint["name"]]
                self.data.qvel[:] = 0
                mujoco.mj_forward(self.model, self.data)
            else:
                self.apply_controls()
            return self.state()

    def control_native(self, command):
        """Drive the unchanged source actuators; passive linkages stay passive."""
        if command.get("mode", "physics") != "physics" or command.get("targets"):
            raise BadRequest("This asset uses its original physical controls. Direct joint posing is not supported.")
        values = command.get("actuators", {})
        if not isinstance(values, dict):
            raise BadRequest("Actuator targets must be an object.")
        controls = {control["name"]: control for control in self.asset.controls}
        validated = {}
        for name, value in values.items():
            if name not in controls:
                raise BadRequest(f"Unknown actuator: {name}")
            if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value):
                raise BadRequest("Actuator targets must be finite numbers.")
            validated[name] = float(np.clip(value, *controls[name]["range"]))
        if "paused" in command and not isinstance(command["paused"], bool):
            raise BadRequest("The paused parameter must be a boolean.")
        if "demo" in command and not isinstance(command["demo"], bool):
            raise BadRequest("The demo parameter must be a boolean.")
        if command.get("reset"):
            self.reset()
        if command.get("demo") is True:
            if not self.demo:
                self.reset()
                self.demo = True
        elif command.get("demo") is False or (self.demo and validated):
            # Hand off at the current physical pose; stop original speed/force
            # actuators rather than writing qpos or freezing passive linkages.
            self.demo = False
            for control in self.asset.controls:
                self.native_targets[control["name"]] = (
                    float(self.data.qpos[self.model.jnt_qposadr[control["joint_id"]]])
                    if control["kind"] == "position" else 0.0)
        self.mode = "physics"
        self.paused = command.get("paused", self.paused)
        self.native_targets.update(validated)
        self.last_access = time.monotonic()
        self.apply_controls()
        mujoco.mj_forward(self.model, self.data)
        return self.state()

    def tick(self, now):
        with self.lock:
            elapsed = min(now - self.last_tick, .08)
            if self.mode != "physics" or self.paused or self.error or now - self.last_access > 30:
                self.last_tick = now
                return
            step = self.model.opt.timestep
            count = min(int(elapsed / step), 160)
            if count < 1:
                return
            self.last_tick = now
            for _ in range(count):
                self.apply_controls()
                mujoco.mj_step(self.model, self.data)
            mujoco.mj_forward(self.model, self.data)
            if not np.isfinite(self.data.qpos).all() or not np.isfinite(self.data.qvel).all():
                self.error = "Simulation reached a non-finite state. Reset the pose to continue."
                self.paused = True

    def state(self):
        with self.lock:
            self.last_access = time.monotonic()
            d, m = self.data, self.model
            transforms = []
            for geom in self.asset.geoms:
                g = geom["id"]
                quat = np.empty(4)
                mujoco.mju_mat2Quat(quat, d.geom_xmat[g])
                transforms.append({"id": g, "position": d.geom_xpos[g].tolist(),
                                   "quaternion": quat[[1, 2, 3, 0]].tolist()})
            warnings = [f"{mujoco.mjtWarning(i).name}: {int(w.number)}" for i, w in enumerate(d.warning) if w.number]
            controls = []
            for control in self.asset.controls:
                a, j = control["id"], control["joint_id"]
                value = d.qpos[m.jnt_qposadr[j]] if control["kind"] == "position" else (d.qvel[m.jnt_dofadr[j]] if control["kind"] == "velocity" else d.actuator_force[a])
                controls.append({"name": control["name"], "target": self.native_targets[control["name"]], "value": float(value)})
            skins = []
            if self.skin_scene is not None:
                update_skin_vertices(m, d, self.skin_scene)
                for skin in self.asset.skins:
                    s = skin["id"]
                    va, vn = int(m.skin_vertadr[s]), int(m.skin_vertnum[s])
                    skins.append({"id": s, "positions": self.skin_scene.skinvert[va * 3:(va + vn) * 3].tolist(),
                                  "normals": self.skin_scene.skinnormal[va * 3:(va + vn) * 3].tolist()})
            return {"time": float(d.time), "mode": self.mode, "paused": self.paused, "demo": self.demo,
                    "controls": controls, "skins": skins,
                    "joints": [{"id": j["id"], "name": j["name"],
                                "value": float(d.qpos[m.jnt_qposadr[j["id"]]]), "target": self.targets[j["name"]],
                                "origin": d.xanchor[j["id"]].tolist(), "axis": d.xaxis[j["id"]].tolist()}
                               for j in self.asset.joints],
                    "transforms": transforms, "contacts": int(d.ncon), "warnings": warnings, "error": self.error}


class Application:
    def __init__(self, data_dir):
        self.data_dir = Path(data_dir).resolve()
        self.assets, self.sessions = {}, {}
        self.lock = threading.RLock()
        definitions = [
            ("camera", "Camera", "Lens · display · dials · shutter",
             "Move the display and lens, set dial rotation speeds, and press the spring-return shutter.",
             {"screen_hinge": "Display angle", "mode_dial": "First dial speed", "focus_ring": "Lens rotation speed",
              "lens_extension": "Lens extension", "secondary_dial": "Second dial speed", "shutter_press": "Shutter pressure"}),
            ("phone", "Phone", "Two-hinge folding",
             "Two opposing hinges fold around the fixed middle panel. Display seams follow the panel motion.",
             {"outer_fold": "First hinge", "camera_fold": "Second hinge"}),
            ("globe", "Globe", "Polar-axis rotation",
             "Turn the globe inside its fixed frame. The magnifier, crank and decorative gears remain fixed.",
             {"body_globe_joint": "Globe rotation"}),
            ("ladder", "Ladder", "Frames and coupled side links",
             "Two drives move the supported frames. The four side links follow their physical constraints.",
             {"front_joint": "Front frame", "rear_joint": "Rear frame",
              "left_A_joint": "Left upper link", "left_B_joint": "Left lower link",
              "right_A_joint": "Right upper link", "right_B_joint": "Right lower link"}),
            ("carousel", "Carousel", "Rotating platform · fixed base",
             "The canopy, horses and platform turn together above the fixed base.",
             {"carousel_bearing": "Platform rotation"}),
        ]
        for identity, name, description, scope, labels in definitions:
            self.assets[identity] = Asset(identity, name, ASSETS / identity / "scene.xml",
                                          description, scope, labels, native_controls=True)
        registry = self.data_dir / "imports.json"
        if registry.exists():
            for entry in json.loads(registry.read_text(encoding="utf-8")):
                try:
                    scene = self.data_dir / entry["scene"]
                    scene.resolve().relative_to(self.data_dir)
                    if scene.is_file():
                        self.assets[entry["id"]] = Asset(entry["id"], entry["name"], scene, "Imported asset", entry.get("scope", ""), entry.get("labels", {}), True,
                                                         self.data_dir / "imports" / entry["id"])
                except (ValueError, KeyError):
                    continue
        self.closed = threading.Event()
        threading.Thread(target=self.loop, name="mujoco-simulation", daemon=True).start()

    def loop(self):
        while not self.closed.wait(.01):
            with self.lock:
                sessions = list(self.sessions.values())
            now = time.monotonic()
            for session in sessions:
                try:
                    session.tick(now)
                except Exception as exc:
                    with session.lock:
                        session.error, session.paused = f"Simulation paused: {exc}", True
                if now - session.last_access > 1200:
                    with self.lock:
                        self.sessions.pop(session.id, None)

    def get_asset(self, identity):
        with self.lock:
            if identity not in self.assets:
                raise KeyError("Asset not found.")
            return self.assets[identity]

    def get_session(self, identity):
        with self.lock:
            if identity not in self.sessions:
                raise KeyError("This session has closed. Select the asset again.")
            return self.sessions[identity]

    def create_session(self, identity):
        asset = self.get_asset(identity)
        session = Session(asset)
        with self.lock:
            if len(self.sessions) >= 24:
                raise BadRequest("Too many viewer sessions are open. Close unused viewers.")
            self.sessions[session.id] = session
        return {"id": session.id, "asset": asset.summary(),
                "model_url": f"/api/assets/{asset.id}/model", "state": session.state()}

    def import_asset(self, content, filename):
        identity = "import_" + uuid.uuid4().hex[:12]
        folder = self.data_dir / "imports" / identity
        folder.mkdir(parents=True)
        try:
            if filename.lower().endswith(".xml"):
                (folder / "scene.xml").write_bytes(content)
            elif filename.lower().endswith(".zip"):
                with zipfile.ZipFile(io.BytesIO(content)) as archive:
                    entries = archive.infolist()
                    if len(entries) > 4096 or sum(x.file_size for x in entries) > MAX_EXPANDED:
                        raise BadRequest("Archive exceeds the expanded limit of 512 MB or 4,096 files.")
                    for entry in entries:
                        path = PurePosixPath(entry.filename.replace("\\", "/"))
                        if path.is_absolute() or ".." in path.parts or (entry.external_attr >> 16) & 0o170000 == 0o120000:
                            raise BadRequest("Archive contains a disallowed path.")
                        target = folder.joinpath(*path.parts).resolve()
                        target.relative_to(folder)
                        if entry.is_dir():
                            target.mkdir(parents=True, exist_ok=True)
                        else:
                            target.parent.mkdir(parents=True, exist_ok=True)
                            with archive.open(entry) as source, target.open("wb") as dest:
                                shutil.copyfileobj(source, dest)
            else:
                raise BadRequest("Choose a .zip asset package or an .xml scene.")
            manifest = {}
            manifests = list(folder.rglob("viewer.json"))
            if manifests:
                manifest = json.loads(manifests[0].read_text(encoding="utf-8"))
                if not isinstance(manifest, dict):
                    raise BadRequest("viewer.json must contain an object.")
            xmls = list(folder.rglob("*.xml"))
            if not xmls:
                raise BadRequest("No XML scene was found in the asset package.")
            for xml in xmls:
                raw = xml.read_bytes()
                if b"<!DOCTYPE" in raw.upper() or b"<!ENTITY" in raw.upper():
                    raise BadRequest("XML declarations with external entities are not supported.")
                tree = ET.fromstring(raw)
                for node in tree.iter():
                    for key in ("file", "meshdir", "texturedir", "assetdir"):
                        value = node.get(key)
                        if value:
                            if "\\" in value or ":" in value or Path(value).is_absolute():
                                raise BadRequest("XML dependencies must use relative paths within the asset package.")
                            try:
                                (xml.parent / value).resolve().relative_to(folder)
                            except ValueError:
                                raise BadRequest("XML references a file outside the asset package.") from None
            if manifest.get("scene"):
                scene = (manifests[0].parent / manifest["scene"]).resolve()
                scene.relative_to(folder)
            else:
                candidates = [q for q in xmls if q.name == "scene.xml"]
                if len(candidates) == 1:
                    scene = candidates[0]
                elif len(xmls) == 1:
                    scene = xmls[0]
                else:
                    raise BadRequest("Multiple scenes were found. Set scene in viewer.json or name the main scene scene.xml.")
            display_name = str(manifest.get("name", Path(filename).stem))[:100]
            labels = manifest.get("labels", {})
            if not isinstance(labels, dict) or not all(isinstance(v, str) for v in labels.values()):
                raise BadRequest("Joint labels must be an object containing text values.")
            asset = Asset(identity, display_name, scene, "Imported asset",
                          str(manifest.get("scope", "Driven by the asset's joints, limits, and physical parameters."))[:1000], labels, True, folder)
            asset.load()
            with self.lock:
                self.assets[identity] = asset
                records = [{"id": a.id, "name": a.name, "scene": str(a.scene.relative_to(self.data_dir)),
                            "scope": a.scope, "labels": a.labels} for a in self.assets.values() if a.imported]
                pending = self.data_dir / "imports.tmp"
                pending.write_bytes(json_bytes(records))
                pending.replace(self.data_dir / "imports.json")
            return {"asset": asset.summary()}
        except Exception:
            shutil.rmtree(folder, ignore_errors=True)
            raise


class Handler(BaseHTTPRequestHandler):
    server_version = "PhysAg3DViewer/1.0"
    protocol_version = "HTTP/1.1"

    @property
    def app(self):
        return self.server.app

    def send(self, data, content_type="application/json; charset=utf-8", status=200, cache=False):
        if not isinstance(data, bytes):
            data = json_bytes(data)
        compressed = len(data) > 4096 and "gzip" in self.headers.get("Accept-Encoding", "") and "image/" not in content_type
        if compressed:
            data = gzip.compress(data, compresslevel=1)
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "private, max-age=86400" if cache else "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Vary", "Accept-Encoding")
        if compressed:
            self.send_header("Content-Encoding", "gzip")
        self.end_headers()
        self.wfile.write(data)

    def read_body(self):
        length = int(self.headers.get("Content-Length", 0))
        if length <= 0 or length > MAX_UPLOAD:
            raise BadRequest("The file is empty or exceeds the 128 MB upload limit.")
        origin = self.headers.get("Origin")
        if origin and urlparse(origin).netloc != self.headers.get("Host"):
            raise BadRequest("Start this operation from the viewer page.")
        content = self.rfile.read(length)
        if len(content) != length:
            raise BadRequest("Upload was incomplete. Please try again.")
        return content

    def handle_request(self):
        path = unquote(urlparse(self.path).path)
        parts = path.strip("/").split("/")
        if self.command == "GET" and path == "/api/health":
            return self.send({"ok": True, "engine": "MuJoCo", "version": mujoco.__version__})
        if self.command == "GET" and path == "/api/assets":
            with self.app.lock:
                return self.send({"assets": [a.summary() for a in self.app.assets.values()]})
        if self.command == "POST" and path == "/api/import":
            filename = unquote(self.headers.get("X-Filename", "asset.zip"))
            return self.send(self.app.import_asset(self.read_body(), filename), status=201)
        if self.command == "POST" and path == "/api/sessions":
            command = json.loads(self.read_body())
            if not isinstance(command, dict) or not isinstance(command.get("asset_id"), str):
                raise BadRequest("Select an asset.")
            return self.send(self.app.create_session(command["asset_id"]), status=201)
        if len(parts) >= 4 and parts[:2] == ["api", "assets"] and self.command == "GET":
            asset = self.app.get_asset(parts[2])
            if len(parts) == 4 and parts[3] == "appearance.glb" and asset.native_controls:
                return self.send((asset.resource_root / "appearance.glb").read_bytes(), "model/gltf-binary")
            if parts[3] == "thumbnail":
                candidates = [asset.scene.parent / "input.webp", asset.scene.parent / "input.png",
                              asset.scene.parent / "input.jpg", asset.scene.parent.parent / "input/source.png"]
                for image in candidates:
                    if image.is_file():
                        return self.send(image.read_bytes(), mimetypes.guess_type(image.name)[0] or "image/png", cache=True)
                return self.send(b'<svg xmlns="http://www.w3.org/2000/svg" width="120" height="120"><rect width="120" height="120" fill="#e8ecf1"/><text x="60" y="70" text-anchor="middle" font-size="40">3D</text></svg>', "image/svg+xml")
            asset.load()
            if parts[3] == "model":
                return self.send(asset.descriptor, cache=True)
            if len(parts) == 5 and parts[3] == "meshes":
                return self.send(asset.mesh_buffers[int(parts[4].split(".")[0])], "application/octet-stream", cache=True)
            if len(parts) == 5 and parts[3] == "textures":
                key = parts[4].split(".")[0]
                return self.send(asset.texture_buffers[int(key) if key.isdigit() else key], "image/png", cache=True)
        if len(parts) >= 3 and parts[:2] == ["api", "sessions"]:
            session = self.app.get_session(parts[2])
            if self.command == "DELETE" and len(parts) == 3:
                origin = self.headers.get("Origin")
                if origin and urlparse(origin).netloc != self.headers.get("Host"):
                    raise BadRequest("Start this operation from the viewer page.")
                with self.app.lock:
                    self.app.sessions.pop(session.id, None)
                return self.send({"ok": True})
            if self.command == "GET" and len(parts) == 4 and parts[3] == "state":
                return self.send(session.state())
            if self.command == "POST" and len(parts) == 4 and parts[3] == "control":
                return self.send(session.control(json.loads(self.read_body())))
        if self.command == "GET" and not path.startswith("/api/"):
            file = (ROOT / "web" / (path.lstrip("/") or "index.html")).resolve()
            file.relative_to(ROOT / "web")
            if file.is_file():
                mime = mimetypes.guess_type(file.name)[0] or "application/octet-stream"
                if file.suffix in (".js", ".mjs"):
                    mime = "text/javascript; charset=utf-8"
                return self.send(file.read_bytes(), mime)
        self.send({"error": "Resource not found."}, status=404)

    def dispatch(self):
        try:
            self.handle_request()
        except (BrokenPipeError, ConnectionResetError):
            pass
        except KeyError as exc:
            self.send({"error": str(exc).strip("'")}, status=404)
        except (ValueError, ET.ParseError, zipfile.BadZipFile, RuntimeError) as exc:
            self.send({"error": str(exc)[:1500]}, status=400)
        except Exception as exc:
            print(f"Request failed: {type(exc).__name__}: {exc}", flush=True)
            self.send({"error": "The operation failed. Check the asset dependencies or server log."}, status=500)

    do_GET = dispatch
    do_POST = dispatch
    do_DELETE = dispatch

    def log_message(self, fmt, *args):
        if "/state" not in str(args[0]):
            super().log_message(fmt, *args)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8891)
    parser.add_argument("--data-dir", type=Path, default=ROOT / ".runtime")
    args = parser.parse_args()
    app = Application(args.data_dir)
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    server.app = app
    print(f"PhysAg3D viewer: http://{args.host}:{server.server_port}", flush=True)
    print(f"Live MuJoCo {mujoco.__version__}; source assets read-only", flush=True)
    try:
        server.serve_forever(poll_interval=.25)
    except KeyboardInterrupt:
        pass
    finally:
        app.closed.set()
        server.server_close()


if __name__ == "__main__":
    main()
