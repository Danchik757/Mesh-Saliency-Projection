#!/usr/bin/env python3
"""
Post-process existing MeshMamba prediction maps to diagnose high KLD.

This script does not rerun gaze projection. It loads already generated
per-face prediction maps, loads the matching GT saliency maps, and recomputes
metrics under controlled diagnostic variants:

- alpha floor on the prediction probability distribution
- support masks
- face-area weighting
- neighbor diffusion on the mesh face graph

The outputs are diagnostic only. They should not replace the benchmark metrics
unless a variant is explicitly promoted and rerun end-to-end.
"""

from __future__ import annotations

import argparse
import csv
import math
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from statistics import mean, median
from typing import Any, Iterable

import numpy as np


REPO_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_MESHMAMBA_ROOT = Path("/home/29d_kon@lab.graphicon.ru/ssd1_link/datasets/MeshMambaSaliency")
DEFAULT_REFERENCE_CSV = Path(
    "/home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/outputs/"
    "MeshMamba_reference_batch_20260601/meshmamba_reference_long.csv"
)
DEFAULT_KLD_SWEEP_CSV = Path(
    "/home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/outputs/"
    "KLD_diagnostic_20260602_064256/kld_sweep_long.csv"
)

METRIC_COLUMNS = [
    "CC",
    "SIM",
    "KLD",
    "MSE",
    "MAE",
    "Spearman",
    "Cosine",
    "AUC_Judd_gt_top_10pct_proxy",
    "AUC_Judd_gt_top_5pct_proxy",
    "AUC_Judd_gt_top_1pct_proxy",
    "NSS_gt_top_10pct_proxy",
    "NSS_gt_top_5pct_proxy",
    "NSS_gt_top_1pct_proxy",
    "PredictionSum",
    "GroundTruthSum",
    "gt_mass_on_pred_zero",
    "pred_mass_on_pred_zero",
    "pred_count_zero",
    "gt_mass_on_pred_le_1e_8",
    "pred_mass_on_pred_le_1e_8",
    "pred_count_le_1e_8",
    "gt_mass_on_pred_le_1e_6",
    "pred_mass_on_pred_le_1e_6",
    "pred_count_le_1e_6",
    "top100_kld_contrib_sum",
    "top100_kld_gt_mass",
    "top100_kld_pred_mass",
]

ROW_COLUMNS = [
    "source_label",
    "source_csv",
    "source_row_index",
    "dataset",
    "texture_type",
    "model",
    "method",
    "source_param_id",
    "source_status",
    "source_KLD",
    "source_CC",
    "source_SIM",
    "variant_family",
    "variant_id",
    "alpha",
    "support_mask",
    "area_weight_mode",
    "diffusion_steps",
    "diffusion_blend",
    "status",
    "error_type",
    "error_message",
    "prediction_path",
    "gt_path",
    "obj_path",
    "n_faces",
    "mask_count",
    "mask_fraction",
    "mask_gt_mass_original",
    "mask_pred_mass_original",
] + METRIC_COLUMNS

SUMMARY_GROUP_COLUMNS = [
    "source_label",
    "dataset",
    "texture_type",
    "method",
    "variant_family",
    "variant_id",
]

SUMMARY_METRICS = [
    "KLD",
    "CC",
    "SIM",
    "Spearman",
    "AUC_Judd_gt_top_10pct_proxy",
    "NSS_gt_top_10pct_proxy",
    "gt_mass_on_pred_zero",
    "gt_mass_on_pred_le_1e_8",
    "gt_mass_on_pred_le_1e_6",
    "top100_kld_gt_mass",
    "top100_kld_pred_mass",
]

TOP_FACE_COLUMNS = [
    "source_label",
    "source_row_index",
    "dataset",
    "texture_type",
    "model",
    "method",
    "source_param_id",
    "variant_id",
    "face_rank",
    "face_index",
    "gt_prob",
    "pred_prob",
    "kld_term",
    "face_area",
]


@dataclass(frozen=True)
class InputSource:
    label: str
    path: Path


@dataclass(frozen=True)
class SourceRow:
    source: InputSource
    row_index: int
    raw: dict[str, str]

    @property
    def dataset(self) -> str:
        value = self.raw.get("dataset") or "meshmamba"
        return value.strip().lower()

    @property
    def texture_type(self) -> str:
        return (self.raw.get("texture_type") or "non_texture").strip()

    @property
    def model(self) -> str:
        return (self.raw.get("model") or "").strip()

    @property
    def method(self) -> str:
        return (self.raw.get("method") or "").strip()

    @property
    def param_id(self) -> str:
        return (self.raw.get("param_id") or "reference").strip()

    @property
    def status(self) -> str:
        return (self.raw.get("status") or "").strip()

    @property
    def report_path(self) -> Path | None:
        value = (self.raw.get("report_path") or "").strip()
        return Path(value) if value else None


@dataclass
class MeshInfo:
    obj_path: Path
    face_areas: np.ndarray
    adjacency: np.ndarray


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Diagnose KLD using existing MeshMamba maps.")
    parser.add_argument(
        "--input-csv",
        action="append",
        default=[],
        help=(
            "Input CSV as LABEL:PATH. Can be repeated. "
            "Defaults to MeshMamba reference and the 20260602 KLD sweep when present."
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(os.environ.get("KLD_POSTPROCESS_OUTPUT_DIR", REPO_ROOT / "results" / "KLD_postprocess_diagnostics")),
    )
    parser.add_argument(
        "--meshmamba-root",
        type=Path,
        default=Path(
            os.environ.get(
                "MESHMAMBA_DATASET_ROOT",
                os.environ.get("MESHMAMBA_NON_TEXTURE_ROOT", str(DEFAULT_MESHMAMBA_ROOT)),
            )
        ),
    )
    parser.add_argument("--methods", default="screen_space,cone")
    parser.add_argument("--texture-types", default="non_texture,rgb_texture")
    parser.add_argument("--alphas", default="0,1e-10,1e-9,1e-8,1e-7,1e-6,1e-5,1e-4,1e-3,1e-2")
    parser.add_argument("--support-masks", default="pred_positive,pred_above_1e_8,pred_above_1e_6,gt_positive,intersection_positive,union_positive")
    parser.add_argument("--area-modes", default="none,multiply_area,divide_area")
    parser.add_argument("--diffusion-steps", default="1,3,5,10,20,40")
    parser.add_argument("--diffusion-blend", type=float, default=0.5)
    parser.add_argument("--top-face-count", type=int, default=50)
    parser.add_argument("--max-input-rows", type=int, default=None)
    parser.add_argument("--write-every", type=int, default=10)
    parser.add_argument(
        "--skip-diffusion",
        action="store_true",
        help="Skip mesh-neighbor diffusion variants. Useful for smoke tests.",
    )
    return parser.parse_args()


def _split_csv(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


def _float_csv(value: str) -> list[float]:
    return [float(part) for part in _split_csv(value)]


def _int_csv(value: str) -> list[int]:
    return [int(part) for part in _split_csv(value)]


def _safe_float(value: Any) -> float | None:
    if value in ("", None):
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(out):
        return None
    return out


def _fmt_float(value: float | None) -> str:
    if value is None:
        return ""
    if not math.isfinite(float(value)):
        return ""
    return f"{float(value):.12g}"


def _normalize_sum(values: np.ndarray) -> np.ndarray:
    values = np.asarray(values, dtype=np.float64).reshape(-1)
    total = float(values.sum())
    if total <= 0.0 or not math.isfinite(total):
        return np.zeros_like(values)
    return values / total


def _normalize_minmax(values: np.ndarray) -> np.ndarray:
    values = np.asarray(values, dtype=np.float64).reshape(-1)
    if values.size == 0:
        return values.copy()
    vmin = float(values.min())
    vmax = float(values.max())
    if not math.isfinite(vmin) or not math.isfinite(vmax) or vmax <= vmin:
        return np.zeros_like(values)
    return (values - vmin) / (vmax - vmin)


def _pearson(first: np.ndarray, second: np.ndarray) -> float:
    first = np.asarray(first, dtype=np.float64).reshape(-1)
    second = np.asarray(second, dtype=np.float64).reshape(-1)
    if first.size < 2 or second.size < 2:
        return 0.0
    first_centered = first - float(first.mean())
    second_centered = second - float(second.mean())
    denom = float(np.linalg.norm(first_centered) * np.linalg.norm(second_centered))
    if denom == 0.0 or not math.isfinite(denom):
        return 0.0
    return float(np.dot(first_centered, second_centered) / denom)


def _rankdata(values: np.ndarray) -> np.ndarray:
    values = np.asarray(values, dtype=np.float64).reshape(-1)
    sorter = np.argsort(values, kind="mergesort")
    sorted_values = values[sorter]
    ranks_sorted = np.empty(values.size, dtype=np.float64)
    start = 0
    while start < values.size:
        end = start + 1
        while end < values.size and sorted_values[end] == sorted_values[start]:
            end += 1
        rank = 0.5 * (start + end - 1) + 1.0
        ranks_sorted[start:end] = rank
        start = end
    ranks = np.empty(values.size, dtype=np.float64)
    ranks[sorter] = ranks_sorted
    return ranks


def _spearman(first: np.ndarray, second: np.ndarray) -> float:
    if first.size < 2 or second.size < 2:
        return 0.0
    return _pearson(_rankdata(first), _rankdata(second))


def _cosine_similarity(first: np.ndarray, second: np.ndarray) -> float:
    denom = float(np.linalg.norm(first) * np.linalg.norm(second))
    if denom == 0.0 or not math.isfinite(denom):
        return 0.0
    return float(np.dot(first, second) / denom)


def _nss(saliency_map: np.ndarray, fixation_mask: np.ndarray) -> float:
    fixation_mask = np.asarray(fixation_mask, dtype=bool).reshape(-1)
    if fixation_mask.sum() == 0:
        return 0.0
    std = float(saliency_map.std())
    if std == 0.0 or not math.isfinite(std):
        return 0.0
    z_map = (saliency_map - float(saliency_map.mean())) / std
    return float(z_map[fixation_mask].mean())


def _auc_judd(saliency_map: np.ndarray, fixation_mask: np.ndarray) -> float:
    saliency_map = _normalize_minmax(saliency_map).reshape(-1)
    fixation_mask = np.asarray(fixation_mask, dtype=bool).reshape(-1)
    fixation_count = int(fixation_mask.sum())
    non_fixation_count = int((~fixation_mask).sum())
    if fixation_count == 0 or non_fixation_count == 0:
        return 0.5
    ranks = _rankdata(saliency_map)
    positive_rank_sum = float(ranks[fixation_mask].sum())
    numerator = positive_rank_sum - fixation_count * (fixation_count + 1.0) / 2.0
    denominator = float(fixation_count * non_fixation_count)
    return float(numerator / denominator)


def compute_metrics(
    pred: np.ndarray,
    gt: np.ndarray,
    proxy_fixation_percentiles: tuple[float, ...] = (90.0, 95.0, 99.0),
) -> dict[str, float]:
    pred = np.asarray(pred, dtype=np.float64).reshape(-1)
    gt = np.asarray(gt, dtype=np.float64).reshape(-1)
    if pred.size != gt.size:
        raise ValueError(f"metric size mismatch: pred={pred.size}, gt={gt.size}")
    if pred.size == 0:
        raise ValueError("empty metric arrays")

    pred_nonnegative = np.clip(pred, a_min=0.0, a_max=None)
    gt_nonnegative = np.clip(gt, a_min=0.0, a_max=None)
    pred_prob = _normalize_sum(pred_nonnegative)
    gt_prob = _normalize_sum(gt_nonnegative)
    pred_unit = _normalize_minmax(pred)
    gt_unit = _normalize_minmax(gt)

    eps = 1e-12
    pred_prob_safe = pred_prob + eps
    gt_prob_safe = gt_prob + eps
    kld_terms = gt_prob_safe * np.log(gt_prob_safe / pred_prob_safe)

    metrics = {
        "CC": _pearson(pred, gt),
        "SIM": float(np.minimum(pred_prob, gt_prob).sum()),
        "KLD": float(np.sum(kld_terms)),
        "MSE": float(np.mean((pred_unit - gt_unit) ** 2)),
        "MAE": float(np.mean(np.abs(pred_unit - gt_unit))),
        "Spearman": _spearman(pred, gt),
        "Cosine": _cosine_similarity(pred, gt),
        "PredictionSum": float(pred.sum()),
        "GroundTruthSum": float(gt.sum()),
    }

    for threshold, label in ((0.0, "zero"), (1e-8, "le_1e_8"), (1e-6, "le_1e_6")):
        low_pred = pred_prob <= threshold
        metrics[f"gt_mass_on_pred_{label}"] = float(gt_prob[low_pred].sum())
        metrics[f"pred_mass_on_pred_{label}"] = float(pred_prob[low_pred].sum())
        metrics[f"pred_count_{label}"] = float(low_pred.sum())

    top_k = min(100, kld_terms.size)
    if top_k > 0:
        idx = np.argpartition(kld_terms, -top_k)[-top_k:]
        metrics["top100_kld_contrib_sum"] = float(kld_terms[idx].sum())
        metrics["top100_kld_gt_mass"] = float(gt_prob[idx].sum())
        metrics["top100_kld_pred_mass"] = float(pred_prob[idx].sum())
    else:
        metrics["top100_kld_contrib_sum"] = 0.0
        metrics["top100_kld_gt_mass"] = 0.0
        metrics["top100_kld_pred_mass"] = 0.0

    for percentile in proxy_fixation_percentiles:
        threshold = float(np.quantile(gt_unit, percentile / 100.0))
        fixation_mask = gt_unit >= threshold
        top_pct = 100.0 - percentile
        label = str(int(round(top_pct))) if math.isclose(top_pct, round(top_pct)) else str(top_pct).replace(".", "p")
        metrics[f"NSS_gt_top_{label}pct_proxy"] = _nss(pred_unit, fixation_mask)
        metrics[f"AUC_Judd_gt_top_{label}pct_proxy"] = _auc_judd(pred_unit, fixation_mask)

    return metrics


def parse_sources(values: list[str]) -> list[InputSource]:
    if not values:
        values = [
            f"reference:{DEFAULT_REFERENCE_CSV}",
            f"kld_sweep:{DEFAULT_KLD_SWEEP_CSV}",
        ]
    sources: list[InputSource] = []
    for value in values:
        if ":" in value:
            label, path = value.split(":", 1)
        else:
            path = value
            label = Path(value).stem
        sources.append(InputSource(label=label.strip(), path=Path(path).expanduser()))
    return sources


def read_source_rows(sources: list[InputSource]) -> list[SourceRow]:
    rows: list[SourceRow] = []
    for source in sources:
        if not source.path.exists():
            print(f"[warn] input CSV missing: {source.path}", file=sys.stderr, flush=True)
            continue
        with source.path.open("r", newline="") as handle:
            reader = csv.DictReader(handle)
            for idx, raw in enumerate(reader):
                rows.append(SourceRow(source=source, row_index=idx, raw=raw))
    return rows


def _candidate_model_names(model: str) -> list[str]:
    raw = model.strip()
    variants = [raw, raw.replace("_", "-"), raw.replace("-", "_")]
    stripped = re.sub(r"([_-])l\d+$", "", raw, flags=re.IGNORECASE)
    if stripped != raw:
        variants.extend([stripped, stripped.replace("_", "-"), stripped.replace("-", "_")])

    deduped: list[str] = []
    seen: set[str] = set()
    for variant in variants:
        key = variant.lower()
        if key not in seen:
            deduped.append(variant)
            seen.add(key)
    return deduped


def _casefold_file_lookup(directory: Path, suffix: str) -> dict[str, Path]:
    if not directory.exists():
        return {}
    return {
        path.name.lower(): path
        for path in sorted(directory.glob(f"*{suffix}"))
        if path.is_file()
    }


def _resolve_casefold_file(directory: Path, candidate_names: list[str], suffix: str) -> Path | None:
    index = _casefold_file_lookup(directory, suffix)
    for name in candidate_names:
        resolved = index.get(f"{name}{suffix}".lower())
        if resolved is not None:
            return resolved
    return None


def find_gt_file(gt_dir: Path, model: str, gt_file: str | None) -> Path:
    if gt_file:
        exact = gt_dir / gt_file
        if exact.exists():
            return exact
        casefold = _casefold_file_lookup(gt_dir, ".csv").get(gt_file.lower())
        if casefold is not None:
            return casefold

    candidate_names = _candidate_model_names(model)
    resolved = _resolve_casefold_file(gt_dir, candidate_names, ".csv")
    if resolved is not None:
        return resolved

    model_norms = {name.lower().replace("_", "-").replace(" ", "-") for name in candidate_names}
    for path in sorted(gt_dir.glob("*.csv")):
        if path.stem.lower().replace("_", "-").replace(" ", "-") in model_norms:
            return path
    raise FileNotFoundError(f"GT file not found for model={model} gt_file={gt_file} in {gt_dir}")


def find_obj_file(mesh_dir: Path, model: str) -> Path:
    if not mesh_dir.exists():
        raise FileNotFoundError(f"Mesh directory missing: {mesh_dir}")
    dir_index = {path.name.lower(): path for path in sorted(mesh_dir.iterdir()) if path.is_dir()}
    model_dir = None
    candidate_names = _candidate_model_names(model)
    for name in candidate_names:
        model_dir = dir_index.get(name.lower())
        if model_dir is not None:
            break
    if model_dir is None:
        raise FileNotFoundError(f"Model directory not found for {model} in {mesh_dir}")
    resolved = _resolve_casefold_file(model_dir, candidate_names, ".obj")
    if resolved is not None:
        return resolved
    obj_files = sorted(model_dir.glob("*.obj"))
    if obj_files:
        return obj_files[0]
    raise FileNotFoundError(f"No OBJ file found in {model_dir}")


def resolve_prediction_path(row: SourceRow) -> Path:
    report_path = row.report_path
    if report_path is None:
        raise FileNotFoundError("report_path is empty")
    parent = report_path.parent
    if row.method == "cone":
        candidates = [
            parent / f"{row.model}_cone_faces.txt",
            parent / f"{row.model}_raycast_faces.txt",
        ]
    elif row.method == "screen_space":
        candidates = [parent / f"{row.model}_screen_space_faces.txt"]
    else:
        raise ValueError(f"unsupported method: {row.method}")

    for candidate in candidates:
        if candidate.exists():
            return candidate

    found = sorted(parent.glob("*faces.txt"))
    if len(found) == 1:
        return found[0]
    raise FileNotFoundError(f"Prediction faces map not found near {report_path}; tried {candidates}")


def load_values(path: Path) -> np.ndarray:
    errors: list[str] = []
    for delimiter in (",", None):
        try:
            data = np.loadtxt(path, delimiter=delimiter, dtype=np.float64)
            return np.asarray(data, dtype=np.float64).reshape(-1)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{delimiter!r}: {exc}")
    raise ValueError(f"Could not load numeric vector from {path}: {'; '.join(errors)}")


def load_mesh_info(obj_path: Path) -> MeshInfo:
    import trimesh

    mesh = trimesh.load(obj_path, force="mesh", process=False)
    face_areas = np.asarray(mesh.area_faces, dtype=np.float64).reshape(-1)
    adjacency = np.asarray(mesh.face_adjacency, dtype=np.int64)
    if adjacency.ndim != 2 or adjacency.shape[1] != 2:
        adjacency = np.empty((0, 2), dtype=np.int64)
    return MeshInfo(obj_path=obj_path, face_areas=face_areas, adjacency=adjacency)


def apply_area_mode(pred: np.ndarray, gt: np.ndarray, areas: np.ndarray, mode: str) -> tuple[np.ndarray, np.ndarray]:
    if mode == "none":
        return pred, gt
    safe_area = np.asarray(areas, dtype=np.float64).reshape(-1)
    safe_area = np.where(safe_area > 0.0, safe_area, np.finfo(np.float64).eps)
    if mode == "multiply_area":
        return pred * safe_area, gt * safe_area
    if mode == "divide_area":
        return pred / safe_area, gt / safe_area
    raise ValueError(f"unknown area mode: {mode}")


def diffuse_prediction(pred: np.ndarray, adjacency: np.ndarray, steps: Iterable[int], blend: float) -> dict[int, np.ndarray]:
    requested = sorted({int(step) for step in steps if int(step) > 0})
    if not requested:
        return {}
    max_step = requested[-1]
    current = np.asarray(pred, dtype=np.float64).reshape(-1).copy()
    n_faces = current.size
    if adjacency.size == 0:
        return {step: current.copy() for step in requested}

    first = adjacency[:, 0]
    second = adjacency[:, 1]
    out: dict[int, np.ndarray] = {}
    for step in range(1, max_step + 1):
        sums = np.zeros(n_faces, dtype=np.float64)
        counts = np.zeros(n_faces, dtype=np.float64)
        np.add.at(sums, first, current[second])
        np.add.at(sums, second, current[first])
        np.add.at(counts, first, 1.0)
        np.add.at(counts, second, 1.0)
        neighbor_mean = current.copy()
        has_neighbor = counts > 0.0
        neighbor_mean[has_neighbor] = sums[has_neighbor] / counts[has_neighbor]
        current = (1.0 - blend) * current + blend * neighbor_mean
        if step in requested:
            out[step] = current.copy()
    return out


def support_mask(name: str, pred: np.ndarray, gt: np.ndarray) -> np.ndarray:
    pred_prob = _normalize_sum(np.clip(pred, a_min=0.0, a_max=None))
    gt_prob = _normalize_sum(np.clip(gt, a_min=0.0, a_max=None))
    pred_positive = pred_prob > 0.0
    gt_positive = gt_prob > 0.0
    if name == "pred_positive":
        return pred_positive
    if name == "pred_above_1e_8":
        return pred_prob > 1e-8
    if name == "pred_above_1e_6":
        return pred_prob > 1e-6
    if name == "gt_positive":
        return gt_positive
    if name == "intersection_positive":
        return np.logical_and(pred_positive, gt_positive)
    if name == "union_positive":
        return np.logical_or(pred_positive, gt_positive)
    raise ValueError(f"unknown support mask: {name}")


def base_row(source_row: SourceRow) -> dict[str, Any]:
    return {
        "source_label": source_row.source.label,
        "source_csv": str(source_row.source.path),
        "source_row_index": source_row.row_index,
        "dataset": source_row.dataset,
        "texture_type": source_row.texture_type,
        "model": source_row.model,
        "method": source_row.method,
        "source_param_id": source_row.param_id,
        "source_status": source_row.status,
        "source_KLD": source_row.raw.get("KLD", ""),
        "source_CC": source_row.raw.get("CC", ""),
        "source_SIM": source_row.raw.get("SIM", ""),
    }


def add_metrics(row: dict[str, Any], pred: np.ndarray, gt: np.ndarray) -> dict[str, Any]:
    row.update(compute_metrics(pred, gt))
    return row


def add_common_variant_fields(
    row: dict[str, Any],
    *,
    variant_family: str,
    variant_id: str,
    alpha: float | None = None,
    support: str = "",
    area_mode: str = "",
    diffusion_steps: int | None = None,
    diffusion_blend: float | None = None,
    prediction_path: Path | None = None,
    gt_path: Path | None = None,
    obj_path: Path | None = None,
    n_faces: int | None = None,
    mask: np.ndarray | None = None,
    pred_prob_original: np.ndarray | None = None,
    gt_prob_original: np.ndarray | None = None,
) -> dict[str, Any]:
    row.update(
        {
            "variant_family": variant_family,
            "variant_id": variant_id,
            "alpha": _fmt_float(alpha),
            "support_mask": support,
            "area_weight_mode": area_mode,
            "diffusion_steps": "" if diffusion_steps is None else diffusion_steps,
            "diffusion_blend": _fmt_float(diffusion_blend),
            "status": "ok",
            "error_type": "",
            "error_message": "",
            "prediction_path": "" if prediction_path is None else str(prediction_path),
            "gt_path": "" if gt_path is None else str(gt_path),
            "obj_path": "" if obj_path is None else str(obj_path),
            "n_faces": "" if n_faces is None else int(n_faces),
        }
    )
    if mask is None:
        row["mask_count"] = "" if n_faces is None else int(n_faces)
        row["mask_fraction"] = 1.0
        row["mask_gt_mass_original"] = 1.0
        row["mask_pred_mass_original"] = 1.0
    else:
        row["mask_count"] = int(mask.sum())
        row["mask_fraction"] = float(mask.sum()) / float(mask.size) if mask.size else 0.0
        row["mask_gt_mass_original"] = (
            float(gt_prob_original[mask].sum()) if gt_prob_original is not None and mask.size else ""
        )
        row["mask_pred_mass_original"] = (
            float(pred_prob_original[mask].sum()) if pred_prob_original is not None and mask.size else ""
        )
    return row


def error_row(source_row: SourceRow, exc: Exception) -> dict[str, Any]:
    row = base_row(source_row)
    row.update(
        {
            "variant_family": "load_error",
            "variant_id": "load_error",
            "alpha": "",
            "support_mask": "",
            "area_weight_mode": "",
            "diffusion_steps": "",
            "diffusion_blend": "",
            "status": "error",
            "error_type": type(exc).__name__,
            "error_message": str(exc),
            "prediction_path": "",
            "gt_path": "",
            "obj_path": "",
            "n_faces": "",
            "mask_count": "",
            "mask_fraction": "",
            "mask_gt_mass_original": "",
            "mask_pred_mass_original": "",
        }
    )
    for metric in METRIC_COLUMNS:
        row[metric] = ""
    return row


def top_kld_faces_rows(
    source_row: SourceRow,
    pred: np.ndarray,
    gt: np.ndarray,
    face_areas: np.ndarray,
    top_face_count: int,
) -> list[dict[str, Any]]:
    if top_face_count <= 0:
        return []
    pred_prob = _normalize_sum(np.clip(pred, a_min=0.0, a_max=None))
    gt_prob = _normalize_sum(np.clip(gt, a_min=0.0, a_max=None))
    eps = 1e-12
    kld_terms = (gt_prob + eps) * np.log((gt_prob + eps) / (pred_prob + eps))
    top_k = min(top_face_count, kld_terms.size)
    if top_k == 0:
        return []
    idx = np.argpartition(kld_terms, -top_k)[-top_k:]
    idx = idx[np.argsort(kld_terms[idx])[::-1]]
    out = []
    for rank, face_idx in enumerate(idx, start=1):
        out.append(
            {
                "source_label": source_row.source.label,
                "source_row_index": source_row.row_index,
                "dataset": source_row.dataset,
                "texture_type": source_row.texture_type,
                "model": source_row.model,
                "method": source_row.method,
                "source_param_id": source_row.param_id,
                "variant_id": "baseline",
                "face_rank": rank,
                "face_index": int(face_idx),
                "gt_prob": float(gt_prob[face_idx]),
                "pred_prob": float(pred_prob[face_idx]),
                "kld_term": float(kld_terms[face_idx]),
                "face_area": float(face_areas[face_idx]) if face_idx < face_areas.size else "",
            }
        )
    return out


def process_source_row(
    source_row: SourceRow,
    *,
    meshmamba_root: Path,
    alphas: list[float],
    support_masks: list[str],
    area_modes: list[str],
    diffusion_steps: list[int],
    diffusion_blend: float,
    skip_diffusion: bool,
    top_face_count: int,
    mesh_cache: dict[Path, MeshInfo],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if source_row.dataset != "meshmamba":
        return [], []
    if source_row.status != "ok":
        return [], []
    if source_row.method not in {"cone", "screen_space"}:
        return [], []

    try:
        prediction_path = resolve_prediction_path(source_row)
        gt_dir = meshmamba_root / "SaliencyMap" / source_row.texture_type
        mesh_dir = meshmamba_root / "MeshFile" / source_row.texture_type
        gt_path = find_gt_file(gt_dir, source_row.model, source_row.raw.get("gt_file"))
        obj_path = find_obj_file(mesh_dir, source_row.model)

        pred = load_values(prediction_path)
        gt = load_values(gt_path)
        if pred.size != gt.size:
            raise ValueError(f"pred/GT size mismatch: pred={pred.size}, gt={gt.size}, gt_path={gt_path}")

        mesh_info = mesh_cache.get(obj_path)
        if mesh_info is None:
            mesh_info = load_mesh_info(obj_path)
            mesh_cache[obj_path] = mesh_info
        if mesh_info.face_areas.size != pred.size:
            raise ValueError(
                f"face-area size mismatch: areas={mesh_info.face_areas.size}, pred={pred.size}, obj={obj_path}"
            )

        pred_prob_original = _normalize_sum(np.clip(pred, a_min=0.0, a_max=None))
        gt_prob_original = _normalize_sum(np.clip(gt, a_min=0.0, a_max=None))
        n_faces = int(pred.size)
        common = {
            "prediction_path": prediction_path,
            "gt_path": gt_path,
            "obj_path": obj_path,
            "n_faces": n_faces,
            "pred_prob_original": pred_prob_original,
            "gt_prob_original": gt_prob_original,
        }

        rows: list[dict[str, Any]] = []
        top_rows = top_kld_faces_rows(source_row, pred, gt, mesh_info.face_areas, top_face_count)

        baseline = add_common_variant_fields(
            base_row(source_row),
            variant_family="baseline",
            variant_id="baseline",
            **common,
        )
        rows.append(add_metrics(baseline, pred, gt))

        n = pred.size
        uniform = np.full(n, 1.0 / float(n), dtype=np.float64)
        pred_prob = pred_prob_original
        gt_prob = gt_prob_original
        for alpha in alphas:
            smoothed_pred = (1.0 - alpha) * pred_prob + alpha * uniform
            row = add_common_variant_fields(
                base_row(source_row),
                variant_family="alpha_floor",
                variant_id=f"alpha_{_fmt_float(alpha).replace('-', 'm').replace('.', 'p')}",
                alpha=alpha,
                **common,
            )
            rows.append(add_metrics(row, smoothed_pred, gt_prob))

        for mask_name in support_masks:
            mask = support_mask(mask_name, pred, gt)
            row = add_common_variant_fields(
                base_row(source_row),
                variant_family="support_mask",
                variant_id=mask_name,
                support=mask_name,
                mask=mask,
                **common,
            )
            if int(mask.sum()) < 2 or float(gt_prob_original[mask].sum()) <= 0.0:
                row.update({"status": "skipped", "error_type": "empty_mask", "error_message": "mask has too few/zero-GT faces"})
                for metric in METRIC_COLUMNS:
                    row[metric] = ""
                rows.append(row)
            else:
                rows.append(add_metrics(row, pred[mask], gt[mask]))

        for mode in area_modes:
            weighted_pred, weighted_gt = apply_area_mode(pred, gt, mesh_info.face_areas, mode)
            row = add_common_variant_fields(
                base_row(source_row),
                variant_family="area_weighting",
                variant_id=mode,
                area_mode=mode,
                **common,
            )
            rows.append(add_metrics(row, weighted_pred, weighted_gt))

        if not skip_diffusion:
            for step, diffused in diffuse_prediction(pred, mesh_info.adjacency, diffusion_steps, diffusion_blend).items():
                row = add_common_variant_fields(
                    base_row(source_row),
                    variant_family="diffusion",
                    variant_id=f"diffusion_steps{step}_blend{_fmt_float(diffusion_blend).replace('.', 'p')}",
                    diffusion_steps=step,
                    diffusion_blend=diffusion_blend,
                    **common,
                )
                rows.append(add_metrics(row, diffused, gt))

        return rows, top_rows
    except Exception as exc:  # noqa: BLE001
        return [error_row(source_row, exc)], []


def write_csv(rows: list[dict[str, Any]], path: Path, fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def write_summary(rows: list[dict[str, Any]], path: Path) -> None:
    groups: dict[tuple[str, ...], list[dict[str, Any]]] = {}
    for row in rows:
        key = tuple(str(row.get(column, "")) for column in SUMMARY_GROUP_COLUMNS)
        groups.setdefault(key, []).append(row)

    summary_rows: list[dict[str, Any]] = []
    for key in sorted(groups):
        group_rows = groups[key]
        ok_rows = [row for row in group_rows if row.get("status") == "ok"]
        out = {column: key[idx] for idx, column in enumerate(SUMMARY_GROUP_COLUMNS)}
        out["n_total"] = len(group_rows)
        out["n_ok"] = len(ok_rows)
        out["n_failed_or_skipped"] = len(group_rows) - len(ok_rows)
        for metric in SUMMARY_METRICS:
            values = [_safe_float(row.get(metric)) for row in ok_rows]
            values = [value for value in values if value is not None]
            out[f"{metric}_mean"] = mean(values) if values else ""
            out[f"{metric}_median"] = median(values) if values else ""
        summary_rows.append(out)

    fieldnames = SUMMARY_GROUP_COLUMNS + ["n_total", "n_ok", "n_failed_or_skipped"]
    for metric in SUMMARY_METRICS:
        fieldnames.extend([f"{metric}_mean", f"{metric}_median"])
    write_csv(summary_rows, path, fieldnames)


def write_best_by_model(rows: list[dict[str, Any]], path: Path) -> None:
    best: dict[tuple[str, ...], dict[str, Any]] = {}
    for row in rows:
        if row.get("status") != "ok":
            continue
        kld = _safe_float(row.get("KLD"))
        if kld is None:
            continue
        key = (
            str(row.get("source_label", "")),
            str(row.get("dataset", "")),
            str(row.get("texture_type", "")),
            str(row.get("model", "")),
            str(row.get("method", "")),
            str(row.get("variant_family", "")),
        )
        prev = best.get(key)
        if prev is None or kld < float(prev["KLD"]):
            best[key] = row
    write_csv([best[key] for key in sorted(best)], path, ROW_COLUMNS)


def write_outputs(output_dir: Path, rows: list[dict[str, Any]], top_rows: list[dict[str, Any]]) -> None:
    rows_sorted = sorted(
        rows,
        key=lambda row: (
            str(row.get("source_label", "")),
            str(row.get("dataset", "")),
            str(row.get("texture_type", "")),
            str(row.get("model", "")),
            str(row.get("method", "")),
            str(row.get("source_param_id", "")),
            str(row.get("variant_family", "")),
            str(row.get("variant_id", "")),
        ),
    )
    write_csv(rows_sorted, output_dir / "postprocess_long.csv", ROW_COLUMNS)
    write_summary(rows_sorted, output_dir / "postprocess_summary.csv")
    write_best_by_model(rows_sorted, output_dir / "postprocess_best_by_model.csv")
    write_csv(top_rows, output_dir / "postprocess_top_kld_faces.csv", TOP_FACE_COLUMNS)


def filter_rows(rows: list[SourceRow], methods: set[str], texture_types: set[str], max_rows: int | None) -> list[SourceRow]:
    filtered: list[SourceRow] = []
    for row in rows:
        if row.dataset != "meshmamba":
            continue
        if row.status != "ok":
            continue
        if row.method not in methods:
            continue
        if row.texture_type not in texture_types:
            continue
        filtered.append(row)
        if max_rows is not None and len(filtered) >= max_rows:
            break
    return filtered


def main() -> int:
    args = parse_args()
    sources = parse_sources(args.input_csv)
    methods = set(_split_csv(args.methods))
    texture_types = set(_split_csv(args.texture_types))
    alphas = _float_csv(args.alphas)
    support_masks = _split_csv(args.support_masks)
    area_modes = _split_csv(args.area_modes)
    diffusion_steps = _int_csv(args.diffusion_steps)

    source_rows = filter_rows(read_source_rows(sources), methods, texture_types, args.max_input_rows)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    print(
        f"[postprocess] input_rows={len(source_rows)} output={args.output_dir} "
        f"mesh_root={args.meshmamba_root}",
        flush=True,
    )

    rows: list[dict[str, Any]] = []
    top_rows: list[dict[str, Any]] = []
    mesh_cache: dict[Path, MeshInfo] = {}

    for idx, source_row in enumerate(source_rows, start=1):
        new_rows, new_top_rows = process_source_row(
            source_row,
            meshmamba_root=args.meshmamba_root,
            alphas=alphas,
            support_masks=support_masks,
            area_modes=area_modes,
            diffusion_steps=diffusion_steps,
            diffusion_blend=args.diffusion_blend,
            skip_diffusion=args.skip_diffusion,
            top_face_count=args.top_face_count,
            mesh_cache=mesh_cache,
        )
        rows.extend(new_rows)
        top_rows.extend(new_top_rows)
        ok_count = sum(1 for row in new_rows if row.get("status") == "ok")
        err_count = sum(1 for row in new_rows if row.get("status") == "error")
        print(
            f"[done] {idx}/{len(source_rows)} {source_row.source.label} "
            f"{source_row.texture_type} {source_row.method} {source_row.model} "
            f"{source_row.param_id}: ok_variants={ok_count} errors={err_count}",
            flush=True,
        )
        if args.write_every > 0 and idx % args.write_every == 0:
            write_outputs(args.output_dir, rows, top_rows)

    write_outputs(args.output_dir, rows, top_rows)
    print(f"[postprocess] long_csv={args.output_dir / 'postprocess_long.csv'}", flush=True)
    print(f"[postprocess] summary_csv={args.output_dir / 'postprocess_summary.csv'}", flush=True)
    print(f"[postprocess] best_csv={args.output_dir / 'postprocess_best_by_model.csv'}", flush=True)
    print(f"[postprocess] top_kld_faces_csv={args.output_dir / 'postprocess_top_kld_faces.csv'}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
