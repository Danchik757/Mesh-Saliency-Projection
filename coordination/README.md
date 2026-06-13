# Project Coordination

This directory preserves multi-agent review instructions, audits, and project
state. Current technical contracts live in `coordination/DATA_CONTRACT.md` and
the authoritative documents under `docs/`.

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

- Integration branch: `integration/final-rc4`.
- Release candidate: `v2.0-data-rc4`, schema version 2.
- Timing contract: `one_turn_from_start`, offset0 fixation JSON.
- Auxiliary tools repository:
  `Danchik757/Mesh-Saliency-Tools`, pinned at `tools/mesh-saliency-tools`.
- Agent branches remain read-only until final post-split review and promotion
  to `main`.

## Current Phase Status

Completed:

- processed fixation JSON is the default input format;
- reports include fixation provenance and resume guards;
- SAL3D fixed per-face GT is supported;
- offset0 participant fixation JSON is tracked and release-packaged;
- release builder/validator, merge guards, resume identity, and provenance are
  updated for rc4;
- alignment, heatmap, and video tools moved to the public tools submodule;
- rc4 release build and clean-extract validation pass locally.

Current active work:

- independent post-integration reviews;
- clean-clone/core-without-submodule verification;
- final promotion to `main` and rc4 upload.

Known excluded/problem data:

- `3DVA_jessi`: only 41 processed fixation frames, excluded by loader;
- `SAL3D_gorgoile`: no processed fixation JSON, excluded from participant-gaze metrics.

See also:

- `coordination/PROJECT_STATE_2026-06-10.md`
- `coordination/RESTRUCTURING_REVIEW_2026-06-10.md`
- `coordination/PIPELINE_3DVA.md`
