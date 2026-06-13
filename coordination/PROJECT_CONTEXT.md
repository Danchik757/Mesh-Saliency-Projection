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
   `participant_data/processed_fixations_offset0_full_cleaned/`.
4. Derive one full-turn frame count from placement JSON.
5. Pair `gaze[k]` with `placement[k]` from frame 0 and drop the trailing 60
   frames.
6. Transfer points to mesh vertices or faces with a projection method.
7. Aggregate participant evidence into a prediction map.
8. Normalize prediction and GT according to each metric's definition.
9. Calculate metrics and generate diagnostic previews.
10. Save per-model reports and compact CSV summaries.

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
| Original participant CSVs | external `GAZE_DATA/csv_for_models/`, release-packaged |
| New postprocessed gaze JSONs | `participant_data/processed_fixations_offset0_full_cleaned/` |
| Dataset indexes | `jsons/dataset_model_info/` |
| Projection methods | `reprojection_methods/` |
| Shared metrics | `metrics/` |
| Batch launchers | `test/launch/` |
| Alignment validation | `tools/mesh-saliency-tools/alignment/`, `debug/` |
| Prediction/GT previews | `tools/mesh-saliency-tools/heatmaps/` |
| Video generation | `tools/mesh-saliency-tools/video/`, `render_reference/` |
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
