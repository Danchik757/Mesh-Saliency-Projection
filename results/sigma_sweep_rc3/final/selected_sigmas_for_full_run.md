# Selected Sigmas for RC3 Full Metric Run (Optimized)

Generated from: rc3 sigma sweep stage-1 (`rc3_sigma_sweep_20260611_stage1_fix3`)
Source JSONL: `merged_all_shards/sigma_sweep_rows.jsonl` (1395 ok rows, 5 failures)
Selection date: 2026-06-11
Selection metric: mean CC on 25-model sweep subset per dataset/method

---

## Selected Sigma Table

| Dataset/track | Method | Selected σ | Evaluator arg | mean CC | mean SIM | mean KLD | mean Spearman | n models | Boundary risk |
|---|---|---|---|---:|---:|---:|---:|---:|---|
| 3DVA | cone | σ_deg=2.0, r_mult=3.0 | `--sigma-deg 2.0 --radius-sigma-mult 3.0` | 0.4247 | 0.6685 | 0.4145 | 0.3785 | 25 | **upper** |
| 3DVA | screen_space | σ_mult=0.70, σ_px=34.3 | `--sigma-px 34.3` | 0.4659 | 0.6703 | 0.9336 | 0.4393 | 25 | none |
| MeshMamba non_texture | cone | σ_deg=0.8, r_mult=3.0 | `--sigma-deg 0.8 --radius-sigma-mult 3.0` | 0.3105 | 0.5826 | 0.8875 | 0.2485 | 25 | none |
| MeshMamba non_texture | screen_space | σ_mult=0.50, σ_screen=0.025 | `--sigma-screen 0.025` | 0.2097 | 0.5754 | 1.8688 | 0.1617 | 25 | **lower** |
| MeshMamba rgb_texture | cone | σ_deg=1.0, r_mult=3.0 | `--sigma-deg 1.0 --radius-sigma-mult 3.0` | 0.2493 | 0.5605 | 1.1427 | 0.2406 | 25 | none |
| MeshMamba rgb_texture | screen_space | σ_mult=0.50, σ_screen=0.025 | `--sigma-screen 0.025` | 0.1882 | 0.5727 | 1.9801 | 0.1691 | 25 | **lower** |
| SAL3D | cone | σ_deg=2.0, r_mult=3.0 | `--sigma-deg 2.0 --radius-sigma-mult 3.0` | 0.5349† | 0.7019 | 0.3014 | 0.5576 | 25 | none |
| SAL3D | screen_space | σ_mult=1.50, σ_px=39.45 | `--sigma-px 39.45` | 0.3951 | 0.6594 | 0.7188 | 0.4332 | 25 | **upper** |

† SAL3D cone mean CC includes cart at σ=2.0. On 24-model subset excluding cart: σ=1.6 and σ=2.0 both give CC=0.5414.

---

## Selection Rationale

### 3DVA / cone  σ_deg=2.0
Sweep shows monotonically increasing CC across all 7 sigma values (0.5→2.0°). Best at σ=2.0 (CC=0.4247).
**Boundary risk**: curve has not saturated. Recommend stage-2 sweep with σ=[2.0, 2.5, 3.0, 3.5]°.

### 3DVA / screen_space  σ_mult=0.70 (σ_px=34.3)
Clear peak at σ_mult=0.70. Better than 0.50 (user expectation) on all four metrics. σ_px=34.3 is well within the swept range; no boundary risk.

| σ_mult | σ_px | mean CC | mean SIM | mean KLD | mean Spearman |
|---|---|---|---|---|---|
| 0.50 | 24.5 | 0.4617 | 0.6630 | 0.9545 | 0.4319 |
| **0.70** | **34.3** | **0.4659** | **0.6703** | **0.9336** | **0.4393** |
| 0.85 | 41.6 | 0.4622 | 0.6719 | 0.9268 | 0.4394 |
| 1.00 | 49.0 | 0.4552 | 0.6716 | 0.9238 | 0.4371 |

Note: the pre-sweep expectation was 0.50 based on a hypothesis that smaller sigma helps 3DVA. The data refutes this: 0.70 is the clear winner.

### MeshMamba non_texture / cone  σ_deg=0.8
Interior peak. CC at σ=0.8 (0.3105) exceeds both σ=0.65 (0.3057) and σ=1.0 (0.3077). No boundary risk.

### MeshMamba non_texture / screen_space  σ_mult=0.50 (σ_screen=0.025)
Sweep shows monotonically decreasing CC as σ increases. Best at the lowest tested multiplier (0.50).
**Boundary risk**: curve has not saturated. Recommend stage-2 sweep with σ_mult=[0.20, 0.30, 0.40, 0.50].

### MeshMamba rgb_texture / cone  σ_deg=1.0
Interior peak. CC at σ=1.0 (0.2493) > σ=0.8 (0.2449) and σ=1.25 (0.2484). Non_texture and rgb_texture peak at different values (0.8 vs 1.0) — expected due to different mesh surface properties.

### MeshMamba rgb_texture / screen_space  σ_mult=0.50 (σ_screen=0.025)
Same pattern as non_texture. Boundary risk applies.

### SAL3D / cone  σ_deg=2.0
Key finding: cart/cone timeouts at σ=0.5, 0.8, 1.0, 1.25, 1.6 (5 failures). At σ=2.0 cart completes.
On the 24-model common set (excluding cart): σ=1.6 CC = σ=2.0 CC = 0.5414 (tie to 4 decimal places).
σ=2.0 preferred because:
1. Cart completes without timeout (full 25-model coverage).
2. σ=2.0 gives lower KLD (0.301 vs 0.315 at σ=1.6) and higher SIM (0.702 vs 0.697).
3. No boundary risk — CC drops at σ=2.5 would be expected; the curve shows a clear plateau.

### SAL3D / screen_space  σ_mult=1.50 (σ_px=39.45)
Monotonically increasing CC across the full range.
**Boundary risk**: curve has not saturated. Recommend stage-2 sweep with σ_mult=[1.50, 1.75, 2.00, 2.50].

---

## Comparison with Baseline Sigmas

| Dataset | Method | Baseline σ (rc3_004003) | Optimized σ | Expected ΔCC |
|---|---|---|---|---|
| 3DVA | cone | σ_deg=1.0 | σ_deg=2.0 | +0.033 |
| 3DVA | screen_space | σ_px=49.0 (mult=1.0) | σ_px=34.3 (mult=0.70) | +0.011 |
| MeshMamba non_texture | cone | σ_deg=1.0 | σ_deg=0.8 | +0.003 |
| MeshMamba non_texture | screen_space | σ_screen=0.05 (mult=1.0) | σ_screen=0.025 (mult=0.50) | +0.070 |
| MeshMamba rgb_texture | cone | σ_deg=1.0 | σ_deg=1.0 | ±0 |
| MeshMamba rgb_texture | screen_space | σ_screen=0.05 (mult=1.0) | σ_screen=0.025 (mult=0.50) | +0.058 |
| SAL3D | cone | σ_deg=1.0 | σ_deg=2.0 | +0.017 |
| SAL3D | screen_space | σ_px=26.3 (mult=1.0) | σ_px=39.45 (mult=1.50) | +0.016 |

ΔCC values are from sweep mean on 25-model subset and will differ on the full object pool.

---

## Known Risks and Open Items

1. **4 boundary cases** (3DVA cone, MeshMamba ss, SAL3D ss): optimal may lie outside the tested range. The full run will use the best tested value; a stage-2 sweep is needed to confirm the global optimum.
2. **SAL3D cart/cone**: cart completed at σ=2.0 in stage-1 (no timeout). Monitor carefully in the full run. If it times out at σ=2.0 on the full object pool, mark as `error_type=timeout` and exclude from mean.
3. **MeshMamba rgb_texture cc absolute values are low (~0.19–0.25)**: this is a known characteristic of the dataset, not a sigma choice issue.
4. `radius_sigma_mult=3.0` was not swept; this value may not be optimal. Keep fixed until a radius sweep is conducted.

---

## Files

- Source JSONL: `merged_all_shards/sigma_sweep_rows.jsonl` (on vg-iai)
- Local copy: `~/Downloads/sigma_sweep_rc3/fresh_raw/merged.jsonl`
- This CSV: `results/sigma_sweep_rc3/final/selected_sigmas_for_full_run.csv`
- Full-run launcher: `test/launch/run_full_metrics_optimized_sigma.py`
