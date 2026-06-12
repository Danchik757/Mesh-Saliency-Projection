#!/usr/bin/env python3
"""Build a versioned benchmark-data release candidate with an explicit manifest.

Targets schema_version=2 and the offset0 / one_turn_from_start contract
(default tag: v2.0-data-rc4).  The participant payload is the full cleaned
offset0 fixation JSON set (298 files); SAL3D ships repaired per-face GT and the
full Smooth Gaze neighbour archive.

This builder intentionally has NO offset_2000 / cropped_reset / rc1 defaults.
The legacy offset_2000 builder is recoverable from git history if ever needed.

Dry run
-------
  python3 scripts/build_release_candidate.py --dry-run
prints the planned archive list and the manifest metadata (schema_version,
based_on, timing/participant contracts) WITHOUT reading source data, zipping,
or running the data-contract validator.  Use it to review the release plan and
in CI as a fast smoke check.
"""

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

# ── release contract constants (schema v2 / offset0 / one_turn_from_start) ──────

SCHEMA_VERSION = 2
DEFAULT_TAG = "v2.0-data-rc4"

FIXATION_ARCHIVE = "participant_fixations_offset0_full_cleaned.zip"
FIXATION_ROOT = "participant_fixations_offset0_full_cleaned"  # archive root inside the zip
# Canonical TRACKED source directory under participant_data/ (note: the source dir
# name differs from the archive root name).
FIXATION_SOURCE_DIRNAME = "processed_fixations_offset0_full_cleaned"
FIXATION_DATA_TAG = "processed_fixations_offset0_full_cleaned"
FIXATION_FORMAT = "one_turn_from_start_offset_0"

EXPECTED_FIXATION_COUNT = 298

# Inputs tracked in the repo vs supplied externally (large GAZE_DATA assets).
TRACKED_INPUTS = (
    "participant_data/collected_gaze_csv_by_model/",
    f"participant_data/{FIXATION_SOURCE_DIRNAME}/",
    "jsons/object_placement/",
)
EXTERNAL_INPUTS = (
    "3DVA / MeshMamba / SAL3D meshes + GT (GAZE_DATA/datasets/...)",
    "SAL3D fixed per-face GT package (sal3d_benchmark_pkg)",
    "SAL3D Smooth_Gaze neighbour archive",
    "source videos (optional, --include-videos)",
)


def parse_args() -> argparse.Namespace:
    repo = Path(__file__).resolve().parents[1]
    saliency_root = repo.parents[2]
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo-root", type=Path, default=repo)
    parser.add_argument("--output-dir", type=Path, default=None,
                        help="Defaults to <repo>/release_assets/<tag>.")
    parser.add_argument("--tag", default=DEFAULT_TAG)
    parser.add_argument(
        "--fixation-source", type=Path, default=None,
        help=("Directory holding the 298 offset0 fixation JSONs "
              "(<model>/fixations.json). Defaults to the tracked source "
              f"<repo>/participant_data/{FIXATION_SOURCE_DIRNAME}."),
    )
    parser.add_argument("--data-3dva-root", type=Path,
                        default=saliency_root / "GAZE_DATA/datasets/3DVA")
    parser.add_argument(
        "--data-meshmamba-root", type=Path,
        default=saliency_root / "GAZE_DATA/datasets/MeshMamba/MeshMambaSaliency",
    )
    parser.add_argument(
        "--data-sal3d-root", type=Path,
        default=saliency_root / "GAZE_DATA/datasets/SAL3D/SAL3D_Dataset",
    )
    parser.add_argument(
        "--data-sal3d-fixed-root", type=Path,
        default=saliency_root / "GAZE_DATA/datasets/SAL3D_fixed/sal3d_benchmark_pkg",
        help="Root of the SAL3D fixed per-face GT package (Meshes/ + *_faces.txt + manifest).",
    )
    parser.add_argument("--videos-root", type=Path, default=saliency_root / "videos")
    parser.add_argument("--include-videos", action="store_true")
    parser.add_argument(
        "--no-sal3d-smooth-gaze", dest="include_sal3d_smooth_gaze",
        action="store_false",
        help="Exclude the full SAL3D Smooth Gaze archive (included by default in rc4).",
    )
    parser.set_defaults(include_sal3d_smooth_gaze=True)
    parser.add_argument("--dry-run", action="store_true",
                        help="Print the release plan + manifest metadata; build nothing.")
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
        if archive_root == "object_placement_json_canonical" and path.suffix.lower() != ".json":
            continue
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


def build_specs(args: argparse.Namespace) -> list[tuple[str, list[tuple[Path, str]]]]:
    """Archive (name, [(source, archive_root), ...]) plan for the offset0 release."""
    repo = args.repo_root.resolve()
    participant = repo / "participant_data"
    placement = repo / "jsons" / "object_placement"
    fixation_source = (
        args.fixation_source
        if args.fixation_source is not None
        else participant / FIXATION_SOURCE_DIRNAME
    )

    specs: list[tuple[str, list[tuple[Path, str]]]] = [
        (
            "participant_gaze_csv_original.zip",
            [(participant / "collected_gaze_csv_by_model", "participant_gaze_csv_original")],
        ),
        (
            FIXATION_ARCHIVE,
            [(fixation_source, FIXATION_ROOT)],
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
                (args.data_3dva_root / "CentricityAndVisibilityMaps",
                 "datasets/3DVA/CentricityAndVisibilityMaps"),
            ],
        ),
        ("3dva_combined_gt.zip", [(args.data_3dva_root / "CombinedGT", "datasets/3DVA/CombinedGT")]),
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
        (
            "sal3d_fixed_face_gt.zip",
            [(args.data_sal3d_fixed_root, "datasets/SAL3D_fixed/sal3d_benchmark_pkg")],
        ),
    ]
    if args.include_sal3d_smooth_gaze:
        specs.append(
            ("sal3d_smooth_gaze.zip",
             [(args.data_sal3d_root / "Smooth_Gaze", "datasets/SAL3D/Smooth_Gaze")])
        )
    if args.include_videos:
        specs.append(("source_videos.zip", [(args.videos_root, "source_videos")]))
    return specs


def build_manifest_metadata(tag: str, commit: str,
                            *, include_smooth_gaze: bool = True) -> dict:
    """Static manifest metadata for the offset0 / one_turn_from_start release.

    Archives are appended by main(); everything else (schema, contracts, based_on)
    is fixed here so it can be unit-tested without building anything.
    """
    return {
        "schema_version": SCHEMA_VERSION,
        "tag": tag,
        "created_unix": int(time.time()),
        "git_commit": commit,
        "based_on": (
            "v2.0-data-rc1 mesh and GT assets with participant fixations regenerated "
            "as full cleaned offset0 one_turn_from_start JSON (298 files), SAL3D "
            "repaired per-face GT added, and full SAL3D Smooth Gaze included"
        ),
        "participant_data_contract": {
            "original_csv_archive": "participant_gaze_csv_original.zip",
            "processed_json_archive": FIXATION_ARCHIVE,
            "fixation_data_tag": FIXATION_DATA_TAG,
            "fixation_format": FIXATION_FORMAT,
            "source_directory_name": "mesh_json__offset_0",
            "automatic_fallback_allowed": False,
            "expected_file_count": EXPECTED_FIXATION_COUNT,
            "usable_lengths": {
                "17s_tracks_full_json_frames": 510,
                "24s_sal3d_full_json_frames": 720,
                "excluded_invalid": ["3DVA_jessi"],
            },
        },
        "timing_contract": {
            "name": "one_turn_from_start",
            "crop_start_seconds": 0.0,
            "crop_end_seconds": 0.0,
            "delay_seconds_default": 0.0,
            "derive_full_turn_from_placement_json": True,
            "pairing": (
                "gaze[k] -> placement[k] for one full object rotation; "
                "extra trailing frames are ignored"
            ),
            "turn_frames": {"3DVA": 450, "MeshMamba": 450, "SAL3D": 660},
        },
        "sal3d_contract": {
            "fixed_face_gt_archive": "sal3d_fixed_face_gt.zip",
            "raw_gaze_archive": "sal3d_gaze_gt.zip",
            "smooth_gaze_archive": "sal3d_smooth_gaze.zip" if include_smooth_gaze else None,
            "gt_domain": "face",
            "use_for_metrics": True,
        },
        "known_blockers": {
            "3DVA": {"invalid_processed": ["jessi"],
                     "reason": "only 41 fixation frames in full processed JSON"},
            "SAL3D": {"missing_processed": ["gorgoile"], "fixed_face_gt_available": True},
        },
        "data_contract_report": "data_contract_validation.json",
        "archives": [],
    }


def fixation_source_dir(args: argparse.Namespace) -> Path:
    if args.fixation_source is not None:
        return Path(args.fixation_source)
    return args.repo_root.resolve() / "participant_data" / FIXATION_SOURCE_DIRNAME


def count_fixation_jsons(source: Path) -> int:
    if not source.is_dir():
        return 0
    return sum(1 for _ in source.glob("*/fixations.json"))


def strict_preflight(args: argparse.Namespace, specs) -> list[str]:
    """Return a list of preflight problems (empty == ready to build).

    A missing required source or a fixation count != 298 is a hard problem; the
    caller must treat a non-empty result as a nonzero exit, never build-and-warn.
    """
    problems: list[str] = []
    seen: set[str] = set()
    for name, trees in specs:
        for source, _root in trees:
            key = str(source)
            if key in seen:
                continue
            seen.add(key)
            if not Path(source).exists():
                problems.append(f"missing source for {name}: {source}")
    src = fixation_source_dir(args)
    n = count_fixation_jsons(src)
    if n != EXPECTED_FIXATION_COUNT:
        problems.append(
            f"fixation source {src} has {n} fixations.json, expected {EXPECTED_FIXATION_COUNT}"
        )
    return problems


def _print_dry_run(args: argparse.Namespace, specs, manifest: dict) -> None:
    print(f"[dry-run] tag={args.tag}  schema_version={SCHEMA_VERSION}")
    print(f"[dry-run] output-dir={args.output_dir}")
    print(f"[dry-run] fixation archive: {FIXATION_ARCHIVE} (expect {EXPECTED_FIXATION_COUNT} JSON)")
    print(f"[dry-run] timing_contract={manifest['timing_contract']['name']} "
          f"crop=({manifest['timing_contract']['crop_start_seconds']},"
          f"{manifest['timing_contract']['crop_end_seconds']}) "
          f"delay={manifest['timing_contract']['delay_seconds_default']}")
    print(f"[dry-run] based_on: {manifest['based_on']}")
    print(f"[dry-run] planned archives ({len(specs)}):")
    for name, trees in specs:
        for source, root in trees:
            exists = "ok" if Path(source).exists() else "MISSING"
            print(f"    {name:42s} <- {source}  [{exists}] -> {root}/")
    print("[dry-run] tracked inputs:")
    for t in TRACKED_INPUTS:
        print(f"    {t}")
    print("[dry-run] externally-supplied inputs:")
    for e in EXTERNAL_INPUTS:
        print(f"    {e}")
    print("[dry-run] manifest metadata:")
    print(json.dumps({k: v for k, v in manifest.items() if k != "archives"},
                     indent=2, sort_keys=True))
    print("[dry-run] no archives written.")


def main() -> int:
    args = parse_args()
    repo = args.repo_root.resolve()
    if args.output_dir is None:
        args.output_dir = repo / "release_assets" / args.tag
    output_dir = args.output_dir.resolve()

    try:
        commit = git_commit(repo)
    except Exception:
        commit = "unknown"

    specs = build_specs(args)
    manifest = build_manifest_metadata(
        args.tag, commit, include_smooth_gaze=args.include_sal3d_smooth_gaze
    )

    problems = strict_preflight(args, specs)

    if args.dry_run:
        _print_dry_run(args, specs, manifest)
        if problems:
            print("[preflight] STRICT FAIL — would refuse to build:")
            for p in problems:
                print(f"    - {p}")
            return 3
        print("[preflight] OK — all sources present and exactly "
              f"{EXPECTED_FIXATION_COUNT} fixation JSON.")
        return 0

    # Real build: strict preflight gates everything.
    if problems:
        print("[preflight] STRICT FAIL — refusing to build:", file=sys.stderr)
        for p in problems:
            print(f"    - {p}", file=sys.stderr)
        return 3

    require_clean_tree(repo)

    if output_dir.exists() and args.force:
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # rc4-compatible data-contract validation against the offset0 source.
    contract_report = output_dir / "data_contract_validation.json"
    subprocess.run(
        [
            "python3", str(repo / "scripts" / "validate_data_contract.py"),
            "--repo-root", str(repo),
            "--processed-root", str(fixation_source_dir(args)),
            "--timing-contract", "one_turn_from_start",
            "--allow-known-blockers",
            "--output-json", str(contract_report),
        ],
        check=True,
    )

    for name, trees in specs:
        print(f"[build] {name}", flush=True)
        manifest["archives"].append(build_archive(output_dir / name, trees, args.force))

    manifest_path = output_dir / "release_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    checksum_lines = [f"{item['sha256']}  {item['name']}" for item in manifest["archives"]]
    (output_dir / "SHA256SUMS").write_text("\n".join(checksum_lines) + "\n")

    # Validate the freshly-written release; a failure fails the build.
    print("[validate] running validate_release_candidate.py ...", flush=True)
    vr = subprocess.run(
        ["python3", str(repo / "scripts" / "validate_release_candidate.py"), str(output_dir)],
    )
    if vr.returncode != 0:
        raise RuntimeError(
            f"release validation failed for {output_dir} (exit {vr.returncode})"
        )
    print(f"[done] {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
