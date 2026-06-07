#!/usr/bin/env python3
"""
Compatibility wrapper.

Canonical path:
  gt_visualizations/preview_meshmamba_cone_alignment.py
"""

from __future__ import annotations

import runpy
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "gt_visualizations"
    / "preview_meshmamba_cone_alignment.py"
)


if __name__ == "__main__":
    runpy.run_path(str(SCRIPT_PATH), run_name="__main__")
