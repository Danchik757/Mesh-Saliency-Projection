#!/usr/bin/env python3
"""
Build per-model combined GT for the 3DVA dataset.

The 3DVA dataset provides 3 independent fixation maps per model (views 300, 413, 599),
each from a different static camera position covering a different side of the mesh.
This script merges them into a single combined GT per model via visibility-weighted
averaging after per-view L1 normalization.

Normalization strategy (per_view_l1, default):
  1. For each view k, normalize GT to sum=1 over visible vertices:
       gt_norm_k[v] = gt_k[v] / sum(gt_k[vis_k])
  2. Combine via visibility-weighted mean:
       combined[v] = sum(gt_norm_k[v] * vis_k[v]) / sum(vis_k[v])

Effect:
  - Each view contributes equal total "attention mass" regardless of how many
    vertices are visible from it.
  - Vertex visible from all 3 views: mean of 3 normalized values.
  - Vertex visible from 1 view only: that view's normalized value.
  - Vertex never visible from any view: 0.0.

Output per model:
  {output-dir}/{model}_combined_gt.txt      — one float per line, N_vertices lines
  {output-dir}/{model}_combined_gt_meta.json — stats (coverage, GT sums, etc.)
  {output-dir}/build_summary.json            — one entry per model

Edge cases:
  - turbine: OBJ has 20000 verts but GT has 19999 lines. Script warns and uses
    the GT line count (not OBJ), so the combined GT is 19999 lines.
  - Any view whose visibility file is missing is skipped with a warning.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np


VIEWS = ("300", "413", "599")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build per-model combined GT for the 3DVA dataset."
    )
    parser.add_argument(
        "--dataset-root",
        type=Path,
        default=Path(os.environ.get(
            "VISUAL_ATTENTION_3D_SHAPES_ROOT",
            "e.g. /path/to/3DVA",
        )),
        help=(
            "Root of the 3DVA dataset. Must contain:\n"
            "  FixationMaps/            — GT TXT files (*_300norm.txt etc.)\n"
            "  CentricityAndVisibilityMaps/ — visibility TXT files (*_300_visibility.txt etc.)"
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Where to write combined GT files. Default: {dataset-root}/CombinedGT/",
    )
    parser.add_argument(
        "--views",
        nargs="+",
        default=list(VIEWS),
        help=f"Views to combine (default: {' '.join(VIEWS)})",
    )
    parser.add_argument(
        "--normalization",
        choices=["per_view_l1", "per_view_max", "none"],
        default="per_view_l1",
        help=(
            "Normalization applied to each view's GT before combining.\n"
            "  per_view_l1: divide by sum of visible-vertex values (recommended)\n"
            "  per_view_max: divide by max value\n"
            "  none: use raw GT values"
        ),
    )
    parser.add_argument(
        "--models",
        nargs="*",
        default=None,
        help="Optional model subset (e.g. bunny A380). Default: auto-discover from FixationMaps/.",
    )
    return parser.parse_args()


def _discover_models(fixation_dir: Path, views: list[str]) -> list[str]:
    """Discover model names from FixationMaps — models that have GT for ALL requested views."""
    # Collect stems grouped by model name
    per_model: dict[str, set[str]] = {}
    for txt_file in sorted(fixation_dir.glob("*.txt")):
        stem = txt_file.stem  # e.g. "bunny_300norm"
        for view in views:
            suffix = f"_{view}norm"
            if stem.endswith(suffix):
                model = stem[: -len(suffix)]
                per_model.setdefault(model, set()).add(view)
                break

    # Keep only models that have ALL requested views
    required = set(views)
    return sorted(m for m, found in per_model.items() if required.issubset(found))


def _load_gt(fixation_dir: Path, model: str, view: str) -> np.ndarray | None:
    candidates = [
        fixation_dir / f"{model}_{view}norm.txt",
        fixation_dir / f"{model.lower()}_{view}norm.txt",
    ]
    for path in candidates:
        if path.is_file():
            return np.loadtxt(str(path), dtype=np.float64)
    return None


def _load_visibility(vis_dir: Path, model: str, view: str) -> np.ndarray | None:
    candidates = [
        vis_dir / f"{model}_{view}_visibility.txt",
        vis_dir / f"{model.lower()}_{view}_visibility.txt",
    ]
    for path in candidates:
        if path.is_file():
            return np.loadtxt(str(path), dtype=np.float64).astype(bool)
    return None


def _normalize_gt(gt: np.ndarray, vis: np.ndarray, mode: str) -> np.ndarray:
    """Normalize GT values according to the chosen strategy."""
    gt_norm = gt.copy()
    if mode == "per_view_l1":
        visible_sum = float(gt[vis].sum())
        if visible_sum > 0:
            gt_norm = gt / visible_sum
    elif mode == "per_view_max":
        gt_max = float(gt.max())
        if gt_max > 0:
            gt_norm = gt / gt_max
    # mode "none": return as-is
    return gt_norm


def build_combined_gt(
    model: str,
    fixation_dir: Path,
    vis_dir: Path,
    views: list[str],
    normalization: str,
) -> tuple[np.ndarray, dict] | None:
    """
    Build combined GT for one model.

    Returns (combined_gt_array, meta_dict) or None on failure.
    combined_gt_array has shape (N,) where N is the GT vertex count.
    """
    # Validate that all views have the same vertex count
    n_verts: int | None = None
    gt_arrays: dict[str, np.ndarray] = {}
    vis_arrays: dict[str, np.ndarray] = {}
    warnings: list[str] = []

    for view in views:
        gt = _load_gt(fixation_dir, model, view)
        if gt is None:
            warnings.append(f"GT file not found for view {view} — skipping this view")
            continue
        vis = _load_visibility(vis_dir, model, view)
        if vis is None:
            warnings.append(f"Visibility file not found for view {view} — skipping this view")
            continue

        if n_verts is None:
            n_verts = len(gt)
        elif len(gt) != n_verts:
            warnings.append(
                f"view {view} GT length {len(gt)} != expected {n_verts} — skipping this view"
            )
            continue
        if len(vis) != n_verts:
            # Tolerance: accept off-by-one differences (e.g. turbine OBJ=20000, GT=19999).
            # Truncate visibility to GT length so both arrays align.
            if abs(len(vis) - n_verts) <= 5:
                original_vis_len = len(vis)
                vis = vis[:n_verts]
                warnings.append(
                    f"view {view} visibility length {original_vis_len} "
                    f"truncated to {n_verts} to match GT length"
                )
            else:
                warnings.append(
                    f"view {view} visibility length {len(vis)} != {n_verts} — skipping this view"
                )
                continue

        gt_arrays[view]  = gt
        vis_arrays[view] = vis

    if not gt_arrays:
        print(f"[ERROR] {model}: no valid views found. Cannot build combined GT.", file=sys.stderr)
        return None

    # Compute visibility-weighted mean of normalized GTs
    combined_num = np.zeros(n_verts, dtype=np.float64)
    combined_den = np.zeros(n_verts, dtype=np.float64)

    gt_sum_per_view: dict[str, float] = {}
    n_visible_per_view: dict[str, int] = {}

    for view in views:
        if view not in gt_arrays:
            continue
        gt  = gt_arrays[view]
        vis = vis_arrays[view]
        gt_norm = _normalize_gt(gt, vis, normalization)

        combined_num += gt_norm * vis.astype(np.float64)
        combined_den += vis.astype(np.float64)

        gt_sum_per_view[view]   = float(gt.sum())
        n_visible_per_view[view] = int(vis.sum())

    # Suppress divide-by-zero warning: denominator=0 cells are replaced by 0.0
    with np.errstate(invalid="ignore", divide="ignore"):
        combined_gt = np.where(combined_den > 0.0, combined_num / combined_den, 0.0)

    n_combined_nonzero = int((combined_gt > 0).sum())
    combined_coverage  = float(100.0 * n_combined_nonzero / n_verts) if n_verts else 0.0

    meta: dict = {
        "model":               model,
        "n_verts":             n_verts,
        "normalization":       normalization,
        "views_used":          [v for v in views if v in gt_arrays],
        "views_skipped":       [v for v in views if v not in gt_arrays],
        "gt_sum_per_view":     gt_sum_per_view,
        "n_visible_per_view":  n_visible_per_view,
        "n_combined_nonzero":  n_combined_nonzero,
        "combined_coverage_pct": round(combined_coverage, 2),
        "combined_gt_sum":     float(combined_gt.sum()),
        "warnings":            warnings,
    }
    return combined_gt, meta


def main() -> int:
    args = parse_args()

    if not args.dataset_root.is_dir():
        print(f"[ERROR] dataset-root not found: {args.dataset_root}", file=sys.stderr)
        return 1

    fixation_dir = args.dataset_root / "FixationMaps"
    vis_dir      = args.dataset_root / "CentricityAndVisibilityMaps"

    if not fixation_dir.is_dir():
        print(f"[ERROR] FixationMaps not found: {fixation_dir}", file=sys.stderr)
        return 1
    if not vis_dir.is_dir():
        print(f"[ERROR] CentricityAndVisibilityMaps not found: {vis_dir}", file=sys.stderr)
        return 1

    output_dir = args.output_dir or (args.dataset_root / "CombinedGT")
    output_dir.mkdir(parents=True, exist_ok=True)

    # Discover or use explicit model list
    if args.models:
        models = args.models
    else:
        models = _discover_models(fixation_dir, list(args.views))
        if not models:
            print(f"[ERROR] No models found in {fixation_dir}", file=sys.stderr)
            return 1

    print(f"[build_3dva_combined_gt] models={len(models)}  views={args.views}  "
          f"normalization={args.normalization}  output={output_dir}")

    all_meta: dict[str, dict] = {}
    n_ok = 0
    n_fail = 0

    for model in models:
        result = build_combined_gt(
            model, fixation_dir, vis_dir,
            list(args.views), args.normalization,
        )

        if result is None:
            n_fail += 1
            continue

        combined_gt, meta = result

        # Warn about vertex count mismatch with OBJ (turbine special case)
        obj_path = args.dataset_root / "3DModels-Simplif-up" / f"{model}.obj"
        if obj_path.is_file():
            n_obj_verts = sum(1 for line in obj_path.read_text(errors="ignore").splitlines()
                             if line.startswith("v "))
            if n_obj_verts != meta["n_verts"]:
                warn_msg = (
                    f"OBJ has {n_obj_verts} verts but GT has {meta['n_verts']} lines. "
                    "Combined GT uses GT line count. Eval scripts must load this OBJ with "
                    "process=False and NOT validate vertex count against combined GT length."
                )
                print(f"[WARN] {model}: {warn_msg}", file=sys.stderr)
                meta["vertex_mismatch"] = True
                meta["n_obj_verts"]     = n_obj_verts
                meta["n_gt_lines"]      = meta["n_verts"]

        for w in meta.get("warnings", []):
            print(f"[WARN] {model}: {w}", file=sys.stderr)

        # Save combined GT
        out_txt = output_dir / f"{model}_combined_gt.txt"
        np.savetxt(str(out_txt), combined_gt, fmt="%.10f")

        # Save meta JSON
        out_meta = output_dir / f"{model}_combined_gt_meta.json"
        out_meta.write_text(json.dumps(meta, indent=2), encoding="utf-8")

        all_meta[model] = meta
        n_ok += 1

        print(
            f"  {model:<22}  n_verts={meta['n_verts']:<6}  "
            f"coverage={meta['combined_coverage_pct']:.1f}%  "
            f"nonzero={meta['n_combined_nonzero']}"
        )

    # Save summary
    summary_path = output_dir / "build_summary.json"
    summary_path.write_text(json.dumps(all_meta, indent=2), encoding="utf-8")

    print(f"\n[build_3dva_combined_gt] done: {n_ok} ok  {n_fail} failed")
    print(f"  output: {output_dir}")
    print(f"  summary: {summary_path}")

    return 0 if n_fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
