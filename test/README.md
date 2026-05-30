# Test Workspace

This directory is reserved for reproducible validation assets that sit between
exploration and the main pipeline.

Planned use:

1. One-frame preview checks per dataset before large runs.
2. Small pilot launch configs for local and server-side sanity checks.
3. Helper scripts for benchmark orchestration that are not yet stable enough
   for the main package layout.
4. Temporary comparison tables or manifests that should remain versioned.

Rules:

1. Do not store raw participant dumps or large generated artifacts here.
2. Keep files deterministic and easy to rerun from a clean checkout.
3. If a script becomes stable and generally useful, move it out of `test/`
   into the proper project area in a later commit.

## Preview Workflow

The first portable preview flow lives here.

Files:

1. `test/tools/render_preview_from_manifest.py`
   Renders one manifest-defined preview using `OBJ + JSON + optional CSV`.
2. `test/launch/run_preview_manifest.sh`
   Runs one preview manifest.
3. `test/launch/run_preview_suite.sh`
   Runs all `preview_*.json` manifests, or a provided subset.
4. `test/env/local_paths.example.sh`
   Example local environment-variable roots.
5. `test/env/vg_intellect_paths.example.sh`
   Example server environment-variable roots.
6. `test/manifests/preview_*.json`
   Per-dataset preview definitions.

Local example:

```bash
source test/env/local_paths.example.sh
test/launch/run_preview_suite.sh
```

Server example pattern:

```bash
source test/env/vg_intellect_paths.example.sh
tmux new -s reproject-preview
nice -n 10 test/launch/run_preview_suite.sh
```
