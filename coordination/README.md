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
- Current remote base before this coordination package:
  `684efc31cbbe90c35b7b761d46b5cd4492e1c5fa`
- Planned immutable worker base: `agent-base-2026-06-09`
- Workers may complete onboarding now, but must not edit implementation code
  until the reviewer/controller publishes the reviewed baseline and base ref.
- Workers never merge directly into `reproject-benchmark`.
- The reviewer/controller reviews and integrates; it does not implement fixes.

## Immediate Phase 1 Blockers

1. Existing evaluators and batch launchers still use original CSV input and no
   approved common crop.
2. The processed-fixation loader and report provenance/resume safety are absent.
3. GitHub Release `v1.0-data` is historical and not valid for the next benchmark.
4. `3DVA_jessi` processed fixations are invalid; `SAL3D_gorgoile` is missing.
5. Deterministic MeshMamba/SAL3D geometry failure handling is incomplete.
6. Metric normalization, aggregation, 3DVA CombinedGT, and cone semantics require
   a documented audit decision.
7. A replacement release and release-only eight-result smoke gate must pass
   before full metric runs.

Phase 2 work is blocked until correct full metric runs have started.
