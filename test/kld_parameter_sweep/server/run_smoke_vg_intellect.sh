#!/usr/bin/env bash
set -euo pipefail

REPO="${REPO:-/home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/Mesh-Saliency-Projection}"
cd "$REPO"

source configs/server_vg_intellect.env

export SAL3D_DATASET_ROOT="${SAL3D_DATASET_ROOT:-/home/29d_kon@lab.graphicon.ru/ssd1_link/datasets/reproject_release_v1/SAL3D}"
export SAL3D_CSV_ROOT="${SAL3D_CSV_ROOT:-/home/29d_kon@lab.graphicon.ru/ssd1_link/datasets/reproject_release_v1/gaze_csv/SAL3D}"
export SAL3D_JSON_ROOT="${SAL3D_JSON_ROOT:-${REPO_ROOT}/jsons/sal3d_jsons}"
export SAL3D_SMOOTH_GAZE_DIR="${SAL3D_SMOOTH_GAZE_DIR:-/home/29d_kon@lab.graphicon.ru/ssd1_link/datasets/reproject_release_v1/SAL3D/Smooth_Gaze}"

export OMP_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export MKL_NUM_THREADS=1
export NUMEXPR_NUM_THREADS=1

RUN_ID="$(date +%Y%m%d_%H%M%S)"
OUT="${OUT:-/home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/outputs/KLD_sweep_smoke_${RUN_ID}}"

"$REPROJECT_PYTHON" test/kld_parameter_sweep/run_kld_parameter_sweep.py \
  --datasets sal3d meshmamba \
  --methods screen_space cone \
  --texture-types non_texture \
  --sal3d-models bunny A380 \
  --meshmamba-models Pear_L3 Flying_saucer_v1_L3 \
  --sal3d-screen-sigma-px 13.15,26.3 \
  --meshmamba-screen-sigma 0.025,0.05 \
  --cone-sigma-deg 1,3 \
  --cone-radius-sigma-mult 3,7 \
  --workers "${WORKERS:-4}" \
  --nice-level "${NICE_LEVEL:-10}" \
  --batch-output-dir "$OUT" \
  --smooth-gaze-dir "$SAL3D_SMOOTH_GAZE_DIR"

echo "[smoke] output=$OUT"
python3 - <<PY
import csv
from pathlib import Path
out = Path("$OUT")
rows = list(csv.DictReader((out / "kld_sweep_long.csv").open()))
bad = [r for r in rows if r["status"] != "ok"]
print(f"[smoke] rows={len(rows)} bad={len(bad)}")
print("[smoke] summary=", out / "kld_sweep_summary.csv")
raise SystemExit(1 if bad else 0)
PY
