# Release build, validation, and run-provenance contract

Covers the offset0 / `one_turn_from_start` data release (schema_version 2,
`v2.0-data-rc4` and later), how to build and validate it, and the
timing/provenance guarantees the runners and merge tool now enforce.

## Release contract (schema_version 2)

| Field | Value |
|-------|-------|
| `schema_version` | `2` |
| `timing_contract.name` | `one_turn_from_start` |
| `timing_contract.crop_start_seconds` / `crop_end_seconds` | `0.0` / `0.0` |
| `timing_contract.delay_seconds_default` | `0.0` |
| `participant_data_contract.processed_json_archive` | `participant_fixations_offset0_full_cleaned.zip` |
| `participant_data_contract.fixation_format` | `one_turn_from_start_offset_0` |
| `participant_data_contract.fixation_data_tag` | `processed_fixations_offset0_full_cleaned` |
| `participant_data_contract.automatic_fallback_allowed` | `false` |

The legacy `offset_2000` / `cropped_reset` / schema-v1 release is **not** produced
by the current builder; recover it from git history if ever required.

## Building (`scripts/build_release_candidate.py`)

Default tag `v2.0-data-rc4`. Includes the 298 offset0 fixation JSONs, SAL3D
repaired per-face GT, and the full SAL3D Smooth Gaze archive.

### Inputs: tracked vs external

Tracked in the repo (default sources):
- `participant_data/collected_gaze_csv_by_model/`
- `participant_data/processed_fixations_offset0_full_cleaned/` — the canonical
  offset0 fixation source (note: the source directory name differs from the
  archive root `participant_fixations_offset0_full_cleaned/`).
- `jsons/object_placement/`

Supplied externally (large `GAZE_DATA` assets, not tracked): 3DVA/MeshMamba/SAL3D
meshes + GT, the SAL3D fixed per-face GT package (`sal3d_benchmark_pkg`), the
SAL3D Smooth Gaze archive, and (optionally) source videos.

### Strict preflight

```bash
# Strict preflight + plan review (no archives written):
python3 scripts/build_release_candidate.py --dry-run
```

`--dry-run` runs a **strict preflight**: it exits **nonzero (3)** if any required
source is missing or the fixation source does not hold **exactly 298**
`*/fixations.json`. Printing `MISSING` and exiting 0 is not done — a missing
input always fails. The same preflight gates a real build before anything is
written.

### Real build

```bash
python3 scripts/build_release_candidate.py --force \
    --fixation-source /path/to/processed_fixations_offset0_full_cleaned \
    --data-sal3d-fixed-root /path/to/sal3d_benchmark_pkg
```

A real build, in order: strict preflight → clean-tree check → rc4-compatible
`validate_data_contract.py` (offset0 source, `--timing-contract
one_turn_from_start`) → write archives + manifest + `SHA256SUMS` →
`validate_release_candidate.py` on the output (a validation failure fails the
build).

`build_manifest_metadata()` is the single source of the structured manifest
(schema, `based_on`, timing/participant/sal3d contracts) and is unit-tested. The
`based_on` text describes offset0 / one_turn data — it never claims
`offset_2000` / `cropped-reset`.

## Validating (`scripts/validate_release_candidate.py`)

```bash
python3 scripts/validate_release_candidate.py release_assets/<tag>
```

Checks (non-exhaustive):

- `schema_version == 2`, timing/participant contract fields.
- **Exact fixation frame counts by dataset prefix:** `3DVA_*` and `MeshMamba_*`
  must be 510, `SAL3D_*` must be 720, `3DVA_jessi` must be 41. A 720-frame file
  under a `3DVA_` prefix is an error even though 720 is a valid length elsewhere.
- Exactly **298** fixation JSONs; archive file-count expectations.
- **Smooth Gaze inventory** (53 models) and **fixed-face GT inventory** (55
  models), plus the documented mismatch sets (fixed-only `MaxPlanck/dog/flowerpot/prot`,
  smooth-only `AudiRS5/bimba`).
- **`based_on` sanity:** fails if the text mentions `offset_2000` / `cropped-reset`.
- Per-archive **SHA-256** (vs manifest and `SHA256SUMS`) and zip **CRC**.

## Run provenance and resume safety

These guarantees apply to `test/launch/run_full_metrics_optimized_sigma.py`,
`test/launch/run_ablation_window_delay.py`, and `test/launch/merge_rc3_final.py`.

- **Canonical `fixation_data_tag`.** The full-run launcher passes
  `--fixation-data-tag processed_fixations_offset0_full_cleaned` to every
  evaluator, so the tag recorded in the report is dictated by the run config, not
  derived from the fixation-root basename. Evaluators fall back to
  `Path(fixation_root).name` **only** when the flag is absent; for launched runs
  the launcher is the single canonical source.
- **Config-aware resume keys.** The full-run job key embeds release tag, timing
  contract, fixation tag, frame offset, delay, and the per-job sigma, so resuming
  into a directory built under a different configuration cannot silently skip an
  incompatible job.
- **Dry-run rows never count as completed.** Resume ignores rows with
  `error_type == "dry_run"`.
- **Resume aggregates, never truncates.** The final CSVs are rebuilt from the
  full JSONL (prior + current rows, deduplicated, ok preferred), so a resumed run
  never overwrites the CSV with only its own slice.
- **Deterministic report selection + provenance check.** The launcher picks the
  `*_report.json` deterministically and rejects a report whose
  `timing_contract` / `frame_offset` / `fixation_data_tag` / `delay_frames`
  disagree with the run contract.
- **Merge refuses to mix configs.** `merge_rc3_final.py` aborts (listing every
  conflict) if `ok` rows disagree on release/timing/fixation/frame_offset/delay
  or on per-`(dataset, method)` sigma, and **drops NaN/Inf** from every mean.
- **No negative indexing.** `utils/participant_loader` rejects negative
  `frame_offset`, `gaze_start_frame`, or `placement_start_frame`, and refuses to
  silently accept an unreadable existing report during a resume.
- **Infeasible ablation jobs rejected pre-launch.** Window/delay combinations
  whose gaze or placement window would fall outside `[0, total_frames)` are
  recorded as `rejected` / `infeasible_window_delay` and never invoke an
  evaluator.
