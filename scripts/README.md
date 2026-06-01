# scripts/

Utility scripts for dataset management and method comparison.

## Dataset lifecycle

| Script | When to run | What it does |
|--------|-------------|--------------|
| `package_datasets.sh` | Once on the data machine | Zips all local datasets into `release_assets/*.zip` |
| `upload_release.sh` | Once after packaging | Creates GitHub Release `v1.0-data` and uploads all ZIPs |
| `download_datasets.sh` | On every new machine | Downloads ZIPs from the release and extracts them |

### package_datasets.sh

```bash
bash scripts/package_datasets.sh                  # core data only (~476 MB compressed)
bash scripts/package_datasets.sh --with-videos    # +256 MB rendered MP4
bash scripts/package_datasets.sh --with-smooth-gaze  # +~2 GB SAL3D auxiliary
```

Reads from hardcoded local paths in the script body. Edit the `# Source paths` section
if data lives elsewhere. Output goes to `release_assets/` (gitignored).

### upload_release.sh

```bash
bash scripts/upload_release.sh              # uses tag v1.0-data, repo from git remote
bash scripts/upload_release.sh --tag v2.0  # custom tag
```

Requires `gh` CLI authenticated (`gh auth login`). Creates the release if it does
not exist; re-uploads (clobbers) if assets already exist.

### download_datasets.sh

```bash
bash scripts/download_datasets.sh --data-root /path/to/data
bash scripts/download_datasets.sh --data-root /path/to/data --with-videos
bash scripts/download_datasets.sh --data-root /path/to/data --only "3dva*"
bash scripts/download_datasets.sh --list    # print available release assets
```

After downloading, configure env vars:
```bash
cp test/env/new_machine.env.sh.template test/env/local_paths.sh
# Set DATA_ROOT= in local_paths.sh
source test/env/local_paths.sh
```

## Method comparison

| Script | What it does |
|--------|-------------|
| `compare_v1_v2_screenspace.py` | Runs screen_space v1 and v2 on one model, prints side-by-side metrics |

```bash
# On vg-intellect:
source configs/server_vg_intellect.env
$REPROJECT_PYTHON scripts/compare_v1_v2_screenspace.py \
    --model Rubber_Duck_v1_L3 --texture-type non_texture
```
