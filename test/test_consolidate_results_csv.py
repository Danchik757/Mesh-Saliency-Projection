from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
PATH = REPO_ROOT / "scripts" / "consolidate_results_csv.py"
SPEC = importlib.util.spec_from_file_location("consolidate_results_csv", PATH)
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_classify_contract_categories():
    assert MODULE.classify(Path("benchmark_runs/rc2_full_metrics/a.csv")) == "rc2"
    assert MODULE.classify(Path("benchmark_runs/rc3_full_metrics_1/a.csv")) == "rc3_baseline"
    assert MODULE.classify(Path("benchmark_runs/rc3_cuthead54_delay02/a.csv")) == "rc3_timing_ablation"
    assert MODULE.classify(Path("sigma_sweep_rc3/final/a.csv")) == "rc3_sigma_sweep"
    assert MODULE.classify(Path("optimized/metrics_compact.csv")) == "rc3_optimized"
    assert MODULE.classify(Path("diagnostics/pilot.csv")) == "diagnostics"


def test_authoritative_selection_is_conservative():
    assert MODULE.is_authoritative(
        Path("benchmark_runs/rc3_full_metrics_summary_all_metrics.csv"), "rc3_baseline"
    )
    assert not MODULE.is_authoritative(Path("pilot.csv"), "diagnostics")
    assert MODULE.is_authoritative(Path("metrics_compact.csv"), "rc3_optimized")


def test_verify_manifest_checks_hash_and_untracked_files(tmp_path):
    output = tmp_path / "csv"
    copied = output / "legacy" / "result.csv"
    copied.parent.mkdir(parents=True)
    copied.write_text("metric,value\nCC,0.5\n")
    digest = MODULE.sha256(copied)
    manifest = output / "manifest.csv"
    manifest.write_text(
        "category,relative_path,source_relative_path,sha256,bytes,authoritative,"
        "run_contract,duplicate_of,notes\n"
        f"legacy,legacy/result.csv,source.csv,{digest},{copied.stat().st_size},"
        "false,legacy,,\n"
    )

    MODULE.verify_manifest(output)

    copied.write_text("metric,value\nCC,0.6\n")
    with pytest.raises(RuntimeError, match="sha256"):
        MODULE.verify_manifest(output)


def test_verify_manifest_rejects_untracked_csv(tmp_path):
    output = tmp_path / "csv"
    output.mkdir()
    (output / "manifest.csv").write_text(
        "category,relative_path,source_relative_path,sha256,bytes,authoritative,"
        "run_contract,duplicate_of,notes\n"
    )
    (output / "extra.csv").write_text("a,b\n")
    with pytest.raises(RuntimeError, match="untracked"):
        MODULE.verify_manifest(output)
