# Final Integration History

## Purpose

This document records the decisions that produced the final rc4 integration
candidate. It is historical context, not a substitute for the current data,
release, metric-run, or CSV contracts.

## Contract evolution

| Generation | Participant input | Timing | Status |
| --- | --- | --- | --- |
| legacy | original per-participant CSV | legacy frame interpretation | retained only for historical comparisons |
| rc2 | processed `offset_2000` JSON | `cropped_reset_offset_2000`, placement offset | superseded |
| rc3/rc4 | processed full-length offset0 JSON | `one_turn_from_start`, no default delay | current |

The current baseline pairs `gaze[k]` with `placement[k]`, uses one full turn
from the beginning, and drops the final 60 frames. Delay and start-crop runs are
separate ablations and must not be merged with baseline results.

## Independent audits

Before integration:

- the macOS audit reviewed core evaluators, release/data contracts, runners,
  merge behavior, Smooth Gaze, and provenance;
- the Windows audit reviewed visualization/render tools, camera conventions,
  map domains, normalization, GPU probing, and future tools boundaries.

The core audit fixed incompatible-run merges, NaN/Inf aggregation, stale release
building, resume identity, delay provenance, and release validation. The tools
audit fixed nested MeshMamba OBJ lookup, portable paths, timing defaults, VTK
probing, placement CLI generation, and ambiguity handling.

Windows core evaluator changes were deliberately not merged because they were
based on a stale core without the final frame-offset/provenance contract. Only
reviewed non-core changes were integrated.

## Data and results decisions

- The 298 offset0 fixation JSON files are tracked and independently hashable.
- Original participant CSV remains external but mandatory for the release.
- SAL3D Smooth Gaze remains mandatory and complete, despite the current
  evaluator using only the first 500 of 2000 stored neighbours.
- Raw maps, PNG, MP4, logs, and per-task output directories are not tracked.
- Unique portable CSVs are indexed under `results/csv/`; missing server outputs
  are documented rather than inferred.

## Finalization sequence

1. Pass core integration tests, compileall, diff-check, data-contract checks,
   and clean release build/validation.
2. Create and validate the public tools repository and submodule boundary.
3. Run independent post-split audits of both repositories.
4. Promote the integration branch to `main`.
5. Publish `v2.0-data-rc4`.
6. Remove obsolete remote agent branches only after release acceptance.
