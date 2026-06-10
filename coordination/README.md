# Project Coordination

This directory is the operational source of truth for the two implementation
workers and the temporary reviewer/controller.

## Roles

| Role | Instruction and append-only log |
| --- | --- |
| macOS Claude implementation worker | `coordination/agents/MACOS_CLAUDE.md` |
| Windows/WSL Claude implementation worker | `coordination/agents/WINDOWS_CLAUDE.md` |
| Reviewer/controller and remote benchmark operator | `coordination/agents/REVIEWER_CONTROLLER.md` |

No agent is the project's author or contributor. Commits use the repository's
existing human git identity with no AI attribution or `Co-authored-by` trailers.

## Start Here

Every role must first read:

1. `coordination/COMMON_AGENT_ONBOARDING.md`
2. the mandatory read order defined in that file
3. its own file under `coordination/agents/`

Copy-ready initial prompts are in `coordination/START_PROMPTS.md`.

Each role may append only to its own agent file. Entries must record commit
hashes where applicable, commands, inputs, results, failures, and unresolved
questions.

## Current Integration State

- Integration branch: `reproject-benchmark`
- Current rc2 integration point during this review: `15eb036`
- Data release used by current benchmark runs: `v2.0-data-rc2`
- Workers never merge directly into `reproject-benchmark`.
- The reviewer/controller reviews and integrates. Implementation work should
  happen on worker branches unless the change is documentation-only or an
  explicitly approved small fix.
- The Windows worker branch is not to be deleted or rewritten while its WSL
  state is unresolved.

## Current Phase Status

Completed for rc2:

- processed fixation JSON is the default input format;
- reports include fixation provenance and resume guards;
- SAL3D fixed per-face GT is supported;
- alignment preview tooling exists for 3DVA, MeshMamba, and SAL3D;
- six-view heatmap rendering exists for qualitative inspection;
- release `v2.0-data-rc2` is published.

Current active work:

- full rc2 metric runs on `vg-iai`;
- review and cleanup of auxiliary tooling before a future submodule split;
- prepare, but do not yet run, rc2-compatible sigma sweep.

Known excluded/problem data:

- `3DVA_jessi`: empty cropped-reset fixation file, excluded by loader;
- `SAL3D_gorgoile`: no processed fixation JSON, excluded from participant-gaze metrics.

See also:

- `coordination/PROJECT_STATE_2026-06-10.md`
- `coordination/RESTRUCTURING_REVIEW_2026-06-10.md`
- `coordination/PIPELINE_3DVA.md`
