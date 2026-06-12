#!/usr/bin/env python3
"""Create or verify the canonical processed-fixation file manifest."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path


FIELDS = ("relative_path", "sha256", "bytes", "frames")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def collect(root: Path) -> list[dict[str, str | int]]:
    rows: list[dict[str, str | int]] = []
    for path in sorted(root.glob("*/fixations.json")):
        frames = json.loads(path.read_text())
        if not isinstance(frames, list):
            raise ValueError(f"{path}: top-level JSON must be a list")
        rows.append({
            "relative_path": path.relative_to(root).as_posix(),
            "sha256": sha256(path),
            "bytes": path.stat().st_size,
            "frames": len(frames),
        })
    return rows


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--compare-root", type=Path)
    parser.add_argument("--expected-count", type=int, default=298)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = args.root.resolve()
    rows = collect(root)
    if len(rows) != args.expected_count:
        raise RuntimeError(f"{root}: found {len(rows)} fixation files, expected {args.expected_count}")

    if args.compare_root is not None:
        other = collect(args.compare_root.resolve())
        if rows != other:
            by_path = {row["relative_path"]: row for row in other}
            mismatches = [
                row["relative_path"] for row in rows
                if by_path.get(row["relative_path"]) != row
            ]
            raise RuntimeError(f"fixation roots differ: {mismatches[:10]}")

    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows(rows)

    print(f"[fixations] files={len(rows)} root={root}")
    if args.compare_root is not None:
        print(f"[fixations] byte-identical to {args.compare_root.resolve()}")
    if args.output is not None:
        print(f"[fixations] manifest={args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
