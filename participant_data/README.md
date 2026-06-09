# Participant Data

This directory stores repository-local participant-side gaze data that is
separate from the canonical object placement / camera JSON files under
`jsons/object_placement/`.

## Layout

| Directory | Contents |
| --- | --- |
| `collected_gaze_csv_by_model/` | Per-model participant CSV files copied from `GAZE_DATA/csv_for_models/`. These keep explicit `t/x/y` gaze samples plus session metadata. |
| `processed_fixations_offset_2000/` | Postprocessed frame-wise `fixations.json` grouped by object. These are screen-space pixel points with implicit timing by frame index. |

Current local copy:

- `collected_gaze_csv_by_model/`: `299` files/directories in the copied tree
- `processed_fixations_offset_2000/`: `298` object folders with `fixations.json`
- structurally valid processed fixation files: `297`
- known invalid processed object: `3DVA_jessi` has `41` frames instead of `510`
- known missing processed object relative to placement JSON inventory:
  `SAL3D_gorgoile`

## Important distinction

- `jsons/object_placement/...` describes the object, camera, video, and per-frame
  transform.
- `participant_data/processed_fixations_offset_2000/.../fixations.json`
  describes participant fixation/gaze observations on the screen.

They serve different stages of the pipeline and should not be mixed.

## Timing convention

`processed_fixations_offset_2000/*/fixations.json` does not store explicit
timestamps per point. Time is encoded by the outer array index:

- outer length = `video_info.total_frames`
- the processed timeline starts after the upstream 2.0-second gaze offset;
- for benchmark pairing, processed gaze frame `k` corresponds to placement/video
  frame `round(1.8 * fps) + k`;
- only the one-full-turn prefix is consumed: `450` processed frames for
  17-second tracks and `660` processed frames for SAL3D;
- placement timestamps and rotations must be read from the matching canonical
  JSON in `jsons/object_placement/...`.

For example:

- `3DVA` / `MeshMamba`: `510` outer entries = `17 s × 30 fps`
- `SAL3D`: `720` outer entries = `24 s × 30 fps`

The common `1.8 s` start crop and `0.2 s` end crop is documented in
`coordination/DATA_CONTRACT.md`. It leaves one full turn:

- `450` frames / `15 s` for 17-second 3DVA and MeshMamba videos;
- `660` frames / `22 s` for 24-second SAL3D videos.

Do not reinterpret the full outer-array length as `processed[i] -> video[i]`.
The explicit pairing rule is `processed[k] -> placement[start_frame + k]`.

## Format

```text
fixations[frame_index][point_index] = [x_px, y_px]
```

The new JSON does not contain participant IDs or explicit timestamps. This means
it supports direct point-equal aggregation, but it cannot independently
reconstruct participant-equal aggregation.

## Current status

These files are staged locally inside the repository tree for reproducibility.
The required distribution mechanism is a versioned GitHub Release asset with a
manifest and checksums. Do not add the large payload to ordinary git history
until the release/data contract is reviewed.
