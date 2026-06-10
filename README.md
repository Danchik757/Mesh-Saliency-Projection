# Mesh-Saliency-Projection

Repository for the main codebase of the mesh saliency projection project.
Implements multiple methods for transferring screen-space gaze data onto 3D mesh vertices/faces
and evaluating the result against ground-truth saliency maps.

Multi-agent work must start from [coordination/README.md](./coordination/README.md).
It defines the current data contract, server paths, release audit, ownership
boundaries, and review gates.

## Current focus

- `v2.0-data-rc2` benchmark pipeline for 3DVA, MeshMamba, and SAL3D;
- processed participant fixation JSON by default (`cropped_reset_offset_2000`);
- two primary baseline methods: `screen_space_gaussian` and `cone_gaussian_on_mesh`;
- SAL3D fixed per-face GT for current OBJ meshes;
- shared metric suite: CC, SIM, KLD, MSE, MAE, Spearman, AUC-Judd proxy, NSS proxy.

## Datasets validated

Current validation status is for the rc2 timing/placement contract. The numeric
IoU is reliable for 3DVA and MeshMamba. For SAL3D the visual overlay is accepted,
but automatic video-mask IoU is conservative because the source videos contain
white objects on a light background.

| Dataset | Smoke models | Alignment status | Metric smoke |
|---------|--------------|------------------|--------------|
| 3DVA | `bunny`, `A380` | accepted | 4/4 ok |
| MeshMamba non_texture | `Starfruit_L3`, `Pear_L3` | accepted, IoU ~0.995 | 4/4 ok |
| MeshMamba rgb_texture | `Starfruit_L3`, `Pear_L3` | accepted, IoU ~0.997 | 4/4 ok |
| SAL3D fixed face GT | `bunny`, `MaxPlanck`, `meca`, `sofa` | visual overlay accepted | 8/8 ok |

Alignment validation details: [test/README.md](./test/README.md)

## Repository structure

| Folder | Contents |
|--------|----------|
| [metrics/](./metrics/README.md) | Shared metric implementations (CC, KL, NSS, AUC, Similarity) |
| [reprojection_methods/](./reprojection_methods/README.md) | All projection methods (cone, screen-space, geodesic) |
| [test/](./test/README.md) | Batch launchers, tests, and legacy alignment/debug tooling |
| [test/launch/](./test/launch/README.md) | Batch and pilot eval launchers for all datasets |
| [test/manifests/](./test/manifests/README.md) | Per-model alignment check manifests (validated IoU) |
| [test/tools/](./test/tools/README.md) | Diagnostic and preview utilities (no eval, debug only) |
| [datasets/](./datasets/README.md) | Dataset reference: contents, sizes, formats, validation status |
| [scripts/](./scripts/README.md) | Dataset download/upload scripts and method comparison tools |
| [docs/](./docs/EVAL_RUNBOOK.md) | Eval runbook and project architecture notes |
| [validation/](./validation/alignment_preview/check_alignment.py) | Current alignment-preview tooling used before full metric runs |
| [visualization/](./visualization/heatmap_six_view/render_six_view_heatmaps.py) | Qualitative heatmap renderers and collages |
| [video_creation/](./video_creation/README.md) | Scripts for generating render videos |
| [requirements/](./requirements/README.md) | Per-environment dependency lists |
| [coordination/](./coordination/README.md) | Current multi-agent instructions, data/release contract, and review gates |
| [coordination/PIPELINE_3DVA.md](./coordination/PIPELINE_3DVA.md) | Current 3DVA benchmark pipeline |
| [md/archive/PIPELINE.md](./md/archive/PIPELINE.md) | Historical pipeline design options |
| [md/archive/DATA_PATHS.md](./md/archive/DATA_PATHS.md) | Historical local/server path reference |

## Production vs auxiliary code

The production benchmark path is intentionally narrow:

- `utils/`
- `metrics/`
- `reprojection_methods/`
- `test/launch/`
- `scripts/`
- `configs/`
- `jsons/`
- `participant_data/README.md` and release metadata only

Diagnostic/rendering helpers are kept in the same repository for now because
they share the projection contract and are still used to validate metric runs.
Candidates for a future helper/submodule split are documented in
[coordination/RESTRUCTURING_REVIEW_2026-06-10.md](./coordination/RESTRUCTURING_REVIEW_2026-06-10.md).
Do not move those paths until compatibility wrappers and tests are added.

## Getting the datasets

Datasets are distributed as ZIP archives attached to a GitHub release. The
historical `v1.0-data` release is not approved for the next benchmark generation;
read [the current release audit](./coordination/RELEASE_AUDIT_2026-06-09.md)
first.
On a new machine:

```bash
# 1. Download, validate, and extract the approved v2 candidate into an empty path
TAG=v2.0-data-rc2 bash scripts/download_release_candidate.sh /path/to/v2.0-data-rc2

# 2. Configure env vars
cp test/env/new_machine.env.sh.template test/env/local_paths.sh
# edit RELEASE_DATA_ROOT in local_paths.sh
source test/env/local_paths.sh
```

To create a new release from local data (maintainer only):
```bash
python3 scripts/validate_data_contract.py --allow-known-blockers
python3 scripts/build_release_candidate.py --include-videos --include-sal3d-smooth-gaze
python3 scripts/validate_release_candidate.py release_assets/v2.0-data-rc2
bash scripts/upload_release_candidate.sh
```

The historical `download_datasets.sh`, `package_datasets.sh`, and
`upload_release.sh` scripts are retained only to reproduce `v1.0-data`.

---

## Visual verification of prediction vs GT

Before relying on metrics, run the visual sanity checks to confirm the method
projects gaze to the correct mesh vertices/faces and that the predicted map is
spatially plausible relative to GT.

Canonical folder:

```text
gt_visualizations/
```

Available viewers:
- `preview_meshmamba_screenspace_alignment.py`
- `preview_meshmamba_cone_alignment.py`
- `preview_sal3d_screenspace_alignment.py`

Example for MeshMamba `screen_space_gaussian`:

```bash
# On vg-intellect:
source configs/server_vg_intellect.env
$REPROJECT_PYTHON gt_visualizations/preview_meshmamba_screenspace_alignment.py \
    --model Rubber_Duck_v1_L3 \
    --texture-type non_texture \
    --output-dir /tmp/preview_v2
```

Output: three-panel PNG images per frame.

| Panel | What it shows |
|-------|--------------|
| **Left** — Gaze density | Where participants looked on screen (input to the method) |
| **Middle** — Predicted saliency | **Our result**: per-face salience assigned by screen_space |
| **Right** — GT saliency | Ground-truth per-face CSV from the dataset (reference) |

Check that hot spots in **Middle** spatially match hot spots in **Right**.
Scripts:
- [`gt_visualizations/preview_meshmamba_screenspace_alignment.py`](./gt_visualizations/preview_meshmamba_screenspace_alignment.py)
- [`gt_visualizations/preview_meshmamba_cone_alignment.py`](./gt_visualizations/preview_meshmamba_cone_alignment.py)
- [`gt_visualizations/preview_sal3d_screenspace_alignment.py`](./gt_visualizations/preview_sal3d_screenspace_alignment.py)

Detailed usage:
- [`gt_visualizations/README.md`](./gt_visualizations/README.md)

## Quick start

```bash
# Set up local environment variables
source test/env/local_paths.example.sh

# Run a reference batch with processed fixation JSON.
# Use --no-resume when changing data, timing, GT, or method parameters.
python3 test/launch/run_meshmamba_reference_batch.py \
    --methods screen_space cone \
    --texture-types non_texture \
    --models Starfruit_L3 Pear_L3 \
    --fixation-root "$REPROJECT_PROCESSED_FIXATIONS_ROOT" \
    --batch-output-dir results/quick_meshmamba_smoke \
    --no-resume
```

## Data paths

Current local and server paths are documented in
[coordination/PROJECT_STATE_2026-06-10.md](./coordination/PROJECT_STATE_2026-06-10.md)
and the server env files under [configs/](./configs/README.md). The older
[md/archive/DATA_PATHS.md](./md/archive/DATA_PATHS.md) is historical only.

Raw datasets stay **outside** the repository. Generated outputs go into `results/`.

Reference:
- [Google Sheets dataset table](https://docs.google.com/spreadsheets/d/1UpTHzfqAma46_czqMvlA_15AVIm5T2Em6d_BmskiCkQ/edit?gid=881515507#gid=881515507)
