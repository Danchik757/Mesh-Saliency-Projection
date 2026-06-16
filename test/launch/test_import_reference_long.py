"""Tests for the reference-long importer/bridge (test/launch/import_reference_long.py).

Covers: schema mapping + method filtering, required-field validation, a compact
14-metric aggregate row produced from real-style input, and a real-data
cross-check that importing the accepted rc3 sal3d/cone long CSV reproduces the
accepted compact row (skipped if the committed CSV is absent).
"""
from __future__ import annotations

import csv
import importlib.util
import json
from pathlib import Path

import pytest

_DIR = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("import_reference_long", _DIR / "import_reference_long.py")
imp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(imp)

_REPO = _DIR.parents[1]
_RC3_SAL3D_LONG = (_REPO / "results/csv/rc3_baseline/benchmark_runs/"
                   "rc3_full_metrics_20260611_004003/csv_only/sal3d_reference_long.csv")
_RC3_COMPACT = (_REPO / "results/csv/rc3_baseline/benchmark_runs/"
                "rc3_full_metrics_20260611_004003_summary_all_metrics.csv")

_METRIC_FIELDS = list(imp.CORE_SOURCE_METRICS) + list(imp.PROXY_SOURCE_METRICS)


def _synthetic_row(model, method, status, base, hit=None):
    row = {"model": model, "method": method, "status": status, "gt_domain": "vertex",
           "gt_match_type": "exact"}
    for i, f in enumerate(_METRIC_FIELDS):
        row[f] = "" if status != "ok" else round(base + i * 0.01, 4)
    if hit is not None:
        row["hit_rate"] = hit
    return row


def _write_long(path: Path, rows, *, include=("hit_rate",)):
    fields = ["model", "method", "status", "gt_domain", "gt_match_type",
              *_METRIC_FIELDS, *include]
    with path.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)


def _make_csv(tmp_path: Path) -> Path:
    rows = [
        _synthetic_row("A", "cone", "ok", 0.40, hit=0.90),
        _synthetic_row("B", "cone", "ok", 0.50, hit=0.80),
        _synthetic_row("C", "cone", "failed", 0.0),
        _synthetic_row("D", "screen_space", "ok", 0.30),
    ]
    path = tmp_path / "ref_long.csv"
    _write_long(path, rows)
    return path


# ── schema mapping / filtering ─────────────────────────────────────────────────

def test_load_reference_long_filters_by_method(tmp_path):
    path = _make_csv(tmp_path)
    cone = imp.load_reference_long(path, method="cone")
    assert sorted(r["model"] for r in cone) == ["A", "B", "C"]   # screen_space D excluded
    screen = imp.load_reference_long(path, method="screen_space")
    assert [r["model"] for r in screen] == ["D"]


def test_required_field_validation_raises(tmp_path):
    # Drop a required metric column ("KLD") -> must raise naming the missing field.
    path = tmp_path / "bad.csv"
    fields = [f for f in (["model", "method", "status"] + _METRIC_FIELDS) if f != "KLD"]
    with path.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
    with pytest.raises(ValueError) as e:
        imp.load_reference_long(path, method="cone")
    assert "KLD" in str(e.value)


def test_texture_filtering_and_no_rows_raises(tmp_path):
    # meshmamba-style CSV that carries a texture_type column (only non_texture rows).
    rows = [
        {**_synthetic_row("A", "cone", "ok", 0.4, hit=0.9), "texture_type": "non_texture"},
        {**_synthetic_row("B", "cone", "ok", 0.5, hit=0.8), "texture_type": "non_texture"},
    ]
    path = tmp_path / "mm_long.csv"
    _write_long(path, rows, include=("hit_rate", "texture_type"))

    got = imp.load_reference_long(path, method="cone", texture_type="non_texture")
    assert [r["model"] for r in got] == ["A", "B"]
    with pytest.raises(ValueError):  # rgb_texture track absent -> no rows
        imp.load_reference_long(path, method="cone", texture_type="rgb_texture")


def test_cone_missing_hit_rate_raises(tmp_path):
    # A cone source with every required metric field but NO hit_rate column must
    # fail fast (hit_rate is a cone/ray statistic and must not be silently dropped).
    rows = [_synthetic_row("A", "cone", "ok", 0.4), _synthetic_row("B", "cone", "ok", 0.5)]
    path = tmp_path / "cone_no_hit.csv"
    _write_long(path, rows, include=())  # drop the hit_rate column
    with pytest.raises(ValueError) as e:
        imp.load_reference_long(path, method="cone")
    assert "hit_rate" in str(e.value)

    # screen_space stays lenient (it has no hit stage): same schema loads fine.
    spath = tmp_path / "screen_no_hit.csv"
    _write_long(spath, [_synthetic_row("D", "screen_space", "ok", 0.3)], include=())
    assert imp.load_reference_long(spath, method="screen_space")  # no raise


def test_texture_request_without_column_raises(tmp_path):
    # Source has no texture_type column; requesting a track must raise, not silently
    # return unscoped mixed-track rows.
    path = _make_csv(tmp_path)
    with pytest.raises(ValueError) as e:
        imp.load_reference_long(path, method="cone", texture_type="rgb_texture")
    assert "texture_type" in str(e.value)


# ── aggregate production ───────────────────────────────────────────────────────

def test_import_produces_compact_14metric_aggregate_row(tmp_path):
    path = _make_csv(tmp_path)
    run_dir = imp.import_reference_run(
        path, tmp_path / "out", dataset="sal3d", method="cone",
        stage="reference_test", extra={"sigma_deg": 1.0, "radius_sigma_mult": 3.0})

    # spec layout exists
    for fname in ("README.md", "params.json", "aggregate_row.json",
                  "metrics_long.jsonl", "metrics_summary.csv", "stdout.log"):
        assert (run_dir / fname).is_file()

    summary = list(csv.DictReader((run_dir / "metrics_summary.csv").open()))[0]
    assert summary["n_ok"] == "2"
    for m in agg_metric_columns():
        assert m in summary                                   # all 14 metric columns present
    # mean of the two ok CC values (0.40, 0.50) = 0.45
    assert summary["CC"] == "0.4500"
    assert summary["hit_rate"] == "0.8500"                    # (0.90 + 0.80)/2

    row = json.loads((run_dir / "aggregate_row.json").read_text())
    assert row["dataset"] == "sal3d" and row["method"] == "cone"
    assert row["gt_domain"] == "vertex" and row["gt_match_type"] == "exact"   # passthrough provenance
    assert row["sigma_deg"] == 1.0 and row["turn_frame_count"] == 660         # caller meta + dataset default


def agg_metric_columns():
    return ("CC", "SIM", "KLD", "MSE", "MAE", "Spearman", "Cosine",
            "AUC_at_10pct", "AUC_at_5pct", "AUC_at_1pct",
            "NSS_at_10pct", "NSS_at_5pct", "NSS_at_1pct", "hit_rate")


# ── real-data cross-check ──────────────────────────────────────────────────────

@pytest.mark.skipif(not (_RC3_SAL3D_LONG.is_file() and _RC3_COMPACT.is_file()),
                    reason="accepted rc3 baseline CSVs not present")
def test_import_real_rc3_sal3d_cone_matches_accepted_compact(tmp_path):
    run_dir = imp.import_reference_run(
        _RC3_SAL3D_LONG, tmp_path / "out", dataset="sal3d", method="cone",
        stage="reference_rc3_baseline", extra={"sigma_deg": 1.0, "radius_sigma_mult": 3.0})

    summary = list(csv.DictReader((run_dir / "metrics_summary.csv").open()))[0]
    accepted = next(r for r in csv.DictReader(_RC3_COMPACT.open())
                    if r["dataset_track"] == "sal3d" and r["method"] == "cone")

    assert summary["n_ok"] == accepted["n_ok"] == "54"        # same common model set
    for metric in ("CC", "SIM", "KLD", "MSE", "MAE", "Spearman", "Cosine",
                   "AUC_at_10pct", "NSS_at_1pct", "hit_rate"):
        assert summary[metric] == accepted[metric], f"{metric}: {summary[metric]} vs {accepted[metric]}"
