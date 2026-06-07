# GPT Work Log And Execution Plan

Last updated: 2026-05-30

## Goal

Build a reproducible benchmark workflow for gaze-to-mesh reprojection methods
across `3DVA`, `MeshMamba`, and later `SAL3D`, with these constraints:

1. Before any large metric run, render at least one preview image per dataset
   to verify that mesh placement and camera framing are correct.
2. Use the code already implemented in this workspace as much as possible.
3. Transfer work to the server via normal `git` commits.
4. Use the server where the videos were previously rendered.
5. Run large jobs with low priority and occupy free nodes without blocking
   higher-priority work.
6. Keep a detailed step-by-step log here so any stage can be reconstructed or
   rolled back by commit.

## Repository Layout Added For This Workflow

1. `test/`
   Purpose: validation assets, preview scripts, pilot launch wrappers, and
   server-side run manifests that are still under active iteration.
2. `trash/`
   Purpose: working notes, coordination logs, and chronological decision
   history.

## Fixed Server Profile

This is the target machine for all large benchmark runs.

1. SSH host
   `vg-intellect`
2. Privilege level
   no `sudo`
3. Server work root
   `/home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING`
4. Server environment root
   `/home/29d_kon@lab.graphicon.ru/ssd1_link/environments`
5. Server dataset root
   `/home/29d_kon@lab.graphicon.ru/ssd1_link/datasets`
6. Known dataset folders under the server dataset root
   `3DVA`, `MeshMambaSaliency`, `SAL3D`
7. Code update policy
   only through GitHub commits
8. Side-input transfer policy
   use `scp` when `csv/json` side inputs are not already mirrored on the
   server
9. Session / launch style
   use `tmux`
10. Dependency policy
    install or update required packages only inside a user-owned conda
    environment under the environments root
11. Geometry metadata policy
    `json` camera/object metadata must be present on the server for correct
    preview rendering and reprojection
12. Metric policy
    compute the broadest reasonable metric set per dataset first, then discard
    metrics later only at the analysis stage if needed
13. Execution order
   local mini test -> server pilot -> full server run
14. Parallel run policy
   use many CPU workers, but only with low priority
15. CPU profile already reported by user
    `AMD EPYC 7532`, `64` logical CPUs

## Collaboration Protocol

There are two cooperating agents:

1. `GPT`
   Owns the main execution plan, user-facing synthesis, and integration.
2. `Claude`
   Owns delegated analysis and implementation subtasks, and records its work in
   `trash/Claude.md`.

Rules:

1. Read both `trash/GPT.md` and `trash/Claude.md` before starting a new block of
   work.
2. Every meaningful change should be tied to a commit hash once committed.
3. Each agent appends its own dated notes rather than overwriting history.
4. Open questions should be written explicitly instead of being left implicit in
   code.
5. If a change affects benchmark validity, note it in both the code commit
   message and the markdown log.
6. Each meaningful commit should get a new append-only log entry with concrete
   scope, files, results, risks, and next step.
7. Important analysis notes between commits should also be appended rather than
   replacing earlier entries.

## Current Technical Baseline

### Datasets

1. `3DVA`
   GT: `per-vertex`
   Status: ready for benchmarking
2. `MeshMamba non_texture`
   GT: `per-face`
   Status: ready for benchmarking
3. `MeshMamba rgb_texture`
   GT: `per-face`
   Status: likely ready, but should follow after `non_texture`
4. `SAL3D`
   GT: not ready-made in the current local dump; needs reconstruction from raw
   gaze samples

### Methods Already Available

1. `screen_space_gaussian`
   Native form: screen-space baseline
2. `cone_projection_on_mesh`
   Native form: mesh-space cone projection
3. `raycast_nearest_vertex`
   Local `3DVA` method
4. `cone_gaussian_on_mesh`
   Local `3DVA` method
5. `our_pipeline`
   Local `MeshMamba` face-level ray-casting pipeline
6. `our_pipeline + diffusion`
   Face-level smoothing variant
7. `our_pipeline + geodesic_kde`
   Face-level smoothing variant
8. MeshMamba-adapted reference methods
   `screen_space_gaussian` and `cone_projection_on_mesh`, converted to
   face-level outputs

## Benchmark Principles

1. Never compare `vertex-level` predictions directly against `face-level` GT.
2. Keep `3DVA` and `MeshMamba` as separate benchmark tracks.
3. Treat `SAL3D` as a later reconstruction track until dense GT is available.
4. Fix geometry and camera placement before drawing conclusions from metrics.
5. Keep `paper-aligned` metrics separate from diagnostic metrics.

## Phase Plan

### Phase 1. Preview Validation Per Dataset

Deliverable: one verified rendered image per dataset.

For each dataset:

1. Pick one representative model.
2. Render a camera-view preview from the same JSON/camera metadata used by the
   reprojection code.
3. Overlay at least a small set of gaze points when available.
4. Compare the preview against the corresponding real video frame.
5. Record whether the dataset requires:
   `recenter_to_bbox_center`, `extra_rotate_x_deg`, `override_fov_deg`, or no
   correction.

Target initial representatives:

1. `3DVA`: `bunny`
2. `MeshMamba non_texture`: `Aquarium_Deep_Sea_Diver_v1_L1` or one already used
   in `MAMBA_GAZE`
3. `MeshMamba rgb_texture`: one model with a matching JSON and GT pair
4. `SAL3D`: one model only for projection sanity, not yet for final metrics

Output contract for this phase:

1. Save one preview image per dataset.
2. Save one overlay variant when gaze overlay is supported.
3. Record the transform recipe used for that preview.
4. Treat this as a strict gate before any full metric run.

### Phase 2. Freeze Dataset-Specific Evaluation Protocols

Deliverable: a fixed metric and output contract per dataset.

1. `3DVA`
   Primary metrics: `CC/LCC`, `AUC_visible_top20`
   Secondary metrics: `Spearman`, `SIM`, `KLD`, `MSE`, `MAE`, `Cosine`,
   `hit_rate`, entropy-style diagnostics
2. `MeshMamba`
   Primary metrics: `CC`, `SIM`, `KLD`, `MSE`
   Secondary metrics: `Spearman`, `Cosine`, proxy `NSS/AUC`,
   `assignment_rate`, raw-vs-normalized variants when available
3. `SAL3D`
   Deferred until GT reconstruction is implemented and validated, but when it
   is ready we should compute the full `CC`, `MSE`, `KLDiv` family plus cheap
   diagnostics

### Phase 3. Pilot Model Set

Deliverable: a small calibrated comparison subset before any cluster-scale run.

1. `3DVA`
   Suggested pilot: `bunny`, `A380`, `dragon`, `chair107`, `flowerpot`,
   `car-vasa`
2. `MeshMamba non_texture`
   Suggested pilot: 5 to 10 geometry-diverse models
3. `MeshMamba rgb_texture`
   Start only after `non_texture` protocol is stable

Execution rule:

1. Run the first pilot locally in the current machine.
2. Use the same commands and manifests later on the server.
3. Only after local validation passes do we move to `vg-intellect`.

### Phase 4. Parameter Sweeps

Deliverable: one chosen default configuration per method family.

1. `cone`-style methods
   Sweep `sigma` and `radius_sigma_mult`
2. `MeshMamba diffusion`
   Sweep `steps` and `alpha`
3. `MeshMamba geodesic_kde`
   Sweep `sigma_scale` and `radius_scale`
4. Camera correction
   Decide whether corrections are:
   per-model, per-dataset, or mixed

### Phase 5. Server Packaging And Launch

Deliverable: commit-based server execution workflow.

Assumptions:

1. Datasets already exist on the server.
2. We need to transfer:
   repository code, run scripts, and participant-level input files if they are
   not already mirrored there.
3. Large runs should go to free nodes with low priority.
4. We cannot rely on `sudo`, so every setup step must live under user-writable
   paths.

Execution policy:

1. Prepare launch wrappers under `test/` or another tracked location.
2. Keep all run outputs and checked-out code under:
   `/home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING`
3. Keep all Python or other runtime environments under:
   `/home/29d_kon@lab.graphicon.ru/ssd1_link/environments`
4. Push all changes through GitHub as normal commits.
5. On the server, pull by commit hash or branch tip.
6. Mirror only the required `csv/json` side inputs when datasets are already
   present on the server.
7. Use low-priority parallel CPU execution after a pilot run passes.
8. Keep per-run manifests that map:
   dataset, method, parameter set, node allocation, output path, and commit
   hash.
9. Use `tmux` for long-running interactive control sessions.
10. Use `scp` when the required `csv/json` side inputs are missing on the
    server.
11. Treat `json` metadata as mandatory inputs, not optional helpers.

Parallelism policy:

1. Prefer dataset-level or model-level parallel fan-out.
2. Default to low-priority Linux execution such as `nice` and bounded worker
   counts.
3. Do not assume the machine is dedicated.
4. Keep the first full run conservative even though `64` CPUs are available.
5. Initial server pilot parallelism should start conservatively, around
   `8-16` workers, and increase only after checking real host load in `htop`.

### Phase 6. Full Benchmark Runs

Deliverable: dataset-level result tables.

1. `3DVA`
   Full 32-model run
2. `MeshMamba non_texture`
   Full benchmark after pilot and parameter freeze
3. `MeshMamba rgb_texture`
   Full benchmark after `non_texture`
4. `SAL3D`
   Separate track after GT reconstruction

### Phase 7. Final Analysis

Deliverable: comparison tables and method conclusions.

1. Per-model table
2. Per-dataset summary
3. Win-rate by metric
4. Notes on failures caused by geometry mismatch instead of algorithm weakness

## Immediate Next Actions

1. Add or adapt preview-render scripts so each dataset can produce one validated
   image locally.
2. Define one local mini-test manifest that will later be reused unchanged on
   `vg-intellect`.
3. Build a server-ready run manifest format tied to commit hashes and server
   paths.
4. Identify exactly which participant CSV and JSON assets must be mirrored to
   the server because datasets are already present there.
5. Prepare a low-priority parallel launch pattern for the server that does not
   require `sudo`.
6. Prepare a first pilot matrix for `3DVA` and `MeshMamba non_texture`.
7. Keep the first server pilot inside `tmux` and with conservative worker
   count.

## Logging Format

Append new entries in this format:

```text
## YYYY-MM-DD HH:MM TZ
Role: GPT
Commit: <hash or UNCOMMITTED>
Scope: <what was changed or analyzed>
Files: <paths>
Result: <main outcome>
Open questions: <if any>
Next step: <single next action>
```

## Initial Entry

```text
## 2026-05-30 MSK
Role: GPT
Commit: UNCOMMITTED
Scope: Created workflow folders and reset the project plan around preview
validation, per-dataset benchmarking, and server execution by commits.
Files: test/README.md, trash/GPT.md, trash/Claude.md
Result: Ready to delegate implementation and audit tasks while keeping a single
coordination log in-repo.
Open questions: none
Next step: delegate server/preview preparation subtasks to Claude.
```

## 2026-05-30 MSK
Role: GPT
Commit: UNCOMMITTED
Scope: Bound the benchmark plan to the actual `vg-intellect` server profile and
to the execution order `local mini test -> server pilot -> full server run`.
Files: trash/GPT.md
Result: The main plan now includes exact work root, environment root, dataset
root, GitHub-only code updates, no-sudo constraint, and low-priority parallel
execution policy for the 64-CPU server.
Open questions: scheduler availability, internet access on the server, exact
GitHub remote workflow, and preferred initial worker count.
Next step: wait for Claude's server-specific addendum, then create portable
preview and launch wrappers under `test/`.

## 2026-05-30 MSK
Role: GPT
Commit: UNCOMMITTED
Scope: Incorporated the user's clarifications about `tmux`, `scp`, mandatory
`json` transfer, broad metric collection, and append-only per-commit logging in
both agent markdown files.
Files: trash/GPT.md, trash/Claude.md
Result: The plan now assumes user-space conda setup, `tmux`-based long runs,
`scp` for side inputs, mandatory `json` metadata on the server, and detailed
append-only logs with each meaningful commit or analysis step.
Open questions: exact first pilot worker count and whether the first
`MeshMamba rgb_texture` preview may remain geometry-only.
Next step: convert these rules into portable `test/` wrappers and a local
mini-test manifest.

## 2026-05-30 MSK
Role: GPT
Commit: UNCOMMITTED
Scope: Implemented the first repo-local portable preview flow under `test/` and
ran a local sanity suite across four dataset manifests.
Files: test/tools/render_preview_from_manifest.py, test/launch/run_preview_manifest.sh,
test/launch/run_preview_suite.sh, test/env/local_paths.example.sh,
test/env/vg_intellect_paths.example.sh, test/manifests/preview_*.json,
test/README.md
Result: Local preview generation now works from manifest + env vars for
`3DVA`, `MeshMamba non_texture`, `MeshMamba rgb_texture`, and `SAL3D`.
Qualitative outcome: `bunny`, `Aquarium_Deep_Sea_Diver_v1_L1`, and `SAL3D A380`
look like plausible start points; `MeshMamba rgb_texture Starfruit_L3` is too
small in frame and needs a geometry recipe pass before server pilot.
Open questions: whether to calibrate a single representative `rgb_texture`
recipe next or defer that sub-track until `non_texture` pilot is stable.
Next step: review the second agent's pilot/transfer wrappers, then prepare the
first cleaned server-side side-input transfer plan and pilot wrapper set.

## 2026-05-30 MSK
Role: GPT
Commit: UNCOMMITTED
Scope: Extended the preview flow to use the user's local original-video folders
and generate side-by-side `video frame vs rendered preview` comparisons where a
matching mp4 is available.
Files: test/tools/render_preview_from_manifest.py, test/env/local_paths.example.sh,
test/manifests/preview_3dva_bunny.json,
test/manifests/preview_meshmamba_non_texture_starfruit.json,
test/manifests/preview_meshmamba_rgb_texture_starfruit.json, test/README.md
Result: Video-based comparisons now exist for `3DVA bunny`, `MeshMamba
non_texture Starfruit_L3`, and `MeshMamba rgb_texture Starfruit_L3`.
Qualitative outcome: `3DVA bunny` is already close in framing and pose; both
`MeshMamba Starfruit` previews are clearly too small in frame relative to the
source video and need geometry/camera calibration before server pilot.
Open questions: whether to keep `Aquarium` as the non-texture geometry recipe
reference while using `Starfruit` as the video-comparison representative.
Next step: either calibrate `MeshMamba Starfruit` against its real video next,
or freeze `3DVA` first and postpone the MeshMamba video-match pass.

## 2026-05-30 MSK
Role: GPT
Commit: UNCOMMITTED
Scope: Calibrated preview geometry against original videos for representative
`3DVA` and `MeshMamba` objects while preserving `json` as the base transform
source of truth.
Files: test/manifests/preview_3dva_bunny.json,
test/manifests/preview_meshmamba_non_texture_starfruit.json,
test/manifests/preview_meshmamba_rgb_texture_starfruit.json,
test/README.md
Result: Chosen local corrective recipes are now:
`3DVA bunny -> recenter=true, rotX=-45, fov=37.5`,
`MeshMamba Starfruit (non/rgb) -> recenter=true, rotX=90, fov=37.5`.
Qualitative outcome: `bunny` no longer has the obvious orientation mismatch
seen in the earlier compare frame; both `Starfruit` tracks now have the correct
vertical orientation and much closer framing, though fine per-model tuning may
still be needed before a full dataset sweep.
Open questions: whether `Starfruit` should remain the canonical video-match
reference for both `MeshMamba` tracks, or whether a second representative model
should be calibrated before server pilot.
Next step: review Claude's wrapper/transfer work, then package the first clean
side-input transfer manifests and server pilot commands.

## 2026-05-30 MSK
Role: GPT
Commit: UNCOMMITTED
Scope: Reviewed and corrected the first batch of server-facing launch/transfer
wrappers after Claude's initial implementation.
Files: configs/server_vg_intellect.env, test/launch/run_3dva_pilot.sh,
test/launch/run_meshmamba_non_texture_pilot.sh,
test/launch/mirror_side_inputs.sh, test/manifests/3dva_pilot.json,
test/manifests/meshmamba_non_texture_pilot.json, test/side_inputs/*
Result: server env now defaults to `WORKERS=12`; `3DVA` pilot wrapper now uses
an object-level low-priority pool; `MeshMamba non_texture` wrapper now points
to `run_meshmamba_gaze.py`, `SaliencyMap/non_texture`, and the real CLI
argument names; side-input inventory/pack scripts exist and local inventories
for `3DVA` and `MeshMamba non_texture` run successfully against real data.
Qualitative outcome: the first server-pilot path is now much closer to runnable
without manual path surgery, though final review is still needed before any
actual `scp` or `tmux` launch.
Open questions: whether to keep the current `MeshMamba` pilot centered on
`Starfruit_L3` only, or add one second representative validated model before
the first server run.
Next step: final review of uncommitted branch state, then prepare a clean commit
and the exact first transfer/launch commands.

## 2026-05-30 MSK
Role: GPT
Commit: UNCOMMITTED
Scope: Prepared the benchmark runtime for real metric runs, validated the
server environment, completed a focused `MeshMamba non_texture` comparison, and
started a separate `3DVA` top10 run using the corrected `-up` OBJ alignment.
Files: configs/server_vg_intellect.env, test/launch/run_metric_preflight.sh,
test/launch/run_3dva_raycast_cone.sh, test/launch/run_meshmamba_baseline_cone.sh,
test/launch/run_meshmamba_baseline_screen_space.sh,
test/launch/run_meshmamba_non_texture_pilot.sh,
test/tools/export_metrics_csv.py,
reprojection_methods/cone_projection_on_mesh/eval_3dva_raycast_cone.py,
reprojection_methods/cone_projection_on_mesh/eval_meshmamba_cone.py,
reprojection_methods/screen_space_gaussian/eval_meshmamba_screen_space.py,
trash/FULL_RUN_INSTRUCTIONS_2026-05-30.md
Result:
- server preflight on `vg-intellect` passes with the runtime env
  `/home/29d_kon@lab.graphicon.ru/ssd1_link/environments/reproject-benchmark`
- `rtree` was installed and smoke tests succeeded for:
  `MeshMamba screen_space`, `MeshMamba cone`, `MeshMamba our_pipeline+diffusion`,
  `3DVA bunny`
- a focused `MeshMamba non_texture` CSV was built at:
  `/home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/outputs/metrics_summary_meshmamba_non_texture_focus.csv`
  using four validated models:
  `Starfruit_L3`, `Mango_L3`, `Rubber_Duck_v1_L3`, `Rhinoceros_v1_L3`
- a separate `3DVA` top10 run was started in:
  `/home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/outputs_3dva_top10_20260530/3DVA/raycast_cone`
  with corrected alignment:
  `3DModels-Simplif-up`, `recenter=true`, `extra_rotate_x_deg=0`,
  JSON FOV (no override)
- a detailed continuation/handoff file was added:
  `trash/FULL_RUN_INSTRUCTIONS_2026-05-30.md`
Qualitative outcome:
- `MeshMamba` is now the cleanest completed comparison block and should be kept
  separate from `3DVA` and `SAL3D`
- `3DVA` server runs are using the correct corrected OBJ source and launcher
  recipe, but exact mask-overlay verification on server is not yet possible
  because `blender` and `3DVA` mp4 videos were not available there during this
  chat
- server repo HEAD checked during this phase was `9622219`, which is valid for
  the current `3DVA`/`MeshMamba` runs but not equal to the newest local working
  tree
Open questions:
- whether to push the latest local lowercase/alias-resolution patch before any
  future `Pear_L3` or case-sensitive path runs
- whether to transfer `3DVA` mp4 videos and install Blender on server for exact
  server-side mask overlay validation
Next step:
- finish the current `3DVA` top10 batch
- rebuild
  `/home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/outputs_3dva_top10_20260530/metrics_summary_3dva_top10.csv`
- summarize `raycast` and `cone` separately, preferably at `GT 413`
- only after that decide whether to expand to full `3DVA` or return to pending
  alias/overlay infrastructure work.

## 2026-05-31 MSK
Role: GPT
Commit: UNCOMMITTED
Scope: Audited unexpectedly poor metrics for `screen_space_gaussian` and
`cone_gaussian_on_mesh`, focusing on whether the implementation or the GT
comparison target is the main failure mode.
Files inspected/used:
`reprojection_methods/screen_space_gaussian/eval_meshmamba_screen_space.py`,
`reprojection_methods/cone_projection_on_mesh/eval_meshmamba_cone.py`,
server reports under
`/home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/outputs/`,
local MeshMamba CSV/JSON/OBJ/GT paths from `test/env/local_paths.example.sh`.
Findings:
- Server reports use the expected validated MeshMamba geometry recipe:
  `recenter=true`, `extra_rotate_x_deg=90`, JSON FOV (`override_fov_deg=null`)
  for the newest runs.
- Tried two experimental code changes locally: per-hit normalized cone Gaussian
  and centroid z-buffer visibility for screen-space. Both were runtime-valid,
  but they did not improve Starfruit metrics; they were reverted before commit.
- `screen_space_gaussian` split-half diagnostic on MeshMamba is very high:
  Starfruit `CC=0.988/Spearman=0.997`; Rubber Duck, Mango, Rhinoceros also
  `CC≈0.975-0.985` and `Spearman≈0.994-0.995`.
- `cone_gaussian_on_mesh` split-half diagnostic on Starfruit is also high:
  `CC=0.919/Spearman=0.959`.
- Despite high split-half stability, comparison to MeshMamba GT remains near
  zero or negative for these models. This strongly suggests the current low
  metrics are not caused by random projection failure; the collected gaze maps
  are internally consistent but do not match the MeshMamba GT saliency maps.
Changes kept:
- MeshMamba launchers now accept local/env-specific `MESHMAMBA_CSV_ROOT` and
  `MESHMAMBA_JSON_ROOT`, fall back from `REPROJECT_DATASET_MESHMAMBA_ROOT` and
  `REPROJECT_OUTPUT_ROOT`, and no longer fail on empty `OVERRIDE_FOV_DEG` under
  macOS bash `set -u`.
- `run_3dva_screen_space.sh` now respects `REPROJECT_PYTHON`.
Validation:
- `python3 -m py_compile` passes for the four active eval scripts.
- `PYTHONPATH=. pytest -q tests/test_metrics_smoke.py` passes.
- Local launcher smoke for `run_meshmamba_baseline_screen_space.sh` works with
  `GAZE_DATA/venv` and explicit MeshMamba CSV/JSON roots.
Risks:
- Do not interpret low MeshMamba GT metrics as proof that geometry alignment is
  wrong without an additional protocol/GT audit. The split-half numbers show
  the projected maps are stable across participants.
- Next useful check is to verify what MeshMamba `SaliencyMap/*.csv` represents
  and whether it is expected to correlate with the collected video-viewing gaze
  protocol.
Next step:
- Keep current method implementations unchanged except path/launcher fixes.
- Run a small table with both external-GT metrics and split-half reliability
  columns for `screen_space_gaussian` and `cone_gaussian_on_mesh`.

## 2026-06-01 MSK
Role: GPT
Commit: 390b0d3
Scope: Stage-1 audit only. No code changes after the snapshot commit.
Checked `EVAL_RUNBOOK.md` against the current eval scripts, launchers, and
path docs to define the authoritative per-dataset recipe and record current
contradictions before any cleanup or new metric runs.
Files:
`trash/EVAL_RUNBOOK.md`,
`trash/Claude.md`,
`reprojection_methods/cone_projection_on_mesh/eval_meshmamba_cone.py`,
`reprojection_methods/screen_space_gaussian/eval_meshmamba_screen_space.py`,
`reprojection_methods/cone_projection_on_mesh/eval_3dva_raycast_cone.py`,
`reprojection_methods/screen_space_gaussian/eval_3dva_screen_space.py`,
`reprojection_methods/cone_projection_on_mesh/eval_sal3d_cone.py`,
`test/launch/run_meshmamba_baseline_cone.sh`,
`test/launch/run_meshmamba_baseline_screen_space.sh`,
`test/launch/run_3dva_raycast_cone.sh`,
`test/launch/run_3dva_screen_space.sh`,
`DATA_PATHS.md`
Result:
Authoritative recipe table based on current code behavior:

| Dataset | Script | Current code recipe to use | GT |
|---|---|---|---|
| MeshMamba non_texture | `eval_meshmamba_cone.py` | `--texture-type non_texture --recenter-to-bbox-center --extra-rotate-x-deg 90 --projection-fov-mode horizontal_to_vertical --transform-order blender_rig` | per-face CSV |
| MeshMamba rgb_texture | `eval_meshmamba_cone.py` | same flags, but `--texture-type rgb_texture` and matching `csv/json` dirs | per-face CSV |
| MeshMamba non_texture | `eval_meshmamba_screen_space.py` | same geometry/FOV flags as cone, plus `--sigma-screen 0.05` | per-face CSV |
| 3DVA | `eval_3dva_raycast_cone.py` | `--recenter-to-bbox-center`; use `3DModels-Simplif-up`; compare against all 3 GT views `300/413/599` | per-vertex TXT |
| 3DVA | `eval_3dva_screen_space.py` | `--recenter-to-bbox-center`; use `3DModels-Simplif-up`; compare against all 3 GT views `300/413/599` | per-vertex TXT |
| SAL3D | `eval_sal3d_cone.py` | defaults already aligned: `gt_column=6`, `recenter=true`, `extra_rotate_x=90`, `projection_fov_mode=horizontal_to_vertical`, `transform_order=blender_rig` | per-vertex from `Gaze/*.txt` |

Main confirmed mismatches:
1. `MeshMamba` runbook and launchers are not in sync.
   Both launchers still default to `PROJECTION_FOV_MODE=vertical` and
   `TRANSFORM_ORDER=eval`, while the runbook says the correct recipe is
   `horizontal_to_vertical + blender_rig`.
2. `MeshMamba screen_space` still appears to lack the back-face culling fix.
   The issue is documented in `trash/Claude.md`, but the current code does not
   show the promised face-normal filtering in the active path.
3. `3DVA` runbook is internally contradictory:
   it recommends `--override-fov-deg 35.9834`, but later says the validated
   geometry recipe is `override_fov_deg=null (use JSON 60°)`.
   Current `run_3dva_raycast_cone.sh` follows the JSON-FOV path by default.
4. `3DVA` A380 special handling is documented but not implemented.
   Neither `eval_3dva_raycast_cone.py` nor `eval_3dva_screen_space.py`
   currently filters A380 CSV rows by `video_id`.
5. `MeshMamba` GT mismatch handling is partial.
   `Moai` fuzzy matching is plausibly covered by the current normalization.
   `Penguin_V2_L3 -> Penguin_v1_iterations-2.csv` is still not explicitly
   handled and should be treated as unresolved until proven by a run.
6. `DATA_PATHS.md` is not authoritative in its current state.
   It still mixes `vg-iai` server-era paths and old SAL3D wording
   (`Smooth_Gaze` as GT), while current eval logic uses `vg-intellect` and
   `Gaze/*.txt col.6` as the operative SAL3D GT source.

Interpretation:
The codebase now has three competing sources of truth:
`EVAL_RUNBOOK.md`, the current eval scripts, and the current launchers/docs.
Before cleanup or full runs, we should freeze one explicit authoritative
recipe per dataset and then bring launchers/docs into alignment with that
recipe in a separate code pass.
Open questions:
1. For `3DVA`, which FOV policy is authoritative for metrics:
   `override_fov_deg=35.9834` or `JSON 60° / override_fov_deg=null`?
2. For `MeshMamba screen_space`, is the back-face culling fix intentionally
   still pending, or was it expected to already be merged?
3. For `Penguin_V2_L3`, do we want an explicit GT alias table rather than
   relying on filename normalization heuristics?
Next step:
Do not change eval code yet. First freeze the authoritative recipe table in
human-readable form, then perform cleanup of non-essential files in a separate
commit, and only after that change launchers/docs to match the frozen recipe.

## 2026-05-31 MSK
Role: GPT
Commit: UNCOMMITTED
Scope: Added first single-gaze-point debug preview for checking CSV timestamp
to video frame to mesh raycast consistency.
Files changed:
`test/tools/debug_single_gaze_projection.py`
Files generated:
`test/output_local/single_point_debug/meshmamba_non_texture/Starfruit_L3/blender_rig/compare_json_fov_vs_fov37p5.png`
Findings:
- For `MeshMamba_non_texture / Starfruit_L3`, selected participant `28745`,
  timestamp `8.478s`, JSON frame index `254` (`json_t=8.4667s`).
- Red CSV gaze point and green reprojected raycast hit overlap with
  `pixel_error ~= 0`, so the ray construction and back-projection are internally
  consistent for the chosen transform/camera settings.
- The debug overlay shows an important visual issue: with JSON FOV (`60 deg`),
  the projected mesh mask is too small relative to the object in the extracted
  video frame. With `override_fov_deg=37.5`, the projected mask is visually much
  closer to the video object.
Risks:
- This is one point/frame/model only; do not change benchmark defaults until
  the same debug check is repeated across several frames and several MeshMamba
  models.
Next step:
- Generate the same debug preview for at least `frame~0`, `frame~100`,
  `frame~250`, `frame~400` and for at least `Mango_L3` / `Rubber_Duck_v1_L3`.

## 2026-05-31 MSK
Role: GPT
Commit: UNCOMMITTED
Scope: Extended `debug_single_gaze_projection.py` with mask IoU diagnostics and
tested MeshMamba FOV handling across several objects/timestamps.
Files changed:
`test/tools/debug_single_gaze_projection.py`
Generated outputs:
`test/output_local/single_point_debug_fov_iou/`,
`test/output_local/single_point_debug_fov_iou_grid/`
Changes:
- Added video-mask extraction from the real source video frame.
- Added projected-mesh-mask vs video-mask IoU, normalized centroid error, bbox
  size error, and mask comparison image.
- Added robust timestamp candidate search: if the nearest gaze point misses the
  mesh, the script tries nearby points before failing.
Findings:
- `json_fov` uses the JSON projection matrix (`fov_degrees ~= 60`) and gives
  IoU around `0.31` on MeshMamba non_texture because it treats the stored FOV as
  vertical FOV in the OpenGL-style projection. The projected mesh is too small.
- `override_fov_deg=37.5` is much better, IoU around `0.91`, but still not exact.
- The best value is not `37.5`; it is `35.98339777`, the vertical FOV derived
  from horizontal `60 deg` at aspect `16:9`:
  `vertical = 2 * atan(tan(horizontal / 2) / aspect)`.
- With `override_fov_deg=35.98339777` and `transform_order=blender_rig`, IoU at
  frame around `8.5s` is:
  Starfruit `0.9956`, Pear `0.9946`, Rubber Duck `0.9956`, Mango `0.9963`.
- Starfruit across timestamps `1.0/4.0/8.5/12.0/15.0s` stays high:
  `0.9940/0.9947/0.9956/0.9917/0.9948`.
- Transform order matters independently of FOV. With `FOV=37.5`, old `eval`
  order gives much lower IoU on some models (`Pear ~0.407`, Rubber Duck ~0.528`,
  Starfruit ~0.620), while `blender_rig` stays around `0.91`.
Interpretation:
- MeshMamba JSON likely stores the original Blender camera angle as horizontal
  FOV, but the saved projection matrix / current eval projection math uses it as
  vertical FOV. The benchmark code should not blindly reuse the JSON projection
  matrix for MeshMamba; it should either derive vertical FOV from the stored
  horizontal FOV and aspect ratio, or use the exact Blender camera projection
  convention.
Next step:
- Add canonical MeshMamba projection mode to both
  `eval_meshmamba_cone.py` and `eval_meshmamba_screen_space.py`:
  `transform_order=blender_rig` and `projection_fov_mode=horizontal_to_vertical`
  (or explicit `override_fov_deg=35.98339777` as a short-term launcher override).
- Rerun small metrics only after the eval scripts use this same geometry recipe.

## 2026-05-31 MSK
Role: GPT
Commit: UNCOMMITTED
Scope: Checked whether the negative MeshMamba metric smoke tests used
`override_fov_deg=37.5`, then ran a quick Starfruit retest with `37.5`.
Findings:
- The negative reports under
  `test/output_local/smoke_after_metric_fixes_launcher/` did NOT use `37.5`.
  Their `method_params.override_fov_deg` is `null`; they used the JSON
  projection matrix.
- They also used the old eval transform order:
  `base_rotate_z -> recenter -> scale -> rotation_z -> extra_rotate_x ->
  extra_rotate_y -> translation`.
- Quick retest with `OVERRIDE_FOV_DEG=37.5` was run for
  `MeshMamba_non_texture / Starfruit_L3`.
Results:
- `screen_space_gaussian`: old JSON FOV `CC=-0.194949`,
  `Spearman=-0.175986`, `SIM=0.335547`, `KLD=8.763546`; new `37.5`
  `CC=0.006084`, `Spearman=0.004534`, `SIM=0.724759`, `KLD=0.268168`.
- `cone_gaussian_on_mesh`: old JSON FOV `CC=-0.120387`,
  `Spearman=-0.137622`, `SIM=0.437408`, `KLD=3.116225`; new `37.5`
  `CC=-0.006520`, `Spearman=-0.024032`, `SIM=0.517984`, `KLD=2.806486`.
- `raycast_nearest_face`: old hit rate `0.221239`; new `37.5` hit rate
  `0.499444`.
Interpretation:
- `37.5` strongly improves scale-sensitive metrics and ray hit rate, but it
  does not fully fix correlation against GT because the eval scripts still do
  not use the `blender_rig` transform order that gives high mask IoU.
Next step:
- Patch MeshMamba eval scripts to support the same transform order used by the
  high-IoU debug preview, then rerun the same one-model smoke test.

## 2026-05-31 MSK
Role: GPT
Commit: UNCOMMITTED
Scope: Implemented and smoke-tested MeshMamba eval support for the high-IoU
preview recipe.
Files changed:
`reprojection_methods/cone_projection_on_mesh/eval_meshmamba_cone.py`,
`reprojection_methods/screen_space_gaussian/eval_meshmamba_screen_space.py`,
`test/launch/run_meshmamba_baseline_cone.sh`,
`test/launch/run_meshmamba_baseline_screen_space.sh`.
Code changes:
- Added `--transform-order {eval,blender_rig}`.
- Added `--projection-fov-mode {vertical,horizontal_to_vertical,json}`.
- `horizontal_to_vertical` with no explicit override reads `fov_degrees` from
  JSON (`~60 deg`) as horizontal FOV and derives effective vertical FOV
  (`35.9833989 deg` for 16:9).
- Launchers now accept `PROJECTION_FOV_MODE` and `TRANSFORM_ORDER`.
Validation:
- `py_compile` passed for both eval scripts and debug tool.
- `bash -n` passed for both launchers.
Smoke commands:
- `screen_space_gaussian`: `PROJECTION_FOV_MODE=horizontal_to_vertical`,
  `TRANSFORM_ORDER=blender_rig`, `PILOT_MODEL=Starfruit_L3`.
- `cone_gaussian_on_mesh`: same settings.
Results versus MeshMamba GT for `Starfruit_L3`:
- `screen_space_gaussian`, old `json+eval`: `CC=-0.194949`,
  `Spearman=-0.175986`, `SIM=0.335547`, `KLD=8.763546`.
- `screen_space_gaussian`, `37.5+eval`: `CC=0.006084`,
  `Spearman=0.004534`, `SIM=0.724759`, `KLD=0.268168`.
- `screen_space_gaussian`, `h2v+eval`: `CC=0.010507`,
  `Spearman=0.006391`, `SIM=0.719969`, `KLD=0.282286`.
- `screen_space_gaussian`, `h2v+blender_rig`: `CC=-0.311927`,
  `Spearman=-0.360560`, `SIM=0.720660`, `KLD=0.252931`.
- `cone_gaussian_on_mesh`, old `json+eval`: `CC=-0.120387`,
  `Spearman=-0.137622`, `SIM=0.437408`, `KLD=3.116225`,
  `hit_rate=0.221239`.
- `cone_gaussian_on_mesh`, `37.5+eval`: `CC=-0.006520`,
  `Spearman=-0.024032`, `SIM=0.517984`, `KLD=2.806486`,
  `hit_rate=0.499444`.
- `cone_gaussian_on_mesh`, `h2v+blender_rig`: `CC=0.064081`,
  `Spearman=-0.147117`, `SIM=0.599305`, `KLD=0.484604`,
  `hit_rate=0.942849`.
Interpretation:
- Geometry got much better in the strict sense: cone hit rate rose from `0.22`
  to `0.94`, matching the mask-IoU diagnostics.
- Metrics against MeshMamba GT did not become high. This means the remaining
  issue is likely not only screen-to-mesh projection. Candidate causes:
  GT protocol/semantics differ from our collected video-gaze protocol; GT face
  correspondence/orientation differs from the OBJ used for rendered videos; or
  the comparison should use a different saliency-map convention/normalization.
Next step:
- Do not launch full server metrics yet. First inspect whether MeshMamba GT
  face order and canonical orientation correspond to `MeshFile/non_texture`
  objects rendered in the videos, preferably by visualizing GT top faces and
  our projected top faces on the same mesh.

## 2026-05-31 MSK
Role: GPT
Commit: UNCOMMITTED
Scope: Current handoff note and task definition for Claude: FOV search and
current problem diagnosis.

### Current Technical State
- MeshMamba projection preview/debug now has two independent diagnostics:
  screen-to-ray-to-screen point consistency and projected mesh mask vs video
  object mask IoU.
- `test/tools/debug_single_gaze_projection.py` can generate a per-point debug
  preview and now writes `mask_metrics` into `report.json`.
- High video-mask IoU was obtained for MeshMamba non_texture with:
  `recenter_to_bbox_center=true`, `extra_rotate_x_deg=90`,
  `transform_order=blender_rig`, and effective vertical FOV near `35.9833989`.
- `35.9833989` is not an arbitrary tuned value; it is the vertical FOV derived
  from a horizontal `60 deg` FOV at aspect `16:9`:
  `vertical = 2 * atan(tan(horizontal / 2) / aspect)`.
- `37.5` is much better than using the JSON projection matrix directly, but it
  is not the best mask-IoU value in the current Starfruit/Pear/Rubber/Mango
  tests.
- Both MeshMamba eval scripts now support:
  `--transform-order {eval,blender_rig}` and
  `--projection-fov-mode {vertical,horizontal_to_vertical,json}`.
- The launchers now expose these as `TRANSFORM_ORDER` and
  `PROJECTION_FOV_MODE`.

### Important Smoke Results
- Previous negative metric reports did not use `37.5`; they used
  `override_fov_deg=null` and the old `eval` transform order.
- `screen_space_gaussian` on Starfruit:
  `json+eval`: `CC=-0.194949`, `Spearman=-0.175986`, `SIM=0.335547`,
  `KLD=8.763546`.
- `screen_space_gaussian` on Starfruit:
  `37.5+eval`: `CC=0.006084`, `Spearman=0.004534`, `SIM=0.724759`,
  `KLD=0.268168`.
- `screen_space_gaussian` on Starfruit:
  `horizontal_to_vertical+blender_rig`: `CC=-0.311927`,
  `Spearman=-0.360560`, `SIM=0.720660`, `KLD=0.252931`.
- `cone_gaussian_on_mesh` on Starfruit:
  `json+eval`: `CC=-0.120387`, `Spearman=-0.137622`, `SIM=0.437408`,
  `KLD=3.116225`, `hit_rate=0.221239`.
- `cone_gaussian_on_mesh` on Starfruit:
  `37.5+eval`: `CC=-0.006520`, `Spearman=-0.024032`, `SIM=0.517984`,
  `KLD=2.806486`, `hit_rate=0.499444`.
- `cone_gaussian_on_mesh` on Starfruit:
  `horizontal_to_vertical+blender_rig`: `CC=0.064081`,
  `Spearman=-0.147117`, `SIM=0.599305`, `KLD=0.484604`,
  `hit_rate=0.942849`.

### Current Problem
- We can make the projected mesh match the actual video object very well
  geometrically. This is proven by high mask IoU and high ray hit rate.
- However, high geometry correctness does not yet produce high correlation
  against MeshMamba GT face saliency maps.
- Therefore the remaining blocker is likely not only "wrong screen-to-mesh
  projection". The failure may be in the GT comparison target, face
  correspondence, coordinate convention, or saliency-map semantics.

### Working Hypotheses
- Hypothesis A: MeshMamba GT `SaliencyMap/non_texture/*.csv` is defined on the
  same OBJ face order, but it corresponds to a different viewing protocol or
  saliency definition than our collected video gaze CSV. This would explain high
  split-half reliability in our gaze maps but poor correlation with GT.
- Hypothesis B: MeshMamba GT face order or face orientation does not match the
  exact OBJ that was rendered in the videos. This would preserve good video
  alignment but break face-level GT comparison.
- Hypothesis C: The object pose in the videos is correct, but GT is in a
  canonical object coordinate system and needs an inverse/aggregation over
  rotations before comparison.
- Hypothesis D: The FOV/transform recipe should be selected by video-mask IoU,
  while GT metrics should be evaluated only after confirming GT face-index
  compatibility by visualizing top-GT faces on the same OBJ.
- Hypothesis E: Some metrics are scale/distribution sensitive. The improvement
  of SIM/KLD and hit rate after FOV fixes is real, but CC/Spearman can remain
  low if GT hotspots are semantically different or face correspondence is wrong.

### Task For Claude: MeshMamba FOV Search
Goal: determine the best FOV recipe for MeshMamba video alignment using
video-mask IoU, not GT correlation. Do not use GT metrics to tune FOV until the
face-level GT compatibility is separately verified.

Constraints:
- Work only in branch `reproject-benchmark`.
- Do not push, commit, scp to server, or run server jobs without explicit GPT
  approval.
- Keep all generated outputs under `test/output_local/`.
- Append findings to `trash/Claude.md`; do not overwrite existing notes.
- If code is changed, keep it small and reviewable. Prefer adding a helper
  script under `test/tools/` instead of modifying core eval logic unless needed.

Use this existing tool:
- `test/tools/debug_single_gaze_projection.py`
- Required local env can be loaded from `test/env/local_paths.example.sh`.
- For MeshMamba non_texture, use:
  `--dataset meshmamba_non_texture`,
  `--transform-order blender_rig`,
  `--recenter-to-bbox-center`,
  `--extra-rotate-x-deg 90`.

Suggested models:
- Minimum first pass:
  `Starfruit_L3`, `Pear_L3`, `Rubber_Duck_v1_L3`, `Mango_L3`.
- If first pass is stable, add diverse shapes:
  `Elephant_v01_l3`, `Fighter_Jet_SG_v1_L3`, `Cat_v1_L3`,
  `Aquarium_Deep_Sea_Diver_v1_L1`, `Bird_v1_L3`, `Boombox_v2_L3`.
- Resolve names case-insensitively because the repo has mixed case filenames.

Suggested timestamps:
- First pass: `1.0`, `4.0`, `8.5`, `12.0`, `15.0`.
- These map roughly to frames `30`, `120`, `255`, `360`, `450` at `30 FPS`.
- If a timestamp has no valid gaze hit, the debug tool should already try nearby
  candidate points. Record any failures.

Search procedure:
- Baselines to always include:
  `json_fov` / no override,
  `37.5`,
  `35.98339777`,
  `36.0`.
- Coarse FOV grid:
  `30.0` to `45.0` degrees, step `0.5`.
- Refined grid:
  around the best coarse FOV for each model, `best-1.0` to `best+1.0`,
  step `0.05`.
- Run with `transform_order=blender_rig` first.
- Optional control: repeat a small subset with `transform_order=eval` to confirm
  that `blender_rig` remains geometrically superior.

Metrics to collect from each `report.json`:
- `mask_metrics.iou`
- `mask_metrics.centroid_error_norm`
- `mask_metrics.size_error_norm`
- `mask_metrics.video_bbox_width/height`
- `mask_metrics.preview_bbox_width/height`
- selected `gaze_point.timestamp`
- `frame_mapping.json_frame_index_0_based`
- `transform.override_fov_deg`
- `transform.transform_order`

Expected output:
- A CSV summary, for example:
  `test/output_local/fov_search_meshmamba_non_texture/fov_search_summary.csv`.
- A JSON summary with per-model/per-timestamp aggregates:
  `test/output_local/fov_search_meshmamba_non_texture/fov_search_summary.json`.
- A short Markdown section appended to `trash/Claude.md` with:
  best FOV per model, global median best FOV, mean/median IoU for `37.5`,
  `35.98339777`, and best-grid FOV, plus failure cases.
- Save a few visual comparison panels for representative models:
  `json_fov` vs `37.5` vs best FOV.

Interpretation rules:
- If best FOV is consistently `35.98-36.00`, treat the correct recipe as
  "horizontal 60 degrees from JSON converted to vertical FOV".
- If best FOV varies materially by model, do not hardcode a dataset-wide
  numeric FOV. Investigate whether model scale/location or JSON export differs
  by model.
- If video-mask IoU is high but GT correlation remains low, do not keep tuning
  FOV to maximize GT. Move to GT face-order/semantics validation.

### Next Work After Claude's FOV Search
- Visualize top faces from MeshMamba GT and top faces from our predictions on
  the same OBJ to test face-index compatibility.
- If face-index compatibility is confirmed, investigate protocol mismatch
  between our gaze CSV and MeshMamba GT.
- If face-index compatibility fails, build a face remapping or use the exact GT
  mesh source expected by `SaliencyMap`.

## 2026-06-01 MSK — authoritative recipes synced, 3DVA FOV resolved, exceptions implemented

Context:
- Continued the post-cleanup eval normalization pass.
- Goal was to execute the first five stabilization items:
  1. lock authoritative recipes,
  2. sync launcher defaults,
  3. resolve 3DVA FOV policy,
  4. confirm/fix MeshMamba screen-space back-face issue,
  5. add explicit exception handling.

What was changed:
- `MeshMamba` eval defaults now match the validated recipe:
  - `recenter_to_bbox_center=True`
  - `extra_rotate_x_deg=90`
  - `projection_fov_mode=horizontal_to_vertical`
  - `transform_order=blender_rig`
- `MeshMamba` launchers were updated to the same defaults:
  - `test/launch/run_meshmamba_baseline_cone.sh`
  - `test/launch/run_meshmamba_baseline_screen_space.sh`
- `MeshMamba` GT lookup now falls back through the resolved OBJ stem.
  This removes the explicit `Penguin_V2_L3 -> Penguin_v1_iterations-2.csv`
  failure mode and also covers similar OBJ/GT stem mismatches.
- `MeshMamba screen_space` now performs actual back-face culling:
  - rotates `mesh.face_normals` per frame,
  - computes camera-facing test from `camera_world - face_centroid`,
  - suppresses non-front-facing faces before bilinear density sampling,
  - reports `culled_back_faces` in `run_stats`.
- `3DVA` authoritative FOV policy is now fixed to `override_fov_deg=35.9834`.
  Rationale was confirmed from the real JSON exports:
  - `fov_degrees ≈ 60`
  - `projection_matrix[1,1] ≈ 1.732`
  - therefore the stored matrix is vertical 60°, which implies horizontal
    `122.55°` at `16:9`, so it cannot be the intended render geometry.
  - Correct eval policy is `horizontal 60° -> vertical 35.9834°`.
- `3DVA` eval scripts now expose `--video-id` and record:
  - `video_id_filter`
  - `video_ids_present`
  - `video_ids_mixed`
- `3DVA` launchers now default to `OVERRIDE_FOV_DEG=35.9834` and accept
  optional `VIDEO_ID`.
- Docs updated:
  - `trash/EVAL_RUNBOOK.md`
  - `DATA_PATHS.md` (reduced authority, corrected server label, SAL3D note)

Targeted verification:
- `python3 -m py_compile` passed for all modified eval scripts.
- `Penguin_V2_L3` smoke (`eval_meshmamba_screen_space.py`) completed successfully.
  Report:
  - `/private/tmp/meshmamba_penguin_smoke/Penguin_V2_L3/smoke/Penguin_V2_L3_report.json`
  - GT resolved as `Penguin_v1_iterations-2.csv`
  - report includes `culled_back_faces`
  - projection metadata shows effective vertical FOV `35.98339890412515`
- `A380` smoke (`eval_3dva_screen_space.py --video-id 2365`) completed successfully.
  Report:
  - `/private/tmp/3dva_a380_smoke/A380/smoke/A380_report.json`
  - report includes `video_id=2365`
  - `gaze_stats.video_ids_present=[1970,2365]`
  - `gaze_stats.video_ids_mixed=true`

Operational note:
- Local system `python3` in this shell did not have `trimesh`; smoke runs were
  executed with `GAZE_DATA/venv/bin/python3`, which is the intended eval env.

## 2026-06-01 MSK — 3DVA overlay IoU check before pilot contradicts new FOV policy

Goal:
- Validate the current 3DVA geometry recipe with Blender/video overlay IoU
  before moving on to pilot metric runs.

Setup:
- Built dedicated manifests with the current eval-side FOV policy:
  `override_fov_deg=35.9834`
- Models checked: `bunny`, `chair107`, `flowerpot`, `A380`
- Manifests:
  - `test/manifests/preview_3dva_bunny_up_eval.json`
  - `test/manifests/preview_3dva_chair107_up_eval.json`
  - `test/manifests/preview_3dva_flowerpot_up_eval.json`
  - `test/manifests/preview_3dva_a380_up_eval.json`
- Batch summary:
  - `test/output_local/blender_mask_batch_3dva_up_eval359834/summary.json`

Important runtime note:
- `evaluate_blender_mask_batch.py` crashed with Blender `SIGSEGV` inside the
  sandbox, but succeeded outside the sandbox with the same command.

Results (old preview recipe `override_fov_deg=null` vs new `35.9834`):
- `bunny`:  `0.9784 -> 0.3561`
- `chair107`: `0.9330 -> 0.2132`
- `flowerpot`: `0.9559 -> 0.3115`
- `A380`: `0.9065 -> 0.1634`
- New batch mean IoU: `0.2611`

Interpretation:
- For the Blender/video overlay pipeline, `35.9834` is clearly wrong.
- The old preview manifests with `override_fov_deg=null` match the source video
  dramatically better than the new eval-side FOV override.
- Therefore we currently have a real split:
  - preview/overlay geometry says: use JSON/`fov60`
  - eval-side projection analysis had suggested: use `35.9834`

Consequence:
- Do **not** start the 3DVA pilot yet.
- First resolve why preview-space and eval-space disagree on FOV convention.
- Most likely next debug target is to inspect how Blender preview interprets
  `camera_static.fov_radians`/`cam_data.angle` versus how the eval scripts
  interpret `projection_matrix` and `build_projection_matrix_from_fov()`.

### Clarification after Claude.md + code audit

The apparent contradiction is now explained by API semantics:

1. **Blender preview pipeline** (`render_preview_from_manifest_blender.py`)
   does **not** use `camera_static["projection_matrix"]`.
   It reconstructs the camera from:
   - `lens_mm`
   - `sensor_width_mm`
   - `sensor_height_mm`
   - `fov_radians` or `override_fov_deg` via `cam_data.angle`

2. In the 3DVA JSON, these fields are internally consistent for a
   **horizontal 60° camera**:
   - `lens_mm = 31.1769`
   - `sensor_width_mm = 36`
   - horizontal FOV from lens/sensor = `60.0000°`
   - Blender preview with `override_fov_deg=null` therefore reproduces the
     source video correctly.

3. The stored JSON `projection_matrix` is a separate issue.
   From the real file:
   - `P[0,0] = 0.9742785`
   - `P[1,1] = 1.7320507`
   - interpreted as a standard OpenGL perspective matrix, that means:
     - vertical FOV = `60°`
     - horizontal FOV = `91.49°`
   This is **not** the intended physical camera.

4. Therefore:
   - for **preview / overlay / Blender canonical IoU**:
     use `override_fov_deg = null`
   - for **eval scripts that call `build_projection_matrix_from_fov()`**:
     `35.9834°` is still the correct **vertical** FOV corresponding to
     physical horizontal `60°` on `16:9`

5. The failed overlay batch with manifests set to `override_fov_deg=35.9834`
   was invalid as a geometry recipe because Blender's `cam_data.angle` in this
   pipeline is acting as the horizontal camera angle under the stored physical
   camera model. So that batch tested the wrong thing.

Practical consequence:
- The recent 3DVA eval-side FOV normalization does **not** automatically imply
  that preview manifests should also switch to `35.9834`.
- Preview and eval must currently be documented separately:
  - preview-space recipe: JSON lens/FOV (`override_fov_deg=null`)
  - eval-space recipe: explicit vertical override (`35.9834`) if using the
    standard matrix builder instead of the malformed JSON matrix

## 2026-06-01 MSK — 3DVA eval-side FOV debug on real gaze/GT (`bunny`)

Scope:
- separate **preview-space** correctness from **eval-space** correctness using
  one real 3DVA object and the in-repo eval math, not Blender IoU.

Files inspected:
- `trash/Claude.md`
- `reprojection_methods/cone_projection_on_mesh/eval_3dva_raycast_cone.py`
- `reprojection_methods/screen_space_gaussian/eval_3dva_screen_space.py`
- `GAZE_DATA/jsons_for_models/3DVA_json/3DVA_bunny.json`

Key Claude note used:
- session 9 explicitly recorded the same projection-matrix convention bug for
  `3DVA` eval scripts as for MeshMamba:
  JSON matrix encodes `P[0,0]=0.974`, `P[1,1]=1.732`, while the physically
  correct 60° horizontal camera on 16:9 should use
  `P[0,0]=1.732`, `P[1,1]=3.079`.

What was checked:
1. Geometry-only ray comparison for representative screen points.
2. One fast eval-side GT comparison on `bunny` using
   `eval_3dva_screen_space.py` internals with:
   - variant A: JSON `projection_matrix`
   - variant B: rebuilt vertical FOV `35.9834°`

Geometry facts:
- Center ray is identical for both matrices.
- Off-center rays differ materially:
  - top/bottom center point: `10.23°`
  - left/right center point: `14.60°`
- This confirms the two matrices are not a mild reparameterization; they send
  different rays through the same gaze coordinates.

`bunny` screen-space GT results (mean over views 300/413/599):
- JSON matrix:
  - `CC = 0.0048`
  - `SIM = 0.2948`
  - `KLD = 1.5280`
  - `MSE = 0.2584`
  - `Spearman = 0.0450`
  - `AUC_Judd_gt_top_10pct_proxy = 0.5433`
- Rebuilt `35.9834°`:
  - `CC = -0.0106`
  - `SIM = 0.2871`
  - `KLD = 1.7580`
  - `MSE = 0.1437`
  - `Spearman = 0.0234`
  - `AUC_Judd_gt_top_10pct_proxy = 0.5260`

Interpretation:
- On this real eval-side test, `35.9834°` does **not** produce a clear
  empirical win.
- It improves `MSE`, but is worse on `CC`, `SIM`, `KLD`, `Spearman`, and AUC.
- Therefore the current blanket switch to `override_fov_deg=35.9834` for 3DVA
  is **not yet validated by GT metrics**, even though the matrix is physically
  more plausible than the stored JSON matrix.

Current status:
- Preview-space recipe remains validated:
  `3DModels-Simplif-up`, `recenter=true`, `extra_rotate_x=0`,
  `override_fov_deg=null`
- Eval-space recipe is still unresolved:
  `JSON projection_matrix` vs rebuilt `35.9834°` needs more evidence than the
  current one-object screen-space test.

Additional spot-check: `A380` with `video_id=2365`, same screen-space A/B.

`A380` screen-space GT results (mean over views 300/413/599):
- JSON matrix:
  - `CC = -0.0686`
  - `SIM = 0.2012`
  - `KLD = 2.1293`
  - `MSE = 0.3085`
  - `Spearman = -0.0425`
  - `AUC_Judd_gt_top_10pct_proxy = 0.4450`
- Rebuilt `35.9834°`:
  - `CC = 0.0097`
  - `SIM = 0.1958`
  - `KLD = 2.4870`
  - `MSE = 0.1648`
  - `Spearman = -0.0858`
  - `AUC_Judd_gt_top_10pct_proxy = 0.4855`

Interpretation update:
- `A380` does show improvement for `35.9834°` on `CC`, `AUC`, and `MSE`.
- But even here the same override is worse on `SIM`, `KLD`, and `Spearman`.
- So the current evidence remains mixed:
  - `bunny`: JSON matrix looks better on most ranking/similarity metrics
  - `A380`: `35.9834°` looks better on `CC/AUC/MSE`
- This is still not strong enough to declare one global eval-side 3DVA FOV
  policy as fully validated.

Next step:
- run the same A/B check on at least one more 3DVA object beyond `bunny` and
  `A380`, and ideally also on the raycast/cone path, not only on the
  screen-space path.

## 2026-06-01 MSK — first server-side MeshMamba smoke after recipe normalization

Scope:
- push normalized benchmark branch to GitHub
- update `vg-intellect` checkout to `b991822`
- run one real server smoke on `MeshMamba non_texture` for
  `Rubber_Duck_v1_L3`

Server state:
- server worktree before update was at `2122e72`
- local benchmark branch had already advanced to `b991822` and was pushed:
  `reproject-benchmark -> origin/reproject-benchmark`
- server was then fast-forwarded to `b991822`

Server smoke command family:
- `test/launch/run_meshmamba_baseline_screen_space.sh`
- `test/launch/run_meshmamba_baseline_cone.sh`

Server output root:
- `/home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/outputs_smoke_20260601`

Model:
- `Rubber_Duck_v1_L3`

Applied recipe on server:
- `recenter_to_bbox_center=true`
- `extra_rotate_x_deg=90`
- `projection_fov_mode=horizontal_to_vertical`
- `transform_order=blender_rig`
- no explicit FOV override; scripts used
  `json_camera_static.fov_degrees=60.000001669652114` and converted it to
  `effective_vertical_fov_deg=35.98339890412515`

Results — screen-space baseline:
- report:
  `/home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/outputs_smoke_20260601/MeshMamba_non_texture/baseline_screen_space/Rubber_Duck_v1_L3/sigma0p05_recenter_rotx90p0_horizontaltovertical_blender_rig/Rubber_Duck_v1_L3_report.json`
- key metrics:
  - `CC = 0.2614`
  - `SIM = 0.5456`
  - `KLD = 2.7818`
  - `MSE = 0.07536`
  - `Spearman = 0.2635`
  - `AUC_Judd_gt_top_10pct_proxy = 0.6948`
- useful runtime diagnostic:
  - `culled_back_faces = 9127648`
  This confirms the new back-face culling path is active in the server run.

Results — cone baseline:
- report:
  `/home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/outputs_smoke_20260601/MeshMamba_non_texture/baseline_cone/Rubber_Duck_v1_L3/recenter_rotx90p0_horizontaltovertical_blender_rig/Rubber_Duck_v1_L3_report.json`
- `raycast_nearest_face`:
  - `CC = 0.1022`
  - `SIM = 0.2515`
  - `KLD = 12.2078`
  - `MSE = 0.01909`
  - `Spearman = 0.0344`
  - `AUC_Judd_gt_top_10pct_proxy = 0.5399`
- `cone_gaussian_on_mesh`:
  - `CC = 0.5963`
  - `SIM = 0.6169`
  - `KLD = 0.9350`
  - `MSE = 0.01455`
  - `Spearman = 0.4383`
  - `AUC_Judd_gt_top_10pct_proxy = 0.8848`
  - `hit_rate = 0.9451`

Interpretation:
- the normalized MeshMamba recipe now runs correctly on `vg-intellect`
- the cone baseline is clearly stronger than both:
  - raw `raycast_nearest_face`
  - screen-space baseline
- this reproduces the qualitative pattern already seen in earlier local
  validation for `Rubber_Duck`

Next step:
- extend the same server smoke to 1–2 additional MeshMamba models before any
  larger pilot batch, while leaving the 3DVA FOV question unresolved.

## 2026-06-01 MSK — consolidated next-work plan and ownership split

This is the current execution plan after:
- 3DVA preview/eval FOV divergence was confirmed
- first real server-side MeshMamba smoke passed on `Rubber_Duck_v1_L3`

### Priority order

1. **Do not start a full 3DVA pilot yet**
   `3DVA` still has an unresolved eval-side FOV policy.
   Preview-space is validated; eval-space is not.

2. **Continue MeshMamba first**
   `MeshMamba non_texture` is currently the most benchmark-ready track:
   geometry validated, server recipe validated, first server metrics obtained.

3. **Treat SAL3D as a bounded reconstruction track**
   The new eval script exists, but metric validity still needs masking of
   zero-GT/uncovered vertices on high-res OBJ models.

### Work phases

#### Phase A — stabilize logs and scratch state

Goal:
- keep only intentional planning changes in the worktree

Tasks:
- decide whether to keep or delete temporary `3DVA` manifests:
  - `test/manifests/preview_3dva_bunny_up_eval.json`
  - `test/manifests/preview_3dva_chair107_up_eval.json`
  - `test/manifests/preview_3dva_flowerpot_up_eval.json`
  - `test/manifests/preview_3dva_a380_up_eval.json`
- keep `trash/GPT.md` and `trash/Claude.md` updated
- no eval-logic changes in this phase

#### Phase B — resolve or explicitly bound the 3DVA eval FOV problem

Goal:
- stop treating `3DVA` FOV as implicitly solved

Required checks:
- run the same A/B (`JSON projection_matrix` vs rebuilt `35.9834°`) on at
  least 1–2 more 3DVA objects
- include not only `screen_space`, but also `raycast/cone`
- prefer one additional simple model plus one complex model beyond
  `bunny` and `A380`
- if results remain mixed, document `3DVA` as having:
  - validated preview-space recipe
  - unresolved eval-space policy

Exit condition:
- either one recipe wins consistently enough to standardize
- or we freeze `3DVA` as an explicitly split track and postpone pilot

#### Phase C — expand MeshMamba server smoke into a mini pilot

Goal:
- confirm server reproducibility on more than one model before scaling out

Required checks:
- run the same server smoke for 1–2 more `MeshMamba non_texture` models
- recommended next models:
  - `Mango_L3`
  - `Rhinoceros_v1_L3`
- compare:
  - `screen_space_gaussian`
  - `raycast_nearest_face`
  - `cone_gaussian_on_mesh`
- verify expected qualitative ordering on server:
  `cone > screen_space > raw raycast` or note deviations

Exit condition:
- if metrics look coherent on 3 models, prepare a small non_texture pilot batch

#### Phase D — validate SAL3D metric protocol

Goal:
- make SAL3D results benchmark-valid instead of merely runnable

Required checks:
- add or validate masking of uncovered OBJ vertices for high-res models
- compute metrics only on GT-covered vertex subset where appropriate
- re-run at least:
  - one 20K direct-match model
  - one high-res subset-match model
- verify whether current low CC on high-res models is mostly a metric-domain
  artifact

Exit condition:
- either SAL3D becomes a clearly valid partial benchmark
- or remains labeled as reconstruction/diagnostic only

#### Phase E — documentation sync and pilot launch gating

Goal:
- make runbook, launchers, and actual practice say the same thing

Tasks:
- once `3DVA` and `SAL3D` status is decided, update:
  - `trash/EVAL_RUNBOOK.md`
  - `DATA_PATHS.md`
  - `trash/GPT.md`
  - `trash/Claude.md`
- then decide which pilot(s) are unlocked:
  - `MeshMamba non_texture`: likely first
  - `3DVA`: only after FOV policy is resolved or explicitly bounded
  - `SAL3D`: only after masking/metric validity is fixed

### Ownership split

#### GPT owns

1. `3DVA` eval-policy resolution
   - all A/B comparisons
   - final decision or explicit deferral
2. server orchestration
   - update/pull state on `vg-intellect`
   - smoke/pilot launches
   - output collection and interpretation
3. benchmark gating decisions
   - when a dataset is ready for pilot
   - when a track stays blocked
4. cleanup / commit sequencing
   - scratch manifests
   - log commits
   - pilot-ready commits

#### Claude owns

1. `SAL3D` benchmark-validity repair
   - GT-covered-vertex masking
   - re-evaluation of high-res models
   - explicit note on which metrics remain meaningful
2. `MeshMamba` extension work that does not change the validated core recipe
   - rgb_texture spot checks
   - additional non_texture local comparisons if useful
   - targeted diagnostics on GT / naming / per-method behavior
3. documentation support
   - append-only notes about findings
   - no silent assumption changes

### Immediate next actions

1. GPT:
   - run 1–2 more server smokes for `MeshMamba non_texture`
   - keep `3DVA` pilot blocked
2. Claude:
   - focus on `SAL3D` GT-domain masking and re-check
3. Shared rule:
   - no one should declare `3DVA` fully normalized until the eval-side FOV
     conflict is either resolved or explicitly frozen as unresolved.

## 2026-06-01 MSK — GT interpretation from "Visual Attention for Rendered 3D Shapes"

Source:
- `/Users/admin/Documents/LAB/READ/# [2018.11] Visual Attention for Rendered 3D Shapes.pdf`

Why this matters:
- this paper is the clearest benchmark-style reference in our workspace for how
  human fixation GT on 3D meshes should be interpreted and evaluated.

Ground-truth construction, per the paper:
1. Raw eye-tracker data is a sequence of 2D fixations `(x, y)` with duration.
2. Each fixation is first mapped to the 3D object by casting the camera ray
   through the fixation pixel and taking the closest intersection point.
3. To avoid losing silhouette fixations, the ray is replaced by a cone and a
   Gaussian is projected onto the mesh.
4. The Gaussian standard deviation is fixed to `49 px`, corresponding to
   `1° visual angle`.
5. Contributions from all observers are summed to obtain the fixation density
   map on the mesh.

Important benchmark semantics from the paper:
1. For the actual benchmark, they choose **static** scenes, not dynamic ones,
   because dynamic fixations depend strongly on camera motion and are not a
   clean target for geometry-only saliency models.
2. GT is evaluated on the **mesh**, not in screen-space.
3. Visibility matters: for evaluation, saliency maps are multiplied by a
   binary visibility field for the given static viewpoint.
4. Two main metrics are used:
   - Pearson linear correlation (`ρ`, same family as `CC/LCC`)
   - `AUC`
5. For `AUC`, fixation maps are thresholded so that `20%` of visible vertices
   are treated as positives.
6. Human upper-bound is estimated by using fixation maps from half the
   observers to predict the fixation maps from the other half.

Practical implication for our repo:
1. GT from this benchmark should be treated as a **smooth per-vertex density
   map on the mesh**, not as sparse hit locations.
2. `cone_gaussian_on_mesh` is conceptually closer to the paper GT than
   `raycast_nearest_vertex/face`.
3. When comparing methods against benchmark GT, visibility masking and
   viewpoint specificity are part of the protocol, not optional details.

## 2026-06-01 MSK — MeshMamba GT lookup fix for symlinked OBJ names

Problem:
- on `vg-intellect`, some MeshMamba model directories expose a convenience OBJ
  symlink with the model-name stem, e.g.
  `Ice_Cream_V1_L3.obj -> Ice_Cream_v1_LOD1.obj`
- GT filenames follow the **real target stem**, not always the symlink stem
- as a result, `find_gt_file(..., extra_candidate_names=[obj_path.stem])`
  could miss GT even though the correct file exists

Fix:
- in both MeshMamba eval scripts, GT lookup now adds:
  - `obj_path.stem`
  - `obj_path.resolve().stem`

Affected files:
- `reprojection_methods/cone_projection_on_mesh/eval_meshmamba_cone.py`
- `reprojection_methods/screen_space_gaussian/eval_meshmamba_screen_space.py`

Purpose:
- unblock valid server runs for cases like:
  - `Ice_Cream_V1_L3 -> Ice_Cream_v1_LOD1.csv`
  - `barbiegirl_V1_L3 -> barbiedoll_v1_L3.csv`
  - `WWII_Plane-Germany_Focke-Wulf_Fw_190_v1 -> WWII_Plane-Germany_Focke-Wulf_FW_190_v1_l3.csv`

## 2026-06-01 MSK — SAL3D full reference run provenance

User asked which script was used for the SAL3D run, which models were included,
and where GT came from.

Actual server wrapper used:
- `/tmp/run_sal3d_full_20260601.sh` on `vg-intellect`

Actual repository entry point:
- `test/launch/run_sal3d_reference_batch.py`

Per-method scripts called by the batch runner:
- `reprojection_methods/screen_space_gaussian/eval_sal3d_screen_space.py`
- `reprojection_methods/cone_projection_on_mesh/eval_sal3d_cone.py`

Actual server command shape:

```bash
cd /home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/Mesh-Saliency-Projection
source configs/server_vg_intellect.env

export SAL3D_DATASET_ROOT=/home/29d_kon@lab.graphicon.ru/ssd1_link/datasets/reproject_release_v1/SAL3D
export SAL3D_CSV_ROOT=/home/29d_kon@lab.graphicon.ru/ssd1_link/datasets/reproject_release_v1/gaze_csv/SAL3D
export SAL3D_JSON_ROOT=/home/29d_kon@lab.graphicon.ru/ssd1_link/datasets/reproject_release_v1/jsons_for_models/SAL3D_json
export SAL3D_SMOOTH_GAZE_DIR=/home/29d_kon@lab.graphicon.ru/ssd1_link/datasets/reproject_release_v1/SAL3D/Smooth_Gaze

nice -n 10 "$REPROJECT_PYTHON" test/launch/run_sal3d_reference_batch.py \
  --methods screen_space cone \
  --workers 4 \
  --batch-output-dir /home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/outputs/SAL3D_reference_batch_20260601 \
  --smooth-gaze-dir "$SAL3D_SMOOTH_GAZE_DIR"
```

Model selection:
- not manually hard-coded in the run command
- `run_sal3d_reference_batch.py` built the model list as a case-insensitive
  intersection of:
  - `$SAL3D_DATASET_ROOT/Gaze/*.txt`
  - `$SAL3D_CSV_ROOT/*.csv`
- this produced `54` SAL3D models and `108` tasks (`54 models × 2 methods`)

Models included:
- `A380`
- `MaxPlanck`
- `alien`
- `alien2`
- `armadillo`
- `building`
- `bunny`
- `camel`
- `car`
- `cart`
- `carter`
- `casting`
- `cat`
- `centauro`
- `chair`
- `chicken`
- `cow`
- `dinosaur`
- `dog`
- `dragon`
- `facestatue`
- `fandisk`
- `flowerpot`
- `footballplayer`
- `gorilla`
- `hand`
- `harley`
- `hay`
- `horse`
- `house`
- `igea`
- `james`
- `jessi`
- `lion`
- `meca`
- `michael3`
- `michael8`
- `octopus`
- `prot`
- `ring`
- `ringdragon`
- `rockerarm`
- `skull`
- `sofa`
- `spaceshuttle`
- `starfish`
- `teapot`
- `torso`
- `triceratop`
- `turbine`
- `vase`
- `victoria`
- `watchtower`
- `wolf`

GT source and semantics:
- GT files came from:
  - `/home/29d_kon@lab.graphicon.ru/ssd1_link/datasets/reproject_release_v1/SAL3D/Gaze/<model>.txt`
- Each file is expected to be an `N×8` text file with columns:
  - `x y z nx ny nz smooth_saliency binary_saliency`
- Current benchmark uses column index `6` by default:
  - `smooth_saliency`
- Column index `7` is available in the scripts but was not used in this run:
  - `binary_saliency`
- If `$SAL3D_SMOOTH_GAZE_DIR/<model>_neighbors.txt` exists, GT is additionally
  smoothed using the dataset/paper-style Smooth_Gaze neighbour propagation.
- Metrics are read from `metrics_vs_gt_covered_only`, not from full-mesh metrics.
  This matters because many SAL3D OBJ meshes have more vertices than the 20k GT
  rows, so only vertices actually covered by the GT file are benchmark-valid.

Transform/projection recipe used by both methods:
- `--recenter-to-bbox-center`
- `--extra-rotate-x-deg 90`
- `--projection-fov-mode horizontal_to_vertical`
- `--transform-order blender_rig`
- no `--override-fov-deg`; the JSON FOV value is used and interpreted as
  horizontal FOV, then converted to vertical FOV for projection.

Method-specific parameters:
- `screen_space_gaussian`:
  - `--sigma-px 26.3`
- `cone_gaussian_on_mesh`:
  - `--sigma-deg 1.0`
  - `--radius-sigma-mult 3.0`

Run result:
- `102 / 108` tasks succeeded.
- `51 / 54` models succeeded for each method.
- `MaxPlanck`, `meca`, and `sofa` failed for both methods because their GT row
  count is larger than the OBJ vertex count:
  - `MaxPlanck`: `GT row count (20000) > OBJ vertex count (19999)`
  - `meca`: `GT row count (20000) > OBJ vertex count (15000)`
  - `sofa`: `GT row count (20000) > OBJ vertex count (15162)`

Local copied result files:
- `results/benchmark_runs/sal3d/2026-06-01_sal3d_reference/sal3d_detailed_by_model_method.csv`
- `results/benchmark_runs/sal3d/2026-06-01_sal3d_reference/sal3d_per_model_wide.csv`
- `results/benchmark_runs/sal3d/2026-06-01_sal3d_reference/sal3d_overall_summary.csv`
- `results/benchmark_runs/sal3d/2026-06-01_sal3d_reference/sal3d_model_metrics_compact.csv`
- `results/benchmark_runs/sal3d/2026-06-01_sal3d_reference/sal3d_failed_rows.csv`
- `results/benchmark_runs/sal3d/2026-06-01_sal3d_reference/sal3d_failed_models_concise.csv`

---

## 2026-06-02 — GT visualization scripts restructured

Goal:
- move method-specific `prediction vs GT` viewers out of `test/tools/`
- make the layout explicit and dataset/method-specific
- keep `test/tools/` for generic utilities only

Canonical folder:
- `test/gt_visualizations/`

Canonical scripts after restructuring:
- `test/gt_visualizations/preview_meshmamba_screenspace_alignment.py`
- `test/gt_visualizations/preview_meshmamba_cone_alignment.py`
- `test/gt_visualizations/preview_sal3d_screenspace_alignment.py`

Backward-compatible wrappers kept in `test/tools/`:
- `preview_screenspace_alignment.py`
- `preview_meshmamba_cone_alignment.py`
- `preview_sal3d_screenspace_alignment.py`

Documentation updated:
- `test/gt_visualizations/README.md` — new dedicated README for all GT viewers
- `test/README.md` — directory tree now includes `gt_visualizations/`
- `test/tools/README.md` — now points to `gt_visualizations/` for method viewers
- `README.md` — top-level docs now point to the new canonical viewer paths

Important implementation note:
- the old MeshMamba screen-space preview script only read legacy env vars
  (`MESHMAMBA_*`) and did not work from `test/env/local_paths.example.sh`
  because that file exports the newer `REPROJECT_*` paths.
- this was fixed in
  `test/gt_visualizations/preview_meshmamba_screenspace_alignment.py`
  by adding fallback resolution:
  - dataset root: `MESHMAMBA_NON_TEXTURE_ROOT` or `REPROJECT_DATASET_MESHMAMBA_ROOT`
  - csv root: `MESHMAMBA_CSV_ROOT` or texture-specific `REPROJECT_GAZE_CSV_*`
  - json root: `MESHMAMBA_JSON_ROOT` or texture-specific `REPROJECT_GAZE_JSON_*`

Smoke checks completed after restructuring:
- `py_compile` passed for:
  - `preview_meshmamba_screenspace_alignment.py`
  - `preview_meshmamba_cone_alignment.py`
  - `preview_sal3d_screenspace_alignment.py`
- MeshMamba cone quick smoke passed from the new path:
  - command:
    - `/Users/admin/Documents/LAB/SALIENCY_code/GAZE_DATA/venv/bin/python3 test/gt_visualizations/preview_meshmamba_cone_alignment.py --model Starfruit_L3 --texture-type non_texture --max-frames 12 --output-dir test/output_local/preview_meshmamba_cone_starfruit_smoke_quick_v2`
  - outputs:
    - `Starfruit_L3_frame0138.png`
    - `Starfruit_L3_frame0277.png`
    - `Starfruit_L3_frame0416.png`
    - `Starfruit_L3_summary.png`
- MeshMamba screen-space runtime smoke passed from the new path:
  - command:
    - `/Users/admin/Documents/LAB/SALIENCY_code/GAZE_DATA/venv/bin/python3 test/gt_visualizations/preview_meshmamba_screenspace_alignment.py --model Starfruit_L3 --texture-type non_texture --preview-frames 138 --output-dir test/output_local/preview_meshmamba_screen_starfruit_smoke_v2`
  - outputs:
    - `Starfruit_L3_frame0138.png`
    - `Starfruit_L3_summary.png`

Resulting convention:
- `test/gt_visualizations/` = method-specific visual comparison scripts
- `test/tools/` = reusable utility/debug helpers not tied to one metric viewer

---

## 2026-06-02 — MeshMamba bad-KLD visual diagnostics

Context:
- after the MeshMamba reference benchmark, the worst KLD cases were concentrated
  in a small set of `rgb_texture` models, especially:
  - `Flying_saucer_v1_L3`
  - `Spinning_Top_v1_L3`
  - `MushroomShitake_L3`
  - `UFO_v1_L2` (screen-space)

Practical fix made before visualization:
- `test/gt_visualizations/preview_meshmamba_cone_alignment.py` originally used
  the `non_texture` CSV/JSON env fallbacks even when `--texture-type rgb_texture`
  was passed.
- fixed so that when explicit `--csv-root/--json-root` are omitted, the script
  now resolves:
  - `REPROJECT_GAZE_CSV_MESHMAMBA_RGB_TEXTURE_ROOT`
  - `REPROJECT_GAZE_JSON_MESHMAMBA_RGB_TEXTURE_ROOT`
  for `rgb_texture`, and keeps the non-texture roots for `non_texture`.

Visualizations generated for the worst benchmark cases:
- output root:
  - `test/output_local/meshmamba_bad_kld/`
- full viewers run for:
  - `Flying_saucer_v1_L3` + `cone_gaussian_on_mesh` + `rgb_texture`
  - `Flying_saucer_v1_L3` + `screen_space_gaussian` + `rgb_texture`
  - `Spinning_Top_v1_L3` + `cone_gaussian_on_mesh` + `rgb_texture`
  - `Spinning_Top_v1_L3` + `screen_space_gaussian` + `rgb_texture`

Benchmark KLD values for these runs:
- `Flying_saucer_v1_L3` + `rgb_texture` + `cone`:
  - `KLD = 16.8744`
- `Flying_saucer_v1_L3` + `rgb_texture` + `screen_space`:
  - `KLD = 5.5428`
- `Spinning_Top_v1_L3` + `rgb_texture` + `cone`:
  - `KLD = 9.5799`
- `Spinning_Top_v1_L3` + `rgb_texture` + `screen_space`:
  - `KLD = 5.6922`

Diagnostic takeaway from summary images:
- `Flying_saucer_v1_L3`:
  - `cone` prediction is much more spread across the visible plate than GT;
    GT mass is sparse/localized on separated components, so KLD explodes when
    prediction gives non-trivial mass almost everywhere visible.
  - `screen_space` is also too diffuse, but it follows the visible silhouette
    more coherently than cone; KLD is still high because GT is much sparser.
- `Spinning_Top_v1_L3`:
  - both methods produce broad, smooth saliency over most of the top, while GT
    is concentrated in a few localized regions (`cap`, side of stem, inner rim).
  - this is a classic high-KLD pattern: prediction is not random, but it fails
    to preserve GT sparsity/localization.

Follow-up fix:
- a visual inconsistency was found between the MeshMamba `screen_space` and
  `cone` viewers: for the same object, the GT panel could look very different
  even though the underlying GT file was identical.
- root cause:
  - `preview_meshmamba_screenspace_alignment.py` drew all visible GT faces,
    including zero-valued ones (blue / low-value dots).
  - `preview_meshmamba_cone_alignment.py` filtered GT to `value > 0`, so only
    positive GT faces were drawn and the rest stayed black.
- this made the same GT map appear "dense" in screen-space and "sparse" in cone.
- fixed by removing the `value > 0` filtering in the cone viewer so both scripts
  now visualize visible zero-valued GT faces in the same way.

Filename convention update:
- GT viewer outputs now include the projection method in the filename:
  - `<model>__<method>__frame<NNNN>.png`
  - `<model>__<method>__summary.png`
- example:
  - `Flying_saucer_v1_L3__cone_gaussian_on_mesh__summary.png`

---

## 2026-06-02 — MeshMamba worst-case PNG bundles (KLD / CC)

New batch script:
- `test/gt_visualizations/generate_meshmamba_worst_case_bundle.py`

Purpose:
- read `results/benchmark_runs/meshmamba/2026-06-02_meshmamba_reference/meshmamba_reference_long.csv`
- select:
  - top-10 worst rows by `KLD` (largest first)
  - top-10 worst rows by `CC` (smallest first)
- run the correct visualization script for each selected row
- collect PNGs into ranked folders and pack them into zip archives

Output root:
- `results/diagnostics/2026-06-02_meshmamba_worst_cases/`

Final bundle artifacts:
- `worst_kld_top10.zip`
- `worst_cc_top10.zip`

Manifest files:
- `worst_kld_top10/worst_kld_manifest.csv`
- `worst_cc_top10/worst_cc_manifest.csv`

Important implementation fixes discovered during the run:
- `preview_meshmamba_screenspace_alignment.py` was updated to resolve GT files
  using both:
  - the requested `model`
  - `obj_path.stem`
  This was required for non-standard dataset names such as:
  - `MushroomShitake_L3` -> `MushroomShitake_v1-L3.csv`
  - `White-TailedDeer_V1_L2` -> `White-Tailed_Deer_v1_l2.csv`
- `generate_meshmamba_worst_case_bundle.py --skip-existing` is useful after
  partial completion or after patching a resolver edge case.

Result summary:
- all targeted worst-case rows were rendered successfully
- because the top-10 `KLD` list and top-10 `CC` list overlap, the number of
  unique generated cases is smaller than 20
- each case directory contains:
  - 3 frame PNGs
  - 1 summary PNG

---

## 2026-06-03 — `gt_visualizations` moved to repo root

Structural change:
- canonical folder moved from:
  - `test/gt_visualizations/`
- to:
  - `gt_visualizations/`

What was updated:
- root docs:
  - `README.md`
- test docs:
  - `test/README.md`
  - `test/tools/README.md`
- moved scripts:
  - `gt_visualizations/preview_meshmamba_screenspace_alignment.py`
  - `gt_visualizations/preview_meshmamba_cone_alignment.py`
  - `gt_visualizations/preview_sal3d_screenspace_alignment.py`
  - `gt_visualizations/generate_meshmamba_worst_case_bundle.py`
- compatibility wrappers in `test/tools/` were repointed to the new root path

Implementation detail:
- after moving the scripts one directory up, `REPO_ROOT` inside the moved
  scripts changed from `Path(__file__).resolve().parents[2]` to `.parents[1]`
  so imports from `reprojection_methods/...` still resolve correctly.

Validation:
- `py_compile` passed for the moved scripts and wrappers
- smoke check passed via the old wrapper entrypoint:
  - `test/tools/preview_meshmamba_cone_alignment.py`
  - output written successfully to:
    - `test/output_local/preview_meshmamba_cone_pear_wrapper_after_move/`

---

## 2026-06-02 — KLD post-processing diagnostics prepared and started

Reason:
- MeshMamba still has substantially higher `KLD` than SAL3D.
- Prior parameter sweep showed that widening `cone_gaussian_on_mesh` helps KLD,
  but it did not fully explain whether the issue is projection, GT/prediction
  support, face-area convention, zero-probability KLD penalty, or missing
  mesh-space smoothing.
- To avoid mixing this with projection errors, the next test intentionally does
  not rerun projection. It loads already saved `*_faces.txt` maps and recomputes
  metrics under diagnostic post-processing variants.

New files:
- `test/kld_parameter_sweep/run_kld_postprocess_diagnostics.py`
- `test/kld_parameter_sweep/server/run_postprocess_diagnostic_vg_intellect.sh`
- `test/kld_parameter_sweep/README.md` was extended with a post-processing
  diagnostic section.

What the script tests:
- `baseline`
  - Recompute metrics from existing maps to verify compatibility with old CSVs.
- `alpha_floor`
  - Adds uniform probability floor to prediction before KLD.
  - Tests whether high KLD is mainly caused by GT-positive faces where
    prediction is exactly zero or near zero.
- `support_mask`
  - Recomputes metrics on selected supports:
    - `pred_positive`
    - `pred_above_1e_8`
    - `pred_above_1e_6`
    - `gt_positive`
    - `intersection_positive`
    - `union_positive`
  - These are diagnostic only and must not be used as final benchmark numbers.
- `area_weighting`
  - Tests `none`, `multiply_area`, `divide_area`.
  - Purpose: detect whether GT/prediction maps should be interpreted as
    per-face mass or per-area density.
- `diffusion`
  - Applies neighbor averaging over the mesh face graph.
  - Steps: `1,3,5,10,20,40`, blend `0.5`.
  - Purpose: test whether mesh-space post-smoothing improves KLD without
    destroying `CC/SIM`.
- `top_kld_faces`
  - Writes top KLD-contributing faces per baseline source row for manual
    inspection.

Server smoke test:
- command:
  - `RUN_ID=smoke_20260602_081254 MAX_INPUT_ROWS=4 SKIP_DIFFUSION=true NICE_LEVEL=15 bash test/kld_parameter_sweep/server/run_postprocess_diagnostic_vg_intellect.sh`
- output:
  - `/home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/outputs/KLD_postprocess_smoke_20260602_081254`
- log:
  - `/home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/tmp_launchers/kld_postprocess_smoke_20260602_081254.log`
- result:
  - 4 input maps
  - 80 diagnostic rows
  - 40 summary rows
  - 16 best-by-model rows
  - 200 top-KLD-face rows
  - 0 errors
- sanity check:
  - baseline/`alpha_0` KLD matches the original reference KLD for checked rows,
    so prediction/GT loading and KLD formula are compatible with prior runs.

Full server run:
- session:
  - `kld_postprocess_full_20260602_081351`
- command:
  - `RUN_ID=full_20260602_081351 NICE_LEVEL=15 bash test/kld_parameter_sweep/server/run_postprocess_diagnostic_vg_intellect.sh`
- output:
  - `/home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/outputs/KLD_postprocess_full_20260602_081351`
- log:
  - `/home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/tmp_launchers/kld_postprocess_full_20260602_081351.log`
- input CSVs:
  - `/home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/outputs/MeshMamba_reference_batch_20260601/meshmamba_reference_long.csv`
  - `/home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/outputs/KLD_diagnostic_20260602_064256/kld_sweep_long.csv`
- detected input rows:
  - `636` MeshMamba maps:
    - `420` full-reference maps
    - `216` focused-KLD-sweep maps
- each full row should produce `26` diagnostic variants.
- first checked progress:
  - 16/636 processed
  - 0 errors
  - intermediate CSVs already present.

Expected final files:
- `postprocess_long.csv`
- `postprocess_summary.csv`
- `postprocess_best_by_model.csv`
- `postprocess_top_kld_faces.csv`

How to monitor manually:
- `ssh vg-intellect 'tmux ls 2>/dev/null | grep kld_postprocess_full_20260602_081351 || true'`
- `ssh vg-intellect 'tail -n 40 /home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/tmp_launchers/kld_postprocess_full_20260602_081351.log'`
- `ssh vg-intellect 'find /home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/outputs/KLD_postprocess_full_20260602_081351 -maxdepth 1 -type f -print -exec wc -l {} \;'`

Interpretation rules after completion:
- If `alpha_floor` sharply lowers `KLD` and keeps `CC/SIM` close to baseline,
  KLD is mostly a zero-probability support problem.
- If `support_mask` is good but baseline is poor, projection may be roughly
  right but prediction support is too sparse or differs from GT support.
- If `area_weighting` changes ranking strongly, the face mass/density convention
  must be resolved before final reporting.
- If `diffusion` lowers `KLD` while preserving `CC/SIM`, promote diffusion as a
  post-processing variant and rerun full MeshMamba metrics with that variant.
- If none of these helps, return to projection/GT-file matching and top-KLD-face
  visual inspection.

### Completion summary

The full run completed successfully.

Final server output:
- `/home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/outputs/KLD_postprocess_full_20260602_081351`

Local copy:
- `results/benchmark_runs/kld_postprocess/2026-06-02_kld_postprocess_full_081351/`

Final file sizes:
- `postprocess_long.csv`
  - `16536` data rows
- `postprocess_summary.csv`
  - `208` data rows
- `postprocess_best_by_model.csv`
  - `2220` data rows
- `postprocess_top_kld_faces.csv`
  - `31800` data rows

Run status:
- all rows are `status=ok`
- no tracebacks or runtime failures were found in the server log

### What changed in methodology

Important: the core projection pipeline was not changed in this stage.

What changed was the evaluation methodology after the prediction maps had
already been produced:

1. We separated projection from metric diagnosis.
   - Instead of rerunning gaze transfer, we reused saved `*_faces.txt` maps.
   - This isolates KLD behavior from camera / pose / JSON alignment issues.

2. We added diagnostic variants on top of fixed prediction maps.
   - `alpha_floor`
     - adds a small uniform floor to prediction probability before `KLD`
   - `support_mask`
     - recomputes metrics only on selected face supports
   - `area_weighting`
     - tests whether GT/prediction should be compared as face mass or density
   - `diffusion`
     - applies face-neighbor smoothing on the mesh graph

3. We explicitly separated "diagnostic tools" from "candidate promoted methods".
   - Diagnostic only:
     - `support_mask`
     - `alpha_floor` as a post-hoc metric trick
   - Potentially promotable as real method variants:
     - `diffusion`
     - possibly `area_weighting`, but only after the GT semantics are verified

This distinction matters because some variants can improve `KLD` by changing
how the metric sees the map, not by actually improving the prediction method.

### What the results say

For full-reference MeshMamba:

- Baseline non-texture:
  - `cone`: `KLD=0.9635`, `CC=0.3212`, `SIM=0.5935`
  - `screen_space`: `KLD=1.9539`, `CC=0.1359`, `SIM=0.5833`
- Baseline rgb-texture:
  - `cone`: `KLD=1.1570`, `CC=0.2696`, `SIM=0.5719`
  - `screen_space`: `KLD=1.9379`, `CC=0.1290`, `SIM=0.5744`

Diagnostic bests on full-reference MeshMamba:

- `alpha_floor=0.01`
  - sharply lowers `KLD`
  - keeps `CC` unchanged and changes `SIM` only slightly
  - example:
    - non-texture `screen_space`: `1.9539 -> 0.8641`
    - rgb-texture `screen_space`: `1.9379 -> 0.8873`
  - interpretation:
    - a large part of the current high `KLD` is caused by GT mass falling onto
      exact or near-zero predicted faces

- `support_mask=intersection_positive`
  - gives the lowest `KLD` of all tested families
  - but it is not a valid benchmark replacement because it changes the region
    on which the metric is computed
  - interpretation:
    - support mismatch is very important, but this is diagnostic evidence only

- `diffusion_steps40_blend0p5`
  - gives a real geometric improvement without changing the evaluation support
  - strongest effect is on `screen_space`
  - example:
    - non-texture `screen_space`: `1.9539 -> 0.7705`
    - rgb-texture `screen_space`: `1.9379 -> 0.9411`
  - `CC` and `SIM` also improve slightly
  - interpretation:
    - mesh-space smoothing is a legitimate candidate to promote into the real
      pipeline, especially for `screen_space`

- `area_weighting=divide_area`
  - strongly raises `CC` / `SIM`
  - example:
    - non-texture `cone`: `CC 0.3212 -> 0.6960`
    - non-texture `screen_space`: `CC 0.1359 -> 0.6991`
  - but `KLD` improves only modestly
  - interpretation:
    - this is a strong signal that GT/prediction mass-vs-density semantics may
      be mismatched, and this must be verified before any promotion

For the focused `kld_sweep` subset the same qualitative pattern holds:
- `alpha_floor` lowers `KLD` strongly
- `support_mask` lowers it even more, diagnostically
- `diffusion` helps `screen_space` more than `cone`
- `area_weighting` is unstable and depends on subset/texture

### Current conclusion

The main issue is no longer best explained by bad camera alignment alone.

The strongest evidence now points to a combination of:
- prediction support being too sparse relative to GT support
- `KLD` being heavily penalized by zero / near-zero predicted probability
- missing mesh-space smoothing, especially for `screen_space`
- possible ambiguity in whether maps should be compared as face mass or density

### Recommended next steps

1. Promote `diffusion` into a real evaluated method variant.
   - Best first target: `screen_space_gaussian + mesh diffusion`
   - Then rerun full MeshMamba metrics end-to-end with this as a real method.

2. Audit GT semantics before promoting any area-weighting rule.
   - Need to determine whether MeshMamba GT CSV values represent:
     - per-face mass
     - per-face density
     - or already normalized saliency independent of face area

3. Treat `alpha_floor` only as evidence, not as the final reported method.
   - It proves why `KLD` is large.
   - It does not by itself mean the prediction method is fixed.

4. Use `postprocess_top_kld_faces.csv` to inspect worst offending faces.
   - This should guide whether the next real fix is:
     - better diffusion
     - visibility/support handling
     - or GT convention alignment

5. After that, rerun a clean benchmark with only promoted variants.
   - Do not mix diagnostic-only variants into the final benchmark table.
