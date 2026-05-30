# Claude Task Brief

Last updated: 2026-05-30

## Your Role

You are the second agent in a shared workflow with `GPT`.

You do not own the final user-facing plan, but you do own delegated subtasks
that make the benchmark runnable and auditable. Your work must be recorded here
so that it can be integrated, reviewed, or rolled back by commit.

Before doing anything:

1. Read `trash/GPT.md`.
2. Read this file in full.
3. Inspect the current repository state.
4. Do not silently change benchmark assumptions.

## Project Context

We are building a reproducible evaluation workflow for gaze-to-mesh saliency
projection methods across multiple datasets.

Current known dataset facts:

1. `3DVA`
   GT is `per-vertex`
   locally benchmarkable now
2. `MeshMamba non_texture`
   GT is `per-face`
   locally benchmarkable now
3. `MeshMamba rgb_texture`
   GT is `per-face`
   should follow after `non_texture`
4. `SAL3D`
   raw gaze is available, but dense GT reconstruction still needs work

Current method families:

1. `screen_space_gaussian`
2. `cone_projection_on_mesh`
3. `raycast_nearest_vertex`
4. `cone_gaussian_on_mesh`
5. `our_pipeline` for MeshMamba
6. `our_pipeline + diffusion`
7. `our_pipeline + geodesic_kde`
8. MeshMamba-adapted reference baselines

Critical constraint:

Before large metric runs, we need one rendered preview image per dataset to
verify that the object is placed correctly in the camera view.

## Main Things You Need To Help With

### Task A. Preview Validation Audit

Goal:
make preview validation easy and reproducible for each dataset.

You should:

1. Find the best existing preview-render code that can already be reused.
2. Identify what is missing for:
   `3DVA`, `MeshMamba non_texture`, `MeshMamba rgb_texture`, and `SAL3D`.
3. Propose a minimal script or command layout that renders one representative
   preview frame per dataset.
4. Explicitly note whether each dataset needs:
   `recenter_to_bbox_center`, `extra_rotate_x_deg`, `override_fov_deg`, or no
   correction by default.

Deliverable:

1. A short implementation plan.
2. Exact file candidates to reuse.
3. Any blockers or ambiguities.

### Task B. Server Execution Audit

Goal:
prepare the benchmark for the external rendering/compute server.

Known server assumptions:

1. The datasets are already on the server.
2. We will transfer code by `git` commits.
3. Participant CSV / JSON side inputs may need to be mirrored there.
4. Large jobs should use low priority and free nodes only.

Concrete server profile for the current benchmark track:

1. SSH host alias: `vg-intellect`.
2. `sudo` is unavailable; all setup and launches must work in user space.
3. Server worktree root:
   `/home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING`
4. Server environments root:
   `/home/29d_kon@lab.graphicon.ru/ssd1_link/environments`
5. Server datasets root:
   `/home/29d_kon@lab.graphicon.ru/ssd1_link/datasets`
6. Expected dataset subdirectories under that root:
   `3DVA`, `MeshMambaSaliency`, `SAL3D`
7. Code updates should reach the server only through GitHub, followed by
   normal `git` checkout / pull on the server side.
8. Execution order is fixed:
   local mini test -> server pilot -> full server run
9. Server jobs should be launched in parallel when useful, but with low
   priority, without `sudo`, and without relying on privileged schedulers or
   machine-wide configuration changes.
10. Future server entrypoints should use portable wrappers and env-driven paths
   instead of hard-coded local or server-specific absolute paths.

You should:

1. Identify which local files must exist on the server in addition to the
   datasets.
2. Suggest a clean commit-driven sync workflow.
3. Suggest where run manifests and launch wrappers should live in the repo.
4. Note any path hard-coding in current scripts that will break on the server.

Deliverable:

1. A concrete checklist of files and directories to sync.
2. A list of scripts that need path cleanup or config injection.
3. A proposed launch pattern for pilot runs and full runs.

### Task C. Method Matrix Audit

Goal:
turn the current codebase into a precise comparison matrix.

You should produce a compact mapping:

1. method name
2. dataset compatibility
3. output granularity: `screen`, `vertex`, or `face`
4. GT granularity expected
5. primary metrics
6. readiness status:
   `ready`, `needs adaptation`, or `blocked`

Do not re-invent methods. Use what is already in the repo unless there is a
clear gap.

## Constraints

1. Do not convert `vertex-level` and `face-level` outputs into one another and
   present that as benchmark-equivalent unless you explicitly label it as an
   adaptation.
2. Do not claim `SAL3D` is benchmark-ready unless dense GT reconstruction is
   implemented and validated.
3. Do not remove existing files or history.
4. If you change code, keep the change minimal and explain why it was needed.
5. If you find a benchmark-validity risk, record it explicitly here.
6. Append new dated notes for each meaningful commit and for each important
   analysis block; do not rewrite earlier log entries.

## Preferred Working Style

1. Reuse existing code before adding new code.
2. Prefer small server-portable wrappers over invasive rewrites.
3. Prefer configuration over hard-coded local paths.
4. Keep notes concrete:
   file paths, functions, arguments, and failure modes.

## Reporting Format

Append new entries in this format:

```text
## YYYY-MM-DD HH:MM TZ
Role: Claude
Commit: <hash or UNCOMMITTED>
Scope: <task block>
Files inspected: <paths>
Files changed: <paths or none>
Findings: <concise factual summary>
Risks: <benchmark or execution risks>
Questions for GPT: <if any>
Next step: <single next action>
```

## Initial Assignment

Start with these three actions:

1. Audit preview-render paths and identify one best script path per dataset.
2. Audit server portability problems caused by hard-coded local paths.
3. Build the first draft of the method compatibility matrix.

Write your findings here before making broad code changes.

## Initial Entry Stub

```text
## 2026-05-30 MSK
Role: Claude
Commit: UNCOMMITTED
Scope: Not started yet
Files inspected: none
Files changed: none
Findings: pending
Risks: pending
Questions for GPT: none yet
Next step: inspect preview scripts and path handling
```

## 2026-05-30 08:48 MSK
Role: Claude
Commit: UNCOMMITTED
Scope: Start audit for preview render paths, server portability, and the first
method compatibility matrix across `3DVA`, `MeshMamba`, and `SAL3D`.
Files inspected: `trash/GPT.md`, `trash/Claude.md`, `test/README.md`,
`utils/path_defaults.py`, `reprojection_methods/*`, `video_creation/*`,
`/Users/admin/Documents/LAB/SALIENCY_code/GAZE_DATA/scripts/render_camera_preview.py`,
`/Users/admin/Documents/LAB/SALIENCY_code/GAZE_DATA/scripts/evaluate_3dva_projection_methods.py`,
`/Users/admin/Documents/LAB/SALIENCY_code/GAZE_DATA/MAMBA_GAZE/*`,
`/Users/admin/Documents/LAB/SALIENCY_code/Rendering/SAL3D/*`,
`/Users/admin/Documents/LAB/SALIENCY_code/MVP/mamba_render_2.py`,
`/Users/admin/Documents/LAB/SALIENCY_code/GAZE_DATA/outputs/3DVA_eval/*`,
`/Users/admin/Documents/LAB/SALIENCY_code/GAZE_DATA/datasets/*`,
`/Users/admin/Documents/LAB/SALIENCY_code/#meshes_2.0/GazeToGT/X/DATASET_PATHS_TEXT_2026-05-06.txt`
Files changed: `trash/Claude.md`
Findings:
1. Preview validation audit.
   `3DVA`
   Best existing one-frame preview is
   `/Users/admin/Documents/LAB/SALIENCY_code/GAZE_DATA/scripts/render_camera_preview.py`.
   It already renders frame-aligned camera previews and optional gaze overlay
   from `OBJ + JSON + CSV`.
   Minimal command:
   `python .../render_camera_preview.py --model bunny --frame 0 --dataset-root /path/to/3DVA --csv-root /path/to/csv_for_models/3DVA --json-root /path/to/jsons_for_models/3DVA_json --overlay-gaze --recenter-to-bbox-center --override-fov-deg 37.5`
   Provisional default correction for the dataset is:
   `recenter_to_bbox_center=true`, `extra_rotate_x_deg=0`, `override_fov_deg=37.5`.
   Evidence: local reports under
   `/Users/admin/Documents/LAB/SALIENCY_code/GAZE_DATA/outputs/3DVA_eval/*/recenter_fov37p5`
   improve hit rate on `bunny`, `dragon`, `chair107`, `flowerpot`, and
   `car-vasa`.
   `MeshMamba non_texture`
   Best existing one-frame preview is
   `/Users/admin/Documents/LAB/SALIENCY_code/GAZE_DATA/MAMBA_GAZE/tools/render_model_preview.py`.
   Server wrapper already exists as
   `/Users/admin/Documents/LAB/SALIENCY_code/GAZE_DATA/MAMBA_GAZE/scripts/render_model_preview.sh`.
   Minimal command:
   `python .../tools/render_model_preview.py --model Aquarium_Deep_Sea_Diver_v1_L1 --mesh-dir /path/to/MeshFile/non_texture --json-dir /path/to/jsons_for_models/Mamba_non_textured --output-image /tmp/aquarium_preview.ppm --recenter-to-bbox-center --extra-rotate-x-deg 90 --override-fov-deg 35.8972065`
   Provisional default correction for the representative pilot model
   `Aquarium_Deep_Sea_Diver_v1_L1` is:
   `recenter_to_bbox_center=true`, `extra_rotate_x_deg=90`,
   `override_fov_deg=35.8972065`.
   This recipe is documented in
   `/Users/admin/Documents/LAB/SALIENCY_code/GAZE_DATA/MAMBA_GAZE/docs/PROJECTION_TRANSFORM_RECIPE.md`.
   `MeshMamba rgb_texture`
   Closest reusable preview base is the same
   `.../MAMBA_GAZE/tools/render_model_preview.py`, but it is not ready as-is for
   `rgb_texture` because it hardcodes JSON names as
   `MeshMamba_non_texture_<model>.json` and its raster preview ignores texture
   materials.
   Texture-faithful fallback is the Blender renderer
   `/Users/admin/Documents/LAB/SALIENCY_code/MVP/mamba_render_2.py`, but that
   is a heavy full-render path, not a cheap one-frame checker.
   Minimal first-pass command, after a small prefix/layout adapter, would be:
   `python .../tools/render_model_preview.py --model Aquarium_Deep_Sea_Diver_v1_L1 --mesh-dir /path/to/MeshFile/rgb_texture --json-dir /path/to/jsons_for_models/Mamba_rgb_textured --output-image /tmp/aquarium_rgb_preview.ppm`
   Current correction candidate is only a carry-over hypothesis from
   `non_texture`; it is not validated dataset-wide.
   `SAL3D`
   No current one-frame preview script is ready as-is for the official SAL3D
   layout.
   Closest reusable assets are:
   `GAZE_DATA/csv_for_models/SAL3D`, `GAZE_DATA/jsons_for_models/SAL3D_json`,
   `GAZE_DATA/videos/SAL3D_videos`, and the old projector
   `/Users/admin/Documents/LAB/SALIENCY_code/GAZE_DATA/scripts/project_gaze_to_3d.py`.
   The blocker is that `project_gaze_to_3d.py` assumes
   `datasets/SAL3D/models/<model>.obj`, while the actual local dataset uses
   `datasets/SAL3D/SAL3D_Dataset/Meshes/<model>.obj`.
   Important distinction: this repo's strong qualitative tooling targets
   `Saliency3D_clear`, not official `SAL3D`.
   Provisional default correction for official `SAL3D` is currently:
   no correction, because no validated preview recipe exists yet.
2. Server portability audit.
   If datasets already exist on the server, additional side inputs still need to
   be mirrored.
   `3DVA`
   Mirror `GAZE_DATA/csv_for_models/3DVA/*.csv` and
   `GAZE_DATA/jsons_for_models/3DVA_json/*.json`.
   `MeshMamba non_texture`
   Mirror `GAZE_DATA/csv_for_models/MeshMamba_non_texture/*.csv` and
   `GAZE_DATA/jsons_for_models/Mamba_non_textured/*.json`.
   `MeshMamba rgb_texture`
   Mirror `GAZE_DATA/csv_for_models/MeshMamba_rgb_texture/*.csv` and
   `GAZE_DATA/jsons_for_models/Mamba_rgb_textured/*.json`.
   `SAL3D`
   Mirror `GAZE_DATA/csv_for_models/SAL3D/*.csv`,
   `GAZE_DATA/jsons_for_models/SAL3D_json/*.json`, and optionally
   `GAZE_DATA/videos/SAL3D_videos/*.mp4` if preview must be compared against
   rendered source video.
   Current server-blocking path/dependency issues:
   `Mesh-Saliency-Projection` repo alone is not enough for full benchmark runs.
   The reusable raw-gaze `3DVA` scripts and all `MeshMamba` pipelines currently
   live outside this repo under `GAZE_DATA/...` and `MVP/...`.
   `video_creation/transfer_visualizations/make_transfer_visualizations.py`
   hardcodes `MPLCONFIGDIR=/private/tmp/mplconfig_codex`, which is macOS-style
   and should be replaced by a Linux-safe writable temp path before server use.
   `reprojection_methods/*` and `video_creation/*` are otherwise mostly portable
   because they take `--dataset-root`, but their `example_path=` hints are still
   local-only.
   `/Users/admin/Documents/LAB/SALIENCY_code/GAZE_DATA/scripts/render_camera_preview.py`
   and `.../evaluate_3dva_projection_methods.py` hardcode local defaults for
   dataset root, CSV root, JSON root, and output dir.
   `/Users/admin/Documents/LAB/SALIENCY_code/GAZE_DATA/MAMBA_GAZE/mamba_gaze/pipeline.py`
   hardcodes local defaults through `DatasetPaths.local_defaults()`.
   `/Users/admin/Documents/LAB/SALIENCY_code/GAZE_DATA/MAMBA_GAZE/configs/lab_graphicon_server.env`
   hardcodes one specific `/mnt/hd2/...` server layout and only `non_texture`
   dirs.
   `/Users/admin/Documents/LAB/SALIENCY_code/GAZE_DATA/MAMBA_GAZE/tools/render_model_preview.py`
   hardcodes the `MeshMamba_non_texture_` JSON prefix.
   `/Users/admin/Documents/LAB/SALIENCY_code/Rendering/SAL3D/SAL3D_render_1.py`,
   `.../SAL3D_render_2.py`, and
   `/Users/admin/Documents/LAB/SALIENCY_code/MVP/mamba_render_2.py` hardcode
   absolute server paths and require Blender + GPU.
   `/Users/admin/Documents/LAB/SALIENCY_code/GAZE_DATA/scripts/project_gaze_to_3d.py`
   uses a stale SAL3D path layout and will fail on the current local dataset
   mirror.
   The `gaze_heatmap_overlays` workflow in this repo also depends on system
   `ffmpeg` and `ffprobe`.
   Minimal commit-driven sync pattern:
   keep stable wrappers and manifests under `test/`, not in ad hoc home-dir
   scripts; add `test/manifests/<dataset>_<pilot|full>.json` with dataset env
   var names, representative models, and transform recipe; add `test/launch/*.sh`
   that only read env vars / manifests; on the server do
   `git checkout <commit>` and run preview manifest first, then pilot/full runs.
3. Method matrix v1.
   `screen_space_gaussian | Saliency3D_clear | screen | screen held-out map / fixation pixels | AUC, NSS, CC | ready`
   `cone_projection_on_mesh | 3DVA published GT | vertex | vertex GT + visible mask | CC, Spearman, SIM, KLD, MSE, AUC_visible_top20 | ready`
   `cone_projection_on_mesh + geodesic_diffusion | 3DVA published GT | vertex | vertex GT + visible mask | CC, Spearman, SIM, KLD, MSE, AUC_visible_top20 | ready`
   `cone_projection_on_mesh | Saliency3D_clear proxy | vertex | vertex held-out cone map + raw hit vertices | CC, Spearman, SIM, KLD, MSE, NSS_raw_vertices, AUC_raw_vertices | ready`
   `raycast_nearest_vertex | 3DVA local raw gaze | vertex | vertex GT (views 300/413/599) | CC/LCC, AUC, SIM, KLD, SE | ready`
   `cone_gaussian_on_mesh | 3DVA local raw gaze | vertex | vertex GT (views 300/413/599) | CC/LCC, AUC, SIM, KLD, SE | ready`
   `our_pipeline | MeshMamba non_texture | face | face GT | CC, SIM, KLD, MSE (+ Spearman, Cosine, proxy NSS/AUC) | ready`
   `our_pipeline + diffusion | MeshMamba non_texture | face | face GT | CC, SIM, KLD, MSE (+ Spearman, Cosine, proxy NSS/AUC) | ready`
   `our_pipeline + geodesic_kde | MeshMamba non_texture | face | face GT | CC, SIM, KLD, MSE (+ Spearman, Cosine, proxy NSS/AUC) | ready`
   `screen_space_gaussian (MeshMamba-adapted) | MeshMamba non_texture | face | face GT | CC, SIM, KLD, MSE (+ proxy NSS/AUC) | ready`
   `cone_projection_on_mesh (MeshMamba-adapted) | MeshMamba non_texture | face | face GT | CC, SIM, KLD, MSE (+ proxy NSS/AUC) | ready`
   `our_pipeline / reference methods | MeshMamba rgb_texture | face | face GT | same metric family as non_texture | needs adaptation`
   `any current method | official SAL3D | screen or vertex | dense GT missing in current workspace | final benchmark metrics not yet valid | blocked`
Risks:
1. Do not conflate `Saliency3D_clear` with official `SAL3D`. Current preview
and evaluation code is strong for the former and weak for the latter.
2. `3DVA` and `MeshMamba` server runs are not reproducible from this repo alone
until the external `GAZE_DATA/...` utilities are either migrated into this repo
or mirrored as a second tracked code source.
3. `MeshMamba rgb_texture` probably has enough core plumbing to run with custom
dirs, but its preview path and launch wrappers are still `non_texture`-centric.
4. The current `3DVA` correction recipe
`recenter_to_bbox_center + override_fov_deg=37.5` is backed by a validated
subset, not by the full 32-model sweep yet.
Questions for GPT:
1. For `MeshMamba rgb_texture`, is a geometry-only frame acceptable for phase-1
preview validation, or must the preview preserve textures?
2. Should the external `GAZE_DATA/MAMBA_GAZE` and `GAZE_DATA/scripts`
dependencies stay external, or should the server-ready subset be moved under
this repo before packaging?
Next step: if GPT wants implementation next, the lowest-risk follow-up is to
put one portable preview wrapper per dataset under `test/` and drive all paths
through env vars / manifests instead of absolute paths.

## 2026-05-30 08:57 MSK
Role: Claude
Commit: UNCOMMITTED
Scope: Incorporated the user-provided concrete server profile into the working
brief so further portability and launch notes target the real host/layout.
Files inspected: `trash/Claude.md`
Files changed: `trash/Claude.md`
Findings:
1. Added explicit server identity and constraints:
   `vg-intellect`, no `sudo`, worktree root
   `/home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING`,
   environments root
   `/home/29d_kon@lab.graphicon.ru/ssd1_link/environments`, and datasets root
   `/home/29d_kon@lab.graphicon.ru/ssd1_link/datasets` with
   `3DVA`, `MeshMambaSaliency`, and `SAL3D`.
2. Made the transport policy explicit:
   code reaches the server only through GitHub.
3. Made the run order explicit:
   local mini test -> server pilot -> full server run.
4. Made the server execution policy explicit:
   parallel when useful, low priority, no `sudo`, and user-space only.
5. Re-stated the portability requirement in operational form:
   portable wrappers and env-driven paths are required for future launchers.
Risks:
1. Any wrapper that still assumes `/Users/...` or `/mnt/...` is now directly
   incompatible with the declared server profile.
2. Any launch path that depends on privileged package install, privileged
   scheduler configuration, or `sudo` should be treated as blocked by default.
Questions for GPT: none
Next step: keep all next server-facing proposals aligned with this exact
`vg-intellect` profile and reject non-portable path assumptions early.

## 2026-05-30 MSK
Role: Claude
Commit: UNCOMMITTED
Scope: Recorded the newly clarified operating rules for side-input transfer,
mandatory `json` metadata, `tmux` usage, broad metric collection, and
append-only per-commit logging.
Files inspected: `trash/Claude.md`
Files changed: `trash/Claude.md`
Findings:
1. `scp` is an approved transfer path for `csv/json` side inputs when GitHub is
   used only for code.
2. `json` camera/object metadata is required on the server, not optional,
   because preview rendering and reprojection depend on it.
3. Long server runs should be assumed to live inside `tmux`.
4. The evaluation policy should prefer computing the full available metric set
   per dataset first, then filtering in analysis rather than under-computing
   during runtime.
5. Agent markdown logs are expected to grow append-only with each meaningful
   commit and major analysis update.
Risks:
1. Any launch design that treats `json` files as derivable or optional will
   break geometric correctness.
2. If wide metric collection is not built into early wrappers, later reruns may
   become unnecessarily expensive.
Questions for GPT: none
Next step: keep future wrapper proposals metric-rich and make `json` side-input
requirements explicit in manifests and launch docs.

## 2026-05-30 MSK
Role: Claude
Commit: 817f6fa
Scope: Task B — portable server wrappers, manifests, path cleanup, and first
commit of test/ and trash/ directories to the reproject-benchmark branch.
Files inspected:
  `utils/path_defaults.py`
  `video_creation/transfer_visualizations/make_transfer_visualizations.py`
  `reprojection_methods/cone_projection_on_mesh/eval_vs_gt_visual_attention.py`
  `reprojection_methods/cone_projection_on_mesh/eval_geodesic_diffusion.py`
  `reprojection_methods/cone_projection_on_mesh/eval_visual_attention_style_saliency3d_clear.py`
  `reprojection_methods/screen_space_gaussian/eval_holdout_screenspace.py`
  `test/README.md`
  `configs/README.md`
  `.gitignore`
  `trash/GPT.md`, `trash/Claude.md`
Files changed:
  `video_creation/transfer_visualizations/make_transfer_visualizations.py` (MPLCONFIGDIR fix + example_path)
  `reprojection_methods/cone_projection_on_mesh/eval_vs_gt_visual_attention.py` (example_path)
  `reprojection_methods/cone_projection_on_mesh/eval_geodesic_diffusion.py` (example_path)
  `reprojection_methods/cone_projection_on_mesh/eval_visual_attention_style_saliency3d_clear.py` (example_path)
  `reprojection_methods/screen_space_gaussian/eval_holdout_screenspace.py` (example_path)
Files created:
  `configs/server_vg_intellect.env`
  `test/manifests/3dva_pilot.json`
  `test/manifests/saliency3d_clear_pilot.json`
  `test/manifests/meshmamba_non_texture_pilot.json`
  `test/manifests/meshmamba_rgb_texture_pilot.json`
  `test/launch/run_3dva_pilot.sh`
  `test/launch/run_saliency3d_clear_pilot.sh`
  `test/launch/run_meshmamba_non_texture_pilot.sh`
  `test/launch/mirror_side_inputs.sh`
  `trash/Claude.md` (this file — first commit)
  `trash/GPT.md` (first commit)
Findings:
1. Path cleanup completed.
   Only real portability bug in this repo: `MPLCONFIGDIR=/private/tmp/mplconfig_codex`
   in `make_transfer_visualizations.py` — macOS `/private/tmp` does not exist on
   Linux. Fixed to `os.path.join(tempfile.gettempdir(), "mplconfig")` which resolves
   to `/tmp/mplconfig` on the server.
   All five `example_path=` hints that contained local `/Users/admin/...` absolute
   paths were replaced with generic `e.g. /srv/datasets/...` strings. These are
   error-message hints only, not execution paths; the real path resolution is
   already fully env-var driven via `utils/path_defaults.py`.
   `utils/path_defaults.py` itself was already clean — it only uses env vars or
   CLI args, no hardcoded paths.
   All `output_dir` defaults in the eval scripts use `REPO_ROOT / "results" / ...`
   which is relative to the repo checkout location — portable as-is.
2. Server env template created.
   `configs/server_vg_intellect.env` covers all required env vars for the
   `vg-intellect` profile: dataset roots (3DVA, MeshMambaSaliency, Saliency3D_clear),
   side-input root, output root, conda env root, MAMBA_GAZE external root,
   and parallelism defaults (WORKERS=8, NICE_LEVEL=10).
   All paths in this file are server-absolute — this is intentional; the file is
   the single authoritative place for server-specific path configuration.
   All launch wrappers read from env vars only; they do not duplicate paths.
3. Manifests created (4 files under test/manifests/).
   `3dva_pilot.json`: 6 pilot models, view 300 start, two in-repo methods,
   transform recipe documented, side inputs NOT needed for in-repo scripts
   (data is inside published dataset), external raw-gaze methods noted separately.
   `saliency3d_clear_pilot.json`: 3 pilot models, screen_space + cone + viz scripts,
   no extra side inputs needed.
   `meshmamba_non_texture_pilot.json`: documents side inputs as mandatory
   (CSV + JSON via scp), transform recipe with validation status, external
   MAMBA_GAZE dependency explicit.
   `meshmamba_rgb_texture_pilot.json`: status=needs_adaptation, blockers listed
   (JSON prefix hardcode, transform not validated, texture preview requires Blender).
4. Launch wrappers created (4 shell scripts under test/launch/).
   `run_3dva_pilot.sh`: env-var driven, nice -n ${NICE_LEVEL}, loops over views,
   calls two in-repo scripts, all paths constructed from env vars.
   `run_saliency3d_clear_pilot.sh`: env-var driven, calls screen_space, cone, and
   viz scripts, output dirs split by method.
   `run_meshmamba_non_texture_pilot.sh`: checks side-input dirs are present before
   starting, delegates to ${MAMBA_GAZE_ROOT}/run_pipeline.py with explicit args.
   IMPORTANT: the MAMBA_GAZE pipeline entrypoint name and CLI may differ — verify
   on server before first run and adjust the script.
   `mirror_side_inputs.sh`: LOCAL-only script, uses scp, driven by
   LOCAL_GAZE_DATA_ROOT and SERVER_SIDE_INPUTS_ROOT env vars, rgb_texture and
   SAL3D blocks commented out until those tracks are ready.
5. Key observation: the in-repo 3DVA scripts (eval_vs_gt_visual_attention.py,
   eval_geodesic_diffusion.py) require no extra side inputs — the published dataset
   already contains PerSubjectFixations, FixationMaps, and OBJ meshes. Only the
   external raw-gaze scripts need the CSV side inputs.
Risks:
1. `run_meshmamba_non_texture_pilot.sh` assumes `${MAMBA_GAZE_ROOT}/run_pipeline.py`
   as the entrypoint. The actual entrypoint name and CLI flags must be confirmed
   against the real MAMBA_GAZE codebase before first server run. The wrapper will
   fail with a clear error if the script is not found.
2. The MeshMamba transform recipe (recenter+extra_rotate_x_deg=90+fov=35.897) is
   validated only on Aquarium_Deep_Sea_Diver_v1_L1. Preview validation per model
   remains a phase-1 gate.
3. `meshmamba_rgb_texture_pilot.json` is status=needs_adaptation and must not be
   used for any metric run until the JSON prefix issue in render_model_preview.py
   is resolved and the transform recipe is validated.
4. Nothing in this commit has been pushed to the server. All changes are local.
   No server push until explicitly requested.
5. `trash/` and `test/` were previously untracked; this commit adds them to git.
   `.gitignore` does not exclude them.
Questions for GPT:
1. For MeshMamba non_texture launch: what is the exact entrypoint script name in
   MAMBA_GAZE_ROOT on the server? `run_pipeline.py` is a placeholder.
2. For MeshMamba rgb_texture phase-1 preview: geometry-only frame accepted, or
   must the preview preserve textures? (Repeated from previous entry — still open.)
3. Parallelism for 3DVA pilot: both in-repo scripts are single-threaded Python
   loops over objects. For the full 32-model run, should we fan out at the
   object level with a job pool, or keep sequential with nice?
Next step: commit this batch to reproject-benchmark, then wait for GPT to confirm
the MAMBA_GAZE entrypoint name and the MeshMamba rgb_texture preview policy
before adapting the MeshMamba wrappers further.

## 2026-05-30 MSK
Role: Claude
Commit: UNCOMMITTED (staged for second commit to reproject-benchmark)
Scope: A — fix server-facing wrappers; B — side-input transfer infrastructure;
C — path portability audit; D — no geometric calibration changes.
Files inspected:
  `test/launch/run_meshmamba_non_texture_pilot.sh`
  `test/launch/run_3dva_pilot.sh` (read-only; updated by GPT hook)
  `test/launch/mirror_side_inputs.sh`
  `configs/server_vg_intellect.env`
  `test/manifests/meshmamba_non_texture_pilot.json`
  `test/manifests/3dva_pilot.json` (read-only; updated by GPT hook)
  `test/manifests/preview_3dva_bunny.json` (read-only; updated by GPT hook)
  `test/manifests/preview_meshmamba_non_texture_starfruit.json` (new by GPT)
  `test/manifests/preview_meshmamba_rgb_texture_starfruit.json` (updated by GPT)
  `test/tools/render_preview_from_manifest.py` (read-only; updated by GPT)
  `test/env/local_paths.example.sh` (read-only; updated by GPT)
  `/Users/admin/Documents/LAB/SALIENCY_code/GAZE_DATA/csv_for_models/*` (local sizes only)
  All new `test/side_inputs/` files
Files changed (Claude):
  `test/launch/run_meshmamba_non_texture_pilot.sh` — 3 fixes:
    1. entrypoint `run_pipeline.py` → `run_meshmamba_gaze.py`
    2. GT path `GT/non_texture` → `SaliencyMap/non_texture`
    3. WORKERS default `8` → `12`
  `configs/server_vg_intellect.env` — WORKERS `8` → `12`, added
    no-nested-parallelism note
  `test/launch/mirror_side_inputs.sh` — complete rewrite: archive-based
    transfer (tar.gz pack → scp → server unpack via here-doc ssh),
    SSH note (host alias must have User set in ~/.ssh/config), references
    new test/side_inputs/pack_*.sh scripts
  `test/manifests/meshmamba_non_texture_pilot.json` — 3 fixes:
    1. `gt_subdir` `GT/non_texture` → `SaliencyMap/non_texture`
    2. entrypoint `mamba_gaze/pipeline.py` → `run_meshmamba_gaze.py`
    3. `initial_server_worker_count` `8` → `12`, added `nested_parallelism: false`
  `test/manifests/3dva_pilot.json` — updated pilot parallelism:
    `initial_server_worker_count` `8` → `12`, added `parallelism_style:
    object_level_pool`, `nested_parallelism: false`
Files created (Claude):
  `test/side_inputs/README.md` — policy table, per-dataset inventory table,
    file counts (3DVA: 32+32, MeshMamba: 105+105), workflow steps
  `test/side_inputs/inventory_3dva.sh` — lists files + sizes, outputs
    server destination layout, dry-run only (no scp)
  `test/side_inputs/inventory_meshmamba_non_texture.sh` — same for MeshMamba,
    includes mandatory JSON warning
  `test/side_inputs/pack_3dva.sh` — creates `3dva_csv.tar.gz` (~38MB) and
    `3dva_json.tar.gz` (~2.6MB); prints server unpack commands after
  `test/side_inputs/pack_meshmamba_non_texture.sh` — creates
    `meshmamba_non_texture_csv.tar.gz` (~81MB) and
    `meshmamba_non_texture_json.tar.gz` (~8.6MB); mandatory JSON warning
  `test/side_inputs/scp_archives.sh` — scp template for both datasets,
    skips missing archives with warnings, NO auto-execution guard
  `test/side_inputs/unpack_on_server.sh` — server-side script, reads
    SIDE_INPUTS_ROOT, unpacks all 4 archives, prints final file counts,
    expected: 3DVA=32+32, MeshMamba=105+105
Files also modified (GPT hooks, not changed by Claude):
  `test/launch/run_3dva_pilot.sh` — GPT added object-level parallel pool,
    WORKERS=12, PILOT_OBJECTS as env var, `run_pooled_eval` helper function
  `test/manifests/3dva_pilot.json` — GPT added bunny model override
    `extra_rotate_x_deg: -45.0` (calibration after video-vs-preview check)
  `test/manifests/meshmamba_non_texture_pilot.json` — GPT updated
    `validated_models` to `Starfruit_L3`, `override_fov_deg` to `37.5`,
    `transfer_method` to `tar.gz + scp + server unpack`
  `test/manifests/preview_3dva_bunny.json` — GPT added `video_path`,
    `extra_rotate_x_deg: -45.0`
  `test/manifests/preview_meshmamba_non_texture_starfruit.json` — new GPT file
    (Starfruit_L3 non_texture pilot, fov=37.5, rotX=90)
  `test/manifests/preview_meshmamba_rgb_texture_starfruit.json` — GPT updated
    (added video_path, recenter=true, rotX=90, fov=37.5)
  `test/tools/render_preview_from_manifest.py` — GPT update (not inspected in detail)
  `test/env/local_paths.example.sh` — GPT update
  `test/README.md` — GPT update
  `trash/GPT.md` — GPT log (not staged; GPT commits their own log)
Findings:
1. Path cleanup verified clean.
   Scan of all new scripts and manifests found zero hardcoded local absolute
   paths in executable code. Absolute paths appear only in:
   a) `configs/server_vg_intellect.env` — intentional (this IS the server config)
   b) Comment-example lines in inventory scripts (`# Example:`) — acceptable
   c) `e.g.` hints in error messages — acceptable
2. Side-input inventory (confirmed from local filesystem):
   3DVA:
     csv: 32 files (~38 MB uncompressed, expect ~5-10 MB gzip)
     json: 32 files (~2.6 MB uncompressed)
   MeshMamba_non_texture:
     csv: 105 files (~81 MB uncompressed, expect ~20-40 MB gzip)
     json: 105 files (~8.6 MB uncompressed)
   Total transfer estimate: <100 MB compressed for both datasets combined.
3. GT path correction confirmed.
   The dataset layout on server uses `SaliencyMap/non_texture` not `GT/non_texture`.
   All references corrected in wrapper and manifest.
4. MAMBA_GAZE entrypoint confirmed.
   Entrypoint is `run_meshmamba_gaze.py` in MAMBA_GAZE_ROOT (confirmed by GPT).
5. Worker count policy.
   12 workers, object-level pool (no nested parallelism).
   Both 3DVA pilot (via `run_pooled_eval` bash pool) and MeshMamba
   (via `--workers` flag to `run_meshmamba_gaze.py`) use this count.
6. Geometric calibration — NOT touched.
   GPT's calibration updates to preview manifests (bunny rotX=-45,
   Starfruit fov=37.5) are committed as-is.
   `run_meshmamba_non_texture_pilot.sh` already had `--override-fov-deg 37.5`
   and `--extra-rotate-x-deg 90` from the GPT hook (validated for Starfruit_L3).
Risks:
1. `run_meshmamba_non_texture_pilot.sh` passes `--override-fov-deg 37.5`
   hardcoded. If a different pilot model has a different validated FOV, the
   wrapper needs to be updated before that model is run. The manifest now
   documents that `Starfruit_L3` is the validated reference; other models still
   need individual preview checks.
2. `mirror_side_inputs.sh` uses `ssh ... bash <<REMOTE ... REMOTE` (here-doc SSH)
   for server unpack. This requires the SSH key to be set up without passphrase
   (or ssh-agent) for non-interactive use. If SSH requires passphrase input,
   use `unpack_on_server.sh` separately after manual scp.
3. `scp_archives.sh` has no guard against accidental execution. Label is clear
   in header: "DO NOT RUN without explicit confirmation from GPT that transfer
   is approved."
4. The 3DVA parallel pool in `run_3dva_pilot.sh` (GPT-authored) uses
   `jobs -pr | wc -l` which is bash-specific. This works on Linux (server)
   and macOS for local testing. If run in a non-bash shell, it will fail at
   the `jobs -pr` call.
Questions for GPT:
1. `run_meshmamba_gaze.py` CLI: the wrapper currently passes
   `--device auto --frame-alignment nearest --point-weight-mode unit
   --smoothing-mode diffusion`. Confirm these flags exist in the actual
   script and no extra required args are missing.
2. For MeshMamba full run (not just Starfruit pilot): should `--override-fov-deg`
   be passed per-model from the JSON, or is `37.5` a dataset-wide constant?
3. Should `scp_archives.sh` include a dry-run mode that only prints the scp
   commands without executing them?
Next step: commit this batch, then GPT reviews the meshmamba_gaze CLI flags
before any server-side run.

## 2026-05-30 10:05 MSK
Role: Claude
Commit: 9a55147 (HEAD); also covers 85c187e and cc7cffb in this session
Scope: Post-batch audit — document commits 85c187e → cc7cffb → 9a55147;
embed read-only command sheet; record open mismatches.
Files inspected:
  `test/launch/run_meshmamba_non_texture_pilot.sh` (HEAD, 110 lines)
  `test/side_inputs/scp_archives.sh` (HEAD, 69 lines)
  `test/manifests/meshmamba_non_texture_pilot.json` (HEAD)
  `test/manifests/3dva_pilot.json` (HEAD)
  `git show --stat` for all three commits
  `git show 9a55147` full diff
Files changed: `trash/Claude.md` (this entry only — append-only)
Findings:

### Commit 85c187e — "Add preview calibration and server pilot wrappers"
  Author: Danchik757 · 2026-05-30 09:45 MSK · 20 files, +786/-101
  This was the large batch commit containing both GPT-authored and
  Claude-authored work from Session 2. Key changes by group:

  Side-input infrastructure (all Claude-authored, new files):
    `test/side_inputs/README.md` — policy table, per-dataset inventory table,
      file counts (3DVA: 32+32, MeshMamba: 105+105), workflow steps
    `test/side_inputs/inventory_3dva.sh` — dry-run listing, no scp
    `test/side_inputs/inventory_meshmamba_non_texture.sh` — same for MeshMamba
    `test/side_inputs/pack_3dva.sh` — creates 3dva_csv.tar.gz + 3dva_json.tar.gz
    `test/side_inputs/pack_meshmamba_non_texture.sh` — creates
      meshmamba_non_texture_csv.tar.gz + meshmamba_non_texture_json.tar.gz
    `test/side_inputs/scp_archives.sh` — scp template (no DRY_RUN yet in this commit)
    `test/side_inputs/unpack_on_server.sh` — server-side unpack + file-count check

  Launch wrappers and manifests (Claude-authored corrections):
    `test/launch/run_meshmamba_non_texture_pilot.sh` — entrypoint fixed to
      run_meshmamba_gaze.py; GT path fixed to SaliencyMap/non_texture;
      WORKERS default raised to 12
    `configs/server_vg_intellect.env` — WORKERS 8 → 12
    `test/manifests/meshmamba_non_texture_pilot.json` — same three corrections
    `test/manifests/3dva_pilot.json` — WORKERS 8 → 12, parallelism_style added

  Preview calibration (GPT-authored, Claude did not touch):
    `test/manifests/preview_3dva_bunny.json` — video_path added,
      extra_rotate_x_deg: -45.0 (bunny calibration from video-vs-preview)
    `test/manifests/preview_meshmamba_non_texture_starfruit.json` — NEW; Starfruit_L3,
      fov=37.5, rotX=90, recenter=true
    `test/manifests/preview_meshmamba_rgb_texture_starfruit.json` — video_path added
    `test/manifests/3dva_pilot.json` — bunny model override extra_rotate_x_deg: -45.0
    `test/launch/run_3dva_pilot.sh` — object-level parallel pool (run_pooled_eval),
      PILOT_OBJECTS env var, WORKERS=12
    `test/tools/render_preview_from_manifest.py` — GPT update
    `test/env/local_paths.example.sh` — GPT update
    `test/README.md` — GPT update
    `test/launch/mirror_side_inputs.sh` — archive-based transfer (tar.gz → scp →
      here-doc SSH unpack); SSH host alias usage documented
    `trash/GPT.md` — GPT session log

### Commit cc7cffb — "append Claude.md log for fixes A-C"
  Author: Danchik757 · 2026-05-30 09:47 MSK · 7 files, +131 insertions
  Claude.md received the prior session's full log entry (131 lines).
  The 6 side-input shell scripts also appear in this commit's stat with 0-byte
  changes — they were already in 85c187e but their execute-bit or index entry
  needed a separate staging pass. No logic changes in this commit.

### Commit 9a55147 — "Refine MeshMamba pilot and scp dry-run"
  Author: Danchik757 · 2026-05-30 09:48 MSK · 2 files, +33/-6
  Addresses GPT question #3 from the prior session log
  ("Should scp_archives.sh include a dry-run mode?") and makes the
  transform parameters overridable.

  `test/launch/run_meshmamba_non_texture_pilot.sh`:
    Added 3 new env-var overrides with defaults:
      RECENTER_TO_BBOX_CENTER=true
      EXTRA_ROTATE_X_DEG=90
      OVERRIDE_FOV_DEG=37.5
    Replaced hardcoded `--recenter-to-bbox-center --extra-rotate-x-deg 90
    --override-fov-deg 37.5` with env-var-driven:
      ${RECENTER_FLAG} (computed from RECENTER_TO_BBOX_CENTER)
      --extra-rotate-x-deg ${EXTRA_ROTATE_X_DEG}
      --override-fov-deg ${OVERRIDE_FOV_DEG}
    Added per-parameter echo lines so server logs show transform values.
    Added "(workers reserved for outer multi-model pool)" to workers log line.

  `test/side_inputs/scp_archives.sh`:
    Added DRY_RUN env var (default 0).
    Added run_scp() helper: if DRY_RUN=1 prints the command; else executes scp.
    All scp calls now go through run_scp().
    DRY_RUN value echoed at startup.

### Mismatches and open questions (do not fix; record only)
  MISMATCH-1: `run_meshmamba_non_texture_pilot.sh:93-107` passes these flags
    to run_meshmamba_gaze.py:
      --device auto
      --frame-alignment nearest
      --point-weight-mode unit
      --smoothing-mode diffusion
    None of these flags have been confirmed against the actual script in
    MAMBA_GAZE_ROOT. If any flag name differs, the pipeline will fail at
    startup with an argparse error. This is the highest-priority open item
    before any server run.
  MISMATCH-2: `run_meshmamba_non_texture_pilot.sh:100` passes
    `--mapping-json "${MAPPING_JSON}"`. Existence of the `--mapping-json`
    flag in run_meshmamba_gaze.py has not been confirmed.
  MISMATCH-3: `run_meshmamba_non_texture_pilot.sh` does not pass a `--workers`
    flag. The WORKERS env var is declared but the script description says
    "workers reserved for outer multi-model pool". It is unclear whether
    run_meshmamba_gaze.py accepts --workers and whether it should be passed
    for the pilot single-model run.
  NOTE: All three mismatches require GPT confirmation from the real MAMBA_GAZE
    codebase. No code changes until confirmed.

Risks:
1. MAMBA_GAZE CLI flags unconfirmed — see mismatches above. First server run
   will fail if any flag is wrong. Mitigation: run with a single model in a
   tmux session and watch argparse output before committing to a full pilot.
2. `run_3dva_pilot.sh` uses `jobs -pr | wc -l` (bash-specific). Ensure the
   server shell is bash when sourcing the script (shebang is `#!/usr/bin/env bash`
   so direct invocation is safe; sourcing into zsh is not).
3. Transform params are now overridable per-run (good), but default values in
   the script (EXTRA_ROTATE_X_DEG=90, OVERRIDE_FOV_DEG=37.5) only match
   Starfruit_L3. Running another model without an explicit override could
   produce silently wrong geometry alignment.
4. unpack_on_server.sh expects file counts 3DVA=32+32 and MeshMamba=105+105.
   If the local GAZE_DATA has a different count (models added or excluded),
   the count-check will print a mismatch warning but not fail. Verify counts
   locally before packing.
Questions for GPT:
1. (Carried forward, highest priority) Confirm exact CLI flags for
   run_meshmamba_gaze.py: --device, --frame-alignment, --point-weight-mode,
   --smoothing-mode, --mapping-json. Are any of these wrong or missing?
2. Does run_meshmamba_gaze.py accept a --workers flag? Should it be passed
   for the single-model pilot or only for multi-model full run?
3. For EXTRA_ROTATE_X_DEG: is 90 a dataset-wide constant for MeshMamba
   non_texture, or does each model require an individually validated value?
Next step: wait for GPT confirmation on MAMBA_GAZE CLI flags (questions 1-2
above) before the first server-side pilot run.

## 2026-05-30 10:30 MSK
Role: Claude
Commit: 46cccf5 (local HEAD; server pulled to 46cccf5)
Scope: Server preparation, side-input transfer, MeshMamba non_texture pilot run.
Files inspected:
  `configs/server_vg_intellect.env` (server copy)
  `test/side_inputs/scp_archives.sh`
  `test/side_inputs/unpack_on_server.sh`
  `test/launch/run_meshmamba_non_texture_pilot.sh`
  `/tmp/meshmamba_pilot.log` (server)
  `outputs/MeshMamba_non_texture/pilot/Starfruit_L3/metrics_vs_gt.json` (server)
  `outputs/MeshMamba_non_texture/pilot/Starfruit_L3/run_summary.json` (server)
  `MAMBA_GAZE/mamba_gaze/name_mapping.py:120` (server)
  `MAMBA_GAZE/run_meshmamba_gaze.py` (server, full arg list confirmed)
Files changed: `trash/Claude.md` (this entry only)
Findings:

### Server state verified
  Both repos present at expected server paths.
  `Mesh-Saliency-Projection` on `reproject-benchmark` at `46cccf5`.
  `MAMBA_GAZE` at `42eb4fc`.
  Conda env `reproject-benchmark` fully functional:
    python 3.11.15, numpy 2.4.4, pandas 3.0.3, scipy 1.17.1, PIL 12.2.0, torch 2.12.0+cpu.

### Side-input transfer completed
  Archives transferred via `scp_archives.sh DRY_RUN=0`:
    3dva_csv.tar.gz 8.1M, 3dva_json.tar.gz 476K,
    meshmamba_non_texture_csv.tar.gz 18M, meshmamba_non_texture_json.tar.gz 1.5M
  `unpack_on_server.sh` ran clean:
    3DVA: 32 csv + 32 json checked OK
    MeshMamba_non_texture: 105 csv + 105 json checked OK
  `tar` warnings about `LIBARCHIVE.xattr.com.apple.provenance` are
  macOS extended attributes that Linux tar ignores — benign, no action needed.

### 3DVA blocker: PerSubjectFixations missing
  `eval_vs_gt_visual_attention.py:163` and `eval_geodesic_diffusion.py:158`
  both call `load_subject_maps()` which reads from `PerSubjectFixations/`.
  This directory does not exist on the server or locally.
  Local `PerSubjectData.zip` is 0 bytes (empty placeholder).
  Without `PerSubjectFixations`, both 3DVA eval scripts will crash at `np.stack([])`.
  Server 3DVA dataset dirs present: `3DModels-Simplif-up`, `3DModels-Simplif-224-up`,
    `CentricityAndVisibilityMaps`, `FixationMaps`, `test_viewpoints`.
  Symlink `3DModels-Simplif -> 3DModels-Simplif-up` was created on server to
  satisfy the hardcoded `dataset_root / "3DModels-Simplif"` in both scripts.
  3DVA pilot is BLOCKED until `PerSubjectFixations` data is available.

### MeshMamba OBJ naming mismatch — 70 of 105 models fixed
  `MAMBA_GAZE/mamba_gaze/name_mapping.py:120` constructs mesh paths as
    `<mesh_dir>/<dir_name>/<dir_name>.obj`
  but the actual OBJ files use different base names, e.g.:
    dir `Starfruit_L3` -> actual OBJ `Starfruit-L3.obj` (hyphen vs underscore)
    dir `Bird_v1_L3` -> actual OBJ `Chick.obj` (completely different name)
  35 models already had matching names; 70 did not.
  Fix applied on server (no code changes to MAMBA_GAZE):
    For each of the 70 mismatched model dirs, created symlink
    `<dir_name>.obj -> <actual_obj_file>` within that directory.
  Symlinks are NOT tracked in git or manifests — if server datasets are
  re-provisioned, this script must be re-run.

### MAMBA_GAZE CLI flags — fully confirmed, all mismatches closed
  All flags used in `run_meshmamba_non_texture_pilot.sh` exist:
    `--model`, `--gaze-csv-dir`, `--mesh-dir`, `--json-dir`, `--gt-dir`,
    `--output-dir`, `--mapping-json`, `--device`, `--frame-alignment`,
    `--point-weight-mode`, `--smoothing-mode`
  `--recenter-to-bbox-center` uses `BooleanOptionalAction` — both
    `--recenter-to-bbox-center` and `--no-recenter-to-bbox-center` are valid.
  `--workers` does NOT exist — parallelism is external only.
  MISMATCH-1, MISMATCH-2, MISMATCH-3 from prior log are all CLOSED.

### MeshMamba non_texture pilot — Starfruit_L3 COMPLETED
  Transform: recenter=true, extra_rotate_x_deg=90, effective_fov_deg=37.5
  Mesh: 16,436 vertices, 32,868 faces
  Participants: 36 loaded, 35 used (1 excluded by pipeline)
  Points used: 21,592 | Hits: 10,781 | Hit rate: 49.9%
  Runtime: 51.8 seconds (cpu)
  Outputs in server `.../outputs/MeshMamba_non_texture/pilot/Starfruit_L3/`:
    aggregate_face_saliency_sum.csv, aggregate_face_saliency_max.csv,
    metrics_vs_gt.json, participant_summary.csv, run_summary.json,
    resolved_paths.json, participants/
  Primary metrics (aggregate_sum):
    CC: -0.109   SIM: 0.326   KLD: 8.29   MSE: 0.130
    Spearman: -0.133   Cosine: 0.351
    AUC_Judd_gt_top_10pct_proxy: 0.393
  IMPORTANT FOR GPT: CC and Spearman are NEGATIVE.
    Predicted saliency is inversely correlated with GT.
    Geometric preview (visual check) was validated for Starfruit_L3, so the
    transform appears correct. Cause is likely in projection or diffusion step.
    Do not proceed to full pilot without GPT analysis.

### `--no-capture-output` required for conda run in tmux
  `conda run` buffers all child stdout/stderr until process exits by default.
  In a detached tmux session this causes the log to be empty until completion.
  Fix: add `--no-capture-output` flag to `conda run` invocations.
  Added to `/tmp/launch_meshmamba_pilot.sh` (server temp file, not in git).

Risks:
1. Negative CC/Spearman on Starfruit_L3 — first pilot, needs GPT analysis.
   Do not extrapolate to other models or proceed to full run without review.
2. 3DVA pilot blocked by missing PerSubjectFixations — do not attempt to run.
3. OBJ symlinks (70 models) live only on server — not tracked in git.
   Document this in any re-provisioning runbook.
4. 1 of 36 participants excluded in Starfruit_L3 — reason not shown in log.
Questions for GPT:
1. CC=-0.109, Spearman=-0.133 for Starfruit_L3 pilot: what does this indicate?
   Is it a projection/smoothing issue, or expected for a pilot on a single model?
2. PerSubjectFixations for 3DVA: where can this data be obtained, or should
   the eval scripts be adapted to work with FixationMaps only?
3. Given negative metrics, should we run a second pilot model (Aquarium_Deep_Sea_Diver_v1_L1)
   before drawing conclusions?
Next step: wait for GPT analysis of pilot metrics before deciding next run.

---

## READ-ONLY COMMAND SHEET (current HEAD = 9a55147)
## Do not execute any command below without GPT approval.
## All commands assume the local repo root as working directory.

### 0. Prerequisites
  # SSH config must have:
  #   Host vg-intellect
  #       HostName <actual-ip-or-hostname>
  #       User 29d_kon@lab.graphicon.ru
  # LOCAL_GAZE_DATA_ROOT must point to the local GAZE_DATA directory.
  # REMOTE_SIDE_INPUTS must point to the server-side side_inputs directory.

### 1. Local inventory (dry-run — lists files and sizes, nothing created)
  LOCAL_GAZE_DATA_ROOT=/path/to/GAZE_DATA \
    bash test/side_inputs/inventory_3dva.sh

  LOCAL_GAZE_DATA_ROOT=/path/to/GAZE_DATA \
    bash test/side_inputs/inventory_meshmamba_non_texture.sh

### 2. Local pack (creates archives under /tmp/reproject_side_inputs)
  LOCAL_GAZE_DATA_ROOT=/path/to/GAZE_DATA \
    bash test/side_inputs/pack_3dva.sh

  LOCAL_GAZE_DATA_ROOT=/path/to/GAZE_DATA \
    bash test/side_inputs/pack_meshmamba_non_texture.sh

  # Archives created:
  #   /tmp/reproject_side_inputs/3dva_csv.tar.gz           (~5-10 MB)
  #   /tmp/reproject_side_inputs/3dva_json.tar.gz          (<1 MB)
  #   /tmp/reproject_side_inputs/meshmamba_non_texture_csv.tar.gz  (~20-40 MB)
  #   /tmp/reproject_side_inputs/meshmamba_non_texture_json.tar.gz (<5 MB)

### 3. Local scp dry-run (DRY_RUN=1 — prints commands only, no transfer)
  DRY_RUN=1 \
  REMOTE_SIDE_INPUTS=/home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/side_inputs \
    bash test/side_inputs/scp_archives.sh

  # To execute the real transfer (requires GPT approval first):
  # DRY_RUN=0 \
  # REMOTE_SIDE_INPUTS=... \
  #   bash test/side_inputs/scp_archives.sh

### 4. Server unpack (run on vg-intellect after scp transfer)
  # On vg-intellect, inside tmux:
  cd /home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/Mesh-Saliency-Projection
  source configs/server_vg_intellect.env
  bash test/side_inputs/unpack_on_server.sh
  # Expected output: 32 CSV + 32 JSON for 3DVA; 105 CSV + 105 JSON for MeshMamba.

### 5. First tmux pilot launches (on vg-intellect — requires MAMBA_GAZE CLI confirmed first)
  # Connect and start tmux:
  ssh vg-intellect
  tmux new -s reproject_pilot

  # Inside tmux — load env and activate conda:
  cd /home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/Mesh-Saliency-Projection
  source configs/server_vg_intellect.env
  conda activate "${CONDA_ENVS_ROOT}/reproject"
  # (or: source "${CONDA_ENVS_ROOT}/reproject/bin/activate" if conda shell init not loaded)

  # Pull latest code first:
  git fetch origin reproject-benchmark
  git checkout reproject-benchmark
  git pull

  # 3DVA pilot (PILOT_VIEWS=300 default, 6 models, object-level pool, WORKERS=12):
  bash test/launch/run_3dva_pilot.sh

  # MeshMamba non_texture pilot — single model Starfruit_L3, MAMBA_GAZE CLI must be confirmed:
  # *** DO NOT RUN until MAMBA_GAZE CLI flags are confirmed by GPT ***
  PILOT_MODEL=Starfruit_L3 bash test/launch/run_meshmamba_non_texture_pilot.sh

  # Detach tmux and leave running: Ctrl-b d
  # Reattach: tmux attach -t reproject_pilot

---

## [2026-05-30] Baseline script authoring — MeshMamba cone/screen-space + 3DVA launch wrappers

### Context
Continuing from previous session (summary: eval_3dva_raycast_cone.py created, pilot ran with CC=-0.109).
Completed all remaining script-authoring tasks from NEXT_AGENT_HANDOFF.md.

### Files created / modified

**New Python evaluation scripts:**

1. `reprojection_methods/cone_projection_on_mesh/eval_meshmamba_cone.py`
   - Face-level adapter of the 3DVA raycast/cone approach for MeshMamba non_texture
   - Methods: `raycast_nearest_face` (accumulate on idx_tri) + `cone_gaussian_on_mesh` (spread to nearby face centroids via cKDTree on `xmesh.triangles_center`)
   - GT: per-face CSV (one float per line), found via fuzzy name match (underscore ↔ dash)
   - OBJ: found via fuzzy match in `{dataset_root}/MeshFile/non_texture/{model}/`
   - JSON prefix: `MeshMamba_non_texture_{model}.json`
   - Env vars: `MESHMAMBA_NON_TEXTURE_ROOT`, `MESHMAMBA_CSV_ROOT`, `MESHMAMBA_JSON_ROOT`, `MESHMAMBA_OUTPUT_DIR`
   - Output: `{model}_raycast_faces.txt`, `{model}_cone_faces.txt`, `{model}_report.json`
   - Metrics: CC, LCC, AUC, KLD, SIM, Spearman, MSE, MAE, Cosine (same as 3DVA script)

2. `reprojection_methods/screen_space_gaussian/eval_meshmamba_screen_space.py`
   - Screen-space Gaussian baseline for MeshMamba non_texture
   - Method `screen_space_gaussian`: build global gaze density map (256×144 + Gaussian blur), then per frame project face centroids to screen and sample density weighted by frame gaze count
   - Correct per-frame rotation handling: uses `frames[f].rotation_z_radians` to transform face centroids each frame
   - Sigma param: `--sigma-screen` (fraction of image width, default 0.05)
   - Same GT/OBJ/JSON path logic as eval_meshmamba_cone.py
   - Env vars: same set as cone script
   - Output: `{model}_screen_space_faces.txt`, `{model}_report.json`

**New launch scripts:**

3. `test/launch/run_3dva_raycast_cone.sh`
   - Batch wrapper for `eval_3dva_raycast_cone.py` over multiple 3DVA models
   - Required env vars: `VISUAL_ATTENTION_3D_SHAPES_ROOT`, `THREE_DVA_CSV_ROOT`, `THREE_DVA_JSON_ROOT`, `OUTPUT_ROOT`
   - Optional: `PILOT_OBJECTS`, `SIGMA_DEG`, `RADIUS_SIGMA_MULT`, `RECENTER_TO_BBOX_CENTER`, `EXTRA_ROTATE_X_DEG`, `OVERRIDE_FOV_DEG`
   - Default model list: `bunny A380 dragon chair107 flowerpot car-vasa`
   - Parallel pool with `WORKERS` (default 4, since each invocation is CPU-heavy raycast)
   - Output: `{OUTPUT_ROOT}/3DVA/raycast_cone/`; per-model `{model}_run.log`

4. `test/launch/run_meshmamba_baseline_cone.sh`
   - Single-model pilot wrapper for `eval_meshmamba_cone.py`
   - Required: `MESHMAMBA_NON_TEXTURE_ROOT`, `SIDE_INPUTS_ROOT`, `OUTPUT_ROOT`
   - Default model: `Starfruit_L3` with `RECENTER_TO_BBOX_CENTER=true`, `EXTRA_ROTATE_X_DEG=90`, `OVERRIDE_FOV_DEG=37.5`
   - Output: `{OUTPUT_ROOT}/MeshMamba_non_texture/baseline_cone/`

5. `test/launch/run_meshmamba_baseline_screen_space.sh`
   - Single-model pilot wrapper for `eval_meshmamba_screen_space.py`
   - Same env vars as baseline_cone; replaces `SIGMA_DEG` with `SIGMA_SCREEN=0.05`
   - Output: `{OUTPUT_ROOT}/MeshMamba_non_texture/baseline_screen_space/`

**Modified:**

6. `test/launch/run_meshmamba_non_texture_pilot.sh`
   - Added `SMOOTHING_MODE="${SMOOTHING_MODE:-diffusion}"` default
   - Added `--smoothing-mode "${SMOOTHING_MODE}"` replacing hardcoded `diffusion`
   - Added echo line for smoothing_mode in startup banner
   - Choices: none / diffusion / geodesic_kde

### Design decisions

- Face centroids in cone method are taken from `xmesh.triangles_center` (after vertex transform) — not computed separately — to ensure exact consistency with the transformed mesh.
- Screen-space script uses 256×144 internal image (factor 7.5 downscale from 1920×1080) for speed; sigma scales proportionally with `_IMG_W`.
- Screen-space sigma is specified as fraction of image width (`--sigma-screen`) not degrees, to decouple it from depth.
- GT fuzzy match: tries exact, then underscore↔dash swap, then case-insensitive normalized match. Raises FileNotFoundError with helpful list of available files on failure.
- OBJ fuzzy match: same strategy + fallback to first `*.obj` in model directory (handles server symlink setup).
- `WORKERS=4` default in 3DVA batch script (not 12) because each call does full raycasting over all frames — much heavier per-model than the original `eval_vs_gt_visual_attention.py`.

### Status

All script-authoring tasks from NEXT_AGENT_HANDOFF.md now complete:
- [x] eval_3dva_raycast_cone.py (previous session)
- [x] eval_meshmamba_cone.py
- [x] eval_meshmamba_screen_space.py
- [x] run_3dva_raycast_cone.sh
- [x] run_meshmamba_baseline_cone.sh
- [x] run_meshmamba_baseline_screen_space.sh
- [x] SMOOTHING_MODE support in run_meshmamba_non_texture_pilot.sh

Not yet committed (pending GPT confirmation). trimesh + sklearn already installed on server.
Next: GPT review → commit → server pilot run for baseline methods.

