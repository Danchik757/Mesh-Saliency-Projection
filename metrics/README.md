# Metrics

This folder contains the project-local implementation of saliency evaluation metrics.

The goal is to keep all comparison logic between a predicted saliency map and ground-truth (`GT`) in one place, with explicit conventions for:

- screen-space evaluation on `H x W` maps;
- mesh-space evaluation on `per-vertex` or `per-face` vectors;
- dense GT maps;
- sparse positive supervision such as fixation pixels or selected mesh vertices;
- ranking-style evaluation restricted to the visible part of a mesh.

## Files

- [common.py](./common.py)
- [screen_space.py](./screen_space.py)
- [mesh_space.py](./mesh_space.py)
- [__init__.py](./__init__.py)

## What is implemented

### Dense prediction vs dense GT

These metrics are implemented for direct `pred` vs `GT` comparison:

- `CC`
  - Pearson correlation coefficient.
- `Spearman`
  - rank correlation, useful when only monotonic agreement matters.
- `SIM`
  - histogram intersection after min-max normalization and distribution normalization.
- `KLD`
  - Kullback-Leibler divergence from `GT` to `pred`.
- `MSE`
  - mean squared error.

These are the main metrics you need when the target is already a dense saliency value on every pixel, face, or vertex.

### Prediction vs sparse positives

These metrics are implemented when GT is available only as sparse positives:

- `NSS`
  - normalized scanpath saliency over fixation pixels or positive vertices.
- `AUC`
  - ROC AUC using positives vs negatives.

This mode is useful for:

- screen-space fixation masks;
- raw hit vertices after gaze re-projection;
- top-k visible vertices promoted to positives for ranking checks.

## Module responsibilities

### `common.py`

This file contains the reusable core implementation:

- shape validation;
- finite-value checks;
- flattening with an optional support mask;
- average-rank computation for tie-aware `Spearman` and `AUC`;
- scalar metric implementations;
- a shared `dense_saliency_metrics(...)` summary function.

Use this file when you want one metric definition to stay consistent across both screen-space and mesh-space evaluation.

### `screen_space.py`

Use this module when:

- `pred` is an image-like saliency map;
- `GT` is a dense `H x W` map;
- fixations are available as `(x, y)` image coordinates or as a binary fixation mask.

Available functions:

- `cc_from_maps(pred, gt)`
- `sim_from_maps(pred, gt)`
- `kld_from_maps(pred, gt)`
- `mse_from_maps(pred, gt)`
- `binary_mask_from_fixation_points(shape, fixation_points)`
- `nss_from_fixation_points(pred, fixation_points)`
- `auc_from_binary_mask(pred, mask)`
- `screen_map_metrics(pred, gt, fixation_points=None, fixation_mask=None)`

### `mesh_space.py`

Use this module when:

- `pred` is a `per-face` or `per-vertex` saliency vector;
- `GT` is a dense vector on the same support;
- you optionally want to restrict evaluation to a visible subset of vertices/faces;
- you sometimes need sparse-positive metrics from reprojected gaze hits.

Available functions:

- `map_metrics(pred, target, visible_mask=None, include_auc_visible_top20=False, kl_key="KL_gt_to_pred")`
- `auc_visible_top20(pred, target, visible_mask)`
- `auc_from_positive_indices(pred, positive_indices)`
- `nss_from_positive_indices(pred, positive_indices)`
- `normalize_distribution(values, mask=None)`

## Metric definitions

### `CC`

Pearson correlation on aligned supports:

```text
CC(pred, gt) =
sum((pred - mean(pred)) * (gt - mean(gt))) /
sqrt(sum((pred - mean(pred))^2) * sum((gt - mean(gt))^2))
```

Interpretation:

- `1.0` means perfect linear agreement;
- `0.0` means no linear correlation;
- `-1.0` means perfect inverse linear relation.

If either input is constant, the implementation returns `NaN`, because correlation is undefined in that case.

### `Spearman`

`Spearman` is Pearson correlation computed on ranks instead of raw values.

Use it when:

- the order of salient regions matters more than exact magnitudes;
- you want robustness to monotonic rescaling.

The implementation uses average ranks for ties.

### `SIM`

`SIM` is the histogram-intersection style score commonly used in saliency evaluation.

Implementation convention in this repository:

1. min-max normalize `pred` and `gt` independently;
2. convert each result into a non-negative distribution summing to `1`;
3. compute `sum(min(pred_norm, gt_norm))`.

Interpretation:

- `1.0` means identical normalized distributions;
- `0.0` means no overlap.

### `KLD`

This repository implements `KLD(GT || pred)`:

```text
KLD = sum( GT_norm * log(GT_norm / pred_norm) )
```

Conventions:

- both inputs are converted into non-negative normalized distributions;
- if values are negative, the minimum is shifted to `0` before normalization;
- if a map becomes degenerate after normalization, a uniform distribution is used.

Interpretation:

- `0.0` means identical distributions;
- larger values mean stronger disagreement.

Important:

- `KLD` is directional;
- `KLD(GT || pred)` is not the same as `KLD(pred || GT)`.

### `MSE`

Plain elementwise mean squared error on aligned supports:

```text
MSE = mean((pred - gt)^2)
```

Interpretation:

- `0.0` is perfect agreement;
- larger values mean larger absolute deviation.

### `NSS`

`NSS` first z-normalizes the prediction map:

```text
z = (pred - mean(pred)) / std(pred)
```

and then averages the z-scores on positive locations only.

Screen-space positives:

- fixation pixels.

Mesh-space positives:

- positive vertex indices after re-projection.

Interpretation:

- positive value means predicted saliency is above average on positive points;
- around `0` means positives are not better than random under z-score normalization;
- negative value means positives are assigned below-average saliency.

### `AUC`

`AUC` is implemented as ROC AUC using the rank-sum / Mann-Whitney view:

- positives: fixation pixels or positive vertices;
- negatives: everything else in the evaluation support.

Interpretation:

- `1.0` is perfect ranking;
- `0.5` is chance level;
- below `0.5` means positives tend to get lower scores than negatives.

The implementation is tie-aware through average ranks.

## Support and masking rules

### Dense support

For dense comparisons, `pred` and `GT` must have the same shape.

Examples:

- `H x W` vs `H x W`
- `N_faces` vs `N_faces`
- `N_vertices` vs `N_vertices`

### Visible-mask restricted support

When evaluating only the visible part of the mesh:

- pass `visible_mask` into `map_metrics(...)`;
- only masked elements participate in `CC`, `SIM`, `KLD`, `MSE`, `Spearman`.

This is useful when the GT is defined for the full mesh, but the experiment cares only about the visible region from a specific view.

### Sparse positives

When GT is not dense:

- use `auc_from_positive_indices(...)`;
- use `nss_from_positive_indices(...)`;
- or convert fixation points into a binary mask and use the screen-space helpers.

## `AUC_visible_top20`

`auc_visible_top20(...)` and `map_metrics(..., include_auc_visible_top20=True)` implement a ranking-style metric for visible vertices/faces:

1. apply `visible_mask`;
2. sort visible GT values descending;
3. mark the top `20%` as positives;
4. compute ROC AUC for the predicted scores against those positives.

This is not the same as dense `CC/SIM/KLD/MSE`.

It answers a different question:

- "Does the prediction rank the most salient visible region above the rest?"

## Typical usage patterns

### 1. Compare dense mesh predictions with dense mesh GT

```python
import numpy as np

from metrics.mesh_space import map_metrics

pred = np.random.rand(20000)
gt = np.random.rand(20000)
visible_mask = np.random.rand(20000) > 0.4

metrics = map_metrics(
    pred,
    gt,
    visible_mask=visible_mask,
    include_auc_visible_top20=True,
)
```

Returned keys:

- `CC`
- `Spearman`
- `SIM`
- `MSE`
- `KL_gt_to_pred`
- optionally `AUC_visible_top20`

### 2. Compare dense screen-space maps and fixation supervision

```python
import numpy as np

from metrics.screen_space import screen_map_metrics

pred = np.random.rand(1080, 1920)
gt = np.random.rand(1080, 1920)
fixation_points = [(100, 200), (150, 220), (400, 500)]

metrics = screen_map_metrics(
    pred,
    gt,
    fixation_points=fixation_points,
)
```

Returned keys:

- `CC`
- `Spearman`
- `SIM`
- `MSE`
- `KLD`
- optionally `AUC`
- optionally `NSS`

### 3. Evaluate sparse positive mesh hits

```python
import numpy as np

from metrics.mesh_space import auc_from_positive_indices, nss_from_positive_indices

pred = np.random.rand(20000)
positive_indices = np.array([4, 18, 18, 105, 777], dtype=np.int64)

auc = auc_from_positive_indices(pred, positive_indices)
nss = nss_from_positive_indices(pred, positive_indices)
```

## Relation to the MeshMamba-style metrics

If you want the metric family typically reported for dense saliency maps in mesh-saliency papers, the closest direct mapping inside this folder is:

- `CC`
- `SIM`
- `KLD`
- `MSE`

Those are exposed through:

- `metrics.common.dense_saliency_metrics(...)`
- `metrics.mesh_space.map_metrics(...)`
- `metrics.screen_space.screen_map_metrics(...)`

## Error handling

The implementation raises `ValueError` when:

- shapes do not match;
- the evaluation support becomes empty after masking;
- an input contains `NaN` or `Inf`.

This is deliberate. Metric code should fail loudly on broken data rather than silently skipping invalid values.

## Practical caveats

- Do not compare raw values of screen-space and mesh-space metrics as if they were the same experiment.
- `AUC` on sparse positives and `CC` on dense GT answer different questions.
- `KLD` is sensitive to normalization conventions; keep the same code path across experiments.
- `SIM` and `KLD` assume non-negative distributions after preprocessing, so avoid mixing implementations from different repositories without checking their normalization rules.

## Tests

The basic smoke tests live in:

- [tests/test_metrics_smoke.py](../tests/test_metrics_smoke.py)

Run from the repository root:

```bash
pytest tests/test_metrics_smoke.py
```
