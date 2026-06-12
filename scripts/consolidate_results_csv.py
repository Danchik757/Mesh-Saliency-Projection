#!/usr/bin/env python3
"""Deduplicate and organize benchmark CSV artifacts into results/csv/.

The source may be a working copy containing historical and current benchmark
outputs. Files are classified from their relative path, copied while preserving
that path beneath a contract category, and indexed by SHA-256.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import shutil
from pathlib import Path


CATEGORIES = (
    "legacy",
    "rc2",
    "rc3_baseline",
    "rc3_timing_ablation",
    "rc3_sigma_sweep",
    "rc3_optimized",
    "diagnostics",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def classify(relative: Path) -> str:
    text = relative.as_posix().lower()
    if "optimized" in text or "opt_" in text:
        return "rc3_optimized"
    if "sigma_sweep" in text:
        return "rc3_sigma_sweep"
    if "ablation" in text or "cuthead" in text or "delay02" in text:
        return "rc3_timing_ablation"
    if "rc3_full_metrics" in text:
        return "rc3_baseline"
    if "rc2" in text:
        return "rc2"
    if any(token in text for token in ("diagnostic", "postprocess", "worst_", "preflight", "pilot")):
        return "diagnostics"
    return "legacy"


def contract_for(category: str) -> str:
    return {
        "rc2": "cropped_reset_offset_2000",
        "rc3_baseline": "one_turn_from_start; frame_offset=0; delay_seconds=0.0",
        "rc3_timing_ablation": "one_turn_from_start; timing/window/delay varies by file",
        "rc3_sigma_sweep": "one_turn_from_start; frame_offset=0; delay_seconds=0.0; sigma varies",
        "rc3_optimized": "one_turn_from_start; frame_offset=0; delay_seconds=0.0; optimized sigma",
        "diagnostics": "diagnostic/non-authoritative",
        "legacy": "legacy or pre-rc2; inspect source columns before comparison",
    }[category]


def is_authoritative(relative: Path, category: str) -> bool:
    name = relative.name.lower()
    if category == "rc3_baseline":
        return "summary_all_metrics" in name
    if category == "rc3_timing_ablation":
        return "all_metrics" in name or "comparison" in name
    if category == "rc3_sigma_sweep":
        return name in {"selected_sigmas_for_full_run.csv", "sigma_sweep_summary.csv"}
    if category == "rc3_optimized":
        return name in {"metrics_compact.csv", "metrics_long.csv"}
    return False


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-results", type=Path)
    parser.add_argument("--output-root", type=Path, default=Path("results/csv"))
    parser.add_argument("--clean", action="store_true")
    parser.add_argument(
        "--verify-only", action="store_true",
        help="Verify the existing output manifest and copied CSV files without writing.",
    )
    return parser.parse_args()


def verify_manifest(output: Path) -> None:
    manifest = output / "manifest.csv"
    if not manifest.is_file():
        raise FileNotFoundError(manifest)

    with manifest.open(newline="") as handle:
        rows = list(csv.DictReader(handle))

    expected: set[Path] = set()
    errors: list[str] = []
    for row in rows:
        relative_text = row["relative_path"]
        if not relative_text:
            continue
        relative = Path(relative_text)
        expected.add(relative)
        path = output / relative
        if not path.is_file():
            errors.append(f"missing:{relative.as_posix()}")
            continue
        actual_hash = sha256(path)
        if actual_hash != row["sha256"]:
            errors.append(f"sha256:{relative.as_posix()}")
        if path.stat().st_size != int(row["bytes"]):
            errors.append(f"bytes:{relative.as_posix()}")

    actual = {
        path.relative_to(output)
        for path in output.rglob("*.csv")
        if path != manifest
    }
    for relative in sorted(actual - expected):
        errors.append(f"untracked:{relative.as_posix()}")
    for relative in sorted(expected - actual):
        errors.append(f"not_found:{relative.as_posix()}")

    if errors:
        raise RuntimeError(f"results CSV verification failed: {errors[:20]}")
    print(f"[results] verified_csv={len(expected)} manifest={manifest}")


def main() -> int:
    args = parse_args()
    output = args.output_root.resolve()
    if args.verify_only:
        verify_manifest(output)
        return 0
    if args.source_results is None:
        raise ValueError("--source-results is required unless --verify-only is used")
    source = args.source_results.resolve()
    if not source.is_dir():
        raise FileNotFoundError(source)
    if args.clean and output.exists():
        for category in CATEGORIES:
            shutil.rmtree(output / category, ignore_errors=True)
        (output / "manifest.csv").unlink(missing_ok=True)
    for category in CATEGORIES:
        (output / category).mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, str | int]] = []
    seen: dict[str, Path] = {}
    for path in sorted(source.rglob("*.csv")):
        if output == path or output in path.parents:
            continue
        relative = path.relative_to(source)
        digest = sha256(path)
        if digest in seen:
            rows.append({
                "category": classify(relative),
                "relative_path": "",
                "source_relative_path": relative.as_posix(),
                "sha256": digest,
                "bytes": path.stat().st_size,
                "authoritative": "false",
                "run_contract": "duplicate",
                "duplicate_of": seen[digest].as_posix(),
                "notes": "Identical CSV omitted from tracked results/csv tree.",
            })
            continue

        category = classify(relative)
        destination_relative = Path(category) / relative
        destination = output / destination_relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destination)
        seen[digest] = destination_relative
        rows.append({
            "category": category,
            "relative_path": destination_relative.as_posix(),
            "source_relative_path": relative.as_posix(),
            "sha256": digest,
            "bytes": path.stat().st_size,
            "authoritative": str(is_authoritative(relative, category)).lower(),
            "run_contract": contract_for(category),
            "duplicate_of": "",
            "notes": "",
        })

    fields = [
        "category", "relative_path", "source_relative_path", "sha256", "bytes",
        "authoritative", "run_contract", "duplicate_of", "notes",
    ]
    manifest = output / "manifest.csv"
    with manifest.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    unique = sum(not row["duplicate_of"] for row in rows)
    duplicates = len(rows) - unique
    print(f"[results] source_csv={len(rows)} unique={unique} duplicates={duplicates}")
    print(f"[results] manifest={manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
