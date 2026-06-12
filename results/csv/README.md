# CSV Results Index

`results/csv/` is the canonical index of portable tabular benchmark outputs.
Raw maps, rendered images, videos, logs, and per-task report directories are
not stored here.

## Categories

| Directory | Meaning |
| --- | --- |
| `legacy/` | Historical or pre-rc2 results. Do not compare directly without inspecting timing and GT contracts. |
| `rc2/` | Cropped-reset / offset-2000 benchmark outputs. |
| `rc3_baseline/` | Offset0, one-turn-from-start baseline runs using the reference sigma configuration. |
| `rc3_timing_ablation/` | Window and fixation/placement delay experiments. |
| `rc3_sigma_sweep/` | Sigma sweep summaries and selected-sigma tables. |
| `rc3_optimized/` | Full runs using selected optimized sigma values. |
| `diagnostics/` | Pilot, preflight, KLD, postprocess, and failure-diagnostic tables. |

`manifest.csv` records SHA-256, source-relative path, run-contract category,
deduplication, and whether a file is authoritative for reporting.

Regenerate from a working copy containing additional result CSVs:

```bash
python3 scripts/consolidate_results_csv.py \
  --source-results /path/to/Mesh-Saliency-Projection/results \
  --output-root results/csv \
  --clean
```

Server outputs must be downloaded before running the command. A missing server
run is not inferred or silently represented as complete.

Verify the tracked CSV files against the manifest after a clone or merge:

```bash
python3 scripts/consolidate_results_csv.py \
  --output-root results/csv \
  --verify-only
```
