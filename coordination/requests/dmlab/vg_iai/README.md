# `vg-iai` dataset-level sigma branch contracts

This directory stores the **request JSON** and **server manifest JSON** files for
dataset-level sigma ablation branches on `vg-iai`.

Contract:

- one branch per `(dataset, method)` pair;
- stage: `sigma`;
- subset: full canonical `jsons/dataset_model_info/*_models.json` inventory;
- timing contract: `one_turn_from_start`;
- fixed `delay_seconds = 0.0`;
- fixed `frame_offset = 0`;
- refined sigma stage enabled unless explicitly disabled.

Each `*.json` request is the input for:

- `test/launch/screen_space_dataset_ablation.py`, or
- `test/launch/cone_dataset_ablation.py`

Each `*.server_manifest.json` is the corresponding **low-priority** server-run
contract emitted by `test/launch/dataset_ablation_server.py`. It never launches
the job; it only pins:

- `repo_commit`
- `checkout_root`
- `request_path`
- `results_root`
- `nice -n 19 ionice -c 2 -n 7`
- expected static candidate run IDs for monitoring/resume

Rebuild the full set for the currently available `vg-iai` runtime roots:

```bash
python3 test/launch/build_server_sigma_request_set.py \
  --out-dir coordination/requests/dmlab/vg_iai \
  --host vg-iai \
  --checkout-root /mnt/ssd1/29d_kon/summer_2026/Mesh-Saliency-Projection \
  --request-root-on-server /mnt/ssd1/29d_kon/summer_2026/Mesh-Saliency-Projection/coordination/requests/dmlab/vg_iai \
  --results-root /mnt/ssd1/29d_kon/summer_2026/results \
  --python /mnt/ssd1/29d_kon/acm_2026/environments/reproject-benchmark/bin/python3 \
  --release-tag v2.0-data-rc3 \
  --fixation-root /mnt/ssd1/29d_kon/acm_2026/shared_release_data/v2.0-data-rc3/extracted/participant_fixations_offset0_full_cleaned \
  --three-dva-dataset-root /mnt/ssd1/29d_kon/acm_2026/shared_release_data/v2.0-data-rc3/extracted/datasets/3DVA \
  --three-dva-json-root /mnt/ssd1/29d_kon/summer_2026/Mesh-Saliency-Projection/jsons/object_placement/3dva_jsons \
  --three-dva-combined-gt-dir /mnt/ssd1/29d_kon/acm_2026/shared_release_data/v2.0-data-rc3/extracted/datasets/3DVA/CombinedGT \
  --meshmamba-json-root /mnt/ssd1/29d_kon/summer_2026/Mesh-Saliency-Projection/jsons/object_placement/mamba_non_jsons \
  --meshmamba-rgb-json-root /mnt/ssd1/29d_kon/summer_2026/Mesh-Saliency-Projection/jsons/object_placement/mamba_rgb_jsons \
  --meshmamba-non-texture-root /mnt/ssd1/29d_kon/acm_2026/shared_release_data/v2.0-data-rc3/extracted/datasets/MeshMamba \
  --meshmamba-rgb-texture-root /mnt/ssd1/29d_kon/acm_2026/shared_release_data/v2.0-data-rc3/extracted/datasets/MeshMamba \
  --sal3d-json-root /mnt/ssd1/29d_kon/summer_2026/Mesh-Saliency-Projection/jsons/object_placement/sal3d_jsons \
  --sal3d-dataset-root /mnt/ssd1/29d_kon/acm_2026/shared_inputs/sal3d_benchmark_pkg \
  --sal3d-fixed-gt-dir /mnt/ssd1/29d_kon/acm_2026/shared_inputs/sal3d_benchmark_pkg/sal3d_fixed_face_gt \
  --sal3d-manifest /mnt/ssd1/29d_kon/acm_2026/shared_inputs/sal3d_benchmark_pkg/sal3d_manifest.csv
```

Run one branch on the server using the `command_str` field from the corresponding
`*.server_manifest.json`.
