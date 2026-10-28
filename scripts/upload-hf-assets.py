"""Publish prepared assets with an in-memory token; no credentials are saved."""
from pathlib import Path
import argparse
import getpass
import hashlib
import json
import logging
import os
import re
import time

from huggingface_hub import HfApi, CommitOperationAdd, set_client_factory
from huggingface_hub.utils._http import default_client_factory


def upload_client():
    # Bound stalled connections; signed storage URLs must not enter logs.
    try:
        import httpx2 as httpx
    except ImportError:
        import httpx
    client = default_client_factory()
    client.timeout = httpx.Timeout(120, connect=30)
    return client


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    logging.getLogger("huggingface_hub.utils._http").setLevel(logging.ERROR)
    set_client_factory(upload_client)
    folder = args.folder.resolve(strict=True)
    token = os.environ.get("HF_TOKEN") or getpass.getpass("HF write token (hidden): ")
    api = HfApi(token=token)
    repo_id = "supra3d/physag3d-web-assets"
    api.auth_check(repo_id, repo_type="dataset", write=True)
    info = api.repo_info(repo_id, repo_type="dataset")
    if info.private or info.gated:
        raise RuntimeError("The website requires a public, ungated dataset.")
    print("Dataset write access verified. Uploading prepared asset folders.", flush=True)
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    allowed = [row["path"] for row in manifest["files"]] + ["manifest.json"]
    hashes = {f["path"]: f["sha256"] for f in manifest["files"]}
    print(json.dumps({"upload_files": len(allowed), "bytes": manifest["bytes"]}), flush=True)
    for attempt in range(3):
        try:
            existing = {f.path: f for f in api.list_repo_tree(repo_id, repo_type="dataset", recursive=True) if hasattr(f, "size")}
            def already_stored(path):
                item, local = existing.get(path), folder / path
                if item is None or item.size != local.stat().st_size:
                    return False
                if item.lfs:
                    return item.lfs.sha256 == hashes.get(path)
                content = local.read_bytes()
                return item.blob_id == hashlib.sha1(f"blob {len(content)}\0".encode() + content).hexdigest()
            operations = [CommitOperationAdd(path_in_repo=path, path_or_fileobj=folder / path)
                          for path in allowed if not already_stored(path)]
            print(json.dumps({"already_published": len(allowed) - len(operations), "remaining": len(operations)}), flush=True)
            commit = None
            pending, pending_bytes, completed, completed_bytes = [], 0, 0, 0
            for operation in operations:
                pending.append(operation)
                pending_bytes += (folder / operation.path_in_repo).stat().st_size
                if pending_bytes >= 80 * 1024 * 1024 or len(pending) >= 64 or operation is operations[-1]:
                    api.preupload_lfs_files(repo_id=repo_id, repo_type="dataset", additions=pending, num_threads=5)
                    completed += len(pending)
                    completed_bytes += pending_bytes
                    progress = {"prepared_files": completed, "total_files": len(operations),
                                "prepared_bytes": completed_bytes, "total_bytes": manifest["bytes"]}
                    args.report.with_suffix(".progress.json").write_text(json.dumps(progress), encoding="utf-8")
                    print(json.dumps(progress), flush=True)
                    pending, pending_bytes = [], 0
            # Bound each commit request so large collections also work over
            # connections that time out while sending a single huge JSON body.
            for offset in range(0, len(operations), 64):
                commit = api.create_commit(repo_id=repo_id, repo_type="dataset", operations=operations[offset:offset + 64],
                                           commit_message="Publish complete PhysAg3D assets and current previews")
                print(json.dumps({"committed_files": min(offset + 64, len(operations)), "total_files": len(operations)}), flush=True)
            break
        except Exception as exc:
            # Only report the class: URLs or authentication data need not enter logs.
            detail = re.sub(r"https?://\S+|hf_[A-Za-z0-9]+", "[redacted]", str(exc))
            print(f"Upload attempt {attempt + 1} failed: {type(exc).__name__}: {detail[:800]}", flush=True)
            if attempt == 2:
                raise RuntimeError("Asset upload failed after three attempts.") from None
            time.sleep(5 * (attempt + 1))
    revision = api.repo_info(repo_id, repo_type="dataset").sha
    files = list(api.list_repo_tree(repo_id, repo_type="dataset", revision=revision, recursive=True))
    remote = {f.path: f for f in files if hasattr(f, "size")}
    hashes = {f["path"]: f["sha256"] for f in manifest["files"]}
    checked = 0
    for path in allowed:
        local = folder / path
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
              "commit_url": commit.commit_url if commit else f"https://huggingface.co/datasets/{repo_id}/commit/{revision}"}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2), flush=True)


if __name__ == "__main__":
    main()
