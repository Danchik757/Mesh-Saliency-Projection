# Project State — 2026-06-10

This document is the current reviewer/controller state for the benchmark work.
It is intended for handoff between agents and for avoiding repeated mistakes.

## Current Priority

1. Integrate the cropped-reset fixation loader.
2. Validate smoke metric runs with the new fixation JSON format.
3. Resolve SAL3D GT/OBJ domain handling before treating SAL3D metrics as final.
4. Only after correct metric smoke runs, continue final heatmap rendering and
   larger sweeps.

## Branch State

Known good integration base:

```text
origin/reproject-benchmark @ b6ff18a
```

macOS fixation-format work:

```text
branch: agent/macos-fixation-format-v2
reported HEAD: 792f0b7
base: origin/reproject-benchmark @ b6ff18a
tests: 194 passed
compileall: clean
```

The A3 logic is accepted in principle, but must be reviewed from the pushed
branch before final integration.

## Fixation JSON Contract

Production processed fixation input is now the cropped-reset format from:

```text
/Users/admin/Downloads/mesh_json_2__offset_2000
```

Semantics:

```text
17-second tracks:
  fixations length: 450
  processed_gaze[0:450] -> placement[54:504]

24-second SAL3D tracks:
  fixations length: 660
  processed_gaze[0:660] -> placement[54:714]
```

The fixation index is reset to zero after upstream removal of the initial
offset. The placement/video timeline is still cropped with:

```text
start crop = 1.8 seconds = 54 frames at 30 fps
end crop   = 0.2 seconds = 6 frames at 30 fps
```

Required provenance for new reports:

```text
input_mode = processed_json
fixation_format = cropped_reset_offset_2000
fixation_start_index = 0
placement_start_frame = 54
placement_end_frame_exclusive = 504 or 714
```

Old full-length reports without `fixation_format` must not be reused with
`--resume`.

Known fixation blockers:

```text
3DVA_jessi: empty cropped-reset fixation file, excluded
SAL3D_gorgoile: no participant fixation JSON, excluded from our gaze metrics
```

## SAL3D Data Interpretation

SAL3D has three relevant data types per object:

```text
Meshes/<model>.obj
Gaze/<model>.txt
Smooth Gaze/<model>_neighbors.txt
```

`Gaze/*.txt` is raw ground truth in gaze-indexing. It normally has 20000 rows
and 8 columns:

```text
columns 0:3  -> xyz of gaze mesh vertices
columns 3:6  -> normals
column 6     -> continuous fixation density, used as raw GT
column 7     -> binary fixation label, not the main benchmark GT
```

`Smooth Gaze/*.txt` contains neighbor lists in gaze-indexing. It contains no
saliency values by itself.

Important: after mesh repair or if the OBJ has a different vertex count, raw
`Gaze/*.txt` must not be compared to OBJ vertices by index.

Correct repaired/fixed SAL3D interpretation:

```text
OBJ: data/SAL3D_almost_fixed/Meshes/<model>.obj
GT:  SAL3D_NPZ_almost/<model>.npz -> target
domain: per-face
target length == number of OBJ faces
```

The fixed pipeline:

1. Loads raw `Gaze[:, 6]` in gaze-indexing.
2. Min-max normalizes it to `[0, 1]`.
3. Applies Smooth Gaze propagation in gaze-indexing.
4. Repairs mesh if needed.
5. Transfers smoothed GT to repaired mesh vertices using KDTree nearest gaze
   point in the file coordinate frame.
6. Converts per-vertex GT to per-face GT by averaging the three face vertices.
7. Min-max normalizes final per-face `target` to `[0, 1]`.

Current fixed SAL3D manifest says there are 55 usable models. Excluded models:

```text
AudiRS5, bimba, blade: OBJ version mismatch with gaze data
gamecontroller, spanner: OBJ exists but no GT
```

For our participant-gaze benchmark, `gorgoile` is additionally excluded until a
processed fixation JSON exists.

Problem models from old evaluator:

```text
MaxPlanck: raw Gaze rows 20000, fixed OBJ verts 19999, NPZ target faces 39994
meca:      raw Gaze rows 20000, fixed OBJ verts 15000, NPZ target faces 30012
sofa:      raw Gaze rows 20000, fixed OBJ verts 15125, NPZ target faces 30246
```

These should be evaluated through fixed per-face NPZ targets, not through raw
`Gaze/*.txt` vertex-index matching.

## Metric Normalization

Metric functions do their own metric-specific normalization:

- CC and Spearman operate on aligned numeric arrays.
- SIM min-max normalizes both maps and converts them to probability
  distributions.
- KLD converts GT and prediction to probability distributions and uses
  `KL(GT || prediction)`.
- MSE is computed after evaluator-side map normalization.
- NSS/AUC use their own saliency-map and fixation-mask semantics.

Do not assume all source files are already `[0, 1]`. Evaluators should record
the domain and any normalization used.

## Heatmap Normalization

Every rendered heatmap must normalize the displayed values independently to
`[0, 1]` before applying the colormap:

```python
if max_value > min_value:
    values01 = (values - min_value) / (max_value - min_value)
else:
    values01 = zeros_like(values)
```

This applies to:

- screen_space_gaussian predictions;
- cone_gaussian_on_mesh predictions;
- MeshMamba GT CSV;
- SAL3D fixed NPZ `target`;
- 3DVA CombinedGT if rendered later.

The renderer must report in its manifest:

```text
map_domain = face or vertex
input_min
input_max
display_normalization = minmax_per_map
colormap = jet
```

For comparison figures, identical normalization policy must be used for method
maps and GT maps. Do not use raw unbounded values directly with `jet`.

## Instructions For macOS Agent

Finish the current intermediate milestone before starting broad final rendering:

1. Keep A3 fixation-format branch ready for review and integration.
2. Audit SAL3D dataset organization using:
   - `dataset_organization.md`
   - `sal3d_fix.py`
   - `sal3d_manifest.md`
3. Produce a short technical note in `coordination/agents/MACOS_CLAUDE.md`
   explaining:
   - raw `Gaze/*.txt` versus `Smooth Gaze/*.txt` versus fixed NPZ;
   - why old vertex-index SAL3D comparison fails for MaxPlanck/meca/sofa;
   - why fixed NPZ `target` is per-face and already `[0, 1]`;
   - how heatmap values must be normalized to `[0, 1]` before rendering;
   - which SAL3D models are excluded and why.
4. Implement six-view renderer only after the reviewer explicitly clears it.
5. If implementing six-view renderer, require map-domain validation:
   - face map length must equal number of faces;
   - vertex map length must equal number of vertices;
   - otherwise fail with a clear status row.

## Data Request For SAL3D Fixed Package

Ask the SAL3D data-preparation agent for a compact benchmark package, not the
full 10.6 GB NPZ bundle:

```text
Please prepare a compact SAL3D benchmark package:

1. data/SAL3D_almost_fixed/Meshes/*.obj for all 55 usable models.
2. Extract only target from each SAL3D_NPZ_almost/<model>.npz into:
   sal3d_fixed_face_gt/<model>_faces.txt
3. Include docs/sal3d_manifest.md.
4. Include docs/sal3d_checksums.md5.
5. Include a CSV manifest:
   model,n_vertices,n_faces,tier,obj_md5,npz_md5,gt_domain,gt_length
6. Ensure gt_domain=face and gt_length == n_faces for every row.
7. Exclude full NPZ ring/texture arrays unless explicitly requested later.

Also provide:
- archive path;
- archive MD5/SHA256;
- command to verify checksums after extraction.
```

This package is enough for our metric evaluators and heatmap renderers.

## Server Run Policy

Do not treat previous `full_20260609` results as final. They were produced
before the cropped-reset fixation contract was integrated.

After A3 integration:

1. Copy/stage the new fixation JSONs on the server.
2. Run release-only smoke on a few models:
   - 3DVA excluding jessi;
   - MeshMamba non_texture;
   - MeshMamba rgb_texture;
   - SAL3D excluding gorgoile.
3. Verify provenance in reports contains `fixation_format`.
4. Only then start full metrics.

CPU/GPU:

- current metrics are CPU-bound;
- `vg-iai` is preferred for full metric runs when free;
- sigma/KLD sweeps should use `vg-intellect` with low priority after the main
  metric pipeline is correct.
