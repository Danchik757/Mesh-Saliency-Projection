#!/usr/bin/env python3
"""Validate release candidate manifest, checksums, CRCs, and data-type separation.

Targets v2.0-data-rc3 (schema_version=2).  RC3-ONLY validator.

Required manifest fields (rc3):
  schema_version                                    == 2
  timing_contract.name                              == "one_turn_from_start"
  timing_contract.delay_seconds_default             == 0.0
  timing_contract.crop_start_seconds                == 0.0
  timing_contract.crop_end_seconds                  == 0.0
  participant_data_contract.processed_json_archive  == participant_fixations_offset0_full_cleaned.zip
  participant_data_contract.automatic_fallback_allowed == False

RC1/RC2 INCOMPATIBILITY: this script will explicitly fail when run against rc1 or rc2
release directories.  Typical rc1/rc2 failure messages:
  - "schema_version must be 2, got 1" (rc1)
  - "timing_contract.name must be 'one_turn_from_start'"
  - "participant_data_contract.processed_json_archive must be 'participant_fixations_offset0_full_cleaned.zip'"
Use git history to recover the pre-rc3 version if rc1/rc2 validation is needed.

Fixation archive frame counts (verified at validation time):
  510 frames: 3DVA and MeshMamba models
  720 frames: SAL3D models
   41 frames: 3DVA_jessi (known blocker, excluded in manifest known_blockers)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from pathlib import Path


EXPECTED_PARTICIPANT_COUNTS = {
    "participant_gaze_csv_original.zip": 298,
    "participant_fixations_offset0_full_cleaned.zip": 298,
}
EXPECTED_ARCHIVE_COUNTS = {
    **EXPECTED_PARTICIPANT_COUNTS,
    "object_placement_json_canonical.zip": 299,
    "3dva_objs_corrected.zip": 32,
    "sal3d_fixed_face_gt.zip": 114,
}
EXPECTED_ARCHIVE_ROOTS = {
    "participant_gaze_csv_original.zip": "participant_gaze_csv_original/",
    "participant_fixations_offset0_full_cleaned.zip": "participant_fixations_offset0_full_cleaned/",
    "object_placement_json_canonical.zip": "object_placement_json_canonical/",
    "3dva_objs_corrected.zip": "datasets/3DVA/3DModels-Simplif-up/",
}
REQUIRED_ARCHIVES = {
    "participant_gaze_csv_original.zip",
    "participant_fixations_offset0_full_cleaned.zip",
    "object_placement_json_canonical.zip",
    "3dva_objs_corrected.zip",
    "3dva_gt.zip",
    "3dva_combined_gt.zip",
    "meshmamba_non_texture_objs.zip",
    "meshmamba_rgb_texture_objs.zip",
    "meshmamba_saliency_gt.zip",
    "sal3d_meshes.zip",
    "sal3d_gaze_gt.zip",
    "sal3d_fixed_face_gt.zip",
}

_FIXATION_ARCHIVE = "participant_fixations_offset0_full_cleaned.zip"
_FIXATION_ROOT = "participant_fixations_offset0_full_cleaned/"
_JESSI_MEMBER = f"{_FIXATION_ROOT}3DVA_jessi/fixations.json"
_EXPECTED_JESSI_FRAMES = 41
_VALID_FRAME_LENGTHS: frozenset[int] = frozenset({510, 720, _EXPECTED_JESSI_FRAMES})


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


def _check_fixation_frame_counts(path: Path, members: set[str], errors: list[str]) -> None:
    """Verify per-file frame counts inside the offset0 fixation archive."""
    bad_lengths: list[str] = []
    jessi_found = False
    with zipfile.ZipFile(path) as archive:
        for member in sorted(members):
            raw = archive.read(member)
            try:
                frames = json.loads(raw)
            except json.JSONDecodeError:
                errors.append(f"invalid JSON in fixation archive: {member}")
                continue
            if not isinstance(frames, list):
                errors.append(f"fixation file is not a list: {member}")
                continue
            n = len(frames)
            if member == _JESSI_MEMBER:
                jessi_found = True
                if n != _EXPECTED_JESSI_FRAMES:
                    errors.append(
                        f"3DVA_jessi frame count: expected {_EXPECTED_JESSI_FRAMES}, got {n}"
                    )
            elif n not in _VALID_FRAME_LENGTHS:
                bad_lengths.append(f"{member}:{n}")
    if not jessi_found:
        errors.append(f"3DVA_jessi/fixations.json not found in {_FIXATION_ARCHIVE}")
    if bad_lengths:
        shown = bad_lengths[:5]
        suffix = f" ... (+{len(bad_lengths) - 5} more)" if len(bad_lengths) > 5 else ""
        errors.append(f"unexpected frame counts in fixation archive: {shown}{suffix}")


def main() -> int:
    args = parse_args()
    root = args.candidate_dir.resolve()
    for required_file in ("release_manifest.json", "SHA256SUMS", "data_contract_validation.json"):
        if not (root / required_file).is_file():
            raise FileNotFoundError(root / required_file)
    manifest = json.loads((root / "release_manifest.json").read_text())
    contract_report = json.loads((root / "data_contract_validation.json").read_text())
    errors: list[str] = []

    schema_version = manifest.get("schema_version")
    if schema_version != 2:
        errors.append(f"schema_version must be 2, got {schema_version!r}")

    archives = {item["name"]: item for item in manifest["archives"]}
    missing = sorted(REQUIRED_ARCHIVES - set(archives))
    if missing:
        errors.append(f"missing required archives: {missing}")

    csv_members: set[str] = set()
    fixation_members: set[str] = set()
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
        if name == _FIXATION_ARCHIVE:
            fixation_members = members
            if any(not member.endswith("/fixations.json") for member in members):
                errors.append("processed fixation archive contains unexpected files")
            _check_fixation_frame_counts(path, members, errors)

    if not csv_members:
        errors.append("original CSV participant archive is empty")
    if not fixation_members:
        errors.append("processed fixation participant archive is empty")

    contract = manifest.get("participant_data_contract", {})
    if contract.get("automatic_fallback_allowed") is not False:
        errors.append("participant data contract must disable automatic fallback")
    if contract.get("processed_json_archive") != _FIXATION_ARCHIVE:
        errors.append(
            f"participant_data_contract.processed_json_archive must be {_FIXATION_ARCHIVE!r}"
        )

    timing = manifest.get("timing_contract", {})
    if timing.get("name") != "one_turn_from_start":
        errors.append("timing_contract.name must be 'one_turn_from_start'")
    if timing.get("delay_seconds_default") != 0.0:
        errors.append("timing_contract.delay_seconds_default must be 0.0")
    if timing.get("crop_start_seconds") != 0.0:
        errors.append("timing_contract.crop_start_seconds must be 0.0")
    if timing.get("crop_end_seconds") != 0.0:
        errors.append("timing_contract.crop_end_seconds must be 0.0")

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
