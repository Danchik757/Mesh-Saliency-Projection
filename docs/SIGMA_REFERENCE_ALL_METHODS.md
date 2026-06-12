# Sigma Reference For All Methods

Last updated: 2026-06-11

This document explains what `sigma` means in our projection code, where the original values came from, which values were used in the latest full rc3 metric run, and what the first sigma sweep suggests for future runs.

It merges two previous notes:

- the original reference about method-level sigma choices;
- the rc3 sigma sweep notes from `trash/SIGMA_PARAMETERS_AND_SWEEP_NOTES.md`.

## Core Idea

Do not mix these three levels:

1. **Method family**
   Example: `screen_space_gaussian`, `cone_gaussian_on_mesh`, `geodesic_diffusion`.

2. **Physical uncertainty**
   Example: `1° visual angle`, `0.5° tracker accuracy`.

3. **Numerical implementation**
   Example: `49 px`, `26.3 px`, `sigma_world`, `sigma_mesh`.

The main source of confusion is that `49 px` and `26.3 px` are usually not the essence of a method. They are pixel-space implementations of a physical angular assumption under a specific screen setup.

## Summary Table

| Method family | Current evaluator / source | Sigma in code | Units | Meaning |
|---|---|---:|---|---|
| 3DVA `screen_space_gaussian` | `reprojection_methods/screen_space_gaussian/eval_3dva_screen_space_combined.py` | `49.0` | px | Gaussian blur on a 1920x1080 screen density image |
| MeshMamba `screen_space_gaussian` | `reprojection_methods/screen_space_gaussian/eval_meshmamba_screen_space.py` | `0.05` | screen fraction | Gaussian blur on a 256x144 density image; effective `sigma_px = 12.8` |
| SAL3D `screen_space_gaussian` | `reprojection_methods/screen_space_gaussian/eval_sal3d_screen_space.py` | `26.3` | px | Gaussian blur on a 1920x1080 screen density image |
| 3DVA / MeshMamba / SAL3D `cone_gaussian_on_mesh` | `reprojection_methods/cone_projection_on_mesh/eval_*_cone*.py` | `1.0` | deg | Angular cone width before depth-dependent world-space conversion |
| Saliency3D_clear deterministic screen baseline | `Dataset (Clear)/Saliency3D_clear/eval_holdout_screenspace.py` | `26.3` | px | Screen-space Gaussian from original Saliency3D setup |
| Saliency3D_clear old stochastic Gaussian | `Dataset (Clear)/Saliency3D_clear/3D_gaze_data/Code/gaussian_distribution_total.py` | `26.3` | px | Same screen-space Gaussian, approximated by random samples |
| Visual-Attention-style transfer to Saliency3D_clear | `reprojection_methods/cone_projection_on_mesh/eval_visual_attention_style_saliency3d_clear.py` | `1.0` / `52.52` | deg / px | `1°` converted to Saliency3D_clear screen setup |
| Geodesic diffusion experiment | `reprojection_methods/cone_projection_on_mesh/eval_geodesic_diffusion.py` | derived | mesh units | Surface diffusion scale derived from angular/edge-length heuristic |

## Screen-Space Gaussian

### Algorithm

Screen-space method works on the image plane:

```text
raw gaze points -> 2D histogram -> Gaussian blur -> sample density on projected mesh
```

The Gaussian is applied before transferring values to mesh vertices/faces.

### Main parameters

- `sigma_px`: absolute Gaussian sigma in pixels.
- `sigma_screen`: normalized sigma as a fraction of density image width; used by MeshMamba and converted internally.

### Formula

```text
D_t(x, y) = Gaussian(H_t(x, y), sigma_px)
```

where:

- `H_t` is the gaze histogram for frame `t`;
- `D_t` is the blurred screen-space density.

### Current baseline values

| Dataset | Parameter | Baseline value | Notes |
|---|---|---:|---|
| 3DVA | `sigma_px` | `49.0` | 1920x1080 density; approximately `1°` visual angle in the 3DVA / Visual Attention setup |
| MeshMamba | `sigma_screen` | `0.05` | 256x144 density; effective `sigma_px = 0.05 * 256 = 12.8` |
| SAL3D | `sigma_px` | `26.3` | 1920x1080 density; derived from `0.5°` tracker accuracy in Saliency3D-style setup |

### Why `49 px` and `26.3 px` differ

They come from different physical assumptions and/or setups:

- `49 px` represents approximately `1°` visual angle in the 3DVA / Visual Attention setup.
- `26.3 px` comes from the Saliency3D setup using `0.5°` tracker accuracy.

They are not two arbitrary versions of the same constant.

## Cone Gaussian On Mesh

### Algorithm

Cone projection works in 3D:

1. Convert a 2D gaze point into a camera ray.
2. Intersect the ray with the mesh.
3. Convert angular uncertainty to world-space sigma using hit depth.
4. Add Gaussian weight to nearby vertices/faces.

### Main parameters

- `sigma_deg`: angular gaze uncertainty in degrees.
- `radius_sigma_mult`: support-radius multiplier; elements within `radius_sigma_mult * sigma_world` are considered.

### Formula

```text
sigma_world = depth * tan(sigma_deg)
```

```text
w(v) = exp(-0.5 * ||v - p_hit||^2 / sigma_world^2)
```

where:

- `p_hit` is the ray/mesh hit point;
- `v` is a nearby vertex/face representative point;
- `depth` is the camera-to-hit depth.

### Current baseline values

| Dataset | `sigma_deg` | `radius_sigma_mult` |
|---|---:|---:|
| 3DVA | `1.0` | `3.0` |
| MeshMamba | `1.0` | `3.0` |
| SAL3D | `1.0` | `3.0` |

### Why cone does not use `49 px`

`49 px` is a screen-space implementation detail. Cone operates after ray/mesh intersection, so its invariant method-level parameter is angular:

```text
sigma_deg = 1°
```

The code then converts it to a mesh/world-space support using depth.

## Saliency3D Clear Screen-Space Baseline

The original Saliency3D-style screen-space baseline uses:

```text
sigma_px = 26.3
```

This is derived from:

- screen diagonal: `24.5"`
- resolution: `1920x1080`
- viewing distance: `85 cm`
- tracker accuracy: `0.5°`

Approximate conversion:

```text
sigma_px = distance_cm * tan(angle_deg) * px_per_cm
```

For this setup:

```text
0.5° -> 26.26 px ~= 26.3 px
```

## Old Stochastic Gaussian Code

In the old Saliency3D code:

```python
np.random.multivariate_normal(mean, C, round(200 * weight))
```

the Gaussian covariance uses:

```text
C = [[26.3^2, 0], [0, 26.3^2]]
```

Important:

- `26.3` is the sigma.
- `200` is not sigma.
- `200` is a Monte Carlo sample budget multiplier.

This old stochastic code is conceptually different from our deterministic evaluators.

## Visual-Attention-Style Transfer To Saliency3D Clear

For Visual-Attention-style transfer, the invariant method assumption is:

```text
sigma_deg = 1.0
```

Under the Saliency3D_clear screen setup, the same `1°` converts to:

```text
sigma_px ~= 52.52
```

This demonstrates the key rule:

```text
same angular method assumption != same pixel sigma across datasets
```

## Geodesic Diffusion Experiment

Geodesic diffusion does not use screen pixels or angular cone support directly. It diffuses saliency along the mesh surface graph.

The experimental parameterization was:

```text
sigma_visual_deg = 1.0
vertex_angle_deg = 0.1
sigma_vertex_steps = sigma_visual_deg / vertex_angle_deg = 10
sigma_mesh = sigma_vertex_steps * mean_edge_length
```

So:

```text
sigma_mesh = 10 * mean_edge_length
```

This is a surface-scale heuristic, not a published paper constant.

## Current rc3 Baseline Metric Run

Baseline run:

```text
/mnt/ssd1/29d_kon/acm_2026/outputs/coordinator/rc3_full_metrics_20260611_004003
```

Timing contract:

```text
timing_contract = one_turn_from_start
delay_seconds = 0.0
gaze_start_frame = 0
placement_start_frame = 0
delay_frames = 0
frame_offset = 0
```

Window:

| Dataset | Total frames | Metric frames | Window |
|---|---:|---:|---|
| 3DVA | 510 | 450 | `gaze[0:450] -> placement[0:450]` |
| MeshMamba | 510 | 450 | `gaze[0:450] -> placement[0:450]` |
| SAL3D | 720 | 660 | `gaze[0:660] -> placement[0:660]` |

This baseline drops the tail: the last 60 frames are not used.

Camera/FOV:

| Parameter | Value |
|---|---:|
| `projection_fov_mode` | `horizontal_to_vertical` |
| input horizontal FOV | `60.0 deg` |
| effective vertical FOV | `35.9834 deg` |

Baseline sigma values in that run:

| Dataset | Method | Sigma |
|---|---|---|
| 3DVA | screen-space | `sigma_px = 49.0` |
| MeshMamba | screen-space | `sigma_screen = 0.05`, effective `sigma_px = 12.8` |
| SAL3D | screen-space | `sigma_px = 26.3` |
| 3DVA | cone | `sigma_deg = 1.0`, `radius_sigma_mult = 3.0` |
| MeshMamba | cone | `sigma_deg = 1.0`, `radius_sigma_mult = 3.0` |
| SAL3D | cone | `sigma_deg = 1.0`, `radius_sigma_mult = 3.0` |

## rc3 Sigma Sweep Stage 1

Run id:

```text
rc3_sigma_sweep_20260611_stage1_fix3
```

Sample:

- 25 models per dataset/track.
- Stratified by current CC distribution.
- Tracks: `3DVA`, `SAL3D`, `MeshMamba non_texture`, `MeshMamba rgb_texture`.

Job status:

| Total | OK | Failed |
|---:|---:|---:|
| 1400 | 1395 | 5 |

All failures were `sal3d/cart/cone` timeouts at multiple `sigma_deg` values.

### Screen-space sweep

The sweep varied dataset-specific baseline sigma by multipliers around the current value.

Conceptually:

```text
candidate_sigma = baseline_sigma * multiplier
```

For MeshMamba this means:

```text
candidate_sigma_screen = 0.05 * multiplier
```

For 3DVA/SAL3D this means:

```text
candidate_sigma_px = baseline_sigma_px * multiplier
```

### Cone sweep

The sweep varied:

```text
sigma_deg
```

while keeping:

```text
radius_sigma_mult = 3.0
```

Radius was not swept in stage 1 because it changes both map shape and runtime.

## Sweep Conclusions

### Method comparison

Cone won on 3 of 4 tracks:

| Dataset/track | Best cone CC | Best screen-space CC | Winner |
|---|---:|---:|---|
| SAL3D | ~0.558 | ~0.403 | cone |
| MeshMamba non_texture | ~0.330 | ~0.215 | cone |
| MeshMamba rgb_texture | ~0.283 | ~0.203 | cone |
| 3DVA | ~0.437 | ~0.476 | screen-space |

3DVA is the only exception, and the gap is relatively small.

### Dataset-specific sigma behavior

Cone:

- `SAL3D`: best region near `1.6-2.0 deg`; curve still rises near the sweep boundary.
- `3DVA`: best observed value near `2.0 deg`; curve may not be saturated.
- `MeshMamba non_texture/rgb_texture`: best region near `0.8-1.0 deg`; larger sigma starts to hurt.

Screen-space:

- `SAL3D`: larger sigma than baseline helps; around `1.5x`.
- `MeshMamba`: smaller sigma than baseline helps; around `0.5x`.
- `3DVA`: weaker consensus, but smaller sigma often helps.

### Runtime observations

- MeshMamba screen-space is much faster than MeshMamba cone.
- SAL3D cone is slow, especially for `cart`.
- `sal3d/cart` should be handled as a slow/outlier model.

## Recommended Next Configurations

For the next full metric pass, use:

| Dataset/track | Method | Recommended sigma |
|---|---|---|
| SAL3D | cone | `sigma_deg = 1.6`, `radius_sigma_mult = 3.0` |
| 3DVA | cone | `sigma_deg = 2.0`, `radius_sigma_mult = 3.0` |
| MeshMamba non_texture | cone | `sigma_deg = 0.8`, `radius_sigma_mult = 3.0` |
| MeshMamba rgb_texture | cone | `sigma_deg = 0.8`, `radius_sigma_mult = 3.0` |
| SAL3D | screen-space | `sigma_px ~= 39.45` (`1.5 * 26.3`) |
| 3DVA | screen-space | `sigma_px ~= 24.5` (`0.5 * 49.0`) |
| MeshMamba non_texture | screen-space | `sigma_screen = 0.025`, effective `sigma_px ~= 6.4` |
| MeshMamba rgb_texture | screen-space | `sigma_screen = 0.025`, effective `sigma_px ~= 6.4` |

Do not change `radius_sigma_mult` yet. It should be swept only after the primary sigma choice is stable.

## Current Delay / Window Caveat

Sigma sweep was performed with:

```text
delay_seconds = 0.0
gaze[0+k] -> placement[0+k]
```

A separate delay/window run is needed to test the hypothesis that human response delay and start-crop should be used:

```text
placement[54+k]
gaze[60+k]      # delay +0.2s at 30 fps
```

This is being evaluated separately from sigma tuning.

## Anti-Confusion Notes

### `49 px` is not the universal cone sigma

Wrong:

```text
cone method => always sigma = 49 px
```

Correct:

```text
cone method => keep angular sigma, e.g. 1°
dataset geometry/depth => convert to world-space support
```

### `26.3 px` is not always “better” than `49 px`

These values come from different assumptions:

- `26.3 px`: approximately `0.5°` tracker accuracy in Saliency3D setup.
- `49 px`: approximately `1°` visual angle in 3DVA / Visual Attention setup.

### `200` is not sigma

In old stochastic code:

```text
26.3 = sigma
200 = sample budget multiplier
```

### Same physical sigma does not imply same pixel sigma

If method is physically defined through visual angle, keep angle invariant and recompute implementation units:

```text
sigma_px = distance_cm * tan(angle_deg) * px_per_cm
```

Pixel sigma depends on:

- screen size;
- resolution;
- viewing distance;
- density image resolution.

Cone world-space sigma additionally depends on:

- object depth;
- camera geometry;
- mesh scale.

## Practical Rules

Use these rules when launching experiments:

1. For baseline comparison with the current rc3 full run, use the baseline table above.
2. For improved full metrics after sweep, use the recommended next configurations.
3. Keep cone `radius_sigma_mult = 3.0` unless explicitly running a radius sweep.
4. Always record sigma parameters in report provenance and CSV outputs.
5. Never compare metrics from different timing windows without naming the timing contract.
6. Treat `sal3d/cart` cone as a slow-model exception.

## Related Files

- `reprojection_methods/screen_space_gaussian/eval_3dva_screen_space_combined.py`
- `reprojection_methods/screen_space_gaussian/eval_meshmamba_screen_space.py`
- `reprojection_methods/screen_space_gaussian/eval_sal3d_screen_space.py`
- `reprojection_methods/cone_projection_on_mesh/eval_3dva_cone_combined.py`
- `reprojection_methods/cone_projection_on_mesh/eval_meshmamba_cone.py`
- `reprojection_methods/cone_projection_on_mesh/eval_sal3d_cone.py`
- `reprojection_methods/cone_projection_on_mesh/README.md`
- `docs/3DVA_VERIFICATION_METHOD.md`
- `trash/SIGMA_PARAMETERS_AND_SWEEP_NOTES.md`
