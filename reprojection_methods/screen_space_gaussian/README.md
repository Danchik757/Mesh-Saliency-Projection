# Screen-Space Gaussian

## Summary

This method builds a saliency map directly in image space:

1. collect raw fixation points `(x, y)` on the rendered image;
2. weight them by fixation duration;
3. deposit them into a 2D screen histogram;
4. convolve the histogram with a Gaussian kernel.

The output is a dense `screen-space saliency map`.

## Source article

Primary source:

- *Saliency3D: A 3D Saliency Dataset Collected on Screen*  
  Paper: [wang24_etras.pdf](https://www.perceptualui.org/publications/wang24_etras.pdf)  
  DOI: [10.1145/3649902.3653350](https://doi.org/10.1145/3649902.3653350)

Dataset page:

- [DaRUS / Saliency3D dataset](https://darus.uni-stuttgart.de/dataset.xhtml?persistentId=doi%3A10.18419%2Fdarus-4101)

## Dataset used in this repository

Default evaluation dataset:

- `Saliency3D_clear`

Relevant local content:

- raw participant files contain:
  - screen coordinates `x, y`
  - duration / weight
  - view identifiers
  - 3D hit point

For this method, only the `screen-space fixation coordinates` and `duration` are required.

## Sigma

Sigma is defined in `screen pixels`.

In the current project, the baseline value is:

```text
sigma = 26.3 px
```

It comes from the article setup:

- eye-to-screen distance
- display size and resolution
- eye tracker angular accuracy

General formula:

```text
sigma_px = distance_cm * tan(angle_deg) * px_per_cm
```

## What is compared

Typical evaluation:

- `predicted screen density map` vs `held-out screen density map`
- `predicted screen density map` vs `held-out fixation pixels`

Currently used metrics:

- `AUC`
- `NSS`
- `CC`

## Script in this folder

- [eval_holdout_screenspace.py](./eval_holdout_screenspace.py)

## Dataset root setup

The script expects the root of `Saliency3D_clear`.

You can provide it in one of two ways:

- pass `--dataset-root /path/to/Saliency3D_clear`
- or set `SALIENCY3D_CLEAR_ROOT=/path/to/Saliency3D_clear`

## Example command

```bash
python3 reprojection_methods/screen_space_gaussian/eval_holdout_screenspace.py \
  --dataset-root /path/to/Saliency3D_clear \
  --model hand \
  --sigma-px 26.3
```
