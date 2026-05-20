# Requirements

This folder contains task-specific requirement files.

The goal is simple:

- do not install everything when the task only needs one part of the project
- keep runtime dependencies separated from visualization and testing
- make environments easier to reproduce

## Files

- [base.txt](./base.txt)
- [metrics.txt](./metrics.txt)
- [screen_space_gaussian.txt](./screen_space_gaussian.txt)
- [cone_projection_on_mesh.txt](./cone_projection_on_mesh.txt)
- [visualization.txt](./visualization.txt)
- [dev.txt](./dev.txt)
- [all.txt](./all.txt)

## What to install for each task

### Only metrics

Use:

- [metrics.txt](./metrics.txt)

This is enough for:

- `metrics/screen_space.py`
- `metrics/mesh_space.py`
- simple metric-only checks

### Screen-space Gaussian evaluation

Use:

- [screen_space_gaussian.txt](./screen_space_gaussian.txt)

This is enough for:

- [reprojection_methods/screen_space_gaussian/eval_holdout_screenspace.py](../reprojection_methods/screen_space_gaussian/eval_holdout_screenspace.py)

### Cone projection and geodesic experiments

Use:

- [cone_projection_on_mesh.txt](./cone_projection_on_mesh.txt)

This is enough for:

- [reprojection_methods/cone_projection_on_mesh/eval_visual_attention_style_saliency3d_clear.py](../reprojection_methods/cone_projection_on_mesh/eval_visual_attention_style_saliency3d_clear.py)
- [reprojection_methods/cone_projection_on_mesh/eval_vs_gt_visual_attention.py](../reprojection_methods/cone_projection_on_mesh/eval_vs_gt_visual_attention.py)
- [reprojection_methods/cone_projection_on_mesh/eval_geodesic_diffusion.py](../reprojection_methods/cone_projection_on_mesh/eval_geodesic_diffusion.py)

### Visualizations and overlays

Use:

- [visualization.txt](./visualization.txt)

This is enough for:

- [video_creation/transfer_visualizations/make_transfer_visualizations.py](../video_creation/transfer_visualizations/make_transfer_visualizations.py)
- overlay and heatmap rendering scripts in `video_creation/`

### Local development and tests

Use:

- [dev.txt](./dev.txt)

This adds:

- `pytest`

### Full local environment

Use:

- [all.txt](./all.txt)

## Example installation commands

Metrics only:

```bash
python3 -m pip install -r requirements/metrics.txt
```

Cone projection workflow:

```bash
python3 -m pip install -r requirements/cone_projection_on_mesh.txt
```

Visualization workflow:

```bash
python3 -m pip install -r requirements/visualization.txt
```

Everything:

```bash
python3 -m pip install -r requirements/all.txt
```

## Current policy

Right now these files contain only the base libraries we are already using in the repository.

That means:

- no GPU stack yet
- no notebook stack yet
- no heavy rendering stack yet

Those can be added later when the corresponding code becomes part of the stable project structure.
