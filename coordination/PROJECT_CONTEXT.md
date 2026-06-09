# Project Context

## Goal

The project transfers participant gaze observations from rendered video frames
onto 3D meshes, aggregates the transferred signal into saliency maps, and
compares predictions with dataset ground truth.

The two fully implemented reference methods currently under active study are:

- `screen_space_gaussian`
- `cone_gaussian_on_mesh`

The final objective is a reproducible benchmark across 3DVA, MeshMamba
non-texture, MeshMamba RGB-texture, and SAL3D, using the same validated input
contract, alignment policy, aggregation policy, and metric definitions.

## Pipeline

For each object:

1. Load the dataset OBJ and GT map.
2. Load the canonical object-placement JSON from `jsons/object_placement/`.
3. Load processed participant screen points from
   `participant_data/processed_fixations_offset_2000/`.
4. Crop `1.8 s` from the beginning and `0.2 s` from the end, deriving the
   resulting full-turn window from placement JSON.
5. Pair each gaze frame with the correct placement/video frame.
6. Transfer points to mesh vertices or faces with a projection method.
7. Aggregate participant evidence into a prediction map.
8. Normalize prediction and GT according to each metric's definition.
9. Calculate metrics and generate diagnostic previews.
10. Save per-model reports and compact CSV summaries.

The current evaluators still read old participant CSVs directly. Migrating them
to the new processed JSON contract is delegated work and must be reviewed before
new full benchmark results are accepted.

The current 3DVA geometry/FOV checkpoint has useful local smoke evidence, but it
must be labeled `old_csv_no_common_crop`. It processes more than the approved
single-turn interval and is not a metric baseline.

The old CSV and new processed JSON remain separate release inputs:

- old CSV is retained for provenance, participant-aware diagnostics, and
  migration checks;
- processed JSON is the required default input for new metric runs.

## Dataset Semantics

| Dataset | Tracks | Prediction/GT support | Placement JSON count | Processed fixation status |
| --- | --- | --- | ---: | --- |
| 3DVA | one | per-vertex | 32 | 32 present, `jessi` invalid length |
| MeshMamba | non_texture, rgb_texture | per-face | 105 + 105 | 210 present and structurally valid |
| SAL3D | one | per-vertex / dataset-specific support | 57 | 56 present, `gorgoile` missing |

## Canonical Repository Locations

| Data or code | Location |
| --- | --- |
| Corrected placement/camera/animation JSON | `jsons/object_placement/` |
| Old participant CSVs | `participant_data/collected_gaze_csv_by_model/` |
| New postprocessed gaze JSONs | `participant_data/processed_fixations_offset_2000/` |
| Dataset indexes | `jsons/dataset_model_info/` |
| Projection methods | `reprojection_methods/` |
| Shared metrics | `metrics/` |
| Batch launchers | `test/launch/` |
| Alignment validation | `test/blender_canonical/`, `test/tools/` |
| Prediction/GT previews | `gt_visualizations/`, `visualization/` |
| Video generation | `video_creation/`, `references/render_scripts/` |
| Historical agent logs | `trash/Claude.md`, `trash/GPT.md` |

## Known Correctness Risks

1. Incorrect object-placement JSON or transform order can produce plausible
   output with incorrect projection.
2. Incorrect FOV interpretation can significantly reduce IoU and metrics.
3. Different Blender versions handle OBJ import axes differently.
4. Old CSVs and new fixation JSONs encode time differently.
5. The new fixation JSONs do not retain participant IDs, so participant-equal
   weighting cannot be reconstructed from them unless an additional mapping is
   provided.
6. A metric can be mathematically correct but methodologically inappropriate
   for a particular GT/support definition.
7. 3DVA rotating-video observations and original static-view GT represent
   different viewing conditions.
8. Existing batch `--resume` behavior can reuse reports from a different
   participant-input/timing contract unless provenance is checked.
9. Cone angular sigma must use camera-to-hit depth; near-plane-to-hit depth is
   not the exact angular-cone definition.

## Authority Rules

- Current technical truth must be supported by code, a reproducible command, and
  a committed artifact or report.
- Historical claims in `trash/*.md` are not automatically current truth.
- No full benchmark result is accepted unless its report records input versions,
  timing mode, projection mode, transform mode, and metric configuration.
- No new method is promoted based only on one model or one metric.
