from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
PATH = REPO_ROOT / "scripts" / "manifest_processed_fixations.py"
SPEC = importlib.util.spec_from_file_location("manifest_processed_fixations", PATH)
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def _write(root: Path, model: str, frames: int) -> None:
    path = root / model / "fixations.json"
    path.parent.mkdir(parents=True)
    path.write_text("[" + ",".join("[]" for _ in range(frames)) + "]")


def test_collect_records_hash_size_and_frames(tmp_path):
    _write(tmp_path, "3DVA_A380", 3)
    rows = MODULE.collect(tmp_path)
    assert len(rows) == 1
    assert rows[0]["relative_path"] == "3DVA_A380/fixations.json"
    assert rows[0]["frames"] == 3
    assert len(rows[0]["sha256"]) == 64
    assert rows[0]["bytes"] > 0


def test_collect_detects_non_list_json(tmp_path):
    path = tmp_path / "bad" / "fixations.json"
    path.parent.mkdir(parents=True)
    path.write_text("{}")
    with pytest.raises(ValueError, match="top-level JSON"):
        MODULE.collect(tmp_path)
