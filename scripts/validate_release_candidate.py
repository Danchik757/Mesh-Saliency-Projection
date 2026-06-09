#!/usr/bin/env python3
"""Validate release candidate manifest, checksums, CRCs, and data-type separation."""

from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from pathlib import Path


EXPECTED_PARTICIPANT_COUNTS = {
    "participant_gaze_csv_original.zip": 298,
    "participant_fixations_processed_offset_2000.zip": 298,
}
EXPECTED_ARCHIVE_COUNTS = {
    **EXPECTED_PARTICIPANT_COUNTS,
    "object_placement_json_canonical.zip": 299,
    "3dva_objs_corrected.zip": 32,
}
EXPECTED_ARCHIVE_ROOTS = {
    "participant_gaze_csv_original.zip": "participant_gaze_csv_original/",
    "participant_fixations_processed_offset_2000.zip": "participant_fixations_processed_offset_2000/",
    "object_placement_json_canonical.zip": "object_placement_json_canonical/",
    "3dva_objs_corrected.zip": "datasets/3DVA/3DModels-Simplif-up/",
}
REQUIRED_ARCHIVES = {
    "participant_gaze_csv_original.zip",
    "participant_fixations_processed_offset_2000.zip",
    "object_placement_json_canonical.zip",
    "3dva_objs_corrected.zip",
    "3dva_gt.zip",
    "3dva_combined_gt.zip",
    "meshmamba_non_texture_objs.zip",
    "meshmamba_rgb_texture_objs.zip",
    "meshmamba_saliency_gt.zip",
    "sal3d_meshes.zip",
    "sal3d_gaze_gt.zip",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("candidate_dir", type=Path)
    parser.add_argument("--output-json", type=Path)
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    args = parse_args()
    root = args.candidate_dir.resolve()
    for required_file in ("release_manifest.json", "SHA256SUMS", "data_contract_validation.json"):
        if not (root / required_file).is_file():
            raise FileNotFoundError(root / required_file)
    manifest = json.loads((root / "release_manifest.json").read_text())
    contract_report = json.loads((root / "data_contract_validation.json").read_text())
    errors: list[str] = []
    archives = {item["name"]: item for item in manifest["archives"]}
    missing = sorted(REQUIRED_ARCHIVES - set(archives))
    if missing:
        errors.append(f"missing required archives: {missing}")

    csv_members: set[str] = set()
    processed_members: set[str] = set()
    for name, item in archives.items():
        path = root / name
        if not path.is_file():
            errors.append(f"archive missing on disk: {name}")
            continue
        actual_hash = sha256(path)
        if actual_hash != item["sha256"]:
            errors.append(f"SHA-256 mismatch: {name}")
        with zipfile.ZipFile(path) as archive:
            bad_member = archive.testzip()
            members = {member for member in archive.namelist() if not member.endswith("/")}
        if bad_member:
            errors.append(f"CRC failure: {name}:{bad_member}")
        if len(members) != item["file_count"]:
            errors.append(f"file count mismatch: {name}")
        if name in EXPECTED_ARCHIVE_COUNTS and len(members) != EXPECTED_ARCHIVE_COUNTS[name]:
            errors.append(
                f"file count mismatch: {name} has {len(members)}, "
                f"expected {EXPECTED_ARCHIVE_COUNTS[name]}"
            )
        expected_root = EXPECTED_ARCHIVE_ROOTS.get(name)
        if expected_root and any(not member.startswith(expected_root) for member in members):
            errors.append(f"archive contains files outside expected root: {name}")
        if name == "participant_gaze_csv_original.zip":
            csv_members = members
            if any(not member.lower().endswith(".csv") for member in members):
                errors.append("original gaze archive contains non-CSV files")
        if name == "participant_fixations_processed_offset_2000.zip":
            processed_members = members
            if any(not member.endswith("/fixations.json") for member in members):
                errors.append("processed fixation archive contains unexpected files")

    if not csv_members:
        errors.append("original CSV participant archive is empty")
    if not processed_members:
        errors.append("processed fixation participant archive is empty")
    contract = manifest.get("participant_data_contract", {})
    if contract.get("automatic_fallback_allowed") is not False:
        errors.append("participant data contract must disable automatic fallback")
    timing = manifest.get("timing_contract", {})
    if timing.get("crop_start_seconds") != 1.8 or timing.get("crop_end_seconds") != 0.2:
        errors.append("timing contract must use the approved 1.8s/0.2s crop")
    if timing.get("derive_full_turn_from_placement_json") is not True:
        errors.append("timing contract must derive full turn from placement JSON")
    if contract_report.get("errors"):
        errors.append("embedded data-contract report contains errors")

    checksum_entries = {}
    for line in (root / "SHA256SUMS").read_text().splitlines():
        digest, separator, name = line.partition("  ")
        if not separator:
            errors.append(f"invalid SHA256SUMS line: {line!r}")
            continue
        checksum_entries[name] = digest
    if set(checksum_entries) != set(archives):
        errors.append("SHA256SUMS archive inventory differs from manifest")
    for name, item in archives.items():
        if checksum_entries.get(name) != item.get("sha256"):
            errors.append(f"SHA256SUMS differs from manifest: {name}")

    result = {
        "candidate_dir": str(root),
        "tag": manifest.get("tag"),
        "archive_count": len(archives),
        "errors": errors,
        "status": "ok" if not errors else "failed",
    }
    if args.output_json:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    return int(bool(errors))


if __name__ == "__main__":
    raise SystemExit(main())
