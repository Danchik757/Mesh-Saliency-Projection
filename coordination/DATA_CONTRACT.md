# Data Contract

## Separate Data Types

The project has three independent JSON/CSV concepts. They must not be mixed.

### 1. Canonical object-placement JSON

Location:

```text
jsons/object_placement/
```

Purpose:

- video FPS, duration, and resolution
- camera/view/projection parameters
- model scale and static transform
- per-frame object rotation
- mapping from a video frame to object pose

These files describe what was shown, not where participants looked.

### 2. Original participant CSV

Location: external `GAZE_DATA/csv_for_models/` input, packaged as
`participant_gaze_csv_original.zip` in the release.

Purpose:

- retain participant/session identity and metadata
- retain explicit `t`, `x`, and `y` samples
- preserve the original input for diagnostics and migration checks

The CSV is the only current source that can support explicit
per-participant weighting because the new JSON no longer stores participant IDs.

### 3. New processed fixation JSON

Location:

```text
participant_data/processed_fixations_offset0_full_cleaned/<dataset_object>/fixations.json
```

Purpose:

- provide postprocessed screen-space points grouped by frame
- remove invalid participants upstream
- provide the new canonical gaze input for future benchmark runs

Format:

```text
fixations[frame_index][point_index] = [x_px, y_px]
```

Properties:

- `frame_index` supplies implicit time
- each point contains pixel coordinates
- there is no explicit timestamp per point
- there is no participant ID
- there is no camera/object placement information

## Verified Inventory for rc4

| Track | Placement JSON | Original CSV | New fixation JSON | Structural result |
| --- | ---: | ---: | ---: | --- |
| 3DVA | 32 | 32 | 32 | 31 valid; `3DVA_jessi` has 41/510 frames |
| MeshMamba non_texture | 105 | 105 | 105 | valid |
| MeshMamba rgb_texture | 105 | 105 | 105 | valid |
| SAL3D | 57 | 56 | 56 | `SAL3D_gorgoile` missing |

All parsed points in the structurally valid files are finite and within the
matching placement JSON resolution. No valid file has an empty frame.

## Timing Rule

The canonical rc4 baseline uses full-length offset0 fixation JSON and exactly one
full object rotation from the start:

```text
timing_contract = one_turn_from_start
frame_offset = 0
delay_seconds = 0.0
pair gaze[k] with placement[k]
```

Verified placement timing groups:

| Track | Video | Rotation speed | Full turn | Baseline window |
| --- | ---: | ---: | ---: | ---: |
| 3DVA | 17 s | 24 deg/s | 15 s | 15 s / 450 frames |
| MeshMamba non_texture | 17 s | 24 deg/s | 15 s | 15 s / 450 frames |
| MeshMamba rgb_texture | 17 s | 24 deg/s | 15 s | 15 s / 450 frames |
| SAL3D | 24 s | 16.363636 deg/s | 22 s | 22 s / 660 frames |

Thus the baseline keeps one full object revolution and drops the final 60
frames. Start-crop and delay variants are ablations, not the baseline.

At 30 FPS:

```text
17-second tracks:
  gaze frames used:       [0, 450)
  placement/video frames: [0, 450)

24-second SAL3D:
  gaze frames used:       [0, 660)
  placement/video frames: [0, 660)
```

The loader rejects negative offsets and windows outside the available frame
range. Reports and resume guards record and verify timing, delay, frame offset,
fixation tag, release tag, and sigma provenance.

## Aggregation Constraint

The new fixation JSON combines points after participant postprocessing and does
not preserve participant identity. Therefore:

- point-equal aggregation is possible directly;
- participant-equal aggregation is not possible from this file alone;
- any claim of participant-equal weighting requires an additional participant
  mapping or a regenerated processed format.

This limitation must be addressed explicitly in the metrics/aggregation audit.

## Versioning and Distribution

Large datasets, OBJ files, GT, original CSVs, new gaze JSONs, and placement JSONs must
be distributed through GitHub Releases, not copied manually between agents or
servers.

The next release candidate must include:

- canonical placement JSONs built from `jsons/object_placement/`
- new processed fixation JSONs
- original CSVs for migration/audit
- validated OBJ/GT archives
- manifest with counts, SHA-256 checksums, and known exclusions

The two participant data types must use unambiguous archive names:

```text
participant_gaze_csv_original.zip
participant_fixations_offset0_full_cleaned.zip
```

They must never be merged into one archive or silently substituted for each
other.

The next release is `v2.0-data-rc4`, schema version 2. It must also include the
mandatory full `sal3d_smooth_gaze.zip` and fixed-face GT. Do not overwrite prior
releases; build and validate a new versioned candidate.
