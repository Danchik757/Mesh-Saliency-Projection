# Transfer Visualizations

## Script

- [make_transfer_visualizations.py](./make_transfer_visualizations.py)

## What the script does

This script builds visual comparisons for the two transfer methods we used on `Saliency3D_clear`.

Method 1:

- screen-space Gaussian around the gaze center

Method 2:

- cone-style projection on mesh inspired by `Visual Attention for Rendered 3D Shapes`

For each selected model the script:

1. loads raw fixation rows from `Saliency3D_clear`
2. selects the dominant `view_key` by total fixation duration
3. splits rows into `train` and `test` participants
4. builds a screen-space prediction map and a held-out screen-space GT map
5. reconstructs a single-view `3D -> 2D` projector from raw hit points
6. builds cone-style train and test maps on the mesh
7. computes metrics for both methods
8. renders comparison figures and writes a JSON summary

## Inputs

Expected dataset root:

- `--dataset-root /path/to/Saliency3D_clear`

You can also set:

- `SALIENCY3D_CLEAR_ROOT=/path/to/Saliency3D_clear`

The script uses:

- raw fixation rows from `3D_gaze_data/Code/Exp1/<model>/`
- mesh vertices from `obj/<model>.obj`
- view metadata from `doi-10.18419-darus-4101/3DSaliency/coordinate.json`

## Outputs

By default the script writes into:

- `results/saliency3d_clear/transfer_visualizations`

Produced files:

- one PNG per model with side-by-side comparison
- or one PNG per model with method-only layout
- `comparison_summary.json` with metrics and projection diagnostics

## Metrics shown on figures

Screen-space branch:

- `AUC`
- `NSS`
- `CC`

Cone-style branch:

- `AUC`
- `NSS`
- `CC`

Important:

- screen-space metrics are computed against held-out test fixations in image space
- cone-style metrics are computed against held-out test hits on the mesh

These numbers are useful for practical inspection, but they are not a perfect apples-to-apples benchmark across spaces.

## Main parameters

- `--models`
  - models to visualize, default: `hand bunny dragon`
- `--test-participants`
  - participants used as held-out test set, default: `zl zy`
- `--screen-sigma-px`
  - Gaussian sigma for screen-space blur, default: `26.3`
- `--cone-sigma-deg`
  - angular sigma for cone-style transfer, default: `1.0`
- `--radius-sigma-mult`
  - search radius multiplier for cone accumulation, default: `3.0`
- `--min-view-samples`
  - minimum required train samples in the selected view, default: `8`
- `--layout`
  - `combined` or `methods_only`

## Example commands

Run the default comparison:

```bash
python3 video_creation/transfer_visualizations/make_transfer_visualizations.py
```

Run on a subset of models with custom output:

```bash
python3 video_creation/transfer_visualizations/make_transfer_visualizations.py \
  --dataset-root /path/to/Saliency3D_clear \
  --models hand bunny \
  --layout methods_only \
  --output-dir results/visualizations/saliency3d_clear
```

Run with a different cone width:

```bash
python3 video_creation/transfer_visualizations/make_transfer_visualizations.py \
  --dataset-root /path/to/Saliency3D_clear \
  --cone-sigma-deg 0.75 \
  --screen-sigma-px 26.3
```

## How the two branches are built

### Screen-space Gaussian branch

The script deposits raw fixation durations into a `1920x1080` histogram and applies Gaussian smoothing:

```text
raw (x, y, duration) -> histogram -> gaussian_filter -> normalized density map
```

This branch is useful when the target representation is defined in image space.

### Cone-style mesh branch

The script fits an affine projector from raw `3D hit -> 2D screen` correspondences for the selected view, then accumulates Gaussian-weighted influence onto visible mesh vertices near each fixation:

```text
raw 3D hits + screen points -> fitted projector -> visible projected vertices -> Gaussian-weighted mesh map
```

This branch is useful when the target representation should live on the object surface.

## Interpreting `projection_rmse_px`

The JSON summary includes `projection_rmse_px`.

This is the reconstruction error of the fitted single-view projector:

```text
RMSE = sqrt(mean((x_pred - x_true)^2 + (y_pred - y_true)^2))
```

Lower is better.

It does not measure saliency quality directly. It measures how accurately the script reconstructed the `3D -> 2D` mapping needed for the cone-style transfer.

## Limitations

- the cone-style branch is a practical proxy inspired by `Visual Attention for Rendered 3D Shapes`, not the original author implementation
- the two methods are evaluated in different spaces, so absolute metric values should be compared carefully
- the selected `view_key` is the dominant view by duration, not a full multi-view reconstruction
