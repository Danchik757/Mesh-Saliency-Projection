"""Tests for the ablation aggregation layer (test/launch/ablation_aggregation.py).

Covers the aggregation schema and grouping behaviour ChatGPT asked to be tested
when the aggregation layer lands: metric means over status-ok models, proxy
rename, screen_space hit_rate handling, the spec directory layout, append-only /
dedupe behaviour, cone vs screen_space separation, and the legacy adapter.
"""
from __future__ import annotations

import csv
import importlib.util
import json
from pathlib import Path

import pytest

_MODULE_PATH = Path(__file__).resolve().parent / "ablation_aggregation.py"
_spec = importlib.util.spec_from_file_location("ablation_aggregation", _MODULE_PATH)
agg = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(agg)


def _rows(method: str):
    rows = [
        {"model": "A", "status": "ok", "CC": 0.50, "SIM": 0.60, "KLD": 0.40,
         "MSE": 0.030, "MAE": 0.10, "Spearman": 0.55, "Cosine": 0.80,
         "AUC_Judd_gt_top_10pct_proxy": 0.80, "AUC_Judd_gt_top_5pct_proxy": 0.82,
         "AUC_Judd_gt_top_1pct_proxy": 0.88, "NSS_gt_top_10pct_proxy": 1.00,
         "NSS_gt_top_5pct_proxy": 1.20, "NSS_gt_top_1pct_proxy": 1.50, "hit_rate": 0.90},
        {"model": "B", "status": "ok", "CC": 0.40, "SIM": 0.50, "KLD": 0.60,
         "MSE": 0.050, "MAE": 0.20, "Spearman": 0.45, "Cosine": 0.70,
         "AUC_Judd_gt_top_10pct_proxy": 0.70, "AUC_Judd_gt_top_5pct_proxy": 0.78,
         "AUC_Judd_gt_top_1pct_proxy": 0.82, "NSS_gt_top_10pct_proxy": 0.80,
         "NSS_gt_top_5pct_proxy": 1.00, "NSS_gt_top_1pct_proxy": 1.30, "hit_rate": 0.80},
        {"model": "C", "status": "failed", "error_type": "no_report"},
    ]
    if method == "screen_space":
        for r in rows:
            r.pop("hit_rate", None)
    return rows


def _params(method: str, **over):
    p = {"stage_name": "stage1_sigma", "dataset": "sal3d", "method": method,
         "timing_contract": "one_turn_from_start", "sigma_deg": 2.0,
         "model_subset_name": "demo_2", "branch": "orchestra/metric-ablation-lab"}
    p.update(over)
    return p


# ── aggregation ────────────────────────────────────────────────────────────────

def test_aggregate_metrics_means_counts_and_rename():
    means, counts = agg.aggregate_metrics(_rows("cone"), "cone")
    assert counts == {"n_ok": 2, "n_failed": 1, "n_total_models": 3}
    assert means["CC"] == pytest.approx(0.45)
    assert means["AUC_at_10pct"] == pytest.approx(0.75)   # proxy rename + mean
    assert means["NSS_at_1pct"] == pytest.approx(1.40)
    assert means["hit_rate"] == pytest.approx(0.85)


def test_screen_space_hit_rate_is_blank():
    means, _ = agg.aggregate_metrics(_rows("screen_space"), "screen_space")
    assert means["hit_rate"] is None
    assert means["CC"] == pytest.approx(0.45)             # other metrics still aggregate


def test_build_aggregate_row_has_full_schema_and_status():
    row = agg.build_aggregate_row(_params("cone"), _rows("cone"), run_id="r1")
    assert set(row) == set(agg.AGGREGATE_COLUMNS)
    assert row["run_id"] == "r1"
    assert row["status"] == "partial"                     # 2 ok, 1 failed
    assert row["error_type"] == "no_report"
    assert row["n_ok"] == 2 and row["n_failed"] == 1
    assert row["model_subset_size"] == 3
    assert row["CC"] == pytest.approx(0.45)


# ── spec layout ────────────────────────────────────────────────────────────────

def test_record_run_creates_spec_layout(tmp_path):
    run_dir = agg.record_run(tmp_path, _params("cone"), _rows("cone"),
                             run_id="sigma_deg2p0", command="python3 demo --x")
    method_root = tmp_path / "ablation" / "stage1_sigma" / "sal3d" / "cone"
    assert run_dir == method_root / "runs" / "sigma_deg2p0"

    for fname in ("README.md", "params.json", "aggregate_row.json",
                  "metrics_long.jsonl", "metrics_summary.csv", "stdout.log"):
        assert (run_dir / fname).is_file(), f"missing {fname}"

    # aggregate tables exist with the right header
    csv_path = method_root / "aggregate" / "ablation_runs.csv"
    jsonl_path = method_root / "aggregate" / "ablation_runs.jsonl"
    assert csv_path.is_file() and jsonl_path.is_file()
    header = next(csv.reader(csv_path.open()))
    assert header == list(agg.AGGREGATE_COLUMNS)

    # metrics_long has one object per model row (incl. failed)
    long_lines = [json.loads(l) for l in (run_dir / "metrics_long.jsonl").read_text().splitlines()]
    assert [r["model"] for r in long_lines] == ["A", "B", "C"]
    assert long_lines[2]["error_type"] == "no_report"

    # metrics_summary is the compact contract row (14 metrics, 4dp)
    summary = list(csv.DictReader((run_dir / "metrics_summary.csv").open()))
    assert summary[0]["CC"] == "0.4500"
    assert summary[0]["AUC_at_10pct"] == "0.7500"

    # README links the aggregate row and records the command
    readme = (run_dir / "README.md").read_text()
    assert "ablation_runs.csv" in readme and "python3 demo --x" in readme


def test_cone_and_screen_space_are_separated(tmp_path):
    agg.record_run(tmp_path, _params("cone"), _rows("cone"), run_id="r")
    agg.record_run(tmp_path, _params("screen_space"), _rows("screen_space"), run_id="r")
    base = tmp_path / "ablation" / "stage1_sigma" / "sal3d"
    assert (base / "cone" / "aggregate" / "ablation_runs.csv").is_file()
    assert (base / "screen_space" / "aggregate" / "ablation_runs.csv").is_file()


def test_record_run_supports_custom_storage_parts_and_preserves_identity(tmp_path):
    params = _params("cone", sigma_deg=1.0, storage_parts=["cone_sigma", "sal3d", "cone", "coarse"])
    rows = [{"model": "A", "status": "ok", "identity_sha1": "abc123", "repo_commit": "deadbeef",
             "CC": 0.50, "SIM": 0.60, "KLD": 0.40, "MSE": 0.03, "MAE": 0.1,
             "Spearman": 0.55, "Cosine": 0.80,
             "AUC_Judd_gt_top_10pct_proxy": 0.80, "AUC_Judd_gt_top_5pct_proxy": 0.82,
             "AUC_Judd_gt_top_1pct_proxy": 0.88, "NSS_gt_top_10pct_proxy": 1.00,
             "NSS_gt_top_5pct_proxy": 1.20, "NSS_gt_top_1pct_proxy": 1.50, "hit_rate": 0.90}]
    run_dir = agg.record_run(tmp_path, params, rows, run_id="r1")
    assert run_dir == tmp_path / "ablation" / "cone_sigma" / "sal3d" / "cone" / "coarse" / "runs" / "r1"
    long0 = json.loads((run_dir / "metrics_long.jsonl").read_text().splitlines()[0])
    assert long0["identity_sha1"] == "abc123"
    assert long0["repo_commit"] == "deadbeef"
    assert (tmp_path / "ablation" / "cone_sigma" / "sal3d" / "cone" / "coarse"
            / "aggregate" / "ablation_runs.csv").is_file()


# ── append-only / dedupe ───────────────────────────────────────────────────────

def test_two_distinct_runs_append_two_rows(tmp_path):
    agg.record_run(tmp_path, _params("cone", sigma_deg=1.0), _rows("cone"), run_id="a")
    agg.record_run(tmp_path, _params("cone", sigma_deg=2.0), _rows("cone"), run_id="b")
    jsonl = (tmp_path / "ablation/stage1_sigma/sal3d/cone/aggregate/ablation_runs.jsonl")
    ids = [json.loads(l)["run_id"] for l in jsonl.read_text().splitlines()]
    assert ids == ["a", "b"]


def test_duplicate_run_id_raises_by_default(tmp_path):
    agg.record_run(tmp_path, _params("cone"), _rows("cone"), run_id="dup")
    with pytest.raises(ValueError):
        agg.record_run(tmp_path, _params("cone"), _rows("cone"), run_id="dup")


def test_supersede_marks_old_then_appends(tmp_path):
    agg.record_run(tmp_path, _params("cone"), _rows("cone"), run_id="dup")
    agg.record_run(tmp_path, _params("cone"), _rows("cone"), run_id="dup",
                   on_duplicate="supersede")
    jsonl = (tmp_path / "ablation/stage1_sigma/sal3d/cone/aggregate/ablation_runs.jsonl")
    objs = [json.loads(l) for l in jsonl.read_text().splitlines()]
    assert [o["status"] for o in objs] == ["superseded", "partial"]
    assert "superseded_by=dup" in objs[0]["notes"]


def _one_ok_row(cc: float):
    """One status-ok model row whose CC value we vary to detect raw-file mutation."""
    return [{"model": "A", "status": "ok", "CC": cc, "SIM": 0.6, "KLD": 0.4,
             "MSE": 0.03, "MAE": 0.1, "Spearman": 0.5, "Cosine": 0.8,
             "AUC_Judd_gt_top_10pct_proxy": 0.8, "AUC_Judd_gt_top_5pct_proxy": 0.82,
             "AUC_Judd_gt_top_1pct_proxy": 0.88, "NSS_gt_top_10pct_proxy": 1.0,
             "NSS_gt_top_5pct_proxy": 1.2, "NSS_gt_top_1pct_proxy": 1.5, "hit_rate": 0.9}]


def _agg_jsonl(tmp_path):
    return tmp_path / "ablation/stage1_sigma/sal3d/cone/aggregate/ablation_runs.jsonl"


def test_duplicate_error_leaves_existing_run_dir_untouched(tmp_path):
    run_dir = agg.record_run(tmp_path, _params("cone"), _one_ok_row(0.50), run_id="dup")
    before = (run_dir / "metrics_long.jsonl").read_text()

    # Second call with the SAME run_id but DIFFERENT data must raise *before*
    # touching the existing raw artifact directory.
    with pytest.raises(ValueError):
        agg.record_run(tmp_path, _params("cone"), _one_ok_row(0.99), run_id="dup")

    assert (run_dir / "metrics_long.jsonl").read_text() == before  # raw NOT mutated
    runs_root = tmp_path / "ablation/stage1_sigma/sal3d/cone/runs"
    assert sorted(p.name for p in runs_root.iterdir()) == ["dup"]  # no rev dir created
    assert len(_agg_jsonl(tmp_path).read_text().splitlines()) == 1  # one aggregate row


def test_supersede_writes_distinct_dir_and_preserves_old_artifacts(tmp_path):
    old_dir = agg.record_run(tmp_path, _params("cone"), _one_ok_row(0.50), run_id="dup")
    old_before = (old_dir / "metrics_long.jsonl").read_text()

    new_dir = agg.record_run(tmp_path, _params("cone"), _one_ok_row(0.99), run_id="dup",
                             on_duplicate="supersede")

    assert new_dir != old_dir
    assert old_dir.name == "dup" and new_dir.name == "dup__rev2"
    # old execution's raw artifacts preserved unchanged
    assert (old_dir / "metrics_long.jsonl").read_text() == old_before
    old_cc = json.loads((old_dir / "metrics_long.jsonl").read_text().splitlines()[0])["CC"]
    new_cc = json.loads((new_dir / "metrics_long.jsonl").read_text().splitlines()[0])["CC"]
    assert old_cc == 0.50 and new_cc == 0.99  # distinct raw provenance per execution


def test_supersede_aggregate_rows_have_distinct_result_root(tmp_path):
    agg.record_run(tmp_path, _params("cone"), _one_ok_row(0.50), run_id="dup")
    agg.record_run(tmp_path, _params("cone"), _one_ok_row(0.99), run_id="dup",
                   on_duplicate="supersede")

    objs = [json.loads(l) for l in _agg_jsonl(tmp_path).read_text().splitlines()]
    assert len(objs) == 2
    assert [o["status"] for o in objs] == ["superseded", "ok"]
    # logical run_id shared, artifact_run_id + result_root distinct
    assert [o["run_id"] for o in objs] == ["dup", "dup"]
    assert [o["artifact_run_id"] for o in objs] == ["dup", "dup__rev2"]
    roots = [o["result_root"] for o in objs]
    assert roots[0] != roots[1]
    assert roots[0].endswith("/runs/dup") and roots[1].endswith("/runs/dup__rev2")
    for r in roots:  # both still point at inspectable raw artifacts
        assert (Path(r) / "metrics_long.jsonl").is_file()


def test_default_run_id_is_deterministic_signature():
    p = _params("cone", sigma_deg=2.0, radius_sigma_mult=3.0)
    assert agg.build_aggregate_row(p, _rows("cone"))["run_id"] == \
           agg.build_aggregate_row(p, _rows("cone"))["run_id"]


def test_run_signature_changes_with_model_set_signature():
    p1 = _params(
        "cone",
        sigma_deg=2.0,
        model_set_signature=agg.model_set_signature(["m1", "m2"]),
    )
    p2 = _params(
        "cone",
        sigma_deg=2.0,
        model_set_signature=agg.model_set_signature(["m1", "m3"]),
    )
    assert agg.run_signature(p1) != agg.run_signature(p2)


# ── legacy adapter ─────────────────────────────────────────────────────────────

def test_adapt_timing_ablation_row_maps_shared_and_preserves_provenance():
    legacy = {"model": "X", "status": "ok", "CC": 0.5, "SIM": 0.6, "KLD": 0.4,
              "MSE": 0.03, "AUC_Judd": 0.77, "NSS": 1.1}
    adapted = agg.adapt_timing_ablation_row(legacy)
    norm = agg.normalize_metric_row(adapted)
    assert norm["CC"] == 0.5 and norm["KLD"] == 0.4      # shared metrics transfer
    assert norm["AUC_at_10pct"] is None                  # single AUC_Judd is NOT a top-k proxy
    assert norm["MAE"] is None and norm["Cosine"] is None
    assert "legacy_AUC_Judd=0.77" in adapted["notes"]
    assert "legacy_NSS=1.1" in adapted["notes"]


# ── dual-KLD (2026-06-15 decision) ──────────────────────────────────────────────

def _kld_rows():
    """Two ok rows carrying both KLD_evaluator and KLD_trusted explicitly."""
    base = dict(SIM=0.6, MSE=0.03, MAE=0.1, Spearman=0.5, Cosine=0.8,
                AUC_Judd_gt_top_10pct_proxy=0.8, AUC_Judd_gt_top_5pct_proxy=0.82,
                AUC_Judd_gt_top_1pct_proxy=0.88, NSS_gt_top_10pct_proxy=1.0,
                NSS_gt_top_5pct_proxy=1.2, NSS_gt_top_1pct_proxy=1.5, hit_rate=0.9)
    return [
        {"model": "A", "status": "ok", "CC": 0.5, "KLD": 0.5,
         "KLD_evaluator": 0.5, "KLD_trusted": 0.04, **base},
        {"model": "B", "status": "ok", "CC": 0.4, "KLD": 0.7,
         "KLD_evaluator": 0.7, "KLD_trusted": 0.06, **base},
    ]


def test_dual_kld_in_aggregate_and_long_but_not_compact(tmp_path):
    run_dir = agg.record_run(tmp_path, _params("cone"), _kld_rows(), run_id="k1")
    method_root = tmp_path / "ablation" / "stage1_sigma" / "sal3d" / "cone"

    # aggregate row carries both explicit KLDs; historical KLD == evaluator KLD
    row = json.loads((run_dir / "aggregate_row.json").read_text())
    assert row["KLD"] == pytest.approx(0.6) == row["KLD_evaluator"]
    assert row["KLD_trusted"] == pytest.approx(0.05)

    # aggregate CSV exposes the diagnostic columns
    header = next(csv.reader((method_root / "aggregate" / "ablation_runs.csv").open()))
    assert "KLD_evaluator" in header and "KLD_trusted" in header

    # historical compact summary keeps its schema (KLD only — no dual-KLD columns)
    sheader = next(csv.reader((run_dir / "metrics_summary.csv").open()))
    assert "KLD" in sheader and "KLD_evaluator" not in sheader and "KLD_trusted" not in sheader

    # per-model long records carry both
    long0 = json.loads((run_dir / "metrics_long.jsonl").read_text().splitlines()[0])
    assert long0["KLD_evaluator"] == 0.5 and long0["KLD_trusted"] == 0.04


def test_kld_trusted_blank_when_inputs_absent(tmp_path):
    # _rows("cone") carry KLD but no KLD_trusted -> evaluator KLD preserved, trusted blank.
    run_dir = agg.record_run(tmp_path, _params("cone"), _rows("cone"), run_id="k2")
    row = json.loads((run_dir / "aggregate_row.json").read_text())
    assert row["KLD_evaluator"] == pytest.approx(row["KLD"])   # falls back to historical KLD
    assert row["KLD_trusted"] == ""                            # inputs unavailable -> blank
