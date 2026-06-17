"""Tests for the downstream stage request builder."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

_DIR = Path(__file__).resolve().parent


def _load(name: str):
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, _DIR / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


ds = _load("build_downstream_request")
core = _load("dataset_ablation_core")


_VG_IAI = dict(
    host="vg-iai",
    checkout_root="/srv/repo/Mesh-Saliency-Projection",
    request_root_on_server="/srv/repo/Mesh-Saliency-Projection/coordination/requests/dmlab/vg_iai",
    results_root="/srv/results",
    repo_url=None,
    python="python3",
    repo_commit=None,
    subset_name=None,
    release_tag="v2.0-data-rc4",
    fixation_data_tag="processed_fixations_offset0_full_cleaned",
    timing_contract="one_turn_from_start",
    window_mode="one_turn_from_start",
    timing_grid=None,
    frame_offset_grid=None,
)


def _args(**kw):
    d = dict(_VG_IAI)
    d.update(kw)
    return type("Args", (), d)()


def _sigma_best(tmp_path: Path, *, dataset: str, method: str,
                sigma_deg: float | None = None,
                sigma_multiplier: float | None = None,
                sigma_px: float | None = None) -> Path:
    if method == "cone":
        bp = {"sigma_deg": sigma_deg or 1.0, "radius_sigma_mult": 3.0,
              "delay_seconds": 0.0, "frame_offset": 0}
    else:
        bp = {"sigma_multiplier": sigma_multiplier or 1.0, "sigma_px": sigma_px or 50.0,
              "delay_seconds": 0.0, "frame_offset": 0}
    payload = {
        "family": f"{method}_sigma_dmlab", "dataset": dataset, "method": method,
        "stage": "sigma", "selection_rule": "mean_CC_on_common_model_set",
        "best_params": bp, "subset_name": f"{dataset}_all_models_rc4",
        "repo_commit": "a" * 40,
    }
    p = tmp_path / f"{dataset}_{method}_sigma_best.json"
    p.write_text(json.dumps(payload))
    return p


def _timing_best(tmp_path: Path, *, dataset: str, method: str,
                 sigma_deg: float | None = None,
                 sigma_multiplier: float | None = None,
                 delay_seconds: float = 0.2) -> Path:
    if method == "cone":
        bp = {"sigma_deg": sigma_deg or 1.0, "radius_sigma_mult": 3.0,
              "delay_seconds": delay_seconds, "frame_offset": 0}
    else:
        bp = {"sigma_multiplier": sigma_multiplier or 1.0, "sigma_px": 50.0,
              "delay_seconds": delay_seconds, "frame_offset": 0}
    payload = {
        "family": f"{method}_timing_dmlab", "dataset": dataset, "method": method,
        "stage": "timing", "selection_rule": "mean_CC_on_common_model_set",
        "best_params": bp, "subset_name": f"{dataset}_all_models_rc4",
        "repo_commit": "a" * 40,
    }
    p = tmp_path / f"{dataset}_{method}_timing_best.json"
    p.write_text(json.dumps(payload))
    return p


# ── timing stage ─────────────────────────────────────────────────────────────

def test_timing_request_from_sigma_best_cone(tmp_path):
    sig_best = _sigma_best(tmp_path, dataset="sal3d", method="cone", sigma_deg=1.25)
    args = _args(out_dir=tmp_path)
    req_path, manifest_path = ds.build_timing_request(sig_best, args)

    req = json.loads(req_path.read_text())
    assert req["dataset"] == "sal3d"
    assert req["method"] == "cone"
    assert req["stage"] == "timing"
    assert req["fixed_sigma"] == {"sigma_deg": 1.25, "radius_sigma_mult": 3.0}
    assert req["delay_policy"].startswith("sweep:")
    assert -3.0 in req["axis_values"] and 3.0 in req["axis_values"]
    assert req["frame_offset_policy"] == "fixed:0"
    core.validate_request(req)


def test_timing_request_from_sigma_best_screen_space(tmp_path):
    sig_best = _sigma_best(tmp_path, dataset="meshmamba_non_texture", method="screen_space",
                           sigma_multiplier=1.3, sigma_px=65.0)
    args = _args(out_dir=tmp_path)
    req_path, manifest_path = ds.build_timing_request(sig_best, args)

    req = json.loads(req_path.read_text())
    assert req["stage"] == "timing"
    assert req["fixed_sigma"]["sigma_multiplier"] == pytest.approx(1.3)
    assert len(req["axis_values"]) == len(ds.TIMING_GRID)


def test_timing_request_uses_custom_grid(tmp_path):
    sig_best = _sigma_best(tmp_path, dataset="sal3d", method="cone")
    args = _args(out_dir=tmp_path, timing_grid=[-0.5, 0.0, 0.5])
    req_path, _ = ds.build_timing_request(sig_best, args)
    req = json.loads(req_path.read_text())
    assert req["axis_values"] == [-0.5, 0.0, 0.5]


def test_timing_request_filename_convention(tmp_path):
    sig_best = _sigma_best(tmp_path, dataset="3dva", method="cone")
    args = _args(out_dir=tmp_path)
    req_path, manifest_path = ds.build_timing_request(sig_best, args)
    assert req_path.name == "3dva_cone_timing.json"
    assert manifest_path.name == "3dva_cone_timing.server_manifest.json"


def test_timing_manifest_has_real_launcher_and_signature(tmp_path):
    sig_best = _sigma_best(tmp_path, dataset="sal3d", method="screen_space",
                           sigma_multiplier=1.0)
    args = _args(out_dir=tmp_path)
    _, manifest_path = ds.build_timing_request(sig_best, args)
    m = json.loads(manifest_path.read_text())
    assert "--mock" not in m["command"]
    assert m["command"][9].endswith("screen_space_dataset_ablation.py")
    assert m["comparability_signature"] in m["branch_dir"]
    assert m["host"] == "vg-iai"


def test_timing_request_inherits_subset_name_from_sigma_best(tmp_path):
    sig_best = _sigma_best(tmp_path, dataset="sal3d", method="cone")
    args = _args(out_dir=tmp_path)
    req_path, _ = ds.build_timing_request(sig_best, args)
    req = json.loads(req_path.read_text())
    assert req["subset_name"] == "sal3d_all_models_rc4"


def test_timing_request_rejects_missing_sigma_best(tmp_path):
    args = _args(out_dir=tmp_path)
    with pytest.raises(ds.DownstreamBuildError, match="not found"):
        ds.build_timing_request(tmp_path / "nonexistent.json", args)


def test_timing_request_rejects_wrong_stage(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"stage": "timing", "best_params": {}}))
    args = _args(out_dir=tmp_path)
    with pytest.raises(ds.DownstreamBuildError, match="expected stage=.sigma"):
        ds.build_timing_request(bad, args)


# ── frame_offset stage ───────────────────────────────────────────────────────

def test_frame_offset_request_from_sigma_and_timing_cone(tmp_path):
    sig_best = _sigma_best(tmp_path, dataset="sal3d", method="cone", sigma_deg=1.6)
    tim_best = _timing_best(tmp_path, dataset="sal3d", method="cone", sigma_deg=1.6, delay_seconds=0.2)
    args = _args(out_dir=tmp_path)
    req_path, manifest_path = ds.build_frame_offset_request(sig_best, tim_best, args)

    req = json.loads(req_path.read_text())
    assert req["stage"] == "frame_offset"
    assert req["fixed_sigma"] == {"sigma_deg": 1.6, "radius_sigma_mult": 3.0}
    assert req["fixed"]["delay_seconds"] == pytest.approx(0.2)
    assert req["delay_policy"] == "fixed:0.2"
    assert 0 in req["axis_values"] and 54 in req["axis_values"]
    core.validate_request(req)


def test_frame_offset_request_from_sigma_and_timing_screen_space(tmp_path):
    sig_best = _sigma_best(tmp_path, dataset="meshmamba_non_texture", method="screen_space",
                           sigma_multiplier=1.0)
    tim_best = _timing_best(tmp_path, dataset="meshmamba_non_texture", method="screen_space",
                            delay_seconds=-0.1)
    args = _args(out_dir=tmp_path)
    req_path, _ = ds.build_frame_offset_request(sig_best, tim_best, args)
    req = json.loads(req_path.read_text())
    assert req["fixed"]["delay_seconds"] == pytest.approx(-0.1)
    assert req["fixed_sigma"]["sigma_multiplier"] == pytest.approx(1.0)
    assert len(req["axis_values"]) == len(ds.FRAME_OFFSET_GRID)


def test_frame_offset_filename_convention(tmp_path):
    sig_best = _sigma_best(tmp_path, dataset="3dva", method="screen_space")
    tim_best = _timing_best(tmp_path, dataset="3dva", method="screen_space")
    args = _args(out_dir=tmp_path)
    req_path, manifest_path = ds.build_frame_offset_request(sig_best, tim_best, args)
    assert req_path.name == "3dva_screen_space_frame_offset.json"
    assert manifest_path.name == "3dva_screen_space_frame_offset.server_manifest.json"


def test_frame_offset_rejects_dataset_mismatch(tmp_path):
    sig_best = _sigma_best(tmp_path, dataset="sal3d", method="cone")
    tim_best = _timing_best(tmp_path, dataset="3dva", method="cone")
    args = _args(out_dir=tmp_path)
    with pytest.raises(ds.DownstreamBuildError, match="mismatch"):
        ds.build_frame_offset_request(sig_best, tim_best, args)


def test_frame_offset_rejects_method_mismatch(tmp_path):
    sig_best = _sigma_best(tmp_path, dataset="sal3d", method="cone")
    tim_best = _timing_best(tmp_path, dataset="sal3d", method="screen_space")
    args = _args(out_dir=tmp_path)
    with pytest.raises(ds.DownstreamBuildError, match="mismatch"):
        ds.build_frame_offset_request(sig_best, tim_best, args)


def test_frame_offset_custom_grid(tmp_path):
    sig_best = _sigma_best(tmp_path, dataset="sal3d", method="cone")
    tim_best = _timing_best(tmp_path, dataset="sal3d", method="cone")
    args = _args(out_dir=tmp_path, frame_offset_grid=[0, 30, 90])
    req_path, _ = ds.build_frame_offset_request(sig_best, tim_best, args)
    req = json.loads(req_path.read_text())
    assert req["axis_values"] == [0, 30, 90]


# ── grid constants ────────────────────────────────────────────────────────────

def test_timing_grid_matches_family_launcher():
    rawd = _load("run_ablation_window_delay")
    assert list(ds.TIMING_GRID) == rawd.LARGE_ABLATION_DELAYS


def test_frame_offset_grid_matches_family_launcher():
    fofl = _load("frame_offset_family_launcher")
    assert ds.FRAME_OFFSET_GRID == fofl.DEFAULT_FRAME_OFFSET_GRID
