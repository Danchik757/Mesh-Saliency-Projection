from __future__ import annotations

import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
MODEL_INFO_ROOT = REPO_ROOT / "jsons" / "dataset_model_info"

EXPECTED_WINDOWS = {
    "3dva_models.json": (510, 450),
    "meshmamba_non_texture_models.json": (510, 450),
    "meshmamba_rgb_texture_models.json": (510, 450),
    "sal3d_models.json": (720, 660),
}

ACTIVE_ENV_FILES = (
    REPO_ROOT / "configs" / "server_vg_intellect.env",
    REPO_ROOT / "test" / "env" / "new_machine.env.sh.template",
    REPO_ROOT / "test" / "env" / "local_paths.example.sh",
)

CURRENT_RELEASE_SCRIPTS = (
    REPO_ROOT / "scripts" / "upload_release_candidate.sh",
    REPO_ROOT / "scripts" / "download_release_candidate.sh",
    REPO_ROOT / "test" / "launch" / "run_full_metrics_optimized_sigma.py",
    REPO_ROOT / "test" / "launch" / "run_sigma_sweep_rc3.py",
)

CURRENT_EVALUATORS = (
    REPO_ROOT / "reprojection_methods" / "cone_projection_on_mesh" / "eval_3dva_cone_combined.py",
    REPO_ROOT / "reprojection_methods" / "cone_projection_on_mesh" / "eval_meshmamba_cone.py",
    REPO_ROOT / "reprojection_methods" / "cone_projection_on_mesh" / "eval_sal3d_cone.py",
    REPO_ROOT / "reprojection_methods" / "screen_space_gaussian" / "eval_3dva_screen_space_combined.py",
    REPO_ROOT / "reprojection_methods" / "screen_space_gaussian" / "eval_meshmamba_screen_space.py",
    REPO_ROOT / "reprojection_methods" / "screen_space_gaussian" / "eval_sal3d_screen_space.py",
)

CURRENT_REFERENCE_RUNNERS = (
    REPO_ROOT / "test" / "launch" / "run_3dva_reference_batch.py",
    REPO_ROOT / "test" / "launch" / "run_meshmamba_reference_batch.py",
    REPO_ROOT / "test" / "launch" / "run_sal3d_reference_batch.py",
)


def _load(filename: str) -> dict:
    return json.loads((MODEL_INFO_ROOT / filename).read_text())


def test_all_model_metadata_uses_baseline_one_turn_contract():
    for filename, (total_frames, turn_frames) in EXPECTED_WINDOWS.items():
        payload = _load(filename)
        assert payload["model_count"] == len(payload["models"])

        for model in payload["models"]:
            timing = model["render_and_projection"]["timing_contract"]
            assert timing["name"] == "one_turn_from_start"
            assert timing["crop_start_seconds"] == 0.0
            assert timing["crop_end_seconds"] == 0.0
            assert timing["placement_start_frame_zero_based"] == 0
            assert timing["placement_end_frame_exclusive_zero_based"] == turn_frames
            assert timing["usable_frames"] == turn_frames
            assert timing["total_frames"] == total_frames
            assert timing["pairing_rule"] == (
                "processed_gaze[k] -> placement[k] for one full turn"
            )


def test_all_model_metadata_uses_offset0_processed_fixations():
    for filename in EXPECTED_WINDOWS:
        for model in _load(filename)["models"]:
            processed = model["participant_data"]["processed_fixations_json"]
            assert processed["timing"] == "one_turn_from_start_offset_0"
            assert "processed_fixations_offset0_full_cleaned" in (
                processed["repository_staging_path"]
            )
            assert "participant_fixations_offset0_full_cleaned" in (
                processed["release_path"]
            )


def test_summary_matches_baseline_contract():
    summary = json.loads((MODEL_INFO_ROOT / "all_datasets_summary.json").read_text())
    timing = summary["timing_contract"]
    assert timing["name"] == "one_turn_from_start"
    assert timing["delay_seconds_default"] == 0.0
    assert timing["crop_start_seconds"] == 0.0
    assert timing["crop_end_seconds"] == 0.0
    assert timing["pairing"] == "gaze[k] -> placement[k] for one full object rotation"
    assert timing["derive_full_turn_from_placement_json"] is True


def test_active_environment_templates_use_offset0_baseline():
    for path in ACTIVE_ENV_FILES:
        text = path.read_text()
        assert "processed_fixations_offset0_full_cleaned" in text
        assert "processed_fixations_offset_2000" not in text
        assert "participant_fixations_processed_offset_2000" not in text
        assert 'REPROJECT_TIMING_CONTRACT="one_turn_from_start"' in text


def test_current_release_scripts_default_to_rc4():
    for path in CURRENT_RELEASE_SCRIPTS:
        text = path.read_text()
        assert "v2.0-data-rc4" in text
        assert 'TAG="${TAG:-v2.0-data-rc1}"' not in text
        assert 'RELEASE_TAG       = os.environ.get("REPROJECT_RELEASE_TAG", "v2.0-data-rc3")' not in text


def test_current_evaluators_default_to_one_turn():
    for path in CURRENT_EVALUATORS:
        text = path.read_text()
        assert 'default=os.environ.get("REPROJECT_TIMING_CONTRACT", TIMING_CONTRACT_ONE_TURN)' in text
        assert 'getattr(args, "timing_contract", TIMING_CONTRACT_ONE_TURN)' in text
        assert "default, offset_2000 data" not in text


def test_current_reference_runners_default_to_one_turn():
    for path in CURRENT_REFERENCE_RUNNERS:
        text = path.read_text()
        assert 'default=os.environ.get("REPROJECT_TIMING_CONTRACT", "one_turn_from_start")' in text
        assert "default, offset_2000 data" not in text


def test_legacy_packaging_helper_has_no_machine_specific_root():
    text = (REPO_ROOT / "scripts" / "package_datasets.sh").read_text()
    assert "/Users/admin" not in text
    assert "build_release_candidate.py" in text
