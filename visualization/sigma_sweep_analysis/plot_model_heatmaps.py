#!/usr/bin/env python3
"""
Sigma sweep — per-model × per-sigma heatmap tables.

One PNG per (dataset, method, metric): rows = models sorted by best cone-CC
(fixed order across all metrics), columns = sigma values, cell text = metric
value.  The baseline reference sigma column is highlighted in green.

Usage
-----
python3 visualization/sigma_sweep_analysis/plot_model_heatmaps.py \
    --jsonl  path/to/sigma_sweep_rows.jsonl \
    --out    path/to/output_heatmaps/

Optional overrides
------------------
--metrics CC SIM KLD NSS AUC_Judd Spearman
--methods cone screen_space
--dpi 130
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Reference sigma values from rc3_full_metrics_20260611_004003
# ---------------------------------------------------------------------------
REF_SIGMA_VAL: float = 1.0   # sigma_multiplier=1.0 or sigma_deg=1.0

REF_ANNOTATION: dict[tuple[str, str], str] = {
    ("3dva",                  "cone"):         "sigma_deg=1.0, r_mult=3.0",
    ("3dva",                  "screen_space"): "sigma_px=49.0  (≈49/1920=0.02552 screen)",
    ("sal3d",                 "cone"):         "sigma_deg=1.0, r_mult=3.0",
    ("sal3d",                 "screen_space"): "sigma_px=26.3  (≈26.3/1920=0.01370 screen)",
    ("meshmamba_non_texture", "cone"):         "sigma_deg=1.0, r_mult=3.0",
    ("meshmamba_non_texture", "screen_space"): "sigma_screen=0.05, sigma_px=12.8 (on 256×144)",
    ("meshmamba_rgb_texture", "cone"):         "sigma_deg=1.0, r_mult=3.0",
    ("meshmamba_rgb_texture", "screen_space"): "sigma_screen=0.05, sigma_px=12.8 (on 256×144)",
}

DATASETS    = ["3dva", "meshmamba_non_texture", "meshmamba_rgb_texture", "sal3d"]
DS_LABELS   = {
    "3dva":                  "3DVA",
    "meshmamba_non_texture": "MeshMamba  non-texture",
    "meshmamba_rgb_texture": "MeshMamba  rgb-texture",
    "sal3d":                 "SAL3D",
}
ALL_METRICS = ["CC", "SIM", "KLD", "NSS", "AUC_Judd", "Spearman"]
METRIC_GOOD = {"CC": "high", "SIM": "high", "KLD": "low",
               "NSS": "high", "AUC_Judd": "high", "Spearman": "high"}
REF_COLOR   = "#00FF88"


def load_data(jsonl_path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows = []
    with open(jsonl_path) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    df = pd.DataFrame(rows)
    for col in ["CC", "SIM", "KLD", "NSS", "AUC_Judd", "Spearman",
                "sigma_deg", "sigma_multiplier"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    ok   = df[df["status"] == "ok"].copy()
    fail = df[df["status"] != "ok"].copy()
    return ok, fail


def build_model_order(ok: pd.DataFrame) -> dict[str, list[str]]:
    """Stable model order per dataset: sorted by best CC (cone) descending."""
    order: dict[str, list[str]] = {}
    for ds in DATASETS:
        cone_sub = ok[(ok["dataset"] == ds) & (ok["method"] == "cone")]
        if len(cone_sub) == 0:
            order[ds] = sorted(ok[ok["dataset"] == ds]["model"].unique())
        else:
            best_cc = cone_sub.groupby("model")["CC"].max().sort_values(ascending=False)
            order[ds] = best_cc.index.tolist()
    return order


def plot_heatmap(
    ok: pd.DataFrame,
    fail: pd.DataFrame,
    model_order: dict[str, list[str]],
    ds: str,
    method: str,
    metric: str,
    out_dir: Path,
    dpi: int = 130,
) -> Path:
    sigma_col  = "sigma_deg" if method == "cone" else "sigma_multiplier"
    ref_annot  = REF_ANNOTATION.get((ds, method), f"σ={REF_SIGMA_VAL:.1f}")

    sub      = ok[(ok["dataset"] == ds) & (ok["method"] == method)].copy()
    fail_sub = fail[(fail["dataset"] == ds) & (fail["method"] == method)].copy()
    if len(sub) == 0:
        raise ValueError(f"No data for {ds}/{method}")

    models     = model_order[ds]
    n_models   = len(models)
    sigma_vals = sorted(sub[sigma_col].dropna().unique())
    n_sigma    = len(sigma_vals)
    ref_idx    = int(np.argmin([abs(sv - REF_SIGMA_VAL) for sv in sigma_vals]))

    pivot = sub.pivot_table(index="model", columns=sigma_col,
                            values=metric, aggfunc="mean")
    pivot = pivot.reindex(index=models, columns=sigma_vals)
    arr   = pivot.values.astype(float)

    vmin = np.nanpercentile(arr, 5)
    vmax = np.nanpercentile(arr, 95)
    if abs(vmax - vmin) < 1e-9:
        vmin -= 0.01; vmax += 0.01

    cmap = plt.get_cmap("YlOrRd_r" if METRIC_GOOD[metric] == "low" else "YlOrRd")

    fig_w = max(10, 1.6 + n_sigma * 0.70 + 2.2)
    fig_h = max(4,  1.4 + n_models * 0.38)
    fig, axes = plt.subplots(
        1, 2, figsize=(fig_w, fig_h),
        gridspec_kw={"width_ratios": [n_sigma, 1], "wspace": 0.03},
    )
    fig.patch.set_facecolor("#0d0d1a")
    ax_heat, ax_best = axes
    for ax in axes:
        ax.set_facecolor("#0d0d1a")

    im = ax_heat.imshow(arr, aspect="auto", cmap=cmap,
                        vmin=vmin, vmax=vmax, interpolation="nearest")

    for x in np.arange(-.5, n_sigma, 1):
        ax_heat.axvline(x, color="#1a1a2e", linewidth=0.5)
    for y in np.arange(-.5, n_models, 1):
        ax_heat.axhline(y, color="#1a1a2e", linewidth=0.5)

    ax_heat.axvspan(ref_idx - 0.5, ref_idx + 0.5,
                    color=REF_COLOR, alpha=0.15, zorder=1)

    best_col_idx = (pivot.idxmax(axis=1) if METRIC_GOOD[metric] == "high"
                    else pivot.idxmin(axis=1))

    for i, model in enumerate(models):
        for j, sv in enumerate(sigma_vals):
            v = arr[i, j]
            if np.isnan(v):
                is_fail = (model in fail_sub["model"].values and
                           sv in fail_sub[sigma_col].dropna().values)
                ax_heat.text(j, i, "T/O" if is_fail else "—",
                             ha="center", va="center", fontsize=6,
                             color="#cc0000" if is_fail else "#888888")
            else:
                ax_heat.text(j, i, f"{v:.3f}", ha="center", va="center",
                             fontsize=6.2, color="black", fontweight="bold")

        best_sv = best_col_idx.get(model)
        if best_sv in sigma_vals:
            ax_heat.add_patch(plt.Rectangle(
                (sigma_vals.index(best_sv) - 0.49, i - 0.49), 0.98, 0.98,
                fill=False, edgecolor="#FFD700", linewidth=1.4, zorder=10))

    ax_heat.add_patch(plt.Rectangle(
        (ref_idx - 0.49, -0.5), 0.98, n_models,
        fill=False, edgecolor=REF_COLOR, linewidth=2.0, zorder=11))

    xlabels = [f"{sv:.2f}" for sv in sigma_vals]
    xlabels[ref_idx] = f"{sigma_vals[ref_idx]:.2f}\n★ ref"
    ax_heat.set_xticks(range(n_sigma))
    ax_heat.set_xticklabels(xlabels, color="white", fontsize=7.5)
    ax_heat.get_xticklabels()[ref_idx].set_color(REF_COLOR)
    ax_heat.get_xticklabels()[ref_idx].set_fontweight("bold")
    ax_heat.xaxis.set_tick_params(length=0)
    ax_heat.set_xlabel("σ_deg" if method == "cone" else "σ_multiplier",
                       color="#cccccc", fontsize=8, labelpad=4)
    ax_heat.set_yticks(range(n_models))
    ax_heat.set_yticklabels(models, color="white", fontsize=7.5)
    ax_heat.yaxis.set_tick_params(length=0)
    for spine in ax_heat.spines.values():
        spine.set_edgecolor("#333355")

    best_per_model = (pivot.max(axis=1) if METRIC_GOOD[metric] == "high"
                      else pivot.min(axis=1)).reindex(models)
    ref_per_model  = pivot.iloc[:, ref_idx]
    best_vals = best_per_model.values.astype(float)
    ref_vals  = ref_per_model.values.astype(float)

    colors_bar = [cmap((v - vmin) / (vmax - vmin)) if not np.isnan(v)
                  else (0.2, 0.2, 0.2, 1) for v in best_vals]
    ax_best.barh(range(n_models), best_vals, color=colors_bar, height=0.65)
    for i, rv in enumerate(ref_vals):
        if not np.isnan(rv):
            ax_best.plot(rv, i, "|", color=REF_COLOR,
                         markersize=9, markeredgewidth=2.0, zorder=5)

    ax_best.set_yticks([])
    ax_best.set_ylim(-0.5, n_models - 0.5)
    ax_best.invert_yaxis()
    ax_best.set_facecolor("#111130")
    ax_best.tick_params(colors="white", labelsize=6.5)
    ax_best.set_xlim(min(0, np.nanmin(best_vals) - 0.05),
                     np.nanmax(best_vals) + 0.05)
    mean_best = np.nanmean(best_vals)
    mean_ref  = np.nanmean(ref_vals)
    ax_best.axvline(mean_best, color="#FFD700", linewidth=1.2, linestyle="--", alpha=0.8)
    ax_best.axvline(mean_ref,  color=REF_COLOR,  linewidth=1.2, linestyle=":",  alpha=0.8)
    ax_best.text(mean_best, n_models - 0.3, f"μ={mean_best:.3f}",
                 color="#FFD700", fontsize=5.5, ha="center", va="bottom")
    ax_best.text(mean_ref, -0.5, f"ref\n{mean_ref:.3f}",
                 color=REF_COLOR, fontsize=5.5, ha="center", va="top")
    ax_best.set_xlabel("best / ref", color="#cccccc", fontsize=7)
    for spine in ax_best.spines.values():
        spine.set_edgecolor("#333355")

    cbar = fig.colorbar(im, ax=axes, orientation="vertical",
                        fraction=0.018, pad=0.01, shrink=0.82)
    cbar.ax.yaxis.set_tick_params(color="white", labelcolor="white", labelsize=6.5)

    good_str = "↑ high=better" if METRIC_GOOD[metric] == "high" else "↓ low=better"
    fig.suptitle(
        f"{DS_LABELS[ds]}  │  {method}  │  {metric}  ({good_str})\n"
        f"rows: sorted by best cone-CC — same order across all metrics"
        f"   │   gold border = per-model optimal σ",
        color="white", fontsize=8.0, y=1.03,
    )
    fig.text(0.01, 0.995, f"★ reference (green):  {ref_annot}",
             color=REF_COLOR, fontsize=7.8,
             transform=fig.transFigure, va="top", ha="left")

    fname = f"{ds}_{method}_{metric}.png"
    out_path = out_dir / fname
    fig.savefig(out_path, dpi=dpi, bbox_inches="tight", facecolor="#0d0d1a")
    plt.close(fig)
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--jsonl",   type=Path, required=True,
                        help="Path to sigma_sweep_rows.jsonl (merged all shards)")
    parser.add_argument("--out",     type=Path, required=True,
                        help="Output directory for PNG files")
    parser.add_argument("--metrics", nargs="+", default=ALL_METRICS,
                        choices=ALL_METRICS, metavar="METRIC")
    parser.add_argument("--methods", nargs="+", default=["cone", "screen_space"],
                        choices=["cone", "screen_space"])
    parser.add_argument("--datasets", nargs="+", default=DATASETS,
                        choices=DATASETS, metavar="DATASET")
    parser.add_argument("--dpi",     type=int, default=130)
    args = parser.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({"font.size": 8, "font.family": "monospace"})

    ok, fail = load_data(args.jsonl)
    print(f"Loaded {len(ok)} ok rows, {len(fail)} failed rows")

    model_order = build_model_order(ok)
    print("Model order (first/last):")
    for ds, models in model_order.items():
        print(f"  {ds}: {len(models)} models  [{models[0]} … {models[-1]}]")

    generated = []
    for ds in args.datasets:
        for method in args.methods:
            for metric in args.metrics:
                sub = ok[(ok["dataset"] == ds) & (ok["method"] == method)][metric].dropna()
                if len(sub) < 5:
                    print(f"  skip {ds}/{method}/{metric}: only {len(sub)} values")
                    continue
                try:
                    p = plot_heatmap(ok, fail, model_order, ds, method, metric,
                                     args.out, args.dpi)
                    print(f"  saved: {p.name}")
                    generated.append(p)
                except Exception as exc:
                    print(f"  ERROR {ds}/{method}/{metric}: {exc}")

    print(f"\n{len(generated)} heatmaps → {args.out}")


if __name__ == "__main__":
    main()
