# Core And Tools Boundary

## Rule

`Mesh-Saliency-Projection` owns reproducible metric computation. The
private `Danchik757/Mesh-Saliency-Tools` repository owns optional alignment,
visualization, heatmap, and video/render utilities.

The core repository must run and test successfully without initializing the
tools submodule.

## Paths that remain core

- `metrics/`
- `reprojection_methods/`
- `utils/`
- `test/launch/`
- `test/kld_parameter_sweep/`
- `scripts/`, `server/`, `configs/`
- `jsons/`, `participant_data/`, `datasets/`, `requirements/`
- core tests and authoritative documentation

## Completed tools migration

| Tools path | Current source |
| --- | --- |
| `alignment/` | `validation/`, `test/blender_canonical/`, `test/overlay_alignment/` |
| `heatmaps/` | `visualization/`, `gt_visualizations/` |
| `video/` | `video_creation/` |
| `debug/` | `test/tools/` |
| `render_reference/` | `references/render_scripts/` |
| `manifests/` | `test/manifests/` |
| `tests/` | tests dedicated only to the migrated tools |

The submodule location in the core repository is:

```text
tools/mesh-saliency-tools
```

## Acceptance gates

1. Search confirms core Python and launchers do not import or execute a planned
   tools path.
2. Any documentation links or compatibility wrappers are updated in the same
   change as the move.
3. Core tests pass without an initialized submodule.
4. Tools tests pass from the standalone tools repository.
5. An authenticated clean clone with `--recurse-submodules` can run documented
   tools examples.
6. Source auxiliary folders are absent from core.

Current split validation:

- core suite: 325 passed;
- tools suite with a core checkout: 419 passed;
- standalone tools suite: 409 passed, 10 core-dependent tests skipped;
- detached core worktree with uninitialized submodule: 325 passed;
- clean recursive clone: core 325 passed and tools 419 passed;
- core search contains no imports or launcher calls into the old auxiliary
  paths;
- tools submodule pinned to `1678a10`.
