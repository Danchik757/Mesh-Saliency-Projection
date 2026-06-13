# Final Integration Audit

## Integrated inputs

- Core/release branch: `agent/rc3-release-and-ablation-infra`, including final
  resume, release, merge, and Smooth Gaze fixes.
- Tools branch: reviewed non-core commits from
  `agent/windows-video-overlays-rc3`.
- Windows core evaluator files were not integrated because the independent
  audit identified them as stale relative to the final frame-offset contract.

## Verified before data/release finalization

- Full merged pytest suite after data/results verification tooling: 695 passed.
- Targeted renderer suite: 228 passed.
- Python compileall: clean.
- Git diff check: clean.
- Canonical fixation inventory: 298 JSON files, byte-identical to the supplied
  offset0 source.
- CSV consolidation: 77 source CSVs, 70 unique files, 7 duplicates removed;
  manifest SHA-256 verification clean.
- Data contract: no unexpected errors; known blockers are `3DVA_jessi` and
  missing `SAL3D_gorgoile` CSV/processed data.
- rc4 builder dry-run: strict preflight passes with explicit external sources.
- Real `v2.0-data-rc4` build from the final code candidate: 13 archives,
  validator `status=ok`.
- Fresh extract: all 13 SHA-256 checks passed; 298 fixation JSON byte-identical
  to tracked source; Smooth Gaze 53 models; fixed-face GT and repaired meshes
  55/55.
- Post-final-audit core suite: 324 passed.
- `Mesh-Saliency-Tools` suite with core checkout: 415 passed; standalone:
  405 passed and 10 core-dependent tests skipped; submodule pinned to
  `f709458`.
- Detached clean core worktree with uninitialized submodule: 324 passed.
- Clean recursive clone: core 324 passed; tools 415 passed; compileall and
  diff-check clean.
- Independent Windows post-split audit approved the integration for `main` and
  rc4 with no blockers. Its active-documentation/default/dependency findings
  were fixed before the final integration commit.

## Required before promotion to main

- Commit this final audit record and rebuild rc4 once more so its manifest
  points at the exact promotion commit.
- Promote the reviewed integration branch without adding code changes.
- Publish rc4, then perform a clean download validation from the published
  GitHub release before deleting agent branches.

## Known blockers and limitations

- `3DVA_jessi` contains only 41 fixation frames and remains excluded.
- `SAL3D_gorgoile` lacks original CSV and processed fixation data.
- SAL3D fixed-face GT is checksum-verifiable but its external regeneration
  pipeline is not currently in the repository.
- Smooth Gaze stores 2000 neighbours per record while the current evaluator
  consumes only the first 500.
- Public tools repository created, independently reviewed, and pinned as
  `tools/mesh-saliency-tools`.
- Agent branches must not be removed until release and submodule acceptance.
