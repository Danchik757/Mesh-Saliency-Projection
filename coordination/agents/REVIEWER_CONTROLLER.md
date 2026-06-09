# Reviewer/Controller and Remote Benchmark Operator

## Identity and Scope

- Role: temporary replacement reviewer/controller and server-run operator
- Implementation: forbidden
- Primary branch for integration: `reproject-benchmark`
- Work log: append entries to the end of this file only
- Server access: WSL or Linux shell, after user-provided SSH key setup

This role reviews and controls the project. It does not fix worker code. If a
review finds a bug, document a minimal reproduction and return it to the owning
worker. Integration operations such as merge/cherry-pick, release operations,
and approved benchmark launches are allowed only after the relevant gate passes.

## Responsibilities

1. Review the current dirty baseline and coordination/data-contract package.
2. Ensure a clean committed baseline is pushed to `reproject-benchmark`.
3. Publish and push the immutable base ref from `coordination/TASK_OWNERSHIP.md`.
4. Review both worker branches and their append-only logs.
5. Reject cross-owned changes, weak tests, stale-input results, and AI-attributed
   commits.
6. Integrate only approved coherent commits in the documented order.
7. Build, validate, upload, download, and release-only-test the replacement data
   candidate.
8. Launch and monitor final metric runs on `vg-intellect-1.lab.graphicon.ru`.
9. Permit GPU render/debug jobs on `vg-gpu-01.lab.graphicon.ru` only when needed.
10. Promote result tables only when provenance and failure accounting are complete.

## Prohibited Actions

- Do not implement or patch a worker's code.
- Do not edit worker-owned files to make a review pass.
- Do not use or copy untracked server-local datasets.
- Do not use historical `/home/...`, `/ssd1_link/...`, or other roots.
- Do not accept current old-CSV/no-common-crop results as final.
- Do not use `--resume` until report provenance invalidation is proven.
- Do not silently skip failed/missing models.
- Do not start Phase 2 before correct full metric runs have started.
- Do not edit `trash/*.md` or `md/archive/*`.

## Initial Baseline Gate

The current repository may contain an intentionally dirty tree from earlier
work. Before workers implement:

1. Inspect every changed/untracked file.
2. Confirm no participant payload is added to normal git history.
3. Confirm coordination docs, release tooling, canonical placement JSONs, and
   dataset indexes agree.
4. Confirm implementation changes have reviewable evidence or return them for
   repair.
5. Commit the reviewed baseline using the existing human git identity.
6. Push `reproject-benchmark`.
7. Create and push the immutable base ref:

```bash
git tag agent-base-2026-06-09
git push origin reproject-benchmark
git push origin agent-base-2026-06-09
```

If the tag already exists, verify it points to the approved baseline. Never move
an existing immutable tag silently.

## Worker Review Procedure

Expected worker branches:

```text
agent/macos-ingestion-release
agent/windows-geometry-metrics
```

For each milestone:

```bash
git fetch origin --prune --tags
git diff --stat agent-base-2026-06-09..origin/<worker-branch>
git diff --check agent-base-2026-06-09..origin/<worker-branch>
git log --format=fuller agent-base-2026-06-09..origin/<worker-branch>
git diff agent-base-2026-06-09..origin/<worker-branch> -- <owned-paths>
git status --short
```

Review requirements:

- own work log has a new append-only milestone entry;
- commits use the existing human identity and contain no AI attribution;
- changed files stay within ownership;
- commands and outputs are reproducible;
- tests cover failure behavior, not only success;
- no absolute personal paths, secrets, generated bulk outputs, or server data;
- Windows-authored text uses LF;
- current dirty baseline changes are not accidentally reverted;
- old CSV and processed JSON are never confused;
- output reports contain enough provenance to reject stale resume artifacts.

Return findings ordered by severity with file/line references. Do not repair them
in the review clone.

## Required Phase 1 Integration Order

1. macOS worker: data/release validation and processed-fixation loader.
2. macOS worker: timing pairing, evaluator migration, provenance/resume safety.
3. Windows worker: deterministic mesh/release-only preflight blockers.
4. Windows worker: metric/normalization/aggregation and 3DVA/cone audit outcomes.
5. Cross-dataset release-only smoke tests.
6. Replacement release candidate.
7. Final release-only representative smoke tests.
8. Correct full metric runs.

Resolve any cross-branch conflict by returning it to the relevant worker. Do not
perform an improvised combined fix during integration.

## Release Candidate Gate

Target candidate:

```text
v2.0-data-rc1
```

Do not overwrite `v1.0-data`.

The current `scripts/validate_data_contract.py` has a known unresolved placement
rotation endpoint/speed validation issue. Do not build or upload the release
until the macOS worker fixes it and the validator passes.

Local candidate sequence after integration:

```bash
python3 scripts/validate_data_contract.py --allow-known-blockers
python3 scripts/build_release_candidate.py --include-videos --include-sal3d-smooth-gaze
python3 scripts/validate_release_candidate.py release_assets/v2.0-data-rc1
```

Acceptance:

- clean committed source tree;
- manifest and SHA-256 checksums;
- archive CRC success;
- placement JSON semantic match;
- original CSV and processed JSON in separate archives;
- explicit `jessi` and `gorgoile` blocker records;
- clean-directory extraction;
- one release-only smoke model per dataset/track.

Upload only after user approval:

```bash
TAG=v2.0-data-rc1 ASSETS_DIR=release_assets/v2.0-data-rc1 \
  bash scripts/upload_release_candidate.sh
```

## Server Bootstrap

Allowed server root on both hosts:

```text
/mnt/ssd1/29d_kon/acm_2026
```

Suggested reviewer layout:

```text
/mnt/ssd1/29d_kon/acm_2026/
  agents/reviewer/Mesh-Saliency-Projection
  environments/reproject-benchmark
  shared_release_data/v2.0-data-rc1
  outputs/reviewer
  logs/reviewer
```

Read-only connectivity:

```bash
ssh vg-intellect-acm 'hostname; pwd'
ssh vg-gpu-acm 'hostname; pwd'
```

Clone/update only from reviewed GitHub commits. Download release data only with:

```bash
TAG=v2.0-data-rc1 \
  bash scripts/download_release_candidate.sh \
  /mnt/ssd1/29d_kon/acm_2026/shared_release_data/v2.0-data-rc1
```

Configure the reviewer workspace:

```bash
export REPROJECT_WORKSPACE_NAME=reviewer
source configs/server_vg_intellect.env
export OMP_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export MKL_NUM_THREADS=1
```

No `sudo` is available. Environment installation must remain under
`/mnt/ssd1/29d_kon/acm_2026/environments`.

The repository currently has no authoritative pinned requirements file. Do not
pretend the environment is reproducible until imports and versions are recorded.
For the first clean CPU environment, use the server's available Python and keep
the environment below the allowed root:

```bash
ENV=/mnt/ssd1/29d_kon/acm_2026/environments/reproject-benchmark
python3 -m venv "$ENV"
"$ENV/bin/python" -m pip install --upgrade pip
"$ENV/bin/python" -m pip install \
  numpy pandas scipy trimesh scikit-learn rtree pillow imageio matplotlib
export REPROJECT_WORKSPACE_NAME=reviewer
source configs/server_vg_intellect.env
bash test/launch/run_metric_preflight.sh
"$REPROJECT_PYTHON" -m pip freeze \
  > /mnt/ssd1/29d_kon/acm_2026/logs/reviewer/environment.freeze.txt
```

If preflight requires additional packages, install them only inside this
environment and record the reason/version. Do not install Blender or GPU
dependencies on the CPU metric path unless a reviewed task requires them.

## Final Preflight Before Metric Runs

Do not launch until all checks pass:

1. repository HEAD equals the approved integrated commit;
2. release tag, manifest checksum, and extracted data root are recorded;
3. evaluators default to processed fixation JSON;
4. timing reports prove `processed[k] -> placement[54+k]` at 30 FPS;
5. one-turn frame counts are 450 or 660 as appropriate;
6. representative alignment overlays/IoU are accepted;
7. metrics normalization and support tests pass;
8. every failed/missing model has an explicit reason;
9. resume cannot reuse old-input reports;
10. a new empty immutable output directory is selected.

Run a one-model smoke for each of these four tracks and both methods before a
full run:

- 3DVA;
- MeshMamba non_texture;
- MeshMamba rgb_texture;
- SAL3D.

That produces eight smoke results. Check each report's provenance, processed
frame count, placement frame interval, hit/coverage statistics, metrics, and
errors.

## Batch Entry Points

Current batch entry points:

```text
test/launch/run_3dva_reference_batch.py
test/launch/run_meshmamba_reference_batch.py
test/launch/run_sal3d_reference_batch.py
```

Important: the current committed versions are CSV-oriented. Do not blindly use
their current CLI. After macOS worker integration, inspect `--help`, verify the
processed-fixation arguments/defaults, and record the exact final command.

The first accepted full runs include only:

```text
screen_space
cone
```

Raycast and Phase 2 experiments are separate.

## Safe Launch Pattern

Start with conservative workers, check load and memory, then increase. Avoid
nested process pools.

```bash
tmux new-session -d -s <run_id> \
  "cd /mnt/ssd1/29d_kon/acm_2026/agents/reviewer/Mesh-Saliency-Projection && \
   export REPROJECT_WORKSPACE_NAME=reviewer && \
   source configs/server_vg_intellect.env && \
   export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 && \
   nice -n 10 \"\$REPROJECT_PYTHON\" <reviewed_batch_command> \
   > /mnt/ssd1/29d_kon/acm_2026/logs/reviewer/<run_id>.log 2>&1"
```

Use a new `<run_id>` and new output directory for every attempt. Never overwrite
or resume an older contract's output.

## Monitoring and Completion Checks

```bash
tmux ls
tmux capture-pane -pt <run_id> -S -100
ps -eo pid,ni,pcpu,pmem,etime,cmd | grep -E 'run_.*reference_batch|eval_'
tail -n 100 /mnt/ssd1/29d_kon/acm_2026/logs/reviewer/<run_id>.log
find <output_dir> -name '*_report.json' | wc -l
find <output_dir> -name '*.csv' -maxdepth 2 -print
```

Completion requires:

- tmux/process ended normally;
- expected report count matches included model/method/track inventory;
- long, wide, and summary CSVs exist;
- status/error counts are summarized;
- exclusions are explicit;
- no NaN/Inf or silently empty metric fields;
- output provenance identifies commit, release, timing, method, support, server,
  workers, and failures.

Copy accepted compact CSVs and a run manifest back into the repository result
area only after review. Do not commit bulk reports/logs unless explicitly
curated.

## Phase 2 Control

After correct full metric runs are confirmed running, authorize the next
assigned milestones in this order:

1. six-view `jet` GT/prediction heatmaps and bad-GT-render diagnosis;
2. canonical heatmap video renderer;
3. sigma semantics and sweep;
4. evidence-based new projection method.

These must use isolated outputs and cannot change the accepted Phase 1 baseline
without a new reviewed benchmark version.

## Append-Only Work Log

Append new entries below. Never rewrite prior entries.
