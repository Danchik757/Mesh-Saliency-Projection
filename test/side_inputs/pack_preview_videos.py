#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import tarfile
from pathlib import Path


def expand_path(raw: str | None) -> Path | None:
    if raw is None:
        return None
    expanded = os.path.expandvars(os.path.expanduser(raw))
    if "$" in expanded:
        raise ValueError(f"Unresolved environment variable in path: {raw}")
    return Path(expanded)


def main() -> None:
    parser = argparse.ArgumentParser(description="Pack preview source videos referenced by manifests into one tar.gz archive.")
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, nargs="+", required=True)
    args = parser.parse_args()

    items: list[tuple[Path, str]] = []
    for manifest_path in args.manifest:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        video_path = expand_path(payload.get("video_path"))
        if video_path is None:
            continue
        if not video_path.exists():
            raise FileNotFoundError(f"Missing video for manifest {manifest_path}: {video_path}")
        dataset = str(payload.get("dataset", "unknown"))
        arcname = f"{dataset}/{video_path.name}"
        items.append((video_path, arcname))

    args.archive.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(args.archive, "w:gz") as tar:
        for src_path, arcname in items:
            tar.add(src_path, arcname=arcname)

    summary = {
        "archive": str(args.archive),
        "count": len(items),
        "files": [{"src": str(src), "arcname": arc} for src, arc in items],
    }
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
