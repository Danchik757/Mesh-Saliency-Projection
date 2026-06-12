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

## Required before promotion to main

- Re-run all gates after documentation/data commits.
- Perform a real clean-tree rc4 build and validate manifest, SHA-256, ZIP CRC,
  fixation counts, Smooth Gaze inventory, and fixed-face GT inventory.
- Perform a clean extract/fresh-download smoke.
- Complete and validate the public tools submodule migration.
- Request independent post-integration audits from macOS and Windows reviewers.
- Confirm optimized full-run CSVs are either downloaded and indexed or
  explicitly remain documented as unavailable.

## Known blockers and limitations

- `3DVA_jessi` contains only 41 fixation frames and remains excluded.
- `SAL3D_gorgoile` lacks original CSV and processed fixation data.
- SAL3D fixed-face GT is checksum-verifiable but its external regeneration
  pipeline is not currently in the repository.
- Smooth Gaze stores 2000 neighbours per record while the current evaluator
  consumes only the first 500.
- The public tools repository/submodule has not yet been created.
- Agent branches must not be removed until release and submodule acceptance.
