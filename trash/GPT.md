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
