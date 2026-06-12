# FINAL macOS Audit — Gate 1 (read-only)

- **Branch audited:** `agent/rc3-release-and-ablation-infra`
- **HEAD:** `9e0082e3aa6df6e90b1e9284723a994aecaa37be` ("fix launcher: hit_rate from run_stats, dry-run shows counts+cmds, SAL3D_MANIFEST")
- **Date:** 2026-06-12
- **Scope:** metrics/, reprojection_methods/, utils/, test/launch/, test/kld_parameter_sweep/, scripts/, server/, configs/, dataset/release contracts, SAL3D fixed-face / Gaze / Smooth Gaze, results & provenance. Independent review of Windows branches' core code.
- **Gate status:** **Gate 1 — AUDIT ONLY. No code was modified. STOP and await reviewer approval before any fix (Gate 2).**

This report makes no commits, runs no server jobs, merges no branches, and changes no evaluator logic.

---

## 1. Verdict summary

| # | Mandatory check | Result |
|---|-----------------|--------|
| 1 | Evaluators share one rc3 timing/provenance contract | **PASS** (1 medium caveat) |
| 2 | Resume guards reject incompatible reports | **PASS** at evaluator level; launcher key is coarse (M4) |
| 3 | Sigma / full-run / sweep / ablation launchers pass correct args | **PASS** |
| 4 | `merge_rc3_final.py` forbids config-mixing & excludes NaN/Inf | **FAIL** (H1, H2) |
| 5 | `build_release_candidate.py` stale (schema v1 / offset_2000) | **CONFIRMED STALE** (H3) |
| 6 | `v2.0-data-rc3` integrity (298 JSON, hashes, based_on, no offset_2000) | **PASS** with 1 manifest text error (M1) |
| 7 | SAL3D Smooth Gaze full analysis | **COMPLETE** — every sub-claim verified |
| 8 | Docs match code | **PASS** with minor stale text (L1, L3) |
| 9 | Classify uncommitted changes | **DONE** — one must-not-commit 358 MB payload (M3) |
| 10 | Windows-branch core-code review | **DONE** — core is stale; do-not-merge core (H4) |

**Test gates:** pytest **417 passed / 0 failed**; `compileall` core dirs **exit 0**; `git diff --check` **clean**.

---

## 2. Findings by severity

### HIGH

**H1 — `merge_rc3_final.py` (and the launcher) do NOT exclude NaN/Inf from metric means.**
`_fv()` uses a bare `float(v)` that **succeeds** on `nan`/`inf`. Python's `json` writes `NaN`/`Infinity` and reads them back as floats, so a single non-finite metric poisons the whole compact-CSV cell to `NaN`.
- `test/launch/merge_rc3_final.py:125-129` (`_fv`), used in mean at `:156`.
- `test/launch/run_full_metrics_optimized_sigma.py:535-539` (`_fv`), used at `:566`.
- Empirically reproduced: `mean([0.5, 0.6, nan, inf]) → nan`.

**H2 — `merge_rc3_final.py` has no config-compatibility guard.**
`merge_rows()` deduplicates **only** on `job_key = optrun:{dataset}:{model}:{method}` (`:100-108`). `release_tag`, `timing_contract`, `fixation_data_tag`, and sigma values are never compared across rows or across input files. Merging JSONL from runs with different sigma/timing/release would silently combine them (ok-preferred, earliest-file-preferred) with no error. The job_key itself omits all config dimensions.

**H3 — `scripts/build_release_candidate.py` is stale and would build the wrong contract.**
- Defaults to **rc1**: `--output-dir …/v2.0-data-rc1`, `--tag v2.0-data-rc1` (`:22-23`).
- Archives the **legacy offset_2000** payload: `participant_fixations_processed_offset_2000` (`:123-124`), recorded as `processed_json_archive` (`:193`).
- Emits **`schema_version: 1`** (`:188`) and a **cropped-reset** `timing_contract` (`crop_start_seconds: 1.8`, `crop_end_seconds: 0.2`, `:196-200`).
- There is **no committed rc3 builder**: the only script touching `participant_fixations_offset0_full_cleaned` / `schema_version 2` is `scripts/validate_release_candidate.py` (a validator, not a builder). The actual rc3 release was produced by an out-of-repo process. Running this script as-is to "rebuild rc3" would silently produce an offset_2000 / schema-v1 release.

**H4 (do-not-merge) — Windows branches' core code is stale (missing `frame_offset`).**
`origin/agent/windows-geometry-metrics`, `windows-rc3-validation`, `windows-video-overlays-rc3` all carry core `metrics/ reprojection_methods/ utils/` files that **predate the `frame_offset` feature**:
- `utils/participant_loader.py`: HEAD has 18 `frame_offset` references; all 3 Windows branches have **0**.
- `eval_sal3d_cone.py` (and the other 5 evaluators): HEAD accepts `--frame-offset`; Windows branches do **not**.
Merging their core files would regress the cut_head/center window-mode capability required by `run_ablation_window_delay.py`. (The Windows branches' diff vs HEAD in core dirs is exclusively the removal of `frame_offset` — no new core improvements.)

### MEDIUM

**M1 — rc3 `release_manifest.json` `based_on` field is factually wrong.**
`release_assets/v2.0-data-rc3/release_manifest.json:97`:
> `"based_on": "v2.0-data-rc1 with processed fixation JSON replaced by cropped-reset offset-2000 data and SAL3D fixed per-face GT added"`
This contradicts every structured field in the same file (`schema_version: 2`, `participant_data_contract.fixation_format: "one_turn_from_start_offset_0"`, `timing_contract.name: "one_turn_from_start"`, `crop_*_seconds: 0.0`) **and** `data_contract_validation.json` ("rc3 intentionally replaces cropped-reset fixation archive from rc2 with full cleaned offset0 fixation JSONs"). The payload is offset0/one_turn; only this descriptive string is stale. Must be corrected before any release upload.

**M2 — `fixation_data_tag` provenance is dual-sourced and not cross-validated.**
The launcher records `FIXATION_DATA_TAG = "processed_fixations_offset0_full_cleaned"` as a hardcoded constant into every JSONL row and into `provenance.json` (`run_full_metrics_optimized_sigma.py:143,399`), but it does **not** pass `--fixation-data-tag` to the evaluator (`build_command`, `:255-257` only passes `--fixation-root`). The evaluator independently derives its tag from `Path(args.fixation_root).name` (`participant_loader` usage in each evaluator). If `FIXATION_ROOT` ever points at a differently-named directory, the launcher-recorded tag would be wrong while the report-recorded tag would be right — and nothing reconciles them.

**M3 — 358 MB run payload is not gitignored and would be staged by `git add -A`.**
`.gitignore:6-11` excludes `results/**/*.json|*.png|*.jpg|*.mp4|*.npy|*.log` but **not** `*.txt`, `*.csv`, or `*.jsonl`. `git check-ignore` confirms `results/benchmark_runs/rc3_full_metrics_20260611_004003/` (358 MB, 1918 `*_vertices.txt` files) is **NOT IGNORED**. This risks committing a large generated payload (against the "do not commit the large participant payload into normal git" constraint).

**M4 — full-run launcher resume key omits sigma/timing.**
`_job_key()` (`run_full_metrics_optimized_sigma.py:370-371`) encodes only dataset/model/method. `load_completed_keys()` skips any `status=="ok"` key. Resuming into a **reused** batch dir after editing the module sigma constants would skip stale rows without recomputation. Mitigated in practice because each run uses a fresh timestamped `--batch-output-dir`. By contrast, the sweep and ablation launchers correctly fold sigma/window/delay into their resume keys (`run_ablation_window_delay.py:17,196`).

### LOW

**L1 — Evaluator help text still references offset_2000 / cropped_reset.**
All 6 evaluators describe `--fixation-root` as "Root of processed_fixations_offset_2000/" and default `--timing-contract` to `cropped_reset` with help "(default, offset_2000 data)" (e.g. `eval_sal3d_cone.py:90,100,104`). Harmless on the launcher path (which always overrides with `one_turn_from_start`), but misleading for direct invocation and inconsistent with the rc3 contract.

**L2 — SAL3D Smooth Gaze stores 4× the neighbors the code uses (release bloat).**
Each record holds **exactly 2000** neighbors (verified: min=max=median=2000 on `ringdragon`), but `apply_gt_smoothing()` clips to the first 500 (`eval_sal3d_screen_space.py:382`, `eval_sal3d_geodesic.py`). 75 % of the 2.11 GB raw / 859 MB zipped payload is never read by the current algorithm.

**L3 — No single doc enumerates the optimized sigmas used in the headline run.**
`docs/SIGMA_REFERENCE_ALL_METHODS.md` documents **baseline/default** sigmas (3DVA 49.0, SAL3D 26.3, MeshMamba 0.05, cone 1.0) — correct as a parameter reference but not the optimized run values (2.0 / 34.3 / 0.8 / 0.025 / 1.0 / 2.0 / 39.45). The optimized values live only in the launcher docstring/constants and `provenance.json`. Risk of misreading the reference as the run config.

**L4 — Fixed-face GT is a regenerated artifact with no in-repo generator.**
`sal3d_fixed_face_gt.zip` (55 models) was generated 2026-06-10 from an external `SAL3D_almost_fixed` / `SAL3D_NPZ_almost` pipeline (per its Russian-language `sal3d_manifest.md`). No repo script reproduces it; it is verifiable only via the per-model `obj_md5`/`npz_md5` in `sal3d_manifest.csv`. Independent reproduction requires preserving that external pipeline.

### Informational (cross-cutting)

The rc3 release **ships** `sal3d_fixed_face_gt` (55 models) whose repaired meshes (MaxPlanck 19999, meca 15000, sofa 15125 verts) resolve the very GT-vs-OBJ vertex-count mismatches that failed in the rc3 metric run — but the run did **not** set `SAL3D_FIXED_GT_DIR`, so MaxPlanck/meca/sofa (6 jobs) failed. Using the shipped fixed-face GT would recover them. (gamecontroller/spanner fail for a different reason: missing Gaze GT, not in the release.)

---

## 3. Per-check evidence

**Check 1 — timing/provenance contract.** All 6 launcher-driven evaluators import the same constants and loader from `utils/participant_loader.py` (`TIMING_CONTRACT_CROPPED_RESET`, `TIMING_CONTRACT_ONE_TURN`, `load_processed_track`), share identical `--timing-contract` default+choices, and call `load_processed_track`. The launcher hardcodes `one_turn_from_start / delay 0 / frame_offset 0 / v2.0-data-rc3` and passes the timing flags to every job. Centralized and consistent. Caveat M2.

**Check 2 — resume guards.** `guard_report_compatible()` (`participant_loader.py:630-682`) raises `ResumeContractMismatchError` on differing `timing_contract / fixation_data_tag / delay_frames / turn_frame_count / gaze_start_frame / placement_start_frame / frame_offset`; strict for one_turn. All 6 evaluators call it before writing (e.g. `eval_sal3d_cone.py:1061`); 8 dedicated tests cover it. Launcher-level caveat: M4.

**Check 3 — launcher args.** `build_command()` passes `--sigma-px`/`--sigma-screen` (screen-space, 1920px → px, 256px → screen) and `--sigma-deg`+`--radius-sigma-mult` (cone) correctly, plus `--texture-type` for MeshMamba and env-driven roots. Sweep (`run_sigma_sweep_rc3.py`) and ablation (`run_ablation_window_delay.py`) launchers document and apply the same contract and base sigmas; window modes map correctly to `--frame-offset` (cut_tail 0 / cut_head tail / center tail//2).

**Check 4 — merge.** See H1, H2.

**Check 5 — release builder.** See H3.

**Check 6 — rc3 integrity.**
- `participant_fixations_offset0_full_cleaned.zip`: manifest claims `file_count: 298`; actual zip listing = **298** `fixations.json`. ✓
- `SHA256SUMS` matches `release_manifest.json` sha256 for **all 14 archives** (programmatic cross-check: all OK). ✓
- `offset_2000` appears **only** in the erroneous `based_on` string — no structural/path references. ✓
- `schema_version: 2`, tag `v2.0-data-rc3`, `git_commit: aa0fec9b…`, per-archive sha256 + SHA256SUMS present. Error: M1.

**Check 7 — Smooth Gaze (all sub-claims verified).**
- `sal3d_smooth_gaze.zip`: **53 files**, total uncompressed **2,112,288,605 B = 2.11 GB**, zip **901,368,899 B = 859 MB**. ✓
- Format: every line carries a `<vid> neighbors` marker → parser keeps `ids`/`neighbor_lists` in lockstep (no silent breakage). Every record = **exactly 2000** neighbors; code uses `[:500]` (L2). ✓
- `sal3d_fixed_face_gt.zip`: **55 models** (55 `Meshes/*.obj`), structure 55 `.obj` + 55 `_faces.txt` + 4 metadata (`SHA256SUMS`, `sal3d_checksums.md5`, `sal3d_manifest.csv`, `sal3d_manifest.md`) = 114 members. ✓
- **Fixed-face GT present, Smooth Gaze missing:** `MaxPlanck, dog, flowerpot, prot`. ✓ (exactly as expected)
- **Smooth Gaze present, fixed-face GT missing:** `AudiRS5, bimba`. ✓ (exactly as expected) — 51 models in common.
- Originality/correctness: Smooth Gaze files (dated 05-30-2026, uniform 2000-neighbor records) read as original SAL3D-derived data, internally consistent. Fixed-face GT is a **derived/regenerated** artifact (not original SAL3D), checksummed per-model but not reproducible from repo scripts (L4).

**Check 8 — docs vs code.** `docs/METRIC_RUN_AND_CSV_CONTRACT.md` matches code: timing block (one_turn / frame_offset 0 / delay 0), the cut-head ablation variant (frame_offset 54 / delay 0.2 / 6 frames), and the **exact** compact-CSV header equal to the launcher's `_COMPACT_METRICS` and `merge_rc3_final.py`. Minor: L1, L3.

**Check 9 — uncommitted classification (20 paths, no forbidden paths touched).** See §4.

**Check 10 — Windows branches.** See H4. Their integration value is **non-core** only: `windows-video-overlays-rc3` adds ~2922 lines under `video_creation/` (overlay + heatmap-video work); geometry/validation branches add windows-specific tooling. Those are out of this audit's core scope and need their own review; their `metrics/reprojection_methods/utils` files must **not** overwrite the audited branch.

---

## 4. Uncommitted change classification

`git status`: 1 modified, 19 untracked. **No forbidden paths touched** (`trash/Claude.md`, `trash/GPT.md`, `md/archive/` all untouched). `git diff --check` clean.

**Safe to commit (code/docs, small):**
- `docs/README.md` (modified, +2 doc links — clean diff)
- `docs/METRIC_RUN_AND_CSV_CONTRACT.md`
- `docs/SIGMA_REFERENCE_ALL_METHODS.md` (consider adding an optimized-sigma cross-reference — L3)
- `test/tools/compare_processed_timing_preview.py`
- `test/manifests/debug_3dva_a380_frame54.json`
- `video_creation/gaze_heatmap_overlays/render_participant_marker_overlay.py`
- `test/launch/merge_rc3_final.py` — **only after H1+H2 are fixed** (otherwise commit with an explicit known-issue note)

**Result data — commit selectively per project policy (small summaries only):**
- `results/ablation_window_delay/` (40 K), `results/preflight/` (20 K, incl. CASEFIX_NOTES.md), `results/benchmark_runs/rc3_*.csv` (4–8 K each), `results/sigma_sweep_rc3/sigma_sweep_rows.jsonl` (224 K) + `sigma_sweep_summary.csv` (140 K)

**MUST NOT commit:**
- `results/benchmark_runs/rc3_full_metrics_20260611_004003/` — **358 MB, 1918 `*_vertices.txt`** (not gitignored — M3)
- `results/benchmark_runs/rc2_full_metrics_20260610_143622/` (980 K run output — prefer artifact storage)
- `trash/SIGMA_PARAMETERS_AND_SWEEP_NOTES.md` — scratch area; not a forbidden file but exclude by convention

---

## 5. Mandatory fixes (Gate 2 — only after reviewer approval)

1. **(H1)** Make `_fv`/aggregation drop non-finite values (`math.isfinite`) in both `merge_rc3_final.py` and `run_full_metrics_optimized_sigma.py`; add a regression test with a `NaN`/`Inf` row.
2. **(H2)** Add a config-compatibility guard to `merge_rc3_final.py`: refuse to merge inputs/rows whose `release_tag` / `timing_contract` / `fixation_data_tag` / sigma differ (assert a single config across all inputs, or fail loudly).
3. **(H3)** Either upgrade `build_release_candidate.py` to schema v2 / offset0 / one_turn with rc3 defaults, or mark it deprecated and add the real rc3 builder; never present it as the rc3 release path.
4. **(M1)** Correct the `based_on` string in the rc3 `release_manifest.json` to describe offset0/one_turn, and re-verify the manifest before any upload.
5. **(M3)** Extend `.gitignore` to exclude `results/**/*.txt|*.csv|*.jsonl` run dumps (or relocate run outputs) so the 358 MB payload cannot be staged.

**Recommended (non-blocking):** M2 (pass/validate `--fixation-data-tag`), M4 (fold config into the full-run resume key), L1 (refresh evaluator help text), L3 (cross-link optimized sigmas), L4 (commit the fixed-face-GT generator or document the external pipeline), and consider setting `SAL3D_FIXED_GT_DIR` to recover the MaxPlanck/meca/sofa SAL3D jobs.

---

## 6. Do-not-merge list

- `origin/agent/windows-geometry-metrics`, `origin/agent/windows-rc3-validation`, `origin/agent/windows-video-overlays-rc3` → **their `metrics/ reprojection_methods/ utils/` core files** (stale, missing `frame_offset`). Core must come from `agent/rc3-release-and-ablation-infra`. Their non-core `video_creation/` additions may be reviewed separately.
- Per standing constraints: never commit to `reproject-benchmark`; do not merge or rebase another worker branch; do not edit `trash/Claude.md`, `trash/GPT.md`, or `md/archive/`.

---

## 7. Test / build gates

| Gate | Command | Result |
|------|---------|--------|
| Unit tests | `python3 -m pytest -q` | **417 passed, 0 failed** (3.51 s) |
| Core timing tests | `pytest test/test_participant_loader.py` | 34 passed (incl. 8 resume-guard tests) |
| Byte-compile | `python3 -m compileall metrics reprojection_methods utils test/launch scripts server` | **exit 0** |
| Whitespace/conflict | `git diff --check` | **clean (exit 0)** |

---

## 8. Gate 1 boundary

Audit complete. **No code changed, no commits, no merges, no server jobs.** Awaiting reviewer/controller approval (Gate 2) before applying any mandatory fix. On approval I will: fix only the assigned core/release items, add tests, make a single commit authored as the human project owner, push the branch, and provide HEAD / diff stat / test results / release dry-run validation.
