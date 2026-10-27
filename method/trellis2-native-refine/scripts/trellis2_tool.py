"""Agent-facing TRELLIS.2 client: doctor, submit, status, collect, inspect."""
from __future__ import annotations

import argparse
import base64
from contextlib import contextmanager
import ctypes
import errno
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shlex
import socket
import struct
import subprocess
import sys
import uuid

HERE = Path(__file__).resolve().parent
DEFAULT_CONFIG = HERE.parent / "references" / "server.json"


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def write_json(path, value, exclusive=False):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x" if exclusive else "w", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write("\n")


def sha_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha_file(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def canonical_hash(value):
    return sha_bytes(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def broker_tcp_rpc(request, destination=None):
    """Reach the existing fixed-purpose broker through an operator SSH tunnel.

    The worker has no SSH credential access. The tunnel terminates at the
    broker's Unix socket, which accepts only bounded inference operations.
    """
    config = request["config"]
    host, port = config.get("broker_host"), config.get("broker_port")
    if host != "127.0.0.1" or type(port) is not int or not 1024 <= port <= 65535:
        raise ValueError("Broker tunnel must be an explicit IPv4 loopback port")
    server = config.get("server_config")
    if not isinstance(server, dict) or server.get("transport") != "unix":
        raise ValueError("Broker tunnel requires the managed Unix server profile")
    payload = json.dumps({**request, "config": server}, ensure_ascii=True,
                         allow_nan=False, separators=(",", ":")).encode("utf-8")
    if len(payload) > 128 * 1024 * 1024:
        raise ValueError("Broker request exceeds 128 MiB limit")

    def receive(stream, count):
        data = bytearray()
        while len(data) < count:
            part = stream.recv(min(1024 * 1024, count - len(data)))
            if not part:
                raise RuntimeError("Incomplete broker response; query the saved receipt")
            data.extend(part)
        return bytes(data)

    try:
        with socket.create_connection((host, port), timeout=120) as stream:
            stream.sendall(struct.pack("!I", len(payload)) + payload)
            length = struct.unpack("!I", receive(stream, 4))[0]
            if not 0 < length <= 16 * 1024 * 1024:
                raise RuntimeError("Invalid broker response length")
            response = json.loads(receive(stream, length))
            if response.get("ok") is not True:
                raise RuntimeError("Broker rejected operation: " + str(response.get("error", "unknown")))
            if destination is None:
                return response["result"]
            count = response.get("binary_bytes")
            if type(count) is not int or not 0 <= count <= 8 * 1024 ** 3:
                raise RuntimeError("Invalid broker artifact size")
            with Path(destination).open("xb") as target:
                while count:
                    block = receive(stream, min(count, 1024 * 1024))
                    target.write(block)
                    count -= len(block)
    except OSError as exc:
        raise RuntimeError("Broker tunnel failed; query the saved receipt before a new submission") from exc


def rpc(request, destination=None):
    config = request["config"]
    if config.get("transport") == "broker_tcp":
        return broker_tcp_rpc(request, destination)
    transport = config.get("transport", "ssh")
    if transport not in ("ssh", "local"):
        raise ValueError("transport must be ssh or local")
    source = (HERE / "remote_worker.py").read_text(encoding="utf-8")
    source += "\n_request = " + repr(request) + "\n"
    if destination is not None:
        source += "fetch(_request)\n"
    else:
        source += "import contextlib\nwith contextlib.redirect_stdout(sys.stderr):\n    _result = dispatch(_request)\nprint(json.dumps(_result, ensure_ascii=False))\n"
    worker_command = [config["python"], "-c", "import sys; exec(sys.stdin.read())"]
    if transport == "local":
        argv = worker_command
    else:
        host = config["ssh_host"]
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.@-]*", host):
            raise ValueError("Use a named SSH host alias in ssh_host")
        argv = ["ssh", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes", "-o", "UserKnownHostsFile=" + str(Path(config.get("known_hosts", Path.home() / ".ssh" / "known_hosts"))), "-o", "ConnectTimeout=10", "-o", "ServerAliveInterval=15", "-o", "ServerAliveCountMax=2", host, shlex.join(worker_command)]
    try:
        if destination is None:
            result = subprocess.run(argv, input=source.encode("utf-8"), stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE, timeout=60, check=False)
        else:
            with Path(destination).open("xb") as stream:
                result = subprocess.run(argv, input=source.encode("utf-8"), stdout=stream,
                                        stderr=subprocess.PIPE, timeout=60, check=False)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(transport + " operation timed out; worker outcome may be unknown. Query the saved receipt before any new submission.") from exc
    if result.returncode:
        diagnostic = result.stderr.decode("utf-8", errors="replace")[-7000:]
        raise RuntimeError(transport + " operation failed; check the saved receipt if submitting. " + diagnostic)
    if destination is not None:
        return None
    try:
        return json.loads(result.stdout.decode("utf-8"))
    except ValueError as exc:
        raise RuntimeError("Unreadable remote response; query the same receipt before retrying submission.") from exc


def prepare_image(path, mask_path=None):
    from PIL import Image, ImageChops, ImageOps
    with Image.open(path) as loaded:
        image = ImageOps.exif_transpose(loaded).convert("RGBA")
    if mask_path:
        with Image.open(mask_path) as loaded:
            mask = ImageOps.exif_transpose(loaded).convert("L")
        if mask.size != image.size:
            raise ValueError("Mask must match EXIF-oriented image dimensions")
        image.putalpha(ImageChops.multiply(image.getchannel("A"), mask))
    if image.getchannel("A").getextrema()[1] == 0:
        raise ValueError("Image/mask has no visible foreground")
    stream = io.BytesIO()
    image.save(stream, format="PNG")
    return stream.getvalue(), list(image.size)


def check_texture_mesh(path):
    import numpy as np
    with np.load(path, allow_pickle=False) as data:
        for key in ("vertices", "faces", "uv"):
            if key not in data:
                raise ValueError("Texture input requires " + key)
        vertices, faces, uv = data["vertices"], data["faces"], data["uv"]
        if vertices.ndim != 2 or vertices.shape[1] != 3 or len(vertices) < 3 or not np.isfinite(vertices).all():
            raise ValueError("Invalid mesh vertices")
        if faces.ndim != 2 or faces.shape[1] != 3 or not len(faces) or faces.dtype.kind not in "iu":
            raise ValueError("Faces must be nonempty integer triangles")
        if faces.min() < 0 or faces.max() >= len(vertices):
            raise ValueError("Face index out of range")
        if uv.shape != (len(vertices), 2) or not np.isfinite(uv).all():
            raise ValueError("UV array must be finite N x 2")
        if np.ptp(vertices, axis=0).max() <= 0:
            raise ValueError("Zero-size mesh")
        paired = ("face_owner" in data, "source_face_index" in data)
        if paired[0] != paired[1]:
            raise ValueError("face_owner and source_face_index must be supplied together")
        if all(paired):
            if data["face_owner"].shape != (len(faces),) or not np.array_equal(np.sort(data["source_face_index"]), np.arange(len(faces))):
                raise ValueError("Invalid per-face ownership/index mapping")
        if "source_vertex_index" in data:
            indices = data["source_vertex_index"]
            if indices.shape != (len(vertices),) or indices.dtype.kind not in "iu" or indices.min() < 0:
                raise ValueError("Invalid UV-to-source vertex index mapping")


def submit(args, config):
    if args.route == "texture" and not args.mesh:
        raise ValueError("--route texture requires --mesh with existing UVs")
    if args.route == "native" and args.mesh:
        raise ValueError("Native image generation does not condition on a mesh; choose texture for that route")
    png, size = prepare_image(args.image, args.mask)
    contents = {"input/source_image.png": png,
                "run_trellis.py": (HERE / "run_trellis.py").read_bytes(),
                "remote_worker.py": (HERE / "remote_worker.py").read_bytes()}
    if args.mesh:
        check_texture_mesh(args.mesh)
        contents["input/mesh_yup.npz"] = Path(args.mesh).read_bytes()
    defaults = config["defaults"].copy()
    defaults.update(read_json(HERE.parent / "references" / "inference-defaults.json").get(args.route, {}))
    settings = {key: getattr(args, key) if getattr(args, key) is not None else defaults[key]
                for key in ("resolution", "steps", "texture_size", "seed", "min_free_gb")}
    if settings["steps"] <= 0 or settings["texture_size"] <= 0 or settings["min_free_gb"] <= 0:
        raise ValueError("Steps, texture size and memory threshold must be positive")
    settings.update(route=args.route, gpu=args.gpu)
    identity = {"config": config, "settings": settings, "files": {k: sha_bytes(v) for k, v in contents.items()},
                "original_image_sha256": sha_file(args.image),
                "mask_sha256": sha_file(args.mask) if args.mask else None,
                "retry_of": str(Path(args.retry_of).resolve()) if args.retry_of else None}
    fingerprint = canonical_hash(identity)
    receipt_path = Path(args.receipt).resolve()
    if receipt_path.exists():
        receipt = read_json(receipt_path)
        if receipt["fingerprint"] != fingerprint:
            raise ValueError("Receipt belongs to a different request. Use a new receipt for changed input, settings, config or adapter.")
        request = receipt["request"]
    else:
        inventory = rpc({"action": "gpus", "config": config})["gpus"]
        choices = [g for g in inventory if g["free_mib"] >= settings["min_free_gb"] * 1024
                   and (args.gpu == "auto" or g["index"] == args.gpu)]
        if not choices:
            raise RuntimeError("No selected GPU has enough free memory. No job submitted.")
        settings["gpu"] = max(choices, key=lambda g: g["free_mib"])["index"]
        request = {"job_id": "t2-" + uuid.uuid4().hex, "config": config, "settings": settings,
                   "fingerprint": fingerprint, "input_size": size,
                   "input_hashes": identity["files"], "original_image_sha256": identity["original_image_sha256"],
                   "mask_sha256": identity["mask_sha256"], "retry_of": identity["retry_of"]}
        receipt = {"schema": "trellis2-skill-receipt-v1", "fingerprint": fingerprint, "request": request,
                   "original_image": str(Path(args.image).resolve())}
        write_json(receipt_path, receipt, exclusive=True)
    response = rpc({**request, "action": "submit", "files": {
        key: {"base64": base64.b64encode(value).decode("ascii"), "sha256": sha_bytes(value)}
        for key, value in contents.items()}})
    response["receipt"] = str(receipt_path)
    return response


def receipt_request(args):
    return read_json(args.receipt)["request"]


@contextmanager
def collection_lock(out):
    """All collectors cooperate on this persistent lock; a crash releases it.

    Do not unlink the lock file: another process may already hold its inode.
    This is not protection against arbitrary non-cooperating filesystem writers.
    """
    lock_path = out / ".collect.lock"
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        if os.name == "posix":
            import fcntl
            fcntl.flock(fd, fcntl.LOCK_EX)
        else:
            import msvcrt
            if os.fstat(fd).st_size == 0:
                os.write(fd, b"\0")
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_LOCK, 1)
        yield
    finally:
        os.close(fd)


def _matching_file(target, expected_bytes, expected_sha256):
    if not os.path.lexists(target):
        return False
    if target.is_symlink() or not target.is_file():
        raise ValueError("Refusing to overwrite different local file: " + str(target))
    if target.stat().st_size != expected_bytes or sha_file(target) != expected_sha256:
        raise ValueError("Refusing to overwrite different local file: " + str(target))
    return True


def _rename_noreplace(source, target):
    """Try a native atomic rename that cannot replace an existing target."""
    if os.name == "nt":
        os.rename(source, target)  # Windows rename fails when target exists.
        return True
    if not sys.platform.startswith("linux"):
        return False
    libc = ctypes.CDLL(None, use_errno=True)
    renameat2 = getattr(libc, "renameat2", None)
    if renameat2 is None:
        return False
    renameat2.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    renameat2.restype = ctypes.c_int
    if renameat2(-100, os.fsencode(source), -100, os.fsencode(target), 1) == 0:
        return True
    error = ctypes.get_errno()
    if error in {errno.ENOSYS, errno.EINVAL, errno.EPERM, errno.ENOTSUP, errno.EOPNOTSUPP}:
        return False
    raise OSError(error, os.strerror(error), str(target))


def _publish_verified(temporary, target, expected_bytes, expected_sha256):
    """Publish complete bytes; caller MUST hold collection_lock(target root).

    Filesystems without hardlinks/RENAME_NOREPLACE use a checked rename under
    the collection's exclusive advisory lock. Cooperating collectors cannot
    overwrite conflicts. A foreign process that ignores this lock can race the
    last existence check; use a dedicated collection directory in that case.
    """
    if temporary.stat().st_size != expected_bytes or sha_file(temporary) != expected_sha256:
        raise ValueError("Downloaded file checksum mismatch: " + target.name)
    with temporary.open("r+b") as stream:
        os.fsync(stream.fileno())
    if _matching_file(target, expected_bytes, expected_sha256):
        return "existing_verified"
    try:
        os.link(temporary, target)
        return "hardlink"
    except FileExistsError:
        _matching_file(target, expected_bytes, expected_sha256)
        return "existing_verified"
    except OSError as exc:
        if exc.errno not in {errno.EPERM, errno.EACCES, errno.ENOSYS, errno.ENOTSUP, errno.EOPNOTSUPP, errno.EXDEV}:
            raise
    try:
        if _rename_noreplace(temporary, target):
            return "rename_noreplace"
    except FileExistsError:
        _matching_file(target, expected_bytes, expected_sha256)
        return "existing_verified"
    if _matching_file(target, expected_bytes, expected_sha256):
        return "existing_verified"
    os.replace(temporary, target)
    return "locked_atomic_replace"


def _publish_json(value, target):
    data = (json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")
    if _matching_file(target, len(data), sha_bytes(data)):
        return
    temporary = target.with_name(target.name + ".part-" + uuid.uuid4().hex)
    try:
        with temporary.open("xb") as stream:
            stream.write(data)
        _publish_verified(temporary, target, len(data), sha_bytes(data))
    finally:
        temporary.unlink(missing_ok=True)


def collect(args):
    request = receipt_request(args)
    listing = rpc({**request, "action": "list_files"})
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    with collection_lock(out):
        _publish_json({"job_id": listing["job_id"], "fingerprint": request.get("fingerprint"),
                       "listing_sha256": canonical_hash(listing)}, out / ".collect.identity.json")
        for item in listing["files"]:
            relative = PurePosixPath(item["path"])
            if (not relative.parts or relative.is_absolute()
                    or item["path"] in {"collection.json", ".collect.lock", ".collect.identity.json"}
                    or any(part in ("..", ".") or ":" in part or "\\" in part for part in relative.parts)):
                raise ValueError("Unsafe remote filename")
            target = out.joinpath(*relative.parts)
            if not target.resolve().is_relative_to(out):
                raise ValueError("Collection path escapes output directory")
            target.parent.mkdir(parents=True, exist_ok=True)
            if _matching_file(target, item["bytes"], item["sha256"]):
                continue
            temporary = target.with_name(target.name + ".part-" + uuid.uuid4().hex)
            try:
                rpc({**request, "action": "fetch", "file": item["path"]}, destination=temporary)
                _publish_verified(temporary, target, item["bytes"], item["sha256"])
            finally:
                temporary.unlink(missing_ok=True)
        # The completion manifest appears only after all listed files verify.
        _publish_json(listing, out / "collection.json")
    return {"state": listing["state"], "job_id": listing["job_id"], "out": str(out),
            "verified_files": len(listing["files"]), "simulation_ready": False}


def inspect_mesh(args):
    import numpy as np
    import trimesh
    scene = trimesh.load(args.mesh, force="scene", process=False)
    mesh = scene.to_mesh() if hasattr(scene, "to_mesh") else scene.dump(concatenate=True)
    if not len(mesh.vertices) or not len(mesh.faces):
        raise ValueError("Mesh is empty")
    report = {"file": str(Path(args.mesh).resolve()), "sha256": sha_file(args.mesh),
              "vertices": len(mesh.vertices), "faces": len(mesh.faces),
              "bounds_in_file_units": mesh.bounds.tolist(), "extents_in_file_units": mesh.extents.tolist(),
              "finite_vertices": bool(np.isfinite(mesh.vertices).all()),
              "watertight": bool(mesh.is_watertight), "winding_consistent": bool(mesh.is_winding_consistent),
              # Count the face graph without constructing textured submeshes;
              # splitting UV islands can otherwise copy textures thousands of times.
              "connected_components": len(trimesh.graph.connected_components(
                  mesh.face_adjacency, nodes=np.arange(len(mesh.faces)), min_len=1)),
              "geometry_count": len(scene.geometry),
              "visuals": [{"name": str(name), "kind": value.visual.kind,
                           "has_uv": getattr(value.visual, "uv", None) is not None,
                           "material_type": type(getattr(value.visual, "material", None)).__name__}
                          for name, value in scene.geometry.items()],
              "appearance_review": "not_performed_by_this_command", "simulation_ready": False}
    if args.out:
        write_json(args.out, report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("doctor", help="Check actual remote paths, imports and GPU inventory")
    sub = commands.add_parser("submit", help="Prepare image, stage an isolated job, detach and save receipt")
    sub.add_argument("--image", required=True)
    sub.add_argument("--mask")
    sub.add_argument("--route", choices=("native", "texture"), default="native")
    sub.add_argument("--mesh")
    sub.add_argument("--receipt", required=True)
    sub.add_argument("--resolution", type=int, choices=(512, 1024))
    sub.add_argument("--steps", type=int)
    sub.add_argument("--texture-size", type=int)
    sub.add_argument("--seed", type=int)
    sub.add_argument("--min-free-gb", type=float)
    sub.add_argument("--gpu", default="auto")
    sub.add_argument("--retry-of")
    for name in ("status", "collect"):
        sub = commands.add_parser(name)
        sub.add_argument("--receipt", required=True)
        if name == "collect":
            sub.add_argument("--out", required=True)
    sub = commands.add_parser("inspect", help="Mesh statistics; does not claim visual or simulation validation")
    sub.add_argument("--mesh", required=True)
    sub.add_argument("--out")
    args = parser.parse_args()
    try:
        if args.command == "doctor":
            result = rpc({"action": "doctor", "config": read_json(args.config)})
        elif args.command == "submit":
            result = submit(args, read_json(args.config))
        elif args.command == "status":
            result = rpc({**receipt_request(args), "action": "status"})
        elif args.command == "collect":
            result = collect(args)
        else:
            result = inspect_mesh(args)
        print(json.dumps(result, ensure_ascii=True, allow_nan=False))
        return 1 if args.command == "doctor" and not result.get("ok") else 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error_type": type(exc).__name__, "error": str(exc)}, ensure_ascii=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
