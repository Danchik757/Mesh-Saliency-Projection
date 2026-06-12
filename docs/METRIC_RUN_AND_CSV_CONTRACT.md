# Metric Run And CSV Contract

Last updated: 2026-06-11

This document fixes the expected benchmark run parameters and the CSV format we use for reporting metrics.

Use it as the reference when launching metric runs, comparing new runs with baseline, or preparing tables for Google Sheets / papers.

## Baseline Metric Run Contract

The current baseline uses full-length rc3 fixation JSON files and evaluates exactly one full object rotation from the beginning of the sequence.

### Dataset Windows

| Dataset | Total frames | Frames used | Pairing |
|---|---:|---:|---|
| 3DVA | 510 | 450 | `gaze[0:450] -> placement[0:450]` |
| MeshMamba | 510 | 450 | `gaze[0:450] -> placement[0:450]` |
| SAL3D | 720 | 660 | `gaze[0:660] -> placement[0:660]` |

### Timing Parameters

| Parameter | Value | Meaning |
|---|---|---|
| `timing_contract` | `one_turn_from_start` | Use one full object rotation from full-length fixation JSON. |
| `frame_offset` | `0` | Start the evaluation window from frame 0. |
| `delay_seconds` | `0.0` | No fixation delay relative to object placement. |
| `delay_frames` | `0` | At 30 fps, the delay is 0 frames. |
| `gaze_start_frame` | `0` | Fixation frames start at frame 0. |
| `placement_start_frame` | `0` | Object placement frames start at frame 0. |
| `turn_frame_count` | `450` or `660` | One full object rotation: 450 frames for 3DVA/MeshMamba, 660 frames for SAL3D. |
| crop behavior | `drop tail` | Drop the final 60 frames; use the first full turn. |

### Dataset-Specific Frame Interpretation

3DVA and MeshMamba:

```text
total duration = 17 s
total frames   = 510
one turn       = 15 s = 450 frames
unused tail    = 60 frames = 2 s
```

SAL3D:

```text
total duration = 24 s
total frames   = 720
one turn       = 22 s = 660 frames
unused tail    = 60 frames = 2 s
```

## Baseline Sigma Values

These are the old baseline sigma values used in the reference full metric run.

| Dataset / track | Method | Sigma used |
|---|---|---|
| 3DVA | `screen_space` | `sigma_px = 49.0` |
| 3DVA | `cone` | `sigma_deg = 1.0`, `radius_sigma_mult = 3.0` |
| SAL3D | `screen_space` | `sigma_px = 26.3` |
| SAL3D | `cone` | `sigma_deg = 1.0`, `radius_sigma_mult = 3.0` |
| MeshMamba non_texture | `screen_space` | `sigma_screen = 0.05`, effective `sigma_px = 12.8` |
| MeshMamba non_texture | `cone` | `sigma_deg = 1.0`, `radius_sigma_mult = 3.0` |
| MeshMamba rgb_texture | `screen_space` | `sigma_screen = 0.05`, effective `sigma_px = 12.8` |
| MeshMamba rgb_texture | `cone` | `sigma_deg = 1.0`, `radius_sigma_mult = 3.0` |

## Alternative Timing Run: Start Crop + 0.2 s Delay

This run is not the baseline. It tests whether metrics improve if the beginning of the presentation is skipped and a human response delay is applied.

### Dataset Windows

| Dataset | Total frames | Frames used | Pairing |
|---|---:|---:|---|
| 3DVA | 510 | 450 | `gaze[60:510] -> placement[54:504]` |
| MeshMamba | 510 | 450 | `gaze[60:510] -> placement[54:504]` |
| SAL3D | 720 | 660 | `gaze[60:720] -> placement[54:714]` |

### Timing Parameters

| Parameter | Value | Meaning |
|---|---|---|
| `timing_contract` | `one_turn_from_start` | Still uses full-length offset0 fixation JSON files. |
| `frame_offset` | `54` | Placement window starts after 1.8 s at 30 fps. |
| `delay_seconds` | `0.2` | Fixations are shifted 0.2 s after the displayed object state. |
| `delay_frames` | `6` | At 30 fps, `0.2 s = 6 frames`. |
| `placement_start_frame` | `54` | Object placement starts at 1.8 s. |
| `gaze_start_frame` | `60` | Fixation frames start at 2.0 s. |
| `turn_frame_count` | `450` or `660` | One full object rotation. |
| crop behavior | `drop head + tail` | Skip the beginning of placement/gaze and still keep exactly one full turn. |

This run should be reported separately from baseline.

## Metrics We Report

The compact CSV must include the following metrics in this exact order:

1. `CC`
2. `SIM`
3. `KLD`
4. `MSE`
5. `MAE`
6. `Spearman`
7. `Cosine`
8. `AUC_at_10pct`
9. `AUC_at_5pct`
10. `AUC_at_1pct`
11. `NSS_at_10pct`
12. `NSS_at_5pct`
13. `NSS_at_1pct`
14. `hit_rate`

### Notes About Proxy AUC/NSS

`AUC_at_10pct`, `AUC_at_5pct`, `AUC_at_1pct` are proxy AUC metrics:

```text
positives = top-k% vertices/faces by GT saliency
```

`NSS_at_10pct`, `NSS_at_5pct`, `NSS_at_1pct` are proxy NSS metrics using the same top-k% GT positives.

They are not classic AUC/NSS over raw fixation-hit points. If classic projected-fixation AUC/NSS is added later, it must use separate column names.

### Notes About hit_rate

`hit_rate` is meaningful for ray/cone methods because those methods explicitly cast gaze rays and count successful mesh hits.

For `screen_space`, `hit_rate` is usually empty because that method does not have a ray/mesh hit stage.

## Required Compact CSV Format

The compact CSV must use this exact header:

```csv
dataset_track,method,n_ok,CC,SIM,KLD,MSE,MAE,Spearman,Cosine,AUC_at_10pct,AUC_at_5pct,AUC_at_1pct,NSS_at_10pct,NSS_at_5pct,NSS_at_1pct,hit_rate
```

### Row Order

Use this row order:

1. `3dva,cone`
2. `3dva,screen_space`
3. `meshmamba_non_texture,cone`
4. `meshmamba_non_texture,screen_space`
5. `meshmamba_rgb_texture,cone`
6. `meshmamba_rgb_texture,screen_space`
7. `sal3d,cone`
8. `sal3d,screen_space`

### Formatting

- Use one row per `(dataset_track, method)`.
- Use 4 digits after the decimal point for metric values.
- Leave unavailable metrics empty, do not write `nan`.
- `n_ok` must count only successful report rows.
- `dataset_track` values must be:
  - `3dva`
  - `meshmamba_non_texture`
  - `meshmamba_rgb_texture`
  - `sal3d`

### Example

```csv
dataset_track,method,n_ok,CC,SIM,KLD,MSE,MAE,Spearman,Cosine,AUC_at_10pct,AUC_at_5pct,AUC_at_1pct,NSS_at_10pct,NSS_at_5pct,NSS_at_1pct,hit_rate
3dva,cone,31,0.4095,0.6431,0.5603,0.0456,0.1512,0.3632,0.7227,0.7234,0.7329,0.7657,0.9534,1.1651,1.4280,0.8884
3dva,screen_space,31,0.4559,0.6697,0.9553,0.0439,0.1549,0.4457,0.7602,0.7595,0.7651,0.7711,0.9860,1.1520,1.3129,
```

## Required Long CSV Format

The long CSV should contain one row per `(dataset_track, model, method)` and should include at least:

```text
dataset_track
texture_type
model
method
status
report_path
gaze_start_frame
placement_start_frame
turn_frame_count
delay_frames
frame_offset
fixation_format
fixation_data_tag
sigma_px
sigma_screen
sigma_deg
radius_sigma_mult
all metric columns used by compact CSV
```

The compact CSV should always be reproducible from the long CSV.

## Baseline Reference Run

Current baseline full run:

```text
/mnt/ssd1/29d_kon/acm_2026/outputs/coordinator/rc3_full_metrics_20260611_004003
```

Current baseline compact CSV:

```text
results/benchmark_runs/rc3_full_metrics_20260611_004003_summary_all_metrics.csv
```

## Start-Crop + Delay Reference Run

Current shifted timing run:

```text
/mnt/ssd1/29d_kon/acm_2026/outputs/coordinator/rc3_full_metrics_cuthead54_delay02_oldsigmas_20260611_115343
```

Current shifted compact CSV:

```text
results/benchmark_runs/rc3_cuthead54_delay02_oldsigmas_all_metrics_compact.csv
```
