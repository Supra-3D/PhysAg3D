"""Publish prepared assets with an in-memory token; no credentials are saved."""
from pathlib import Path
import argparse
import getpass
import hashlib
import json
import os
import time

from huggingface_hub import HfApi


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    folder = args.folder.resolve(strict=True)
    token = os.environ.get("HF_TOKEN") or getpass.getpass("HF write token (hidden): ")
    api = HfApi(token=token)
    repo_id = "supra3d/physag3d-web-assets"
    api.auth_check(repo_id, repo_type="dataset", write=True)
    info = api.repo_info(repo_id, repo_type="dataset")
    if info.private or info.gated:
        raise RuntimeError("The website requires a public, ungated dataset.")
    print("Dataset write access verified. Uploading prepared asset folders.", flush=True)
    for attempt in range(3):
        try:
            commit = api.upload_folder(
                repo_id=repo_id,
                repo_type="dataset",
                folder_path=folder,
                ignore_patterns=[".cache/**", "*.tmp", ".physag-assets-stage.json"],
                commit_message="Publish 236 complete PhysAg3D browser assets",
            )
            break
        except Exception as exc:
            # Only report the class: URLs or authentication data need not enter logs.
            print(f"Upload attempt {attempt + 1} failed: {type(exc).__name__}", flush=True)
            if attempt == 2:
                raise RuntimeError("Asset upload failed after three attempts.") from None
            time.sleep(5 * (attempt + 1))
    revision = api.repo_info(repo_id, repo_type="dataset").sha
    files = list(api.list_repo_tree(repo_id, repo_type="dataset", revision=revision, recursive=True))
    remote = {f.path: f for f in files if hasattr(f, "size")}
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    hashes = {f["path"]: f["sha256"] for f in manifest["files"]}
    checked = 0
    for local in folder.rglob("*"):
        if not local.is_file() or ".cache" in local.parts or local.suffix == ".tmp" or local.name == ".physag-assets-stage.json":
            continue
        path = local.relative_to(folder).as_posix()
        if path not in remote or remote[path].size != local.stat().st_size:
            raise RuntimeError(f"Uploaded asset size mismatch: {path}")
        item = remote[path]
        if item.lfs and path in hashes:
            if item.lfs.sha256 != hashes[path]:
                raise RuntimeError(f"Uploaded asset checksum mismatch: {path}")
        elif item.blob_id:
            content = local.read_bytes()
            digest = hashlib.sha1(f"blob {len(content)}\0".encode() + content).hexdigest()
            if digest != item.blob_id:
                raise RuntimeError(f"Uploaded file checksum mismatch: {path}")
        checked += 1
    report = {"repo_id": repo_id, "revision": revision, "files_verified": checked,
              "commit_url": commit.commit_url}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2), flush=True)


if __name__ == "__main__":
    main()
