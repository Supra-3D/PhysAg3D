# PhysAg3D website

The `homepage` branch contains the complete website package in [`website/`](website/), imported from `PhysAg3D_完整网页.zip`. It includes the page source, all 236 gallery assets, videos, the five native interactive examples, the viewer service, third-party licenses, and the bundled Windows Python environment.

The original files are preserved byte for byte. Large models, media, and runtime binaries are stored with Git LFS.

## Clone the complete package

Install [Git LFS](https://git-lfs.com/), then run:

```sh
git lfs install
git clone --branch homepage --single-branch https://github.com/Supra-3D/PhysAg3D.git
cd PhysAg3D
git lfs pull
```

GitHub's **Download ZIP** may contain LFS pointer files instead of the actual assets. Use the commands above for a complete working copy.

## Run on Windows

Open `website/START_PREVIEW.bat`, or run the following from PowerShell at the repository root:

```powershell
.\website\runtime\python.exe -B .\website\launch.py
```

The bundled environment is for Windows 10/11, 64-bit. The launcher normally opens `http://127.0.0.1:8765/` and selects an available port if necessary. Keep the local server running while using the viewer.

Verify the delivered files with:

```powershell
.\website\runtime\python.exe -B .\website\verify_package.py
```

See [`website/使用说明.md`](website/使用说明.md) for the original package documentation.

## Browser-only deployment

The public site is **https://supra-3d.github.io/PhysAg3D/**. Its Pages build includes the project overview, paper, films, research figures, evaluation tables, and a browser-based 3D Studio for all 236 gallery entries. The five featured examples and Gallery cards open the same Studio; hover previews and recorded videos remain available.

The online Studio runs in the visitor's browser with Three.js. Available controls depend on each asset: joint manipulation, embedded or recorded motion, surface deformation, or static orbit/zoom inspection. The five featured examples use browser-side kinematic controls; they do not run the offline MuJoCo force/contact solver. No Python service or GPU server is needed by this public deployment. The original `website/` package retains its native MuJoCo implementation for offline use.

After fetching Git LFS assets, run `python scripts/build-static.py` to regenerate the public root files from `website/` and the browser-specific overrides in `scripts/browser-viewer/`. The builder copies the browser viewer, catalogue, and model/motion JSON into the published tree, while model binaries and large media are resolved to the pinned asset host. It preserves the original offline source files. `_config.yml` excludes that offline package and the build scripts from GitHub Pages. The build report is written to Git's resolved metadata directory, including when building from a worktree.

Preview the generated site at its production URL prefix with `python scripts/preview-static.py`, then open `http://127.0.0.1:8875/PhysAg3D/`. This static preview does not start the Python physics API.

The published paper is maintained directly at `assets/PhysAg3D.pdf`. Replace that file to update the paper; the static build preserves it instead of copying the older PDF from the offline package.

The public method figure is `assets/method.svg`, extracted from Figure 2 of the paper with vector text and lines. Both the inline figure and the full-size dialog use this asset. To re-extract it, install PyMuPDF and run `python scripts/extract-method-figure.py`; recheck the crop if the paper layout changes. Normal static builds retain the committed SVG.

Small images, the paper, viewer code, and motion metadata are served directly by Pages. Models, videos, and large images currently use public GitHub media URLs pinned to the original package commit. These downloads use the repository's Git LFS bandwidth allowance. The `website/` directory remains the complete offline version with native physics and source assets.

Migration to the [Hugging Face dataset](https://huggingface.co/datasets/supra3d/physag3d-web-assets) is prepared but not yet published. `python scripts/prepare-hf-assets.py` creates one complete asset folder per case under `assets/generated-latest/img_NNN/`, plus an index and integrity manifest. `scripts/upload-hf-assets.py` uploads that prepared directory once a credential with dataset write access is available. Switch the viewer and build asset URLs only after upload verification, using the verified dataset revision. Upload credentials are used only by the local publisher; they are never included in the public viewer.

Validation covers all 236 models with `scripts/tests/browser-smoke.cjs --all`, native joint geometry with `scripts/tests/native-controls.mjs`, homepage controls and mobile layouts with `scripts/tests/page-interaction.cjs`, and actual mouse/touch manipulation with `scripts/tests/direct-drag.cjs`. The browser scripts use Playwright with Microsoft Edge. Use `--network` for actual asset-host requests; deterministic local checks use `scripts/tests/fixture-server.py` and the original model bytes.

- [GitHub Pages limits](https://docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits)
- [Git Large File Storage](https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-git-large-file-storage)
