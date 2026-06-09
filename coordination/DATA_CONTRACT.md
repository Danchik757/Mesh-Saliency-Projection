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

### 2. Old participant CSV

Location:

```text
participant_data/collected_gaze_csv_by_model/
```

Purpose:

- retain participant/session identity and metadata
- retain explicit `t`, `x`, and `y` samples
- preserve the old input for diagnostics and migration checks

The CSV is the only current repository-side source that can support explicit
per-participant weighting because the new JSON no longer stores participant IDs.

### 3. New processed fixation JSON

Location:

```text
participant_data/processed_fixations_offset_2000/<dataset_object>/fixations.json
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

## Verified Inventory on 2026-06-09

| Track | Placement JSON | Old CSV | New fixation JSON | Structural result |
| --- | ---: | ---: | ---: | --- |
| 3DVA | 32 | 32 | 32 | 31 valid; `3DVA_jessi` has 41/510 frames |
| MeshMamba non_texture | 105 | 105 | 105 | valid |
| MeshMamba rgb_texture | 105 | 105 | 105 | valid |
| SAL3D | 57 | 56 | 56 | `SAL3D_gorgoile` missing |

All parsed points in the structurally valid files are finite and within the
matching placement JSON resolution. No valid file has an empty frame.

## Timing Rule

The same crop rule applies to every dataset and method:

```text
crop_start_seconds = 1.8
crop_end_seconds = 0.2
```

The processed gaze JSON was generated after removing an upstream 2.0-second
interval. Pairing its first frame with the placement/video frame at `1.8 s`
compensates for the assumed `0.2 s` human visual reaction delay.

The usable duration is calculated from placement JSON, not hardcoded:

```text
usable_duration = video_info.duration_seconds - 1.8 - 0.2
start_frame = round(1.8 * fps)
end_frame = total_frames - round(0.2 * fps)
pair gaze[k] with placement[start_frame + k]
```

Verified placement timing groups:

| Track | Video | Rotation speed | Full turn | Usable window |
| --- | ---: | ---: | ---: | ---: |
| 3DVA | 17 s | 24 deg/s | 15 s | 15 s / 450 frames |
| MeshMamba non_texture | 17 s | 24 deg/s | 15 s | 15 s / 450 frames |
| MeshMamba rgb_texture | 17 s | 24 deg/s | 15 s | 15 s / 450 frames |
| SAL3D | 24 s | 16.363636 deg/s | 22 s | 22 s / 660 frames |

Thus the common crop leaves exactly one full object revolution for both
17-second and 24-second video families.

At 30 FPS:

```text
17-second tracks:
  gaze frames used:       [0, 450)
  placement/video frames: [54, 504)

24-second SAL3D:
  gaze frames used:       [0, 660)
  placement/video frames: [54, 714)
```

The loader must verify the rotation speed and full-turn duration from
`animation.rotation_speed_deg_per_sec` and/or unwrapped per-frame rotations. It
must fail if the cropped duration is not one full turn within tolerance.

This mapping still requires single-point/frame preview evidence before final
benchmark acceptance.

## Aggregation Constraint

The new fixation JSON combines points after participant postprocessing and does
not preserve participant identity. Therefore:

- point-equal aggregation is possible directly;
- participant-equal aggregation is not possible from this file alone;
- any claim of participant-equal weighting requires an additional participant
  mapping or a regenerated processed format.

This limitation must be addressed explicitly in the metrics/aggregation audit.

## Versioning and Distribution

Large datasets, OBJ files, GT, old CSVs, new gaze JSONs, and placement JSONs must
be distributed through GitHub Releases, not copied manually between agents or
servers.

The next release candidate must include:

- canonical placement JSONs built from `jsons/object_placement/`
- new processed fixation JSONs
- old CSVs for migration/audit
- validated OBJ/GT archives
- manifest with counts, SHA-256 checksums, and known exclusions

The two participant data types must use unambiguous archive names:

```text
participant_gaze_csv_original.zip
participant_fixations_processed_offset_2000.zip
```

They must never be merged into one archive or silently substituted for each
other.

Do not overwrite `v1.0-data`. Build and validate a new versioned release
candidate first.
