# Core Test Workspace

This directory contains core metric-pipeline regression tests, benchmark
launchers, environment templates, and release/data-contract checks.

Optional alignment, preview, heatmap, and video/render tests moved to the public
[`Mesh-Saliency-Tools`](../tools/mesh-saliency-tools/README.md) submodule.

## Core layout

| Path | Purpose |
| --- | --- |
| `launch/` | Reference, full-run, sigma-sweep, ablation, and merge launchers |
| `kld_parameter_sweep/` | Core KLD parameter-sweep implementation |
| `env/` | Local/server environment templates |
| `test_*.py` | Core evaluator, provenance, release, runner, and result tests |

## Run

```bash
python3 -m pytest -q
python3 -m compileall -q metrics reprojection_methods utils test scripts server
git diff --check
```

Core tests must pass without initializing `tools/mesh-saliency-tools`.

For alignment, heatmap, and video tools:

```bash
git submodule update --init --recursive
python3 -m pytest -q tools/mesh-saliency-tools/tests
```
