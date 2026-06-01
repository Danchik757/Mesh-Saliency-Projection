#!/usr/bin/env bash
set -euo pipefail

DEFAULT_ROOT="/home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/outputs"
OUT="${OUT:-}"
LOG="${LOG:-}"

if [[ -z "$OUT" ]]; then
  OUT="$(find "$DEFAULT_ROOT" -maxdepth 1 -type d -name 'KLD_sweep_nightly_*' 2>/dev/null | sort | tail -1)"
fi
if [[ -z "$LOG" ]]; then
  LOG="$(find /tmp -maxdepth 1 -type f -name 'kld_sweep_nightly_*.log' 2>/dev/null | sort | tail -1)"
fi

echo "[monitor] output=${OUT:-missing}"
echo "[monitor] log=${LOG:-missing}"
echo "[monitor] tmux sessions:"
tmux ls 2>/dev/null | grep -E 'kld_sweep|sal3d_full|meshmamba_full' || true

if [[ -n "$OUT" && -d "$OUT" ]]; then
  echo "[monitor] reports=$(find "$OUT" -name '*_report.json' 2>/dev/null | wc -l)"
  if [[ -f "$OUT/kld_sweep_long.csv" ]]; then
    echo "[monitor] rows=$(tail -n +2 "$OUT/kld_sweep_long.csv" | wc -l)"
  fi
  if [[ -f "$OUT/kld_sweep_summary.csv" ]]; then
    echo "[monitor] summary head:"
    sed -n '1,12p' "$OUT/kld_sweep_summary.csv"
  fi
  if [[ -f "$OUT/kld_sweep_best_by_model.csv" ]]; then
    echo "[monitor] best rows:"
    sed -n '1,12p' "$OUT/kld_sweep_best_by_model.csv"
  fi
fi

if [[ -n "$LOG" && -f "$LOG" ]]; then
  echo "[monitor] log tail:"
  tail -40 "$LOG"
fi
