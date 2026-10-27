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

## Deployment status

The static showcase is published at **https://supra-3d.github.io/PhysAg3D/**. It includes the project overview, paper, films, all 236 gallery entries, recorded demonstrations, research figures, and evaluation tables. Live physics interaction is deferred until a Python/MuJoCo backend is connected; demo buttons currently open the corresponding recorded clips.

Run `python scripts/build-static.py` to regenerate the public root files from `website/`. The original offline package remains unchanged. `_config.yml` excludes that package and the build scripts from GitHub Pages.

Small images and the paper are served directly by Pages. Videos and large images use public GitHub media URLs pinned to the imported package commit. Those downloads use the repository owner's Git LFS bandwidth allowance. The `website/` directory remains the complete offline version with native physics and source assets.

- [GitHub Pages limits](https://docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits)
- [Git Large File Storage](https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-git-large-file-storage)
