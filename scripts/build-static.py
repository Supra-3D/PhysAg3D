"""Build the browser-only GitHub Pages site from the offline website package."""
from pathlib import Path
import hashlib
import json
import re
import shutil
import subprocess

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "website"
SOURCE_COMMIT = "24f4db5cb22791f4059dc74cfdc556778f7a4882"
PUBLIC_URL = "https://supra-3d.github.io/PhysAg3D/"
FILM_PATH = "assets/film-final-20261028.mp4"
STORAGE = json.loads((ROOT / "scripts/asset-storage.json").read_text(encoding="utf-8"))
MEDIA_BASE = STORAGE["base_url"]
LFS_SUFFIXES = {".glb", ".obj", ".mp4", ".png", ".webp", ".pdf", ".dll", ".pyd", ".exe", ".lib", ".zip", ".woff2"}
SMALL_ASSET_LIMIT = 512 * 1024


def stored_url(path):
    return MEDIA_BASE + STORAGE["paths"].get(path, path)


def curate(items, policy):
    def case_id(item):
        return item.get("caseId") or item.get("source", {}).get("case_id") or re.search(r"img_\d{3}$", item["id"]).group()
    by_case = {case_id(item): item for item in items}
    excluded, priority = set(policy["excluded"]), policy["priority"]
    assert len(by_case) == len(items)
    assert len(priority) == len(set(priority)) and not excluded.intersection(priority)
    assert set(priority).union(excluded).issubset(by_case), "Curated asset is missing from the source"
    return [by_case[key] for key in priority] + [item for item in items if case_id(item) not in excluded.union(priority)]


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise ValueError(f"Expected one source fragment: {old[:100]!r}")
    return text.replace(old, new, 1)


def write(path, text):
    target = ROOT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8", newline="\n")


def copy_public(source, relative):
    """Copy a real source asset, never publish an unresolved Git LFS pointer."""
    with source.open("rb") as stream:
        if stream.read(43).startswith(b"version https://git-lfs.github.com/spec/v1"):
            raise ValueError(f"Restore the source asset with scripts/restore-assets.py: {source}")
    target = ROOT / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)


def build_viewer():
    source = SOURCE / "viewer/web"
    overrides = ROOT / "scripts/browser-viewer"
    for name in ("index.html", "gallery-app.js", "gallery-adapter.js"):
        if not (overrides / name).is_file():
            raise FileNotFoundError(f"Missing browser viewer source: {overrides / name}")
    published = set()
    for path in sorted(source.rglob("*")):
        if not path.is_file() or path.relative_to(source).as_posix() in {"app.js", "source-materials.js"}:
            continue
        relative = "viewer/" + path.relative_to(source).as_posix()
        copy_public(path, relative)
        published.add(relative)
    for path in sorted(overrides.rglob("*")):
        if path.is_file():
            relative = "viewer/" + path.relative_to(overrides).as_posix()
            copy_public(path, relative)
            published.add(relative)
    return published


def main():
    hero_media = json.loads((ROOT / "scripts/hero-media.json").read_text(encoding="utf-8"))
    raw = (SOURCE / "gallery-data.js").read_text(encoding="utf-8")
    gallery = json.loads(raw[raw.index("["):].strip().rstrip(";"))
    assert len(gallery) == 236 and len({item["id"] for item in gallery}) == 236
    policy = json.loads((ROOT / "scripts/gallery-curation.json").read_text(encoding="utf-8"))
    gallery = curate(gallery, policy)
    # Featured demos still use the shared records; hide these cases only in the Gallery.
    gallery_only_excluded = set(policy.get("gallery_only_excluded", []))
    assert gallery_only_excluded.issubset({item["caseId"] for item in gallery})
    visible_gallery = [item for item in gallery if item["caseId"] not in gallery_only_excluded]
    catalog = json.loads((SOURCE / "assets/gallery-models/catalog.json").read_text(encoding="utf-8"))
    catalog["assets"] = curate(catalog["assets"], policy)
    catalog["expected_assets"] = len(catalog["assets"])
    assert [item["id"] for item in gallery] == [item["id"] for item in catalog["assets"]]
    # Reuse the delivered feature films for the same five native models. Their
    # Gallery cards previously used the separate, smaller uniform previews.
    hero_source = (SOURCE / "hero.js").read_text(encoding="utf-8")
    hero_match = re.search(r"const assets=(\[.*?\])\.map", hero_source, re.DOTALL)
    if not hero_match:
        raise ValueError("Cannot read the delivered feature-film mapping")
    feature_films = {item["key"]: item for item in json.loads(hero_match[1])}
    for item, model in zip(gallery, catalog["assets"]):
        if model.get("native_asset_id"):
            feature = feature_films[model["native_source_identity"]["overview_key"]]
            item["video"] = f'assets/hero/{feature["mediaKey"]}.mp4'
            item["poster"] = item["previewPoster"] = f'assets/hero/{feature["mediaKey"]}-poster.webp'
            item["description"], item["note"] = feature["description"], feature["note"]
            item["defaultView"], item["interaction"], item["previewFit"] = "orbit", None, "contain"
            item["videoLabel"] = "Mechanism close-ups"
            model["video_url"] = "/" + hero_media["clips"][feature["key"]]["output"]
            model["poster_url"] = "/" + item["poster"]
        else:
            # The other cases have one delivered final preview each. Keep its
            # bytes and ensure that its case matches the model it opens.
            case = model["source"]["case_id"]
            assert item["caseId"] == case
            assert item["video"] == f"assets/uniform-videos/{case}.mp4"
            assert item["poster"] == f"assets/uniform-videos/{case}.webp"
    assets = {p for folder in ["hero", "uniform-videos"]
              for p in (SOURCE / "assets" / folder).rglob("*") if p.is_file()}
    assets.update(p for p in (SOURCE / "assets").iterdir() if p.is_file())
    assets.update(SOURCE / value for item in gallery for value in item.values()
                  if isinstance(value, str) and value.startswith("assets/"))
    # Include all explicit hero inputs even if the gallery uses another thumbnail.
    assets.update(SOURCE / match for match in re.findall(r"['\"](assets/[^'\"`]+)['\"]", hero_source))
    # Model and motion metadata are served with the page. Large binary assets
    # remain on the pinned media host and are resolved by the browser viewer.
    assets.add(SOURCE / "assets/gallery-models/catalog.json")
    assets.update((SOURCE / "assets/generated-latest").rglob("*.json"))
    remote = {}
    local = []
    for source in sorted(assets):
        if not source.is_file() or not source.resolve().is_relative_to(SOURCE.resolve()):
            raise ValueError(f"Missing or unsafe media: {source}")
        relative = source.relative_to(SOURCE).as_posix()
        if source.suffix in LFS_SUFFIXES and source.suffix != ".pdf" and (source.suffix == ".mp4" or source.stat().st_size > SMALL_ASSET_LIMIT):
            remote[relative] = stored_url(relative)
        else:
            target = ROOT / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            # The published paper is maintained separately from the offline archive.
            if relative == "assets/PhysAg3D.pdf":
                if not target.is_file():
                    raise FileNotFoundError("Restore the published assets/PhysAg3D.pdf before building")
            else:
                copy_public(source, relative)
            local.append(relative)

    write("assets/gallery-models/catalog.json", json.dumps(catalog, ensure_ascii=False, indent=2) + "\n")

    method_figure = ROOT / "assets/method.svg"
    if not method_figure.is_file():
        raise FileNotFoundError("Restore assets/method.svg or run scripts/extract-method-figure.py")
    local.append("assets/method.svg")

    # Keep the supplied final film separate from the original offline package.
    if not (ROOT / FILM_PATH).is_file():
        raise FileNotFoundError(f"Restore the published Film video: {FILM_PATH}")
    remote["assets/film.mp4"] = FILM_PATH
    local.append(FILM_PATH)

    # These unchanged short recordings are ordinary Pages files and also on HF.
    for clip in hero_media["clips"].values():
        if not (ROOT / clip["output"]).is_file():
            raise FileNotFoundError("Run scripts/build-hero-videos.py before the static build")
        remote["assets/hero/" + clip["original_key"] + ".mp4"] = clip["output"]
        local.append(clip["output"])
    overview = hero_media["overview"]
    if not (ROOT / overview["output"]).is_file():
        raise FileNotFoundError("The short overview video is missing")
    remote[overview["original"]] = overview["output"]
    remote[overview["original"].replace(".mp4", "-poster.webp")] = remote.get(overview["poster"], overview["poster"])
    local.append(overview["output"])

    array_start = hero_source.index("[", hero_source.index("const assets="))
    definitions, used = json.JSONDecoder().raw_decode(hero_source[array_start:])
    for definition in definitions:
        definition["beats"] = hero_media["clips"][definition["key"]]["beats"]
        if definition["key"] == "camera":
            definition["description"] = "Quick lens and display demonstrations, followed by parallel close-ups of both dials and the shutter."
            definition["note"] += " The final controls are presented as parallel recorded close-ups."
    hero_source = hero_source[:array_start] + json.dumps(definitions, ensure_ascii=False, indent=2) + hero_source[array_start + used:]
    chapters = [{key: value for key, value in chapter.items() if key != "key"} for chapter in overview["chapters"]]
    hero_source, replacements = re.subn(r"  const chapters=\[.*?\n  \];", "  const chapters=" + json.dumps(chapters, ensure_ascii=False, indent=2) + ";", hero_source, count=1, flags=re.S)
    assert replacements == 1
    hero_source = hero_source.replace("28-second overview", f"{overview['duration']}-second overview")

    def media(path):
        return remote.get(path, path)

    def literals(text):
        return re.sub(r"(?P<q>['\"])(?P<p>assets/[^'\"`\s<>]+)(?P=q)",
                      lambda m: m["q"] + media(m["p"]) + m["q"], text)

    write("static-assets.js", "/* Generated by scripts/build-static.py. */\n(() => {\n  const media = "
          + json.dumps(remote, ensure_ascii=False, separators=(",", ":"))
          + ";\n  window.PHYSAG3D_ASSET_URL = path => media[path] || path;\n})();\n")
    for item in gallery:
        for key, value in item.items():
            if isinstance(value, str) and value.startswith("assets/"):
                item[key] = media(value)
    write("gallery-data.js", "window.PHYSAG3D_GALLERY = " + json.dumps(gallery, ensure_ascii=False, indent=2) + ";\n")

    html = literals((SOURCE / "index.html").read_text(encoding="utf-8"))
    html = html.replace("Guangdong Laboratory of AI and Digital Economy (SZ)",
                        "Guangdong Laboratory of Artificial Intelligence and Digital Economy (SZ)")
    html = replace_once(html, '<strong>236 assets.</strong>', f'<strong>{len(visible_gallery)} assets.</strong>')
    html = replace_once(html, 'New additions only <span>(153)</span>',
                        f'New additions only <span>({sum(bool(item.get("newInGallery")) for item in visible_gallery)})</span>')
    html = replace_once(html, 'src="assets/method.webp"', 'src="assets/method.svg"')
    html = replace_once(html, '<script src="music.js" defer>', '<script src="static-assets.js" defer></script>\n  <script src="music.js" defer>')
    html = replace_once(html, '<small>28 seconds</small>', f'<small>{overview["duration"]} seconds</small>')
    html = html.replace("https://physag3d.pkujunyiyao.chatgpt.site/", PUBLIC_URL)
    html = replace_once(html, '<meta property="og:type" content="website">',
                        '<meta property="og:type" content="website">\n  <link rel="canonical" href="' + PUBLIC_URL + '">')
    # Refresh browser caches whenever either interaction stylesheet changes.
    for stylesheet in ["styles.css", "hero.css"]:
        version = hashlib.sha256((SOURCE / stylesheet).read_bytes()).hexdigest()[:12]
        html, count = re.subn(r'href="' + re.escape(stylesheet) + r'(?:\?[^\"]*)?"',
                              f'href="{stylesheet}?v={version}"', html)
        assert count == 1, f"Missing stylesheet reference: {stylesheet}"
    write("index.html", html)

    app = literals((SOURCE / "app.js").read_text(encoding="utf-8"))
    app = replace_once(app, "method:{src:'method.webp'", "method:{src:'method.svg'")
    app = app.replace("'assets/'+f.src", "window.PHYSAG3D_ASSET_URL('assets/'+f.src)")
    write("app.js", app)
    hero = literals(hero_source)
    for suffix in [".mp4", "-poster.webp"]:
        template = "`assets/hero/${x.mediaKey}" + suffix + "`"
        if template not in hero:
            raise ValueError("Hero media template changed")
        hero = hero.replace(template, "window.PHYSAG3D_ASSET_URL(" + template + ")")
    write("hero.js", hero)
    gallery_js = (SOURCE / "gallery.js").read_text(encoding="utf-8")
    if gallery_only_excluded:
        gallery_js = replace_once(gallery_js, "const items = window.PHYSAG3D_GALLERY || [];",
                                 "const items = (window.PHYSAG3D_GALLERY || []).filter(item => !"
                                 + json.dumps(sorted(gallery_only_excluded)) + ".includes(item.caseId));")
    gallery_js = replace_once(gallery_js, "detail.textContent=(item.caseId?item.caseId+' · ':'')+categoryText(item);", "detail.textContent=categoryText(item);")
    gallery_js = replace_once(gallery_js, "video.tabIndex=-1;",
                             "video.tabIndex=-1;\n    if(item.previewFit==='contain'){video.style.objectFit='contain';media.style.background='#172830';}")
    write("gallery.js", gallery_js)
    write("interactive.js", (ROOT / "scripts/static-interactive.js").read_text(encoding="utf-8"))
    for name in ["styles.css", "hero.css", "music.css", "explore.css", "music.js"]:
        write(name, (SOURCE / name).read_text(encoding="utf-8"))
    viewer_files = build_viewer()

    # Fail the build if published HTML refers to a missing local file.
    for reference in re.findall(r'(?:src|href|poster)="([^"]+)"', html):
        if reference.startswith(("http:", "https:", "#", "mailto:", "data:")):
            continue
        if not (ROOT / reference.split("?", 1)[0]).is_file():
            raise ValueError(f"Broken published reference: {reference}")
    published_bytes = sum((ROOT / path).stat().st_size for path in set(local) | viewer_files)
    assert published_bytes < 900 * 1024 * 1024
    report = {"gallery_assets": len(visible_gallery), "local_media_files": len(local),
              "local_media_bytes": published_bytes, "external_media_files": len(remote),
              "viewer_files": len(viewer_files), "source_commit": SOURCE_COMMIT,
              "asset_host": "huggingface",
              "mode": "browser-interactive"}
    report_path = Path(subprocess.check_output(
        ["git", "rev-parse", "--git-path", "static-build-report.json"],
        cwd=ROOT, text=True).strip())
    if not report_path.is_absolute():
        report_path = ROOT / report_path
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
