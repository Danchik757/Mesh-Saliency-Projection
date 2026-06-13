# Project Structure

## Stable core

- `metrics/`
- `reprojection_methods/`
- `utils/`
- `test/launch/`
- `test/kld_parameter_sweep/`
- `scripts/`
- `server/`
- `configs/`
- `jsons/`
- `participant_data/`
- `results/csv/`
- `docs/`
- `datasets/`
- `requirements/`

## Why this structure

- `metrics/`
  - one place for trusted metric implementations
- `reprojection_methods/`
  - method-specific code and documentation
- `requirements/`
  - task-specific dependency files instead of one oversized environment
- `datasets/`
  - dataset manifests, adapters, and split definitions
- `results/csv/`
  - portable, deduplicated result tables and their SHA-256 manifest
- `docs/`
  - project-level explanations and planning notes
- `utils/`
  - small reusable helpers that are not tied to one method
- `configs/`
  - reproducible run configurations
- `experiments/`
  - one-off or exploratory scripts before they are promoted into stable modules
- `test/`
  - active core regression tests and production launchers
- `tests/`
  - reserved compatibility test directory

## Auxiliary tools submodule

Alignment, visualization, heatmap, video/render, manifests, and tool-specific
tests live in the private `Danchik757/Mesh-Saliency-Tools` repository, connected
at `tools/mesh-saliency-tools`. See
[CORE_TOOLS_BOUNDARY.md](./CORE_TOOLS_BOUNDARY.md).

## Recommended rule

Keep stable logic in:

- `metrics/`
- `reprojection_methods/`
- `utils/`
- `test/launch/`
- `test/kld_parameter_sweep/`
- `conftest.py`
- `pytest.ini`

The core metric pipeline must not import or execute the auxiliary submodule.
Core tests must pass in a clone where the submodule is not initialized.
