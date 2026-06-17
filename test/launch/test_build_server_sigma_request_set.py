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
    python = "python3"
    repo_commit = "a" * 40
    release_tag = "v2.0-data-rc4"
    fixation_data_tag = "processed_fixations_offset0_full_cleaned"
    timing_contract = "one_turn_from_start"
    window_mode = "one_turn_from_start"
    fixed_delay_seconds = 0.0
    fixed_frame_offset = 0
    no_refined = False


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
    assert manifest["request_path"] == (
        "/srv/repo/Mesh-Saliency-Projection/coordination/requests/dmlab/vg_iai/3dva_screen_space_sigma.json"
    )
    assert manifest["repo"]["checkout_root"] == "/srv/repo/Mesh-Saliency-Projection"
    assert manifest["results_root"] == "/srv/results"


def test_request_and_manifest_names_are_stable():
    assert batch._request_filename("sal3d", "cone") == "sal3d_cone_sigma.json"
    assert batch._manifest_filename("sal3d", "cone") == "sal3d_cone_sigma.server_manifest.json"
