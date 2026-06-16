"""Stage-1 evaluator metric-parity harness (NON-DESTRUCTIVE).

This test imports the six authoritative baseline evaluator scripts and
characterises their private ``compute_metrics`` against the trusted ``metrics/``
module. It MUST NOT modify any evaluator. It only reads and compares.

Scope (per ChatGPT review 2026-06-15 00:05 Europe/Moscow):

  Six evaluator scripts across eight dataset/method combinations. MeshMamba
  reuses one script per method across the ``non_texture`` and ``rgb_texture``
  tracks; the metric code path is identical for both tracks (the track only
  selects which upstream data is loaded, not the metric formula). Both tracks
  are registered and covered explicitly below.

  Six scripts:
    - reprojection_methods/cone_projection_on_mesh/eval_3dva_cone_combined.py
    - reprojection_methods/screen_space_gaussian/eval_3dva_screen_space_combined.py
    - reprojection_methods/cone_projection_on_mesh/eval_meshmamba_cone.py
    - reprojection_methods/screen_space_gaussian/eval_meshmamba_screen_space.py
    - reprojection_methods/cone_projection_on_mesh/eval_sal3d_cone.py
    - reprojection_methods/screen_space_gaussian/eval_sal3d_screen_space.py

What this harness asserts:

  * cross-script consistency -- all six ``compute_metrics`` agree on the seven
    core metrics (CC, SIM, KLD, MSE, MAE, Spearman, Cosine) for identical input;
  * trusted-module parity for the OVERLAPPING metrics the trusted module
    actually defines:
      - CC       : matches trusted ``pearson_cc``;
      - Spearman : matches trusted ``spearman_cc``;
      - MSE      : DIVERGES from trusted on raw input, but equals trusted
                   ``mse_score`` applied to min-max-normalised inputs -- i.e. the
                   only difference is the min-max preprocessing;
      - SIM      : DIVERGES from trusted (evaluator clip+sum-norm vs trusted
                   minmax+distribution-norm);
      - KLD      : DIVERGES from trusted (evaluator clip+sum-norm+eps vs trusted
                   shift-min+distribution-norm).

Documented EXCLUSIONS (intentionally NOT compared to the trusted module):

  * MAE, Cosine                -- not defined in the trusted module;
  * AUC_Judd_gt_top_*pct_proxy -- Judd trapezoid ROC, a different algorithm from
                                  the trusted Mann-Whitney rank-sum ``AUC``;
  * NSS_gt_top_*pct_proxy      -- proxy NSS over top-k% GT positives;
  * hit_rate                   -- pipeline-level ray/cone statistic, not part of
                                  ``compute_metrics`` (screen_space has none).

The SIM / KLD / MSE-vs-raw divergence tests are CHARACTERISATION tests of a
known, not-yet-adjudicated difference. They intentionally go red if anyone
reconciles the evaluator and trusted implementations, which forces re-review of
this Stage-1 finding. Do NOT edit the evaluators to satisfy them without
explicit ChatGPT/user sign-off.
"""
from __future__ import annotations

import importlib

import numpy as np
import pytest

from metrics.common import (
    kldiv_score,
    mse_score,
    normalize_minmax,
    pearson_cc,
    similarity_score,
    spearman_cc,
)

CONE = "cone"
SCREEN = "screen_space"

# Six evaluator module paths -> (dataset, method).
SIX_SCRIPTS: dict[str, tuple[str, str]] = {
    "reprojection_methods.cone_projection_on_mesh.eval_3dva_cone_combined": ("3dva", CONE),
    "reprojection_methods.screen_space_gaussian.eval_3dva_screen_space_combined": ("3dva", SCREEN),
    "reprojection_methods.cone_projection_on_mesh.eval_meshmamba_cone": ("meshmamba", CONE),
    "reprojection_methods.screen_space_gaussian.eval_meshmamba_screen_space": ("meshmamba", SCREEN),
    "reprojection_methods.cone_projection_on_mesh.eval_sal3d_cone": ("sal3d", CONE),
    "reprojection_methods.screen_space_gaussian.eval_sal3d_screen_space": ("sal3d", SCREEN),
}

# Eight dataset_track/method combinations -> module providing compute_metrics.
# MeshMamba's two tracks share one script per method (track changes upstream
# input data only, not the metric formula).
EIGHT_COMBINATIONS: dict[tuple[str, str], str] = {
    ("3dva", CONE): "reprojection_methods.cone_projection_on_mesh.eval_3dva_cone_combined",
    ("3dva", SCREEN): "reprojection_methods.screen_space_gaussian.eval_3dva_screen_space_combined",
    ("meshmamba_non_texture", CONE): "reprojection_methods.cone_projection_on_mesh.eval_meshmamba_cone",
    ("meshmamba_non_texture", SCREEN): "reprojection_methods.screen_space_gaussian.eval_meshmamba_screen_space",
    ("meshmamba_rgb_texture", CONE): "reprojection_methods.cone_projection_on_mesh.eval_meshmamba_cone",
    ("meshmamba_rgb_texture", SCREEN): "reprojection_methods.screen_space_gaussian.eval_meshmamba_screen_space",
    ("sal3d", CONE): "reprojection_methods.cone_projection_on_mesh.eval_sal3d_cone",
    ("sal3d", SCREEN): "reprojection_methods.screen_space_gaussian.eval_sal3d_screen_space",
}

CORE_METRICS = ("CC", "SIM", "KLD", "MSE", "MAE", "Spearman", "Cosine")

# Proxy AUC/NSS keys emitted by compute_metrics (default percentiles 90/95/99 ->
# top 10/5/1 pct). The launchers rename these to AUC_at_*pct / NSS_at_*pct in the
# compact CSV. Cross-script equality here is what justifies using a single
# representative script to pin the AUC_at_*/NSS_at_* contract metrics.
PROXY_METRICS = (
    "AUC_Judd_gt_top_10pct_proxy",
    "AUC_Judd_gt_top_5pct_proxy",
    "AUC_Judd_gt_top_1pct_proxy",
    "NSS_gt_top_10pct_proxy",
    "NSS_gt_top_5pct_proxy",
    "NSS_gt_top_1pct_proxy",
)

# Overlapping metrics the trusted module also defines.
PARITY_TOL = 1e-9      # CC / Spearman / MSE-mechanism should match to ~fp noise.
DIVERGE_MARGIN = 1e-3  # SIM / KLD differ from trusted by clearly more than this.


def _load(module_path: str):
    return importlib.import_module(module_path)


def _synthetic(seed: int, n: int = 2000, nonneg: bool = False):
    """Deterministic correlated (pred, gt). Default contains negatives, which
    stresses the clip-vs-shift normalisation difference between the evaluators
    and the trusted module."""
    rng = np.random.default_rng(seed)
    pred = rng.normal(0.3, 1.0, size=n)
    gt = 0.6 * pred + rng.normal(0.0, 0.8, size=n)
    if nonneg:
        pred = np.abs(pred)
        gt = np.abs(gt)
    return pred, gt


# Frozen inputs so numeric examples in the report stay reproducible.
PRED_NEG, GT_NEG = _synthetic(seed=0)              # correlated, with negatives
PRED_POS, GT_POS = _synthetic(seed=1, nonneg=True)  # correlated, non-negative

INPUT_CASES = {
    "with_negatives": (PRED_NEG, GT_NEG),
    "non_negative": (PRED_POS, GT_POS),
}


@pytest.fixture(scope="module")
def evaluators():
    """Import all six evaluator modules once."""
    return {path: _load(path) for path in SIX_SCRIPTS}


# ── registry / scope coverage ──────────────────────────────────────────────────

def test_six_scripts_and_eight_combinations_registered():
    assert len(SIX_SCRIPTS) == 6
    assert len(EIGHT_COMBINATIONS) == 8
    # Exactly six distinct evaluator modules back the eight combinations.
    assert len(set(EIGHT_COMBINATIONS.values())) == 6


def test_meshmamba_tracks_share_one_metric_code_path(evaluators):
    """non_texture and rgb_texture must resolve to the SAME compute_metrics, i.e.
    the MeshMamba track does not change the metric formula."""
    for method in (CONE, SCREEN):
        non = EIGHT_COMBINATIONS[("meshmamba_non_texture", method)]
        rgb = EIGHT_COMBINATIONS[("meshmamba_rgb_texture", method)]
        assert non == rgb
        assert _load(non).compute_metrics is _load(rgb).compute_metrics


def test_all_six_scripts_expose_compute_metrics(evaluators):
    for path, module in evaluators.items():
        assert hasattr(module, "compute_metrics"), f"{path} missing compute_metrics"
        out = module.compute_metrics(PRED_NEG, GT_NEG)
        assert isinstance(out, dict)
        for key in CORE_METRICS:
            assert key in out, f"{path} compute_metrics missing {key!r}"
            assert np.isfinite(out[key]), f"{path} {key} not finite"


# ── cross-script consistency ───────────────────────────────────────────────────

@pytest.mark.parametrize("case", list(INPUT_CASES))
@pytest.mark.parametrize("metric", CORE_METRICS)
def test_cross_script_consistency(evaluators, metric, case):
    """All six evaluators must agree on every core metric for identical input."""
    pred, gt = INPUT_CASES[case]
    values = [module.compute_metrics(pred, gt)[metric] for module in evaluators.values()]
    assert np.allclose(values, values[0], rtol=0, atol=1e-12), (
        f"{metric} disagrees across scripts on {case}: {dict(zip(SIX_SCRIPTS, values))}"
    )


@pytest.mark.parametrize("case", list(INPUT_CASES))
@pytest.mark.parametrize("metric", PROXY_METRICS)
def test_cross_script_consistency_proxy_auc_nss(evaluators, metric, case):
    """All six evaluators must agree on every proxy AUC/NSS metric for identical
    input. This is distinct from the trusted-module exclusion (the proxy AUC uses
    a Judd trapezoid, not the trusted Mann-Whitney rank-sum): here we only prove
    cross-SCRIPT equality, which is what licenses the representative-script
    mapping of AUC_at_*/NSS_at_* in the pinned 14-metric table."""
    pred, gt = INPUT_CASES[case]
    values = [module.compute_metrics(pred, gt)[metric] for module in evaluators.values()]
    assert np.allclose(values, values[0], rtol=0, atol=1e-12), (
        f"{metric} disagrees across scripts on {case}: {dict(zip(SIX_SCRIPTS, values))}"
    )


# ── trusted-module parity: matching metrics ────────────────────────────────────

@pytest.mark.parametrize("case", list(INPUT_CASES))
def test_cc_matches_trusted(evaluators, case):
    pred, gt = INPUT_CASES[case]
    ref = pearson_cc(pred, gt)
    for path, module in evaluators.items():
        got = module.compute_metrics(pred, gt)["CC"]
        assert np.isclose(got, ref, rtol=0, atol=PARITY_TOL), f"{path} CC={got} vs trusted={ref}"


@pytest.mark.parametrize("case", list(INPUT_CASES))
def test_spearman_matches_trusted(evaluators, case):
    pred, gt = INPUT_CASES[case]
    ref = spearman_cc(pred, gt)
    for path, module in evaluators.items():
        got = module.compute_metrics(pred, gt)["Spearman"]
        assert np.isclose(got, ref, rtol=0, atol=PARITY_TOL), f"{path} Spearman={got} vs trusted={ref}"


# ── trusted-module parity: documented divergences ──────────────────────────────

def test_mse_divergence_is_only_minmax_preprocessing(evaluators):
    """Evaluator MSE != trusted MSE on raw input, but EQUALS trusted mse_score on
    min-max-normalised inputs -- proving the divergence is purely preprocessing."""
    pred, gt = PRED_NEG, GT_NEG
    raw = mse_score(pred, gt)
    on_minmax = mse_score(normalize_minmax(pred), normalize_minmax(gt))
    for path, module in evaluators.items():
        got = module.compute_metrics(pred, gt)["MSE"]
        assert np.isclose(got, on_minmax, rtol=0, atol=PARITY_TOL), (
            f"{path} MSE={got} vs trusted-on-minmax={on_minmax}"
        )
        assert abs(got - raw) > DIVERGE_MARGIN, (
            f"{path} MSE unexpectedly equals trusted raw MSE ({got} vs {raw}); "
            "the known min-max preprocessing divergence may have been changed."
        )


def test_sim_diverges_from_trusted(evaluators):
    """CHARACTERISATION: evaluator SIM (clip+sum-norm) differs from trusted SIM
    (minmax+distribution-norm). Goes red only if the two are reconciled."""
    pred, gt = PRED_NEG, GT_NEG
    ref = similarity_score(pred, gt)
    for path, module in evaluators.items():
        got = module.compute_metrics(pred, gt)["SIM"]
        assert abs(got - ref) > DIVERGE_MARGIN, (
            f"{path} SIM={got} now matches trusted={ref}; re-review Stage-1 divergence."
        )


def test_kld_diverges_from_trusted(evaluators):
    """CHARACTERISATION: evaluator KLD (clip+sum-norm+eps) differs from trusted
    KLD (shift-min+distribution-norm). Goes red only if the two are reconciled."""
    pred, gt = PRED_NEG, GT_NEG
    ref = kldiv_score(pred, gt)
    for path, module in evaluators.items():
        got = module.compute_metrics(pred, gt)["KLD"]
        assert abs(got - ref) > DIVERGE_MARGIN, (
            f"{path} KLD={got} now matches trusted={ref}; re-review Stage-1 divergence."
        )


# ── documented exclusions ──────────────────────────────────────────────────────

def test_excluded_metrics_present_and_finite_but_not_compared(evaluators):
    """MAE, Cosine, and the proxy AUC/NSS keys exist and are finite, but are not
    compared to the trusted module (see module docstring for the reason each is
    excluded)."""
    pred, gt = PRED_NEG, GT_NEG
    for path, module in evaluators.items():
        out = module.compute_metrics(pred, gt)
        for key in ("MAE", "Cosine"):
            assert key in out and np.isfinite(out[key]), f"{path} missing/!finite {key}"
        nss_proxy = [k for k in out if k.startswith("NSS_gt_top_") and k.endswith("pct_proxy")]
        auc_proxy = [k for k in out if k.startswith("AUC_Judd_gt_top_") and k.endswith("pct_proxy")]
        assert nss_proxy, f"{path} exposes no NSS proxy keys"
        assert auc_proxy, f"{path} exposes no AUC_Judd proxy keys"
        for key in nss_proxy + auc_proxy:
            assert np.isfinite(out[key]), f"{path} {key} not finite"


def test_hit_rate_is_pipeline_level_not_in_compute_metrics(evaluators):
    """hit_rate is a ray/cone pipeline statistic; it must not appear in
    compute_metrics output (screen_space has no hit stage at all)."""
    pred, gt = PRED_NEG, GT_NEG
    for path, module in evaluators.items():
        assert "hit_rate" not in module.compute_metrics(pred, gt), (
            f"{path} unexpectedly emits hit_rate from compute_metrics"
        )
