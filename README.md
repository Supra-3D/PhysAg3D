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

This commit imports the source and assets. The root `index.html` remains the existing Coming Soon page. `_config.yml` excludes `website/` from the current GitHub Pages build so that importing the application does not publish a partial website.

The full package is approximately 6.1 GB and its five native examples require the Python/MuJoCo API. The complete site therefore needs backend and asset hosting before deployment at `https://supra-3d.github.io/PhysAg3D/`. GitHub Pages serves static files, has a 1 GB published-site limit, and does not serve Git LFS assets directly.

- [GitHub Pages limits](https://docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits)
- [Git Large File Storage](https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-git-large-file-storage)
