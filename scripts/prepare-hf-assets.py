#!/usr/bin/env python3
"""Prepare and verify one-folder-per-case browser assets. Never uploads files.

Run after git lfs pull:
    python scripts/prepare-hf-assets.py --output ../PhysAg3D-hf-assets
Add --include-videos to include each case's recorded preview in its folder.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import shutil
import struct
import tempfile
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parent.parent
SCHEMA = "physag3d-browser-assets-v1"
SOURCE_COMMIT = "24f4db5cb22791f4059dc74cfdc556778f7a4882"
LFS_POINTER = b"version https://git-lfs.github.com/spec/v1"
HASH = re.compile(r"^[a-fA-F0-9]{64}$")


def digest_file(path):
    checksum = hashlib.sha256()
    with path.open("rb") as stream:
        first = stream.read(64)
        if first.startswith(LFS_POINTER):
            raise ValueError(f"Unresolved Git LFS pointer; run git lfs pull: {path}")
        checksum.update(first)
        for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            checksum.update(chunk)
    return checksum.hexdigest()


def safe_file(root, relative):
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError(f"Resource escapes the source directory: {relative}")
    return path


def resource(source, url, metadata_path=None):
    """Match the viewer's distinction between /assets and relative assets/."""
    parsed = urlsplit(url)
    if parsed.scheme or parsed.netloc:
        raise ValueError(f"Unexpected external source resource: {url}")
    path = unquote(parsed.path)
    base = source if path.startswith("/") or metadata_path is None else metadata_path.parent
    resolved = safe_file(base, path.lstrip("/"))
    if not resolved.is_relative_to(source.resolve()):
        raise ValueError(f"Resource escapes website/: {url}")
    if not resolved.is_file():
        raise FileNotFoundError(f"Missing browser resource: {resolved}")
    return resolved


def glb_external_files(path):
    with path.open("rb") as stream:
        header = stream.read(20)
        if header.startswith(LFS_POINTER[:20]):
            raise ValueError(f"Run git lfs pull before preparing: {path}")
        if len(header) != 20 or header[:4] != b"glTF" or header[16:20] != b"JSON":
            raise ValueError(f"Invalid GLB header: {path}")
        document = json.loads(stream.read(struct.unpack_from("<I", header, 12)[0]))
    return [entry["uri"] for group in ("images", "buffers") for entry in document.get(group, [])
            if entry.get("uri") and not entry["uri"].startswith("data:")]


def plan_assets(source, include_videos=False):
    catalog_path = source / "assets/gallery-models/catalog.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    assets = catalog["assets"]
    if len(assets) != 236 or len({item["id"] for item in assets}) != 236:
        raise ValueError("The browser catalogue must contain 236 unique assets")
    cases = [item["source"]["case_id"] for item in assets]
    if len(set(cases)) != len(cases):
        raise ValueError("Multiple catalogue items share one case folder")
    folders = {path.name for path in (source / "assets/generated-latest").iterdir() if path.is_dir()}
    if folders != set(cases):
        raise ValueError("Case folder inventory differs from the browser catalogue")
    plan, case_records, expected = {}, [], {}

    def add(path, destination=None, case=None, role="source", sha256=None):
        path = path.resolve()
        if not path.is_file() or not path.is_relative_to(source):
            raise ValueError(f"Missing or unsafe source file: {path}")
        target = destination or path.relative_to(source).as_posix()
        prior = plan.get(target)
        if prior and prior["source"] != path:
            raise ValueError(f"Conflicting destination: {target}")
        plan.setdefault(target, {"source": path, "case_id": case, "roles": set()})["roles"].add(role)
        if sha256 and HASH.fullmatch(sha256):
            expected.setdefault(target, set()).add(sha256.lower())
        return target

    add(catalog_path, role="browser_catalogue")
    for item in assets:
        case = item["source"]["case_id"]
        if not re.fullmatch(r"img_[0-9]+", case):
            raise ValueError(f"Unexpected case folder: {case}")
        folder = f"assets/generated-latest/{case}"
        for path in sorted((source / folder).rglob("*")):
            if path.is_file():
                add(path, case=case, role="complete_case_source")
        metadata_path = resource(source, item["metadata_url"]) if item.get("metadata_url") else None
        metadata = item.get("metadata") or (json.loads(metadata_path.read_text(encoding="utf-8")) if metadata_path else {})
        resources = item.get("resources", {})

        def reference(key):
            return resources.get(key) or metadata.get("files", {}).get(key)

        def source_hash(key):
            hashes = metadata.get("hashes", {})
            return hashes.get(key) or hashes.get(key + "_sha256") or (hashes.get("skin_sha256") if key == "recorded_skin" else None)

        model = resource(source, item.get("asset_url") or reference("asset"), metadata_path)
        model_hash = item.get("asset_sha256") or metadata.get("hashes", {}).get("asset") or metadata.get("hashes", {}).get("asset_glb_sha256")
        if not model_hash or not HASH.fullmatch(model_hash):
            raise ValueError(f"The browser model has no integrity hash: {item['id']}")
        runtime = [add(model, case=case, role="browser_model", sha256=model_hash)]
        if metadata_path:
            runtime.append(add(metadata_path, case=case, role="browser_metadata"))
        manifest_bodies = metadata.get("manifest", {}).get("requirements", {}).get("bodies", [])
        keys = []
        if reference("trajectory") and (metadata.get("recorded_replay", {}).get("available") or manifest_bodies):
            keys.append("trajectory")
            if reference("recorded_skin"):
                keys.append("recorded_skin")
            elif reference("skin"):
                keys.append("skin")
        if metadata.get("approximate_soft", {}).get("available") and reference("approximate_soft"):
            keys.append("approximate_soft")
        for key in keys:
            runtime.append(add(resource(source, reference(key), metadata_path), case=case, role=f"browser_{key}", sha256=source_hash(key)))
        if model.suffix.lower() == ".glb":
            for uri in glb_external_files(model):
                runtime.append(add(resource(source, uri, model), case=case, role="external_gltf_dependency"))
        image = resource(source, item["input_url"])
        input_path = add(image, case=case, role="input_image")
        poster_source = resource(source, item["poster_url"])
        poster = add(poster_source, f"{folder}/poster{poster_source.suffix.lower()}", case, "poster")
        video = None
        if include_videos and item.get("video_url"):
            video_source = resource(source, item["video_url"])
            video = add(video_source, f"{folder}/preview{video_source.suffix.lower()}", case, "recorded_preview")
        case_records.append({"id": item["id"], "case_id": case, "name": item["name"],
                             "name_zh": item.get("nameZh"), "folder": folder, "model": model.relative_to(source).as_posix(),
                             "input": input_path, "poster": poster, "preview": video,
                             "original_poster": poster_source.relative_to(source).as_posix(),
                             "capabilities": item.get("capabilities", []), "native_asset_id": item.get("native_asset_id"),
                             "browser_files": runtime, "catalogue_entry": item})
    return plan, sorted(case_records, key=lambda case: case["case_id"]), expected


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT / "website")
    parser.add_argument("--output", type=Path, default=ROOT.parent / "PhysAg3D-hf-assets")
    parser.add_argument("--include-videos", action="store_true")
    args = parser.parse_args()
    source, output = args.source.resolve(), args.output.resolve()
    if output == source or output.is_relative_to(source):
        raise ValueError("The staging directory must be outside the source website")
    plan, cases, expected = plan_assets(source, args.include_videos)
    marker_path = output / ".physag-assets-stage.json"
    marker = {"schema": SCHEMA, "managed_files": []}
    if output.exists() and any(output.iterdir()):
        if not marker_path.is_file():
            raise FileExistsError(f"Refusing to use an unrelated nonempty directory: {output}")
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
        if marker.get("schema") != SCHEMA:
            raise ValueError("Unrecognized staging directory marker")
    output.mkdir(parents=True, exist_ok=True)
    marker_path.write_text(json.dumps(marker, indent=2) + "\n", encoding="utf-8")
    managed = set(marker["managed_files"])
    package_manifest = json.loads((source / "package-manifest.json").read_text(encoding="utf-8"))
    original_hashes = {row["path"]: row["sha256"] for row in package_manifest["files"]}
    records, source_hashes, reused = [], {}, 0

    def publish(relative, data=None, original=None, sha256=None):
        nonlocal reused
        destination = safe_file(output, relative)
        if destination.exists():
            desired = sha256 or hashlib.sha256(data).hexdigest()
            if digest_file(destination) == desired:
                reused += 1
                return
            if relative not in managed:
                raise FileExistsError(f"Refusing to overwrite an unrelated file: {destination}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=destination.parent, prefix=".stage-", delete=False) as stream:
            temp = Path(stream.name)
            try:
                if original:
                    with original.open("rb") as input_stream:
                        shutil.copyfileobj(input_stream, stream, 4 * 1024 * 1024)
                else:
                    stream.write(data)
            except BaseException:
                stream.close(); temp.unlink(missing_ok=True); raise
        try:
            temp.replace(destination)
        finally:
            temp.unlink(missing_ok=True)

    for i, (relative, entry) in enumerate(sorted(plan.items()), 1):
        original = entry["source"]
        source_relative = original.relative_to(source).as_posix()
        digest = source_hashes.setdefault(source_relative, None)
        if digest is None:
            digest = source_hashes[source_relative] = digest_file(original)
        if original_hashes.get(source_relative) != digest:
            raise ValueError(f"Source differs from the delivered package checksum: {source_relative}")
        for checksum in expected.get(relative, set()):
            if digest != checksum:
                raise ValueError(f"Browser metadata hash mismatch: {relative}")
        publish(relative, original=original, sha256=digest)
        records.append({"path": relative, "source_path": "website/" + source_relative,
                        "bytes": original.stat().st_size, "sha256": digest, "case_id": entry["case_id"],
                        "roles": sorted(entry["roles"]), "browser_hash_verified": bool(expected.get(relative))})
        if i % 100 == 0:
            print(json.dumps({"prepared": i, "of": len(plan)}), flush=True)

    def generated(relative, content, case=None):
        data = content.encode("utf-8")
        publish(relative, data=data)
        records.append({"path": relative, "source_path": None, "bytes": len(data),
                        "sha256": hashlib.sha256(data).hexdigest(), "case_id": case, "roles": ["generated_index"]})

    for case in cases:
        card = {**case["catalogue_entry"], "hf_bundle": {key: value for key, value in case.items() if key != "catalogue_entry"}}
        generated(case["folder"] + "/asset-card.json", json.dumps(card, ensure_ascii=False, indent=2) + "\n", case["case_id"])
        relative_model = Path(case["model"]).relative_to(case["folder"]).as_posix()
        relative_input = Path(case["input"]).relative_to(case["folder"]).as_posix()
        text = (f"# {case['name']} ({case['case_id']})\n\n"
                f"Gallery ID: `{case['id']}`. This folder contains one complete browser 3D asset and its delivered interaction data.\n\n"
                f"- [3D model]({relative_model})\n- [Input image]({relative_input})\n"
                f"- [Preview poster]({Path(case['poster']).name})\n- [Catalogue entry and browser dependencies](asset-card.json)\n\n"
                "Model and source JSON bytes are unchanged. GLB files contain their own PBR textures unless external dependencies are listed in asset-card.json.\n\n"
                "Capabilities differ by asset: joint manipulation, saved motion, surface deformation, or static inspection. Browser joint controls are geometric and are not a new live physics simulation.\n")
        if case["preview"]:
            text += f"\n[Recorded preview]({Path(case['preview']).name})\n"
        generated(case["folder"] + "/README.md", text, case["case_id"])

    index_cases = [{key: value for key, value in case.items() if key != "catalogue_entry"} for case in cases]
    generated("asset-index.json", json.dumps({"schema": SCHEMA, "assets": index_cases}, ensure_ascii=False, indent=2) + "\n")
    lines = ["# PhysAg3D browser 3D assets", "", "236 assets, one complete asset per `assets/generated-latest/img_NNN/` folder.", "",
             "Each folder includes the original model, input image, interaction metadata where available, a poster, and an asset card. Model and original JSON paths are preserved for the GitHub Pages viewer.", "",
             "The asset catalogue is `assets/gallery-models/catalog.json`; `asset-index.json` maps gallery IDs to folders; `manifest.json` records file sizes and SHA-256 checksums.", "",
             "This bundle contains the browser assets, not the Windows Python runtime or the original MuJoCo backend. Original producer metadata may name historical authoring files; the runtime dependency list is in each asset card.", "",
             "Recorded MP4 previews are " + ("included in each asset folder." if args.include_videos else "not included; the website's existing videos remain separately hosted."), "",
             "Source: https://github.com/Supra-3D/PhysAg3D/tree/homepage/website", "", "## Asset index", ""]
    for case in cases:
        lines.append(f"- [{case['case_id']} — {case['name']}]({case['folder']}/README.md)")
    generated("README.md", "\n".join(lines) + "\n")
    summary = {"schema": SCHEMA, "assets": len(cases), "files": len(records),
               "bytes": sum(row["bytes"] for row in records), "browser_hashes_verified": len(expected),
               "source_files_verified_against_package": len(source_hashes),
               "file_types": dict(sorted(Counter(Path(row["path"]).suffix for row in records).items())),
               "source_commit": SOURCE_COMMIT, "include_videos": args.include_videos,
               "unresolved_lfs_pointers": 0}
    manifest = {**summary, "files": sorted(records, key=lambda row: row["path"])}
    publish("manifest.json", data=(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    marker["managed_files"] = sorted({row["path"] for row in records} | {"manifest.json"})
    marker_path.write_text(json.dumps(marker, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({**summary, "output": str(output), "reused_files": reused,
                      "upload_exclude": [".physag-assets-stage.json"]}, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
