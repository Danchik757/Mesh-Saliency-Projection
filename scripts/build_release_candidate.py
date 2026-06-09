#!/usr/bin/env python3
"""Build a versioned benchmark-data release candidate with an explicit manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import time
import zipfile
from pathlib import Path
from typing import Iterable


def parse_args() -> argparse.Namespace:
    repo = Path(__file__).resolve().parents[1]
    saliency_root = repo.parents[2]
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=repo)
    parser.add_argument("--output-dir", type=Path, default=repo / "release_assets" / "v2.0-data-rc1")
    parser.add_argument("--tag", default="v2.0-data-rc1")
    parser.add_argument("--data-3dva-root", type=Path, default=saliency_root / "GAZE_DATA/datasets/3DVA")
    parser.add_argument(
        "--data-meshmamba-root",
        type=Path,
        default=saliency_root / "GAZE_DATA/datasets/MeshMamba/MeshMambaSaliency",
    )
    parser.add_argument(
        "--data-sal3d-root",
        type=Path,
        default=saliency_root / "GAZE_DATA/datasets/SAL3D/SAL3D_Dataset",
    )
    parser.add_argument("--videos-root", type=Path, default=saliency_root / "videos")
    parser.add_argument("--include-videos", action="store_true")
    parser.add_argument("--include-sal3d-smooth-gaze", action="store_true")
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def iter_files(source: Path) -> Iterable[Path]:
    if source.is_symlink():
        source = source.resolve()
    for path in sorted(source.rglob("*"), key=lambda value: value.as_posix().lower()):
        if path.is_file() and path.name != ".DS_Store" and "__MACOSX" not in path.parts:
            yield path


def add_tree(archive: zipfile.ZipFile, source: Path, archive_root: str) -> int:
    source = source.resolve()
    count = 0
    for path in iter_files(source):
        relative = path.relative_to(source).as_posix()
        archive.write(path, f"{archive_root.rstrip('/')}/{relative}")
        count += 1
    return count


def build_archive(output: Path, trees: list[tuple[Path, str]], force: bool) -> dict:
    if output.exists():
        if not force:
            raise FileExistsError(f"{output} already exists; pass --force to replace it")
        output.unlink()
    output.parent.mkdir(parents=True, exist_ok=True)
    source_counts: dict[str, int] = {}
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for source, archive_root in trees:
            if not source.exists():
                raise FileNotFoundError(source)
            source_counts[archive_root] = add_tree(archive, source, archive_root)
    with zipfile.ZipFile(output) as archive:
        bad_member = archive.testzip()
        members = [name for name in archive.namelist() if not name.endswith("/")]
    if bad_member:
        raise RuntimeError(f"{output}: CRC failure in {bad_member}")
    return {
        "name": output.name,
        "bytes": output.stat().st_size,
        "sha256": sha256(output),
        "file_count": len(members),
        "source_counts": source_counts,
    }


def git_commit(repo: Path) -> str:
    return subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()


def require_clean_tree(repo: Path) -> None:
    status = subprocess.check_output(
        ["git", "-C", str(repo), "status", "--porcelain"],
        text=True,
    ).strip()
    if status:
        raise RuntimeError("release candidate must be built from a clean committed git tree")


def main() -> int:
    args = parse_args()
    repo = args.repo_root.resolve()
    output_dir = args.output_dir.resolve()
    participant = repo / "participant_data"
    placement = repo / "jsons" / "object_placement"
    require_clean_tree(repo)

    specs: list[tuple[str, list[tuple[Path, str]]]] = [
        (
            "participant_gaze_csv_original.zip",
            [(participant / "collected_gaze_csv_by_model", "participant_gaze_csv_original")],
        ),
        (
            "participant_fixations_processed_offset_2000.zip",
            [(participant / "processed_fixations_offset_2000", "participant_fixations_processed_offset_2000")],
        ),
        ("object_placement_json_canonical.zip", [(placement, "object_placement_json_canonical")]),
        (
            "3dva_objs_corrected.zip",
            [(args.data_3dva_root / "3DModels-Simplif-up", "datasets/3DVA/3DModels-Simplif-up")],
        ),
        (
            "3dva_gt.zip",
            [
                (args.data_3dva_root / "FixationMaps", "datasets/3DVA/FixationMaps"),
                (
                    args.data_3dva_root / "CentricityAndVisibilityMaps",
                    "datasets/3DVA/CentricityAndVisibilityMaps",
                ),
            ],
        ),
        (
            "3dva_combined_gt.zip",
            [(args.data_3dva_root / "CombinedGT", "datasets/3DVA/CombinedGT")],
        ),
        (
            "meshmamba_non_texture_objs.zip",
            [(args.data_meshmamba_root / "MeshFile/non_texture", "datasets/MeshMamba/MeshFile/non_texture")],
        ),
        (
            "meshmamba_rgb_texture_objs.zip",
            [(args.data_meshmamba_root / "MeshFile/rgb_texture", "datasets/MeshMamba/MeshFile/rgb_texture")],
        ),
        (
            "meshmamba_saliency_gt.zip",
            [(args.data_meshmamba_root / "SaliencyMap", "datasets/MeshMamba/SaliencyMap")],
        ),
        ("sal3d_meshes.zip", [(args.data_sal3d_root / "Meshes", "datasets/SAL3D/Meshes")]),
        ("sal3d_gaze_gt.zip", [(args.data_sal3d_root / "Gaze", "datasets/SAL3D/Gaze")]),
    ]
    if args.include_sal3d_smooth_gaze:
        specs.append(
            (
                "sal3d_smooth_gaze.zip",
                [(args.data_sal3d_root / "Smooth_Gaze", "datasets/SAL3D/Smooth_Gaze")],
            )
        )
    if args.include_videos:
        specs.append(("source_videos.zip", [(args.videos_root, "source_videos")]))

    if output_dir.exists() and args.force:
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    contract_report = output_dir / "data_contract_validation.json"
    subprocess.run(
        [
            "python3",
            str(repo / "scripts" / "validate_data_contract.py"),
            "--repo-root",
            str(repo),
            "--allow-known-blockers",
            "--output-json",
            str(contract_report),
        ],
        check=True,
    )
    manifest = {
        "schema_version": 1,
        "tag": args.tag,
        "created_unix": int(time.time()),
        "git_commit": git_commit(repo),
        "participant_data_contract": {
            "original_csv_archive": "participant_gaze_csv_original.zip",
            "processed_json_archive": "participant_fixations_processed_offset_2000.zip",
            "automatic_fallback_allowed": False,
        },
        "timing_contract": {
            "crop_start_seconds": 1.8,
            "crop_end_seconds": 0.2,
            "derive_full_turn_from_placement_json": True,
        },
        "data_contract_report": contract_report.name,
        "known_blockers": {
            "3DVA": {"invalid_processed": ["jessi"]},
            "SAL3D": {"missing_csv": ["gorgoile"], "missing_processed": ["gorgoile"]},
        },
        "archives": [],
    }
    for name, trees in specs:
        print(f"[build] {name}", flush=True)
        manifest["archives"].append(build_archive(output_dir / name, trees, args.force))

    manifest_path = output_dir / "release_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    checksum_lines = [f"{item['sha256']}  {item['name']}" for item in manifest["archives"]]
    (output_dir / "SHA256SUMS").write_text("\n".join(checksum_lines) + "\n")
    print(f"[done] {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
