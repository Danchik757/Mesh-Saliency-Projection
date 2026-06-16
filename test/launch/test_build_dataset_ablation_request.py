from __future__ import annotations

import argparse
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


builder = _load("build_dataset_ablation_request")


def _index(tmp_path: Path, filename: str, models: list[str]) -> Path:
    path = tmp_path / filename
    path.write_text(json.dumps([{"model": m} for m in models], indent=2))
    return path


def _wrapped_index(tmp_path: Path, filename: str, models: list[str]) -> Path:
    path = tmp_path / filename
    path.write_text(json.dumps({"dataset": "x", "models": [{"model": m} for m in models]}, indent=2))
    return path


def _args(**kwargs):
    base = dict(
        dataset="sal3d",
        method="screen_space",
        stage="sigma",
        out=Path("/tmp/out.json"),
        subset_name=None,
        models=None,
        limit_models=None,
        repo_commit="a" * 40,
        release_tag="v2.0-data-rc4",
        fixation_data_tag="processed_fixations_offset0_full_cleaned",
        timing_contract="one_turn_from_start",
        window_mode="one_turn_from_start",
        fixed_delay_seconds=0.0,
        fixed_frame_offset=0,
        fixed_sigma_value=None,
        axis_values=None,
        no_refined=False,
        resolved_env=[],
        python=None,
        timeout_seconds_per_invocation=None,
        checkout_root=None,
    )
    base.update(kwargs)
    return argparse.Namespace(**base)


def test_build_sigma_request_uses_all_models(monkeypatch, tmp_path):
    monkeypatch.setitem(builder.MODEL_INDEX, "sal3d", _index(tmp_path, "sal3d.json", ["dog", "cat", "bunny"]))
    req = builder.build_request(_args())
    assert req["models"] == ["dog", "cat", "bunny"]
    assert req["subset_name"] == "sal3d_all_models"
    assert req["sigma"] == {"refined": True}
    assert req["frame_offset_policy"] == "fixed:0"
    assert req["delay_policy"] == "fixed:0.0"


def test_build_timing_request_derives_fixed_sigma(monkeypatch, tmp_path):
    monkeypatch.setitem(
        builder.MODEL_INDEX, "3dva",
        _wrapped_index(tmp_path, "3dva.json", ["A380", "blade-200K"]),
    )
    req = builder.build_request(_args(
        dataset="3dva",
        stage="timing",
        fixed_sigma_value=0.7,
        axis_values=["-0.5", "0.0", "0.5"],
        resolved_env=["FIXATION_ROOT=/srv/fix", "THREE_DVA_JSON_ROOT=/srv/jsons"],
        checkout_root="/srv/repo/Mesh-Saliency-Projection",
        python="/srv/env/bin/python",
        timeout_seconds_per_invocation=3600,
    ))
    assert req["models"] == ["A380", "blade-200K"]
    assert req["fixed_sigma"]["sigma_multiplier"] == 0.7
    assert req["fixed_sigma"]["sigma_px"] == pytest.approx(34.3)
    assert req["axis_values"] == [-0.5, 0.0, 0.5]
    assert req["frame_offset_policy"] == "fixed:0"
    assert req["delay_policy"] == "sweep:-0.5,0.0,0.5"
    assert req["resolved_env"]["FIXATION_ROOT"] == "/srv/fix"
    assert req["checkout_root"] == "/srv/repo/Mesh-Saliency-Projection"
    assert req["python"] == "/srv/env/bin/python"
    assert req["timeout_seconds_per_invocation"] == 3600


def test_build_frame_offset_request_for_cone(monkeypatch, tmp_path):
    monkeypatch.setitem(
        builder.MODEL_INDEX, "meshmamba_non_texture",
        _index(tmp_path, "mm.json", ["Watermelon_V1_L3", "Statue_v1_L2_David"]),
    )
    req = builder.build_request(_args(
        dataset="meshmamba_non_texture",
        method="cone",
        stage="frame_offset",
        fixed_sigma_value=1.6,
        fixed_delay_seconds=0.2,
        axis_values=["0", "30", "54"],
        models=["Statue_v1_L2_David"],
        subset_name="single_model_smoke",
    ))
    assert req["models"] == ["Statue_v1_L2_David"]
    assert req["fixed_sigma"] == {"sigma_deg": 1.6, "radius_sigma_mult": 3.0}
    assert req["axis_values"] == [0, 30, 54]
    assert req["frame_offset_policy"] == "sweep:0,30,54"
    assert req["delay_policy"] == "fixed:0.2"


def test_build_request_rejects_unknown_model(monkeypatch, tmp_path):
    monkeypatch.setitem(builder.MODEL_INDEX, "sal3d", _index(tmp_path, "sal3d.json", ["dog"]))
    with pytest.raises(builder.RequestBuildError, match="unknown models"):
        builder.build_request(_args(models=["cat"]))


def test_parse_env_pairs_requires_key_value():
    with pytest.raises(builder.RequestBuildError, match="KEY=VALUE"):
        builder._parse_env_pairs(["FIXATION_ROOT"])
