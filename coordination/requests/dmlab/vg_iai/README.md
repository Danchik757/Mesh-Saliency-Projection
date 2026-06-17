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

Rebuild the full set:

```bash
python3 test/launch/build_server_sigma_request_set.py \
  --out-dir coordination/requests/dmlab/vg_iai \
  --host vg-iai \
  --checkout-root /mnt/ssd1/29d_kon/summer_2026/Mesh-Saliency-Projection \
  --request-root-on-server /mnt/ssd1/29d_kon/summer_2026/Mesh-Saliency-Projection/coordination/requests/dmlab/vg_iai \
  --results-root /mnt/ssd1/29d_kon/summer_2026/results
```

Run one branch on the server using the `command_str` field from the corresponding
`*.server_manifest.json`.
