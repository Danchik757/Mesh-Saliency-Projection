#!/usr/bin/env python3
"""
Sigma sweep — metric vs sigma line plots.

One figure per metric × method (cone / screen_space), 2×2 grid of datasets.
Each panel shows mean ± stderr (shaded) ± std (lighter shaded), optimal sigma
marked with a gold star, and a vertical baseline reference line with annotation.

Usage
-----
python3 visualization/sigma_sweep_analysis/plot_sigma_curves.py \
    --jsonl  path/to/sigma_sweep_rows.jsonl \
    --out    path/to/output_plots/

Optional overrides
------------------
--metrics CC SIM KLD NSS AUC_Judd Spearman
--methods cone screen_space
--dpi 140
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
# x-axis position in the sweep (sigma_deg=1.0 / sigma_multiplier=1.0 for all)
# ---------------------------------------------------------------------------
REF_X: dict[str, float] = {"cone": 1.0, "screen_space": 1.0}

# Human-readable annotation shown on each panel (exact evaluator values)
REF_LABEL: dict[tuple[str, str], str] = {
    ("3dva",                  "cone"):         "baseline\nσ_deg=1.0",
    ("3dva",                  "screen_space"): "baseline\nσ_px=49.0\n(mult≈1.0)",
    ("sal3d",                 "cone"):         "baseline\nσ_deg=1.0",
    ("sal3d",                 "screen_space"): "baseline\nσ_px=26.3\n(mult=1.0)",
    ("meshmamba_non_texture", "cone"):         "baseline\nσ_deg=1.0",
    ("meshmamba_non_texture", "screen_space"): "baseline\nσ_screen=0.05\nσ_px=12.8",
    ("meshmamba_rgb_texture", "cone"):         "baseline\nσ_deg=1.0",
    ("meshmamba_rgb_texture", "screen_space"): "baseline\nσ_screen=0.05\nσ_px=12.8",
}

DATASETS = ["3dva", "meshmamba_non_texture", "meshmamba_rgb_texture", "sal3d"]
DS_LABELS = {
    "3dva":                  "3DVA",
    "meshmamba_non_texture": "MeshMamba  non-texture",
    "meshmamba_rgb_texture": "MeshMamba  rgb-texture",
    "sal3d":                 "SAL3D",
}
ALL_METRICS  = ["CC", "SIM", "KLD", "NSS", "AUC_Judd", "Spearman"]
METRIC_GOOD  = {"CC": "high", "SIM": "high", "KLD": "low",
                "NSS": "high", "AUC_Judd": "high", "Spearman": "high"}
METRIC_LABEL = {
    "CC":       "CC  (Correlation Coefficient)",
    "SIM":      "SIM  (Similarity)",
    "KLD":      "KLD  (Kullback-Leibler Divergence)",
    "NSS":      "NSS  (Normalized Scan-path Saliency)",
    "AUC_Judd": "AUC-Judd",
    "Spearman": "Spearman  ρ",
}
METHOD_COLOR = {"cone": "#2196F3", "screen_space": "#FF9800"}
REF_COLOR    = "#00FF88"


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
                "sigma_deg", "sigma_multiplier", "base_sigma"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    ok   = df[df["status"] == "ok"].copy()
    fail = df[df["status"] != "ok"].copy()
    return ok, fail


def curve_data(
    ok: pd.DataFrame, ds: str, method: str, metric: str
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    sigma_col  = "sigma_deg" if method == "cone" else "sigma_multiplier"
    sub        = ok[(ok["dataset"] == ds) & (ok["method"] == method)]
    sigma_vals = sorted(sub[sigma_col].dropna().unique())
    means, stds, ns = [], [], []
    for sv in sigma_vals:
        v = sub[sub[sigma_col] == sv][metric].dropna()
        means.append(v.mean()); stds.append(v.std()); ns.append(len(v))
    means  = np.array(means)
    stds   = np.array(stds)
    stderr = stds / np.sqrt(np.maximum(np.array(ns), 1))
    return np.array(sigma_vals), means, stds, stderr


def ss_base_sigma(ok: pd.DataFrame, ds: str) -> float | None:
    sub  = ok[(ok["dataset"] == ds) & (ok["method"] == "screen_space")]
    vals = sub["base_sigma"].dropna()
    return float(vals.iloc[0]) if len(vals) > 0 else None


def apply_dark_style() -> None:
    plt.rcParams.update({
        "figure.facecolor":  "#0d0d1a",
        "axes.facecolor":    "#111130",
        "axes.edgecolor":    "#aaaaaa",
        "axes.labelcolor":   "white",
        "xtick.color":       "white",
        "ytick.color":       "white",
        "text.color":        "white",
        "grid.color":        "#333355",
        "grid.alpha":        0.45,
        "legend.facecolor":  "#1a1a3a",
        "legend.edgecolor":  "#555588",
        "legend.labelcolor": "white",
        "font.size":         9,
    })


def plot_metric_method(
    ok: pd.DataFrame,
    fail: pd.DataFrame,
    metric: str,
    method: str,
    out_dir: Path,
    dpi: int = 140,
) -> Path:
    sigma_col   = "sigma_deg" if method == "cone" else "sigma_multiplier"
    xlabel_base = "σ_deg (degrees)" if method == "cone" else "σ  multiplier"
    col         = METHOD_COLOR[method]
    good_str    = "↑ higher=better" if METRIC_GOOD[metric] == "high" else "↓ lower=better"

    fig, axes = plt.subplots(2, 2, figsize=(13, 9), tight_layout=True)
    fig.patch.set_facecolor("#0d0d1a")
    fig.suptitle(
        f"{METRIC_LABEL[metric]}  vs  σ  —  {method}  ({good_str})",
        color="white", fontsize=12, y=1.01,
    )

    for ax, ds in zip(axes.flat, DATASETS):
        ax.set_facecolor("#111130")
        ax.set_title(DS_LABELS[ds], color="white", fontsize=10, pad=5)
        ax.grid(True, linestyle="--", alpha=0.35)

        sigma_vals, means, stds, stderr = curve_data(ok, ds, method, metric)
        if len(sigma_vals) == 0 or np.all(np.isnan(means)):
            ax.text(0.5, 0.5, "no data", transform=ax.transAxes,
                    ha="center", va="center", color="#888888")
            continue

        ax.plot(sigma_vals, means, "o-", color=col,
                linewidth=2.5, markersize=5, zorder=3, label="mean")
        ax.fill_between(sigma_vals, means - stderr, means + stderr,
                        alpha=0.35, color=col, linewidth=0, label="±stderr")
        ax.fill_between(sigma_vals, means - stds, means + stds,
                        alpha=0.12, color=col, linewidth=0, label="±std")

        best_i = (np.nanargmin(means) if METRIC_GOOD[metric] == "low"
                  else np.nanargmax(means))
        ax.plot(sigma_vals[best_i], means[best_i], "*",
                color="#FFD700", markersize=14, zorder=6,
                markeredgecolor="white", markeredgewidth=0.6,
                label=f"best  σ={sigma_vals[best_i]:.2f}")

        if method == "screen_space":
            b = ss_base_sigma(ok, ds)
            if b is not None:
                ax2 = ax.twiny()
                ax2.set_xlim(ax.get_xlim())
                ax2.set_xticks(sigma_vals)
                ax2.set_xticklabels([f"{v * b:.4f}" for v in sigma_vals],
                                    rotation=30, fontsize=6.5, color="#aaaacc")
                ax2.set_xlabel("effective  σ  (base × mult)", color="#aaaacc", fontsize=7)
                ax2.tick_params(colors="#aaaacc")

        # baseline reference line
        ref_x   = REF_X[method]
        ref_lbl = REF_LABEL.get((ds, method), f"baseline\nσ={ref_x:.1f}")

        ax.axvline(ref_x, color=REF_COLOR, linewidth=1.8,
                   linestyle="--", alpha=0.9, zorder=4)

        ref_y = (means[list(sigma_vals).index(ref_x)]
                 if ref_x in sigma_vals
                 else float(np.interp(ref_x, sigma_vals, means)))
        if not np.isnan(ref_y):
            ax.plot(ref_x, ref_y, "D", color=REF_COLOR,
                    markersize=8, zorder=7,
                    markeredgecolor="white", markeredgewidth=0.7)

        x_range  = sigma_vals[-1] - sigma_vals[0]
        if ref_x > sigma_vals[0] + x_range * 0.7:
            text_x, ha_align = ref_x - x_range * 0.03, "right"
        else:
            text_x, ha_align = ref_x + x_range * 0.03, "left"

        ylim = ax.get_ylim()
        ax.text(text_x, ylim[0] + (ylim[1] - ylim[0]) * 0.01,
                ref_lbl, color=REF_COLOR, fontsize=6.8,
                ha=ha_align, va="bottom",
                bbox=dict(facecolor="#001a0d", alpha=0.75,
                          pad=2, edgecolor=REF_COLOR, linewidth=0.8))

        # timeout annotation for sal3d/cart/cone
        if method == "cone" and ds == "sal3d":
            fail_sigs = (
                fail[(fail["dataset"] == "sal3d") & (fail["method"] == "cone") &
                     (fail["error_type"] == "timeout")]["sigma_deg"]
                .dropna().unique()
            )
            for fs in fail_sigs:
                ax.axvline(fs, color="#ff4444", linestyle=":", linewidth=1.0, alpha=0.7)
            if len(fail_sigs):
                ax.text(0.02, 0.97,
                        f"⚠  {len(fail_sigs)} timeout(s)  sal3d/cart/cone\n"
                        "(red dots = missing, not in mean)",
                        transform=ax.transAxes, color="#ff9999", fontsize=6.5,
                        va="top", ha="left",
                        bbox=dict(facecolor="#220000", alpha=0.8,
                                  pad=2, edgecolor="#ff4444", linewidth=0.8))

        ax.set_xlabel(xlabel_base, color="#cccccc", fontsize=8)
        ax.set_ylabel(METRIC_LABEL[metric], fontsize=8)
        ax.tick_params(colors="white", labelsize=8)
        for spine in ax.spines.values():
            spine.set_edgecolor("#444466")
        ax.legend(loc="best", fontsize=7.5, framealpha=0.6)

    for ax in axes.flat[len(DATASETS):]:
        ax.set_visible(False)

    fname = f"{metric.lower()}_vs_sigma_{method}.png"
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
    parser.add_argument("--dpi",     type=int, default=140)
    args = parser.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    apply_dark_style()

    ok, fail = load_data(args.jsonl)
    print(f"Loaded {len(ok)} ok rows, {len(fail)} failed rows")

    generated = []
    for method in args.methods:
        for metric in args.metrics:
            sub = ok[ok["method"] == method][metric].dropna()
            if len(sub) < 10:
                print(f"  skip {metric}/{method}: only {len(sub)} values")
                continue
            p = plot_metric_method(ok, fail, metric, method, args.out, args.dpi)
            print(f"  saved: {p.name}")
            generated.append(p)

    print(f"\n{len(generated)} plots → {args.out}")


if __name__ == "__main__":
    main()
