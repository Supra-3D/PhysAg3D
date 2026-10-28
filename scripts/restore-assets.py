"""Restore original source binaries from public HF storage, without Git LFS."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import time
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parent.parent


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main():
    storage = json.loads((ROOT / "scripts/asset-storage-files.json").read_text(encoding="utf-8"))

    def restore(item):
        destination = (ROOT / item["source"]).resolve()
        if not destination.is_relative_to(ROOT / "website"):
            raise ValueError(f"Invalid source destination: {item['source']}")
        if destination.is_file() and destination.stat().st_size == item["bytes"] and digest(destination) == item["sha256"]:
            return False
        destination.parent.mkdir(parents=True, exist_ok=True)
        for attempt in range(3):
            temporary = None
            try:
                with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as output:
                    temporary = Path(output.name)
                    with urlopen(storage["base_url"] + item["path"], timeout=120) as response:
                        shutil.copyfileobj(response, output, 1024 * 1024)
                if temporary.stat().st_size != item["bytes"] or digest(temporary) != item["sha256"]:
                    raise ValueError(f"Stored source checksum mismatch: {item['source']}")
                temporary.replace(destination)
                return True
            except Exception:
                if attempt == 2:
                    raise
                time.sleep(attempt + 1)
            finally:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)

    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(restore, storage["files"]))
    print(json.dumps({"verified": len(results), "downloaded": sum(results)}))


if __name__ == "__main__":
    main()
