# Participant Data

This directory stores repository-local participant-side gaze data that is
separate from the canonical object placement / camera JSON files under
`jsons/object_placement/`.

## Layout

| Directory | Contents |
| --- | --- |
| `processed_fixations_offset0_full_cleaned/` | Canonical tracked frame-wise `fixations.json` grouped by object. These are cleaned screen-space pixel points with implicit timing by frame index. |

Original participant CSV files remain external at `GAZE_DATA/csv_for_models/`
and are packaged into the data release through
`scripts/build_release_candidate.py --participant-csv-source`.

- `processed_fixations_offset0_full_cleaned/`: `298` object folders with `fixations.json`
- structurally valid processed fixation files: `297`
- known invalid processed object: `3DVA_jessi` has `41` frames instead of `510`
- known missing processed object relative to placement JSON inventory:
  `SAL3D_gorgoile`

## Important distinction

- `jsons/object_placement/...` describes the object, camera, video, and per-frame
  transform.
- `participant_data/processed_fixations_offset0_full_cleaned/.../fixations.json`
  describes participant fixation/gaze observations on the screen.

They serve different stages of the pipeline and should not be mixed.

## Timing convention

`processed_fixations_offset0_full_cleaned/*/fixations.json` does not store explicit
timestamps per point. Time is encoded by the outer array index:

- outer length = `video_info.total_frames`
- the processed timeline starts at frame `0`;
- benchmark pairing is `gaze[k] -> placement[k]`;
- only the one-full-turn prefix is consumed: `450` processed frames for
  17-second tracks and `660` processed frames for SAL3D;
- placement timestamps and rotations must be read from the matching canonical
  JSON in `jsons/object_placement/...`.

For example:

- `3DVA` / `MeshMamba`: `510` outer entries = `17 s × 30 fps`
- `SAL3D`: `720` outer entries = `24 s × 30 fps`

The benchmark keeps one full turn from the beginning and drops the trailing
frames:

- `450` frames / `15 s` for 17-second 3DVA and MeshMamba videos;
- `660` frames / `22 s` for 24-second SAL3D videos.

The explicit pairing rule is `processed[k] -> placement[k]` for the one-turn
prefix.

## Format

```text
fixations[frame_index][point_index] = [x_px, y_px]
```

The new JSON does not contain participant IDs or explicit timestamps. This means
it supports direct point-equal aggregation, but it cannot independently
reconstruct participant-equal aggregation.

## Current status

These files are tracked in Git for reproducibility and are also distributed in
the versioned GitHub data release with a manifest and checksums.
