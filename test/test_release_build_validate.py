"""
Tests for the rc4 release builder and the strengthened validator (Gate 2):

builder (scripts/build_release_candidate.py)
  - manifest metadata is schema_version 2, offset0 / one_turn_from_start
  - based_on never mentions offset_2000 / cropped-reset
  - --dry-run exits 0 without touching source data

validator (scripts/validate_release_candidate.py)
  - exact frame counts keyed on dataset prefix (510 / 720 / 41)
  - based_on stale-data sanity check
  - Smooth Gaze + fixed-face GT inventory and the documented mismatch sets
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_builder = _load("build_release_candidate", REPO_ROOT / "scripts" / "build_release_candidate.py")
_validator = _load("validate_release_candidate", REPO_ROOT / "scripts" / "validate_release_candidate.py")


# ── builder manifest metadata ───────────────────────────────────────────────────

def test_manifest_metadata_is_schema2_offset0():
    m = _builder.build_manifest_metadata("v2.0-data-rc4", "deadbeef")
    assert m["schema_version"] == 2
    assert m["tag"] == "v2.0-data-rc4"
    assert m["timing_contract"]["name"] == "one_turn_from_start"
    assert m["timing_contract"]["crop_start_seconds"] == 0.0
    assert m["timing_contract"]["crop_end_seconds"] == 0.0
    pdc = m["participant_data_contract"]
    assert pdc["processed_json_archive"] == "participant_fixations_offset0_full_cleaned.zip"
    assert pdc["fixation_format"] == "one_turn_from_start_offset_0"
    assert pdc["automatic_fallback_allowed"] is False
    assert pdc["expected_file_count"] == 298


def test_manifest_based_on_has_no_legacy_terms():
    based_on = _builder.build_manifest_metadata("v2.0-data-rc4", "x")["based_on"].lower()
    for stale in ("offset_2000", "offset-2000", "cropped-reset", "cropped_reset"):
        assert stale not in based_on


def test_smooth_gaze_is_mandatory():
    # Item 3: no exclusion flag, manifest always references it, specs always build it.
    import inspect
    assert "--no-sal3d-smooth-gaze" not in inspect.getsource(_builder.parse_args)
    assert "include_smooth_gaze" not in inspect.signature(_builder.build_manifest_metadata).parameters

    manifest = _builder.build_manifest_metadata("v2.0-data-rc4", "x")
    assert manifest["sal3d_contract"]["smooth_gaze_archive"] == "sal3d_smooth_gaze.zip"

    class NS:
        repo_root = REPO_ROOT
        fixation_source = None
        participant_csv_source = REPO_ROOT / "x"
        data_3dva_root = REPO_ROOT / "x"
        data_meshmamba_root = REPO_ROOT / "x"
        data_sal3d_root = REPO_ROOT / "x"
        data_sal3d_fixed_root = REPO_ROOT / "x"
        videos_root = REPO_ROOT / "x"
        include_videos = False
    spec_names = [name for name, _ in _builder.build_specs(NS())]
    assert "sal3d_smooth_gaze.zip" in spec_names


def test_default_fixation_source_is_canonical_tracked_path():
    # Item 1: the default tracked source is participant_data/processed_fixations_offset0_full_cleaned/
    class NS:
        fixation_source = None
        repo_root = REPO_ROOT
    src = _builder.fixation_source_dir(NS())
    assert src == REPO_ROOT / "participant_data" / "processed_fixations_offset0_full_cleaned"
    assert _builder.FIXATION_SOURCE_DIRNAME == "processed_fixations_offset0_full_cleaned"
    # archive root name stays distinct
    assert _builder.FIXATION_ROOT == "participant_fixations_offset0_full_cleaned"


def test_builder_dry_run_strict_fail_on_missing_sources():
    # Strict preflight: missing offset0 source locally → nonzero, not exit 0.
    proc = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "build_release_candidate.py"), "--dry-run"],
        capture_output=True, text=True,
    )
    assert proc.returncode == 3, proc.stdout
    assert "STRICT FAIL" in proc.stdout
    assert "schema_version=2" in proc.stdout  # plan still printed


def test_strict_preflight_clean_with_synthetic_298(tmp_path):
    src = tmp_path / "fix"
    for i in range(298):
        d = src / f"M{i:03d}"
        d.mkdir(parents=True)
        (d / "fixations.json").write_text("[]")

    class NS:
        fixation_source = src
        repo_root = REPO_ROOT
    specs = [("participant_fixations_offset0_full_cleaned.zip", [(src, _builder.FIXATION_ROOT)])]
    assert _builder.strict_preflight(NS(), specs) == []
    # 297 → fails the count check
    next(src.iterdir()).rename(tmp_path / "moved")
    assert _builder.strict_preflight(NS(), specs)


# ── validator: per-prefix frame lengths ─────────────────────────────────────────

def test_expected_frames_by_prefix():
    assert _validator._expected_frames_for("3DVA_A380") == 510
    assert _validator._expected_frames_for("MeshMamba_Cat_v1_L3") == 510
    assert _validator._expected_frames_for("SAL3D_alien") == 720
    assert _validator._expected_frames_for("3DVA_jessi") == 41
    assert _validator._expected_frames_for("Mystery_model") is None


def _make_fixation_zip(path: Path, entries: dict[str, int]) -> None:
    root = "participant_fixations_offset0_full_cleaned"
    with zipfile.ZipFile(path, "w") as z:
        for model_id, n in entries.items():
            z.writestr(f"{root}/{model_id}/fixations.json", json.dumps([[[0.0, 0.0]]] * n))


def test_fixation_lengths_ok(tmp_path):
    p = tmp_path / "fix.zip"
    _make_fixation_zip(p, {"3DVA_A380": 510, "SAL3D_alien": 720, "3DVA_jessi": 41})
    with zipfile.ZipFile(p) as z:
        members = {m for m in z.namelist() if not m.endswith("/")}
    errors: list[str] = []
    _validator._check_fixation_frame_counts(p, members, errors)
    assert errors == []


def test_sal3d_file_with_3dva_prefix_length_rejected(tmp_path):
    p = tmp_path / "fix.zip"
    # A 720-frame file under a 3DVA_ prefix is wrong even though 720 is valid elsewhere.
    _make_fixation_zip(p, {"3DVA_A380": 720, "SAL3D_alien": 720, "3DVA_jessi": 41})
    with zipfile.ZipFile(p) as z:
        members = {m for m in z.namelist() if not m.endswith("/")}
    errors: list[str] = []
    _validator._check_fixation_frame_counts(p, members, errors)
    assert any("frame counts not matching dataset prefix" in e for e in errors)


# ── validator: based_on sanity ──────────────────────────────────────────────────

def test_based_on_stale_flagged():
    errors: list[str] = []
    _validator._check_based_on(
        {"based_on": "rc1 with cropped-reset offset-2000 data"}, errors)
    assert errors and "based_on" in errors[0]


def test_based_on_clean_ok():
    errors: list[str] = []
    _validator._check_based_on(
        {"based_on": "rc1 assets with offset0 one_turn_from_start fixations"}, errors)
    assert errors == []


# ── validator: SAL3D inventories ────────────────────────────────────────────────

def _common_models() -> list[str]:
    return [f"model{i:02d}" for i in range(51)]


def _make_smooth_zip(path: Path, models: list[str]) -> None:
    root = "datasets/SAL3D/Smooth_Gaze"
    with zipfile.ZipFile(path, "w") as z:
        for mdl in models:
            z.writestr(f"{root}/{mdl}_neighbors.txt", "0 neighbors\n")


def _make_fixed_zip(path: Path, models: list[str]) -> None:
    root = "datasets/SAL3D_fixed/sal3d_benchmark_pkg"
    with zipfile.ZipFile(path, "w") as z:
        for mdl in models:
            z.writestr(f"{root}/Meshes/{mdl}.obj", "v 0 0 0\n")
            z.writestr(f"{root}/{mdl}_faces.txt", "0\n")
        z.writestr(f"{root}/SHA256SUMS", "x\n")


def test_inventory_clean_passes(tmp_path):
    common = _common_models()
    smooth = common + ["AudiRS5", "bimba"]                 # 53
    fixed = common + ["MaxPlanck", "dog", "flowerpot", "prot"]  # 55
    _make_smooth_zip(tmp_path / "sal3d_smooth_gaze.zip", smooth)
    _make_fixed_zip(tmp_path / "sal3d_fixed_face_gt.zip", fixed)
    archives = {"sal3d_smooth_gaze.zip": {}, "sal3d_fixed_face_gt.zip": {}}
    errors: list[str] = []
    _validator._check_sal3d_inventories(tmp_path, archives, errors)
    assert errors == [], errors


def test_inventory_wrong_count_flagged(tmp_path):
    _make_smooth_zip(tmp_path / "sal3d_smooth_gaze.zip", ["only_one"])
    archives = {"sal3d_smooth_gaze.zip": {}}
    errors: list[str] = []
    _validator._check_sal3d_inventories(tmp_path, archives, errors)
    assert any("Smooth Gaze inventory" in e for e in errors)


def test_fixed_face_gt_mesh_pairing_enforced(tmp_path):
    # An .obj without its matching _faces.txt must be flagged.
    common = _common_models()
    fixed = common + ["MaxPlanck", "dog", "flowerpot", "prot"]
    path = tmp_path / "sal3d_fixed_face_gt.zip"
    root = "datasets/SAL3D_fixed/sal3d_benchmark_pkg"
    with zipfile.ZipFile(path, "w") as z:
        for mdl in fixed:
            z.writestr(f"{root}/Meshes/{mdl}.obj", "v 0 0 0\n")
            if mdl != "dog":  # drop dog's per-face GT → pairing error
                z.writestr(f"{root}/{mdl}_faces.txt", "0\n")
    errors: list[str] = []
    _validator._check_sal3d_inventories(tmp_path, {"sal3d_fixed_face_gt.zip": {}}, errors)
    assert any("without per-face GT" in e for e in errors)


# ── validate_data_contract: one_turn support ────────────────────────────────────

def test_validate_data_contract_one_turn_placement_ok():
    # Under one_turn_from_start the cropped-window checks are skipped; real
    # placement JSONs must still validate (no invalid_placement entries).
    dc = REPO_ROOT / "scripts" / "validate_data_contract.py"
    proc = subprocess.run(
        [sys.executable, str(dc), "--timing-contract", "one_turn_from_start",
         "--allow-known-blockers"],
        capture_output=True, text=True,
    )
    data = json.loads(proc.stdout)
    assert data["timing_contract"] == "one_turn_from_start"
    for track, tr in data["tracks"].items():
        assert tr["invalid_models"]["placement"] == {}, (track, tr["invalid_models"]["placement"])


# ── synthetic end-to-end release validation ─────────────────────────────────────

def _zip_tree(path, root, names, content="x\n"):
    with zipfile.ZipFile(path, "w") as z:
        for n in names:
            z.writestr(f"{root}/{n}", content)


def _build_synthetic_release(out):
    import hashlib
    out.mkdir(parents=True, exist_ok=True)
    common = [f"model{i:02d}" for i in range(51)]

    # fixation archive: prefix-correct lengths incl jessi=41, total 298
    fix = out / "participant_fixations_offset0_full_cleaned.zip"
    froot = "participant_fixations_offset0_full_cleaned"
    with zipfile.ZipFile(fix, "w") as z:
        ids = ([f"3DVA_m{i:03d}" for i in range(100)]
               + [f"MeshMamba_m{i:03d}" for i in range(99)]
               + [f"SAL3D_m{i:03d}" for i in range(98)]
               + ["3DVA_jessi"])
        assert len(ids) == 298
        for mid in ids:
            n = 41 if mid == "3DVA_jessi" else (720 if mid.startswith("SAL3D_") else 510)
            z.writestr(f"{froot}/{mid}/fixations.json", json.dumps([[[0.0, 0.0]]] * n))

    _zip_tree(out / "participant_gaze_csv_original.zip", "participant_gaze_csv_original",
              [f"m{i:03d}.csv" for i in range(298)])
    _zip_tree(out / "object_placement_json_canonical.zip", "object_placement_json_canonical",
              [f"p{i:03d}.json" for i in range(299)])
    _zip_tree(out / "3dva_objs_corrected.zip", "datasets/3DVA/3DModels-Simplif-up",
              [f"o{i:02d}.obj" for i in range(32)])
    _zip_tree(out / "3dva_gt.zip", "datasets/3DVA", ["FixationMaps/a.txt", "CentricityAndVisibilityMaps/b.txt"])
    _zip_tree(out / "3dva_combined_gt.zip", "datasets/3DVA/CombinedGT", ["a.txt"])
    _zip_tree(out / "meshmamba_non_texture_objs.zip", "datasets/MeshMamba/MeshFile/non_texture", ["a.obj"])
    _zip_tree(out / "meshmamba_rgb_texture_objs.zip", "datasets/MeshMamba/MeshFile/rgb_texture", ["a.obj"])
    _zip_tree(out / "meshmamba_saliency_gt.zip", "datasets/MeshMamba/SaliencyMap", ["a.txt"])
    _zip_tree(out / "sal3d_meshes.zip", "datasets/SAL3D/Meshes", ["a.obj"])
    _zip_tree(out / "sal3d_gaze_gt.zip", "datasets/SAL3D/Gaze", ["a.txt"])

    # smooth gaze: 53 = 51 common + AudiRS5 + bimba
    _make_smooth_zip(out / "sal3d_smooth_gaze.zip", common + ["AudiRS5", "bimba"])
    # fixed-face: 55 models = 51 common + 4 fixed-only, paired .obj + _faces.txt + 4 metadata = 114
    fixed = common + ["MaxPlanck", "dog", "flowerpot", "prot"]
    ffroot = "datasets/SAL3D_fixed/sal3d_benchmark_pkg"
    with zipfile.ZipFile(out / "sal3d_fixed_face_gt.zip", "w") as z:
        for mdl in fixed:
            z.writestr(f"{ffroot}/Meshes/{mdl}.obj", "v 0 0 0\n")
            z.writestr(f"{ffroot}/{mdl}_faces.txt", "0\n")
        for meta in ("SHA256SUMS", "sal3d_checksums.md5", "sal3d_manifest.csv", "sal3d_manifest.md"):
            z.writestr(f"{ffroot}/{meta}", "x\n")

    def _sha(p):
        h = hashlib.sha256()
        h.update(p.read_bytes())
        return h.hexdigest()

    names = [p.name for p in sorted(out.glob("*.zip"))]
    archives = []
    for name in names:
        p = out / name
        with zipfile.ZipFile(p) as z:
            fc = len([m for m in z.namelist() if not m.endswith("/")])
        archives.append({"name": name, "sha256": _sha(p), "file_count": fc})

    manifest = _builder.build_manifest_metadata("v2.0-data-rc4", "synthetic")
    manifest["archives"] = archives
    (out / "release_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    (out / "SHA256SUMS").write_text("\n".join(f"{a['sha256']}  {a['name']}" for a in archives) + "\n")
    (out / "data_contract_validation.json").write_text(json.dumps({"errors": []}) + "\n")


def test_synthetic_release_passes_validation(tmp_path):
    rel = tmp_path / "v2.0-data-rc4"
    _build_synthetic_release(rel)
    proc = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "validate_release_candidate.py"), str(rel)],
        capture_output=True, text=True,
    )
    data = json.loads(proc.stdout)
    assert data["status"] == "ok", data["errors"]
    assert proc.returncode == 0
