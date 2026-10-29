"""Package each complete, revision-pinned HF case folder as a verified ZIP."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path, PurePosixPath
import argparse
import hashlib
import json
import re
import zipfile


def build_case(case_id, records, source, output):
    target = output / f"{case_id}.zip"
    temporary = target.with_suffix('.zip.tmp')
    prefix = f"assets/generated-latest/{case_id}/"
    expected = []
    raw_bytes = 0
    with zipfile.ZipFile(temporary, 'w', allowZip64=True) as archive:
        for row in sorted(records, key=lambda item: item['path']):
            path = row['path']
            assert path.startswith(prefix)
            relative = PurePosixPath(path[len('assets/generated-latest/'):])
            if relative.is_absolute() or '..' in relative.parts:
                raise ValueError(f"Unsafe case path: {path}")
            local = source / path
            if local.is_symlink() or not local.resolve().is_relative_to(source.resolve()):
                raise ValueError(f"Unsafe source file: {path}")
            if local.stat().st_size != row['size']:
                raise ValueError(f"Source size differs from HF: {path}")
            sha256 = hashlib.sha256()
            blob = hashlib.sha1(f"blob {row['size']}\0".encode())
            info = zipfile.ZipInfo(relative.as_posix(), date_time=(1980, 1, 1, 0, 0, 0))
            # Preserve byte runs for HF Xet deduplication against the source files.
            # ZIP_STORED is standard ZIP and opens without additional software.
            info.compress_type = zipfile.ZIP_STORED
            info.external_attr = 0o100644 << 16
            with local.open('rb') as src, archive.open(info, 'w', force_zip64=True) as dst:
                while chunk := src.read(1024 * 1024):
                    sha256.update(chunk)
                    blob.update(chunk)
                    dst.write(chunk)
            if (row['sha256'] and sha256.hexdigest() != row['sha256']) or (not row['sha256'] and blob.hexdigest() != row['blob']):
                raise ValueError(f"Source checksum differs from HF: {path}")
            expected.append(relative.as_posix())
            raw_bytes += row['size']
    with zipfile.ZipFile(temporary) as archive:
        assert archive.namelist() == expected
        if bad := archive.testzip():
            raise ValueError(f"ZIP checksum failed: {case_id}/{bad}")
        # The case identity is checked independently of its directory name.
        info = json.loads(archive.read(f'{case_id}/ASSET_INFO.json'))
        assert info['case_id'] == case_id
        assert info['source_gallery']['caseId'] == case_id
        gallery_id = info['source_gallery']['id']
        assert gallery_id.endswith(case_id)
    temporary.replace(target)
    with target.open('rb') as stream:
        checksum = hashlib.file_digest(stream, 'sha256').hexdigest()
    return {'caseId': case_id, 'galleryId': gallery_id, 'name': info['name'], 'file': target.name,
            'bytes': target.stat().st_size, 'sha256': checksum, 'files': len(expected), 'sourceBytes': raw_bytes}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--inventory', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    inventory = json.loads(args.inventory.read_text(encoding='utf-8'))
    grouped = {}
    for row in inventory['files']:
        parts = PurePosixPath(row['path']).parts
        assert parts[:2] == ('assets', 'generated-latest') and re.fullmatch(r'img_\d{3}', parts[2])
        grouped.setdefault(parts[2], []).append(row)
    args.output.mkdir(parents=True, exist_ok=True)
    results = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(build_case, case, rows, args.source, args.output) for case, rows in grouped.items()]
        for future in as_completed(futures):
            results.append(future.result())
            if len(results) % 20 == 0 or len(results) == len(grouped):
                print(json.dumps({'packed': len(results), 'total': len(grouped), 'zipBytes': sum(x['bytes'] for x in results)}), flush=True)
    manifest = {'schema': 1, 'sourceRepository': 'supra3d/physag3d-web-assets',
                'sourceRevision': inventory['revision'], 'assets': sorted(results, key=lambda item: item['caseId'])}
    (args.output / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('All case files verified against the pinned HF revision; every ZIP passed CRC and identity checks.', flush=True)


if __name__ == '__main__':
    main()
