#!/usr/bin/env python3
"""Compatibility wrapper for the dedicated KLD sweep benchmark package."""

from __future__ import annotations

import runpy
from pathlib import Path


TARGET = Path(__file__).resolve().parents[1] / "kld_parameter_sweep" / "run_kld_parameter_sweep.py"
runpy.run_path(str(TARGET), run_name="__main__")
