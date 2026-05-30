#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
from scipy.ndimage import gaussian_filter

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from metrics.screen_space import auc_from_binary_mask, binary_mask_from_fixation_points, cc_from_maps, nss_from_fixation_points
from utils.path_defaults import resolve_dataset_root


WIDTH = 1920
HEIGHT = 1080


@dataclass
class GazeRow:
    x: float
    y: float
    weight: float


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Hold-out screen-space evaluation for Saliency3D_clear."
    )
    parser.add_argument(
        "--dataset-root",
        type=Path,
        default=None,
        help="Root directory of Saliency3D_clear.",
    )
    parser.add_argument("--model", default="hand")
    parser.add_argument("--sigma-px", type=float, default=26.3)
    parser.add_argument(
        "--test-participants",
        nargs="+",
        default=["zl", "zy"],
        help="Participant ids held out for testing.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(
            REPO_ROOT / "results" / "saliency3d_clear" / "screen_space_gaussian"
        ),
    )
    return parser.parse_args()


def load_participant_rows(path: Path) -> list[GazeRow]:
    rows: list[GazeRow] = []
    with path.open("r", encoding="utf-8", errors="ignore") as f:
        reader = csv.reader(f)
        for cols in reader:
            if not cols or len(cols) < 11:
                continue
            try:
                x = float(cols[4])
                y = float(cols[5])
                weight = float(cols[10])
            except ValueError:
                continue
            if math.isnan(x) or math.isnan(y) or math.isnan(weight):
                continue
            rows.append(GazeRow(x=x, y=y, weight=max(weight, 0.0)))
    return rows


def deposit_bilinear(canvas: np.ndarray, x: float, y: float, weight: float) -> None:
    x = float(np.clip(x, 0.0, WIDTH - 1.0))
    y = float(np.clip(y, 0.0, HEIGHT - 1.0))

    x0 = int(np.floor(x))
    y0 = int(np.floor(y))
    x1 = min(x0 + 1, WIDTH - 1)
    y1 = min(y0 + 1, HEIGHT - 1)

    dx = x - x0
    dy = y - y0

    w00 = (1.0 - dx) * (1.0 - dy)
    w10 = dx * (1.0 - dy)
    w01 = (1.0 - dx) * dy
    w11 = dx * dy

    canvas[y0, x0] += weight * w00
    canvas[y0, x1] += weight * w10
    canvas[y1, x0] += weight * w01
    canvas[y1, x1] += weight * w11


def build_density_map(rows: Iterable[GazeRow], sigma_px: float) -> np.ndarray:
    hist = np.zeros((HEIGHT, WIDTH), dtype=np.float32)
    for row in rows:
        deposit_bilinear(hist, row.x, row.y, row.weight)
    density = gaussian_filter(hist, sigma=sigma_px, mode="constant")
    total = float(density.sum())
    if total > 0.0:
        density /= total
    return density.astype(np.float32, copy=False)


def main() -> None:
    args = parse_args()
    dataset_root = resolve_dataset_root(
        args.dataset_root,
        env_var="SALIENCY3D_CLEAR_ROOT",
        dataset_name="Saliency3D_clear",
        example_path="e.g. /srv/datasets/Saliency3D_clear",
    )
    model_dir = dataset_root / "3D_gaze_data" / "Code" / "Exp1" / args.model
    if not model_dir.is_dir():
        raise SystemExit(f"Model directory not found: {model_dir}")

    participant_files = sorted([p for p in model_dir.iterdir() if p.is_file()])
    all_participants = [p.name for p in participant_files]
    test_participants = sorted(args.test_participants)
    train_participants = [p for p in all_participants if p not in test_participants]

    if not train_participants:
        raise SystemExit("Empty train split.")
    if not test_participants:
        raise SystemExit("Empty test split.")

    train_rows: list[GazeRow] = []
    test_rows: list[GazeRow] = []
    per_participant_counts: dict[str, int] = {}

    for p in participant_files:
        rows = load_participant_rows(p)
        per_participant_counts[p.name] = len(rows)
        if p.name in test_participants:
            test_rows.extend(rows)
        else:
            train_rows.extend(rows)

    if not train_rows or not test_rows:
        raise SystemExit("Train or test rows are empty.")

    pred_map = build_density_map(train_rows, sigma_px=args.sigma_px)
    test_map = build_density_map(test_rows, sigma_px=args.sigma_px)
    fixation_points = [
        (
            int(np.clip(round(row.x), 0, WIDTH - 1)),
            int(np.clip(round(row.y), 0, HEIGHT - 1)),
        )
        for row in test_rows
    ]
    fixation_mask = binary_mask_from_fixation_points((HEIGHT, WIDTH), fixation_points)

    cc = cc_from_maps(pred_map, test_map)
    nss = nss_from_fixation_points(pred_map, fixation_points)
    auc = auc_from_binary_mask(pred_map, fixation_mask)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    tag = f"{args.model}_sigma{str(args.sigma_px).replace('.', 'p')}_{'_'.join(test_participants)}"
    report_path = args.output_dir / f"{tag}.json"

    summary = {
        "dataset_root": str(dataset_root),
        "model": args.model,
        "sigma_px": args.sigma_px,
        "resolution": [WIDTH, HEIGHT],
        "train_participants": train_participants,
        "test_participants": test_participants,
        "per_participant_counts": per_participant_counts,
        "num_train_rows": len(train_rows),
        "num_test_rows": len(test_rows),
        "num_test_unique_pixels": int(fixation_mask.sum()),
        "metrics": {
            "AUC": auc,
            "NSS": nss,
            "CC": cc,
        },
        "notes": {
            "AUC": "roc_auc_score over full 1920x1080 grid using test fixation mask as positives",
            "NSS": "mean z-scored predicted saliency at all test fixation rows",
            "CC": "Pearson correlation between train density map and test density map",
            "map_builder": "weighted fixation histogram convolved with deterministic Gaussian filter",
            "weight_column": "column 10 from Exp1 participant files",
        },
    }

    report_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(json.dumps(summary, indent=2))
    print(f"\nSaved report: {report_path}")


if __name__ == "__main__":
    main()
