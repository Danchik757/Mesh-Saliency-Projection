# Video Creation

This folder stores scripts that generate visual comparisons, figures, and later video assets for the project.

## Current subfolders

- [transfer_visualizations](./transfer_visualizations/README.md)
- [gaze_heatmap_overlays](./gaze_heatmap_overlays/README.md)
- [gaze_heatmap_overlays](./gaze_heatmap_overlays/README.md)

## What is here now

The main visualization workflow currently lives in:

- [transfer_visualizations/make_transfer_visualizations.py](./transfer_visualizations/make_transfer_visualizations.py)
- [gaze_heatmap_overlays/render_heatmap_overlay.py](./gaze_heatmap_overlays/render_heatmap_overlay.py)
- [gaze_heatmap_overlays/make_gif.py](./gaze_heatmap_overlays/make_gif.py)
- [gaze_heatmap_overlays/render_heatmap_overlay.py](./gaze_heatmap_overlays/render_heatmap_overlay.py)
- [gaze_heatmap_overlays/make_gif.py](./gaze_heatmap_overlays/make_gif.py)

This script is not a metric benchmark by itself. It is a reporting and inspection tool that renders side-by-side comparisons for two reprojection methods on `Saliency3D_clear`:

- screen-space Gaussian transfer
- cone-style projection on mesh

It also writes a JSON summary with the metrics shown on the figures.

The `gaze_heatmap_overlays` subfolder is a separate screen-space visualization workflow for rendering gaze heatmaps directly over source videos.

## Typical outputs

- side-by-side method comparison PNGs
- method-only comparison PNGs
- JSON summaries for reports or debugging
- heatmap overlay MP4 videos
- palette-based GIF previews

## Recommended usage

Use this folder for:

- qualitative inspection of transfer behavior
- figures for documentation and reports
- sanity checks before large metric runs

Do not use it as the only source of quantitative evaluation. The core metric scripts remain in:

- [reprojection_methods/screen_space_gaussian](../reprojection_methods/screen_space_gaussian/README.md)
- [reprojection_methods/cone_projection_on_mesh](../reprojection_methods/cone_projection_on_mesh/README.md)
