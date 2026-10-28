"""Extend the verified case bundles with unchanged public media and former LFS files.

Run prepare-hf-assets.py --include-videos first. This only packages files and
records storage paths; it never rebuilds models, videos, or interaction data.
"""
from pathlib import Path
from collections import Counter
import hashlib
import json
import shutil
import subprocess

ROOT = Path(__file__).resolve().parent.parent
STAGE = ROOT.parent / "PhysAg3D-hf-assets"
BASE = "https://huggingface.co/datasets/supra3d/physag3d-web-assets/resolve/main/"


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def digest(path):
    with path.open("rb") as stream:
        if stream.read(43).startswith(b"version https://git-lfs.github.com/spec/v1"):
            raise ValueError(f"Unresolved source pointer: {path}")
        stream.seek(0)
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main():
    manifest = read(STAGE / "manifest.json")
    marker = read(STAGE / ".physag-assets-stage.json")
    records = {x["path"]: x for x in manifest["files"]}
    owned = set(marker["managed_files"])
    by_source = {x["source_path"]: x["path"] for x in records.values() if x["source_path"]}
    aliases = {}
    source_hashes = {"website/" + x["path"]: x["sha256"]
                     for x in read(ROOT / "website/package-manifest.json")["files"]}
    cases = read(STAGE / "asset-index.json")["assets"]
    # Public poster copies and original source files share each case's folder.
    # Recover both aliases when rerunning against an extended manifest.
    for case in cases:
        by_source["website/" + case["original_poster"]] = case["poster"]
        aliases[case["original_poster"]] = case["poster"]
    native = {x["native_asset_id"]: x["case_id"] for x in cases if x.get("native_asset_id")}
    media = read(ROOT / "scripts/hero-media.json")

    def add(source, target, case=None, role="stored_source"):
        path = ROOT / source
        checksum = digest(path)
        if source in source_hashes and checksum != source_hashes[source]:
            raise ValueError(f"Delivered source changed: {source}")
        destination = (STAGE / target).resolve()
        assert destination.is_relative_to(STAGE.resolve())
        if destination.exists() and digest(destination) != checksum:
            raise ValueError(f"Conflicting stored file: {target}")
        if not destination.exists():
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, destination)
        if target not in records:
            records[target] = {"path": target, "source_path": source, "bytes": path.stat().st_size,
                               "sha256": checksum, "case_id": case, "roles": [role]}
        elif role not in records[target]["roles"]:
            records[target]["roles"].append(role)
        owned.add(target)
        by_source[source] = target
        return target

    # Include complete native assets (scene XML, meshes, textures, and metadata).
    for name, case in native.items():
        folder = ROOT / "website/viewer/assets" / name
        for path in sorted(folder.rglob("*")):
            if path.is_file():
                add(path.relative_to(ROOT).as_posix(),
                    f"assets/generated-latest/{case}/native/{path.relative_to(folder).as_posix()}",
                    case, "native_source")

    # Keep a verified recovery location for every binary formerly held in Git LFS.
    lfs = json.loads(subprocess.check_output(["git", "lfs", "ls-files", "--json"], cwd=ROOT, text=True))["files"]
    if not lfs:
        lfs = [{"name": x["source"], "oid": x["sha256"], "size": x["bytes"]}
               for x in read(ROOT / "scripts/asset-storage-files.json")["files"]]
    restore = []
    for item in lfs:
        source = item["name"]
        target = by_source.get(source)
        if not target:
            relative = source.removeprefix("website/")
            case = None
            if relative.startswith("assets/hero/"):
                key = Path(relative).name.split("-")[0]
                name = "phone" if key == "trifold" else key
                case = native.get(name)
                target = f"assets/generated-latest/{case}/hero/{Path(relative).name}" if case else relative
            elif relative.startswith("assets/") and relative != "assets/PhysAg3D.pdf":
                target = relative
            else:
                target = "offline/" + relative
            add(source, target, case)
        record = records[target]
        if record["sha256"] != item["oid"] or record["bytes"] != item["size"]:
            raise ValueError(f"Git LFS/source checksum mismatch: {source}")
        restore.append({"source": source, "path": target, "bytes": record["bytes"], "sha256": record["sha256"]})
        if source.startswith("website/assets/"):
            aliases[source.removeprefix("website/")] = target

    # Publish exactly the current edited films, without regenerating any frames.
    for key, clip in media["clips"].items():
        case = native["phone" if key == "trifold" else key]
        target = add(clip["output"], f"assets/generated-latest/{case}/showcase.mp4", case, "current_preview")
        aliases[clip["output"]] = target

    # Preserve current paper/figures/posters too; generated JSON stays unchanged.
    for path in sorted((ROOT / "assets").rglob("*")):
        if not path.is_file() or path.suffix.lower() == ".json":
            continue
        source = path.relative_to(ROOT).as_posix()
        if source in aliases and source.startswith("assets/hero/"):
            continue
        target = aliases.get(source, source)
        if target in records and records[target]["sha256"] != digest(path):
            target = source
        add(source, target, role="public_media")
        aliases[source] = target

    # Paths used by the build and viewer. Original per-case relative paths remain valid.
    storage = {"base_url": BASE, "paths": dict(sorted((a, b) for a, b in aliases.items() if a != b))}
    write(ROOT / "scripts/asset-storage.json", storage)
    write(ROOT / "scripts/asset-storage-files.json", {"base_url": BASE, "files": restore})
    manifest["files"] = sorted(records.values(), key=lambda x: x["path"])
    manifest["bytes"] = sum(x["bytes"] for x in records.values())
    manifest["file_types"] = dict(sorted(Counter(Path(x).suffix for x in records).items()))
    manifest["storage"] = "huggingface"
    write(STAGE / "manifest.json", manifest)
    owned.add("manifest.json")
    marker["managed_files"] = sorted(owned)
    write(STAGE / ".physag-assets-stage.json", marker)
    print(json.dumps({"files": len(records), "bytes": manifest["bytes"], "cases": len(cases),
                      "former_lfs_files_verified": len(restore), "path_aliases": len(storage["paths"])}), flush=True)


if __name__ == "__main__":
    main()
