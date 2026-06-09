# Approved Decisions

Approved by the user on 2026-06-09. These decisions are binding until explicitly
revised.

## 1. Large Data Distribution

- keep code, small manifests, validators, and documentation in normal git;
- distribute OBJ, GT, old CSV, processed fixation JSON, and placement JSON
  snapshots as versioned GitHub Release assets;
- do not commit the current 517 MB `participant_data/` payload to ordinary git
  history.

Reason: normal git history would permanently carry every large data revision;
release assets allow immutable versioned benchmark inputs with checksums.

## 2. Replacement Release Tag

```text
v2.0-data-rc1
```

Do not overwrite `v1.0-data`. Promote a later validated candidate to a stable
tag only after release-only smoke tests pass.

## 3. Timing Contract

Apply `1.8 s` start crop and `0.2 s` end crop to every dataset, method, placement
JSON timeline, and source-video diagnostic. Determine full-turn duration from
placement JSON:

- 17-second tracks: 15-second / 450-frame usable window;
- 24-second SAL3D: 22-second / 660-frame usable window.

The frame pairing still requires visual proof before final benchmark acceptance.

## 4. Invalid or Missing Processed Fixations

- block `3DVA_jessi` from processed-fixation benchmarks until its 510-frame file
  is regenerated or the 41-frame file is explained and explicitly supported;
- block `SAL3D_gorgoile` until its processed fixation JSON is produced;
- never silently fall back to old CSV for these models in a processed-JSON run.

## 5. Worker Start Point

- review the current dirty working tree and this coordination package;
- create one reviewed baseline commit;
- push it to `reproject-benchmark`;
- create and push the immutable `BASE_REF` from `coordination/TASK_OWNERSHIP.md`;
- only then allow the two worker branches to edit implementation code.

## 6. Server Runs

- no server execution before each worker's local/unit smoke test and
  reviewer/controller review;
- CPU experiments on `vg-intellect-1.lab.graphicon.ru`;
- Blender/render/video work on `vg-gpu-01.lab.graphicon.ru`;
- exactly three GPUs only after checking current availability;
- all work below `/mnt/ssd1/29d_kon/acm_2026`.

## 7. Work Phases

Phase 1 has strict priority: remove all blockers, integrate changes, publish the
release/baseline, run release-only smoke tests, and start correct full metric
runs.

Phase 2 begins only after the reviewer/controller confirms Phase 1 metric runs
are correctly running. It includes heatmap improvements, sigma sweep, heatmap
video renderer, and the research method.
