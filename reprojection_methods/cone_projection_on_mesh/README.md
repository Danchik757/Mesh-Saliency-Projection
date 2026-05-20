# Cone Projection On Mesh

## Summary

This method transfers fixation uncertainty from the rendered image to the surface of the mesh.

Core idea:

1. start from a fixation point in image space;
2. interpret the fixation as a cone-like uncertainty region instead of a single perfect ray;
3. project the uncertainty onto the visible mesh;
4. accumulate a dense `per-vertex saliency map`.

This is the method family used when the target lives on the object surface instead of on the screen.

## Source article

Primary source:

- *Visual Attention for Rendered 3D Shapes*  
  DOI: [10.1111/cgf.13353](https://doi.org/10.1111/cgf.13353)  
  Eurographics Digital Library page: [paper entry](https://diglib.eg.org/items/1ad7338c-2b0b-4384-bc21-5c32eb95071c)

Important statement from the paper:

- fixation mapping is performed by replacing the ray with a cone;
- a Gaussian distribution is projected on the 3D mesh;
- the published fixation sigma is `49 px`, corresponding to `1 degree of visual angle`.

## Datasets used in this repository

### 1. Visual Attention for Rendered 3D Shapes

This dataset contains:

- `PerSubjectFixations/`
  - already smoothed `per-vertex` maps for each subject and view
- `FixationMaps/`
  - final aggregated `per-vertex` ground truth maps
- `CentricityAndVisibilityMaps/`
  - visibility masks for the corresponding views
- `3DModels-Simplif/`
  - simplified meshes used for evaluation

In this repository, it is used to:

- evaluate the method on the original benchmark;
- compare train / test subject maps;
- compare train maps against final GT;
- test a geodesic diffusion variant as an auxiliary experiment.

### 2. Saliency3D_clear

This dataset contains:

- raw 2D fixation coordinates on screen
- fixation durations
- view identifiers
- 3D hit points for each raw fixation
- mesh files

It does **not** expose a ready-made final GT folder in the same format as `Visual Attention for Rendered 3D Shapes`.

In this repository, it is used to:

- transfer the cone-projection idea to a different dataset;
- build held-out `mesh-space` target maps from raw data;
- compare subject groups by `CC`, `Spearman`, `KL`, `AUC`, and `NSS`.

## Sigma

In the original article, sigma is defined in `screen pixels`:

```text
sigma = 49 px = 1 degree of visual angle
```

Why pixels:

- the fixation is originally observed on the rendered image;
- the uncertainty is defined around that image-space fixation;
- only after that the uncertainty is projected onto the mesh.

So sigma is **not** stored on the mesh.
What is stored on the mesh is the resulting `per-vertex weight`.

For cross-dataset transfer to `Saliency3D_clear`, the same angular idea is reused, but converted to the setup of that dataset:

```text
sigma_px = distance_cm * tan(angle_deg) * px_per_cm
```

For `1 degree` under the `Saliency3D_clear` setup, the working value used in this project is about:

```text
sigma = 52.52 px
```

## What is compared

Typical evaluation:

- `train per-vertex map` vs `test per-vertex map`
- `train per-vertex map` vs `final GT per-vertex map`
- `train per-vertex map` vs held-out sparse fixation vertices

Currently used metrics:

- `CC`
- `Spearman`
- `MSE`
- `KL`
- `AUC_visible_top20`
- `AUC` on sparse positive vertices
- `NSS` on sparse positive vertices

## Scripts in this folder

- [eval_visual_attention_style_saliency3d_clear.py](./eval_visual_attention_style_saliency3d_clear.py)
  - cone-style projection transferred to `Saliency3D_clear`
- [eval_vs_gt_visual_attention.py](./eval_vs_gt_visual_attention.py)
  - train/test/GT comparison on `Visual Attention for Rendered 3D Shapes`
- [eval_geodesic_diffusion.py](./eval_geodesic_diffusion.py)
  - auxiliary geodesic-aware diffusion experiment

## Dataset root setup

### For `Saliency3D_clear`

Use one of:

- `--dataset-root /path/to/Saliency3D_clear`
- `SALIENCY3D_CLEAR_ROOT=/path/to/Saliency3D_clear`

### For `Visual Attention for Rendered 3D Shapes`

Use one of:

- `--dataset-root /path/to/Visual Attention for Rendered 3D Shapes`
- `VISUAL_ATTENTION_3D_SHAPES_ROOT=/path/to/Visual Attention for Rendered 3D Shapes`

## Example commands

Cone-style transfer on `Saliency3D_clear`:

```bash
python3 reprojection_methods/cone_projection_on_mesh/eval_visual_attention_style_saliency3d_clear.py \
  --dataset-root /path/to/Saliency3D_clear \
  --models hand bunny dragon
```

Comparison against published `Visual Attention` GT:

```bash
python3 reprojection_methods/cone_projection_on_mesh/eval_vs_gt_visual_attention.py \
  --dataset-root /path/to/Visual\ Attention\ for\ Rendered\ 3D\ Shapes \
  --objects hand-35K A380 bunny
```

Geodesic diffusion experiment:

```bash
python3 reprojection_methods/cone_projection_on_mesh/eval_geodesic_diffusion.py \
  --dataset-root /path/to/Visual\ Attention\ for\ Rendered\ 3D\ Shapes
```
