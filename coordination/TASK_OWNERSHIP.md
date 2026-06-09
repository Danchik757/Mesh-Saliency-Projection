# Task Ownership

## Base Ref

```text
BASE_REF=agent-base-2026-06-09
```

Workers may read and report before this ref exists. They must not edit
implementation code until the reviewer/controller has reviewed the baseline,
pushed `reproject-benchmark`, and published this immutable ref.

## Phase 1 Ownership

| Workstream | Owner | Primary owned paths |
| --- | --- | --- |
| Processed fixation ingestion, timing, evaluator migration, provenance/resume safety, release contract | macOS Claude | `participant_data/`, new `utils/participant_*`, release tooling under `scripts/`, evaluator input/timeline adapters, batch input/provenance adapters, dedicated tests |
| Mesh/release-only preflight, alignment gate, metrics/aggregation/3DVA/cone audit and tests | Windows/WSL Claude | new `utils/mesh_*`, geometry/preflight tools, `metrics/`, metric tests, audit documents, assigned alignment diagnostics |
| Review, integration, replacement release, server smoke/full runs | Reviewer/controller | branch review, approved integration, release operations, remote run control, result promotion |

## Conflict Rules

- macOS Claude must not change metric formulas, mesh-loading policy,
  visualization, sigma sweeps, or research methods.
- Windows Claude must not change participant loaders, evaluator input/timeline
  logic, batch input migration, or release packaging.
- Reviewer/controller must not implement fixes in worker-owned paths.
- Shared coordination documents are controlled by the reviewer/controller after
  this package is published.
- If a required fix crosses ownership, document a minimal reproduction and
  request reassignment. Do not patch the foreign path.
- Do not edit `trash/*.md` or `md/archive/*`.

## Phase 1 Integration Order

1. Publish reviewed baseline and `BASE_REF`.
2. Integrate release/data validation and processed-fixation loader.
3. Integrate timing pairing, evaluator migration, and provenance-safe resume.
4. Integrate deterministic mesh/release-only preflight fixes.
5. Integrate metric/aggregation/3DVA/cone audit corrections approved by review.
6. Build and validate the replacement release.
7. Pass one model per dataset/track per method: eight smoke results.
8. Start correct full metric runs.

## Phase 2 Assignment

Only after step 8:

| Workstream | Initial owner |
| --- | --- |
| Six-view `jet` heatmaps, GT-render diagnosis, heatmap video | Windows/WSL Claude |
| Sigma semantics/sweep and evidence-based new method | macOS Claude |

## Required Evidence for Every Worker Commit

- exact command and test;
- input model/dataset/track;
- release/data version;
- expected and actual result;
- output location;
- known limitations and unresolved questions;
- commit hash and pushed branch;
- clean `git status --short`;
- no unrelated changed files or AI attribution.
