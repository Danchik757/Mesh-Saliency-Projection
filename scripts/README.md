# scripts/

Utility scripts for dataset management and method comparison.

The current GitHub Release `v1.0-data` is a historical release and is not
approved for the next benchmark generation. Read
[`coordination/RELEASE_AUDIT_2026-06-09.md`](../coordination/RELEASE_AUDIT_2026-06-09.md)
before using the lifecycle scripts below. Release-contract corrections are owned
by the macOS Claude workstream.

## Dataset lifecycle

| Script | When to run | What it does |
|--------|-------------|--------------|
| `validate_data_contract.py` | Before packaging or benchmark migration | Separately validates canonical placement JSON, original participant CSV, and processed fixation JSON |
| `build_release_candidate.py` | Build the next versioned benchmark input | Creates explicit v2 archives, manifest, and SHA-256 checksums |
| `validate_release_candidate.py` | Before upload and after download | Validates manifest, checksums, ZIP CRC, and participant data separation |
| `upload_release_candidate.sh` | After coordinator approval | Creates a new prerelease and uploads a validated candidate |
| `download_release_candidate.sh` | On each agent/server clone | Downloads, validates, and extracts a candidate into an isolated data root |
| `package_datasets.sh` | Once on the data machine | Zips all local datasets into `release_assets/*.zip` |
| `upload_release.sh` | Once after packaging | Creates GitHub Release `v1.0-data` and uploads all ZIPs |
| `download_datasets.sh` | On every new machine | Downloads ZIPs from the release and extracts them |

The last three scripts are retained for the historical `v1.0-data` workflow.
New work must use the release-candidate scripts.

### v2 release candidate

```bash
python3 scripts/validate_data_contract.py --allow-known-blockers
python3 scripts/build_release_candidate.py \
    --include-videos \
    --include-sal3d-smooth-gaze
python3 scripts/validate_release_candidate.py release_assets/v2.0-data-rc1
```

Participant archives are intentionally separate:

```text
participant_gaze_csv_original.zip
participant_fixations_processed_offset_2000.zip
```

There is no automatic fallback between them.

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
