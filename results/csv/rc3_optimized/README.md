# RC3 Optimized-Sigma Results

This category is reserved for full-dataset runs using the sigma values selected
from the rc3 stage-1 sweep.

No optimized full-run CSV is currently tracked. At consolidation time the
server output roots on `vg-iai`, `vg-gml01`, and `vg-gml02` were not reachable
from the integration environment, so completion and provenance could not be
verified. Do not substitute smoke-run or partial CSV files.

After downloading verified `metrics_long.csv`, `metrics_compact.csv`, and
`provenance.json`, rerun `scripts/consolidate_results_csv.py` and mark the
verified optimized files authoritative in `results/csv/manifest.csv`.
