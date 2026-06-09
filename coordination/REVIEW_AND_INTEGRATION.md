# Review and Integration

## Reviewer/Controller Responsibilities

The reviewer/controller does not perform delegated implementation work. It:

1. reviews worker branches and append-only logs;
2. rejects changes that cross ownership boundaries;
3. reproduces smoke tests;
4. checks release/data versions and server paths;
5. integrates only approved commits in the documented order;
6. runs replacement-release and release-only gates;
7. launches and monitors accepted cross-dataset benchmarks;
8. promotes only validated artifacts and results.

The complete operational runbook is:

```text
coordination/agents/REVIEWER_CONTROLLER.md
```

## Worker Review Gate

A worker milestone is ready for review only when:

- the branch is pushed;
- the worker MD contains an appended milestone entry;
- `git status --short` is clean;
- tests and smoke commands are listed;
- generated outputs are outside git unless explicitly curated;
- no secrets, absolute personal paths, or server-local untracked data are added;
- Windows-authored text files use LF;
- changes stay inside owned paths;
- commits use the existing human identity with no AI attribution.

## Review Commands

```bash
git fetch origin --prune --tags
git diff --stat agent-base-2026-06-09..origin/<worker-branch>
git diff --check agent-base-2026-06-09..origin/<worker-branch>
git log --format=fuller agent-base-2026-06-09..origin/<worker-branch>
```

Inspect every changed file and reproduce the documented smoke test. Findings are
returned to the owning worker; the reviewer/controller does not patch them.

## Final Benchmark Gate

No full benchmark begins until:

1. the replacement release passes the acceptance gate;
2. evaluators use processed fixation JSON by default;
3. timing mapping is recorded and visually verified;
4. object alignment is verified for representative tracks;
5. metric formulas/normalization/support tests pass;
6. failed/missing models have explicit inclusion/exclusion policy;
7. output directories are new and immutable;
8. resume cannot reuse another gaze/timing contract;
9. 3DVA CombinedGT and cone semantics have approved audit decisions;
10. one model per four tracks per two methods passes release-only smoke.

## Result Provenance

Every promoted result summary identifies:

- git commit;
- release tag and manifest checksum;
- dataset/track;
- included and excluded models;
- method and parameters;
- participant input type;
- timing/crop mode and placement frame range;
- placement/FOV/transform mode;
- metric support/normalization mode;
- worker count and server;
- failure count.
