from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

_DIR = Path(__file__).resolve().parent


def _load(name: str):
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, _DIR / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


batch = _load("build_server_sigma_request_set")


class Args:
    out_dir = Path("/tmp/out")
    host = "vg-iai"
    checkout_root = "/srv/repo/Mesh-Saliency-Projection"
    request_root_on_server = "/srv/repo/Mesh-Saliency-Projection/coordination/requests/dmlab/vg_iai"
    results_root = "/srv/results"
    repo_url = None
    python = "/srv/env/bin/python3"
    timeout_seconds_per_invocation = 3600
    repo_commit = "a" * 40
    release_tag = "v2.0-data-rc4"
    fixation_data_tag = "processed_fixations_offset0_full_cleaned"
    timing_contract = "one_turn_from_start"
    window_mode = "one_turn_from_start"
    fixed_delay_seconds = 0.0
    fixed_frame_offset = 0
    no_refined = False
    fixation_root = "/srv/release/participant_fixations_offset0_full_cleaned"
    three_dva_dataset_root = "/srv/release/datasets/3DVA"
    three_dva_json_root = "/srv/repo/Mesh-Saliency-Projection/jsons/object_placement/3dva_jsons"
    three_dva_combined_gt_dir = "/srv/release/datasets/3DVA/CombinedGT"
    meshmamba_json_root = "/srv/repo/Mesh-Saliency-Projection/jsons/object_placement/mamba_non_jsons"
    meshmamba_rgb_json_root = "/srv/repo/Mesh-Saliency-Projection/jsons/object_placement/mamba_rgb_jsons"
    meshmamba_non_texture_root = "/srv/release/datasets/MeshMamba"
    meshmamba_rgb_texture_root = "/srv/release/datasets/MeshMamba"
    sal3d_json_root = "/srv/repo/Mesh-Saliency-Projection/jsons/object_placement/sal3d_jsons"
    sal3d_dataset_root = "/srv/shared_inputs/sal3d_benchmark_pkg"
    sal3d_fixed_gt_dir = "/srv/shared_inputs/sal3d_benchmark_pkg/sal3d_fixed_face_gt"
    sal3d_manifest = "/srv/shared_inputs/sal3d_benchmark_pkg/sal3d_manifest.csv"


def test_build_request_and_manifest_roundtrip(tmp_path):
    args = Args()
    args.out_dir = tmp_path
    req_path, manifest_path = batch.build_request_and_manifest(
        args, dataset="3dva", method="screen_space"
    )
    request = json.loads(req_path.read_text())
    manifest = json.loads(manifest_path.read_text())
    assert req_path.name == "3dva_screen_space_sigma.json"
    assert manifest_path.name == "3dva_screen_space_sigma.server_manifest.json"
    assert request["subset_name"] == "3dva_all_models_rc4"
    assert request["sigma"] == {"refined": True}
    assert request["python"] == "/srv/env/bin/python3"
    assert request["timeout_seconds_per_invocation"] == 3600
    assert request["resolved_env"] == {
        "FIXATION_ROOT": "/srv/release/participant_fixations_offset0_full_cleaned",
        "VISUAL_ATTENTION_3D_SHAPES_ROOT": "/srv/release/datasets/3DVA",
        "THREE_DVA_JSON_ROOT": "/srv/repo/Mesh-Saliency-Projection/jsons/object_placement/3dva_jsons",
        "THREE_DVA_COMBINED_GT_DIR": "/srv/release/datasets/3DVA/CombinedGT",
    }
    assert manifest["request_path"] == (
        "/srv/repo/Mesh-Saliency-Projection/coordination/requests/dmlab/vg_iai/3dva_screen_space_sigma.json"
    )
    assert manifest["repo"]["checkout_root"] == "/srv/repo/Mesh-Saliency-Projection"
    assert manifest["results_root"] == "/srv/results"
    assert manifest["command"][8] == "/srv/env/bin/python3"


def test_request_and_manifest_names_are_stable():
    assert batch._request_filename("sal3d", "cone") == "sal3d_cone_sigma.json"
    assert batch._manifest_filename("sal3d", "cone") == "sal3d_cone_sigma.server_manifest.json"
