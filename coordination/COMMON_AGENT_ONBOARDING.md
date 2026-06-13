# Common Agent Onboarding

This is the mandatory starting document for every worker and reviewer/controller.
It is intentionally strict because the repository contains useful historical
results mixed with obsolete input contracts and server paths.

## Project Objective

The benchmark transfers recorded screen-space gaze to a 3D mesh and compares the
resulting saliency map with dataset GT. The two methods that must be made
reproducible first are:

- `screen_space_gaussian`
- `cone_gaussian_on_mesh`

The Phase 1 objective is not parameter tuning. It is a correct, release-only,
reproducible full run for:

- 3DVA;
- MeshMamba non_texture;
- MeshMamba rgb_texture;
- SAL3D.

## Mandatory Read Order

Before editing, reviewing, or running anything:

1. `coordination/COMMON_AGENT_ONBOARDING.md`
2. `coordination/PROJECT_CONTEXT.md`
3. `coordination/DATA_CONTRACT.md`
4. `coordination/RELEASE_AUDIT_2026-06-09.md`
5. `coordination/SERVER_GIT_POLICY.md`
6. `coordination/TASK_OWNERSHIP.md`
7. `coordination/REVIEW_AND_INTEGRATION.md`
8. `coordination/DECISIONS_REQUIRED.md`
9. the assigned file under `coordination/agents/`
10. `docs/EVAL_RUNBOOK.md`
11. `trash/Claude.md` and `trash/GPT.md` as append-only historical evidence

Do not treat historical commands, paths, metric values, or conclusions as
current truth without checking the current code and data contract.

## Canonical Inputs

The following data types are independent and must never be silently substituted:

| Input | Canonical location or release archive | Use |
| --- | --- | --- |
| Object placement/camera/animation JSON | `jsons/object_placement/` | What was rendered |
| Original participant CSV | `participant_gaze_csv_original.zip` | Compatibility and participant-aware audit only |
| Processed fixation JSON | `participant_fixations_offset0_full_cleaned.zip` | Default input for new benchmark runs |
| OBJ and GT | Versioned GitHub Release assets | Geometry and comparison target |

Processed fixation JSON format:

```text
fixations[processed_frame_index][point_index] = [x_px, y_px]
```

It has no participant IDs and no explicit timestamps. Therefore direct
participant-equal aggregation cannot be claimed from this format.

Known blockers:

- `3DVA_jessi/fixations.json` has 41 frames instead of 510;
- `SAL3D_gorgoile/fixations.json` and its original CSV are missing;
- neither case may silently fall back to another input.

## Approved Timing Contracts

The baseline rule applies to every dataset and method:

```text
timing_contract = one_turn_from_start
frame_offset = 0
delay_seconds = 0.0
processed_gaze[k] -> placement/video frame k
```

The baseline usable interval must be derived and verified from placement JSON:

- 17-second tracks: use gaze and placement frames `[0, 450)`, one 15-second
  turn, and drop the final 60 frames;
- 24-second SAL3D: use gaze and placement frames `[0, 660)`, one 22-second
  turn, and drop the final 60 frames.

The front-crop plus response-delay experiment remains supported, but it is an
ablation and must never be merged with baseline results:

```text
frame_offset = 54
delay_seconds = 0.2
3DVA/MeshMamba: gaze[60:510] -> placement[54:504]
SAL3D:           gaze[60:720] -> placement[54:714]
```

Launch it through `test/launch/run_ablation_window_delay.py` with
`--frame-offset-override 54 --delays 0.2`. The offset and delay must appear in
the job key, output path, CSV, and report provenance.

Never clamp an out-of-window gaze sample to the final placement frame. Reject or
explicitly drop it.

## Current State and Critical Risks

Current evaluators and launchers use the canonical processed offset0 fixation
JSON input and record timing provenance. Original CSV input is retained only
for explicitly labelled legacy comparisons.

Before a final run, the assigned workers and reviewer must still verify:

1. the requested baseline or ablation timing parameters;
2. report provenance and resume safety;
3. deterministic MeshMamba/SAL3D geometry failure handling;
4. metric normalization and aggregation semantics;
5. 3DVA CombinedGT equal-view semantics;
6. cone depth definition and mesh-density dependence;
7. `A380` old-CSV mixed-video compatibility behavior;
8. SAL3D/GT support mismatches, including `turbine`;
9. release-candidate validator correctness and release-only smoke tests.

## Git and Authorship Rules

- Each worker uses a separate clone, work directory, branch, environment, and
  output directory.
- Start implementation only from the published immutable `BASE_REF`.
- Never commit directly to `reproject-benchmark`.
- Do not merge or rebase another worker branch.
- Commit small coherent milestones and push them.
- Use the repository's existing human git identity.
- Do not mention an AI, Claude, ChatGPT, Codex, an agent, or a model in commit
  author data, commit messages, trailers, or `Co-authored-by`.
- Do not add yourself as a contributor.
- Do not edit `trash/Claude.md`, `trash/GPT.md`, or anything under `md/archive/`.
- Append progress only to the assigned agent MD.
- Stop and document a conflict instead of editing another worker's owned paths.

## Server and Data Rules

Servers:

| Purpose | Host | Only allowed root |
| --- | --- | --- |
| CPU metrics | `vg-intellect-1.lab.graphicon.ru` | `/mnt/ssd1/29d_kon/acm_2026` |
| GPU rendering/debug | `vg-gpu-01.lab.graphicon.ru` | `/mnt/ssd1/29d_kon/acm_2026` |

There is no `sudo`. Do not use any historical `/home/...`, `/ssd1_link/...`, or
other server-local dataset paths. Accepted inputs arrive only through reviewed
Git commits and a validated GitHub Release candidate.

All long jobs use `tmux`, `nice -n 10`, logs, machine-readable summaries, and
new immutable output directories. Process-parallel CPU jobs set BLAS/OpenMP
thread counts to 1.

## Phase Gate

Phase 1 has absolute priority:

1. review and publish a clean baseline;
2. fix input/timing/provenance and geometry/metrics blockers;
3. build and validate the replacement release;
4. pass release-only preflight and representative smoke tests;
5. start correct full metric runs.

Only after the reviewer/controller confirms that correct full metric runs have
started may Phase 2 begin: heatmaps, six-view rendering, heatmap video, sigma
sweeps, and a new research method.

## Required Milestone Evidence

Every milestone entry in an agent work log must contain:

- branch and commit hash;
- exact files changed;
- exact commands run;
- input release/data version and model/track;
- expected and actual result;
- output paths;
- failures and unresolved questions;
- confirmation that `git status --short` is clean after the push.
