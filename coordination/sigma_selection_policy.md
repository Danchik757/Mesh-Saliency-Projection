# Sigma is selected per (dataset, method), not per model

_orchestra/metric-ablation-lab — dataset-method ablation orchestration._

## The rule

**Sigma (and, downstream, delay / frame_offset) is chosen once per
`(dataset, method)` pair — never per model.** A single value is committed for the
whole dataset-method branch.

Selection is decided by **mean CC on the common model set**:

1. Every sigma candidate is evaluated on the **same full model subset**.
2. The **common model set** is the intersection of models that succeeded
   (`status == ok`) for **every** candidate in the branch.
3. Mean metrics are recomputed **only on that intersection**.
4. `branch_best` is the candidate with the highest **mean CC on the common set**.

This prevents two failure modes:

- **Per-model selection** — picking sigma from the single best-scoring model.
  Forbidden: the ranking is a mean over the common set, so one outlier model
  cannot swing the choice.
- **Unfair aggregate selection** — picking sigma by an aggregate when different
  sigmas have different surviving models. Forbidden: all candidates are scored on
  the *same* intersection, so a candidate cannot win by dropping its hard models.

`CC` is the only ranking metric. SIM / KLD / MSE / MAE / Spearman / Cosine /
AUC@{10,5,1} / NSS@{10,5,1} / hit_rate are stored as **diagnostics** only. No
multi-objective selector is used without separate agreement.

## Single-model runs

**Single-model runs are smoke / contract validation only.** They confirm the
evaluator CLI and the timing contract work end to end. They never select sigma.

## Holds

A branch is **held** (no promotion, `_held.json` written) when the common set is
empty or covers less than **70 %** of the full subset (`coverage_common < 0.70`) —
the intersection is then too thin to compare candidates fairly.

## Comparability — never mix incompatible runs

Runs are comparable only when these all match:
`release_tag`, `fixation_data_tag`, `timing_contract`, `frame_offset_policy`,
`delay_policy`, and the subset signature. These are hashed into a
`comparability_signature`. Runs with different signatures are kept as **separate
rows** in the shared table and are never averaged or ranked together.

## Where things live

- Launchers: `test/launch/screen_space_dataset_ablation.py`,
  `test/launch/cone_dataset_ablation.py` (thin), over
  `test/launch/dataset_ablation_core.py` (engine).
- Per-branch artifacts:
  `results/ablation/<method>_<stage>_dmlab/<dataset>/<method>/<comparability_signature>/`
  → `manifest.json`, `README.md`, `aggregate/ablation_runs.{jsonl,csv}`,
  `aggregate/common_model_summary.json`, and `branch_best.json` (or `_held.json`).
  The branch path is **signature-scoped**: an incompatible run (different
  release/fixation/timing/offset/delay/subset) lands in its own directory and
  never overwrites another's markers. Aggregate `run_id`s are likewise suffixed
  with the comparability signature so they cannot collide across configs.
- Shared table (one row per completed branch):
  `results/ablation/_tables/dataset_method_ablation.csv`.

`results/ablation/` is runtime output and git-ignored; commit a copy explicitly
only when a campaign checkpoint is wanted.

## Dry-run for one (dataset, method)

```bash
# plan only — validate request + list candidates, run nothing
python3 test/launch/screen_space_dataset_ablation.py \
    --request test/launch/examples/screen_space_sigma_request.example.json --dry-run

# local mock execution (no assets, deterministic) — writes all artifacts + table
python3 test/launch/screen_space_dataset_ablation.py \
    --request test/launch/examples/screen_space_sigma_request.example.json \
    --results-root /tmp/dmlab_demo --mock
```

`cone_dataset_ablation.py` takes the same flags. Real evaluator runs require the
dataset/gaze assets and explicit approval; the launcher refuses a non-mock run
without them and never submits server jobs.
