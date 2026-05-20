# Project Structure

## Current folders

- `metrics/`
- `reprojection_methods/`
- `video_creation/`
- `requirements/`
- `datasets/`
- `results/`
- `docs/`
- `utils/`
- `configs/`
- `experiments/`
- `tests/`

## Why this structure

- `metrics/`
  - one place for trusted metric implementations
- `reprojection_methods/`
  - method-specific code and documentation
- `video_creation/`
  - scripts for figures, videos, and visual comparisons
- `requirements/`
  - task-specific dependency files instead of one oversized environment
- `datasets/`
  - dataset manifests, adapters, and split definitions
- `results/`
  - generated reports and evaluation outputs
- `docs/`
  - project-level explanations and planning notes
- `utils/`
  - small reusable helpers that are not tied to one method
- `configs/`
  - reproducible run configurations
- `experiments/`
  - one-off or exploratory scripts before they are promoted into stable modules
- `tests/`
  - smoke tests and regression checks

## Good next folders to add later

- `dataset_adapters/`
  - if multiple datasets need their own loaders and column parsers
- `notebooks/`
  - only for exploration, not for core pipeline logic
- `reports/`
  - human-readable experiment summaries
- `assets/`
  - diagrams, thumbnails, presentation material
- `benchmarks/`
  - reproducible benchmark suites for comparing methods

## Recommended rule

Keep stable logic in:

- `metrics/`
- `reprojection_methods/`
- `utils/`

Keep experimental logic in:

- `experiments/`

Promote code from `experiments/` into the stable folders only after the method and metrics are fixed.
