#!/usr/bin/env bash
# Pilot launch for MeshMamba non_texture baseline: screen_space_gaussian.
#
# Wraps reprojection_methods/screen_space_gaussian/eval_meshmamba_screen_space.py.
# Accumulates gaze in a 2D density image, projects face centroids to screen per
# frame, samples the density, and compares against per-face GT CSV.
#
# Usage (on vg-intellect inside tmux):
#   source configs/server_vg_intellect.env
#   bash test/launch/run_meshmamba_baseline_screen_space.sh
#
# Required env vars:
#   MESHMAMBA_NON_TEXTURE_ROOT  — dataset root (MeshFile/non_texture, SaliencyMap/non_texture)
#   SIDE_INPUTS_ROOT            — root for mirrored CSV/JSON side inputs
#   OUTPUT_ROOT                 — writable output root
#
# Optional env vars (defaults shown):
#   WORKERS=4
#   NICE_LEVEL=10
#   PILOT_MODEL=Starfruit_L3
#   SIGMA_SCREEN=0.05          — Gaussian sigma as fraction of image width
#   RECENTER_TO_BBOX_CENTER=true
#   EXTRA_ROTATE_X_DEG=90
#   OVERRIDE_FOV_DEG=37.5
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
EVAL_SCRIPT="${REPO_ROOT}/reprojection_methods/screen_space_gaussian/eval_meshmamba_screen_space.py"

# ---------- required env var checks ----------
: "${MESHMAMBA_NON_TEXTURE_ROOT:?Set MESHMAMBA_NON_TEXTURE_ROOT (see configs/server_vg_intellect.env)}"
: "${SIDE_INPUTS_ROOT:?Set SIDE_INPUTS_ROOT}"
: "${OUTPUT_ROOT:?Set OUTPUT_ROOT}"

# ---------- defaults ----------
WORKERS="${WORKERS:-4}"
NICE_LEVEL="${NICE_LEVEL:-10}"
PILOT_MODEL="${PILOT_MODEL:-Starfruit_L3}"
SIGMA_SCREEN="${SIGMA_SCREEN:-0.05}"
RECENTER_TO_BBOX_CENTER="${RECENTER_TO_BBOX_CENTER:-true}"
EXTRA_ROTATE_X_DEG="${EXTRA_ROTATE_X_DEG:-90}"
OVERRIDE_FOV_DEG="${OVERRIDE_FOV_DEG:-37.5}"

CSV_DIR="${SIDE_INPUTS_ROOT}/MeshMamba_non_texture/csv"
JSON_DIR="${SIDE_INPUTS_ROOT}/MeshMamba_non_texture/json"
OUTPUT_DIR="${OUTPUT_ROOT}/MeshMamba_non_texture/baseline_screen_space"
mkdir -p "${OUTPUT_DIR}"

echo "[run_meshmamba_baseline_screen_space] repo_root=${REPO_ROOT}"
echo "[run_meshmamba_baseline_screen_space] dataset_root=${MESHMAMBA_NON_TEXTURE_ROOT}"
echo "[run_meshmamba_baseline_screen_space] csv_dir=${CSV_DIR}"
echo "[run_meshmamba_baseline_screen_space] json_dir=${JSON_DIR}"
echo "[run_meshmamba_baseline_screen_space] output_dir=${OUTPUT_DIR}"
echo "[run_meshmamba_baseline_screen_space] workers=${WORKERS}  nice=${NICE_LEVEL}"
echo "[run_meshmamba_baseline_screen_space] sigma_screen=${SIGMA_SCREEN}"
echo "[run_meshmamba_baseline_screen_space] recenter=${RECENTER_TO_BBOX_CENTER}  extra_rotate_x=${EXTRA_ROTATE_X_DEG}  override_fov=${OVERRIDE_FOV_DEG}"
echo "[run_meshmamba_baseline_screen_space] pilot_model=${PILOT_MODEL}"

if [ "${RECENTER_TO_BBOX_CENTER}" = "true" ]; then
  RECENTER_FLAG="--recenter-to-bbox-center"
else
  RECENTER_FLAG="--no-recenter-to-bbox-center"
fi

nice -n "${NICE_LEVEL}" python3 "${EVAL_SCRIPT}" \
  --model "${PILOT_MODEL}" \
  --dataset-root "${MESHMAMBA_NON_TEXTURE_ROOT}" \
  --csv-root "${CSV_DIR}" \
  --json-root "${JSON_DIR}" \
  --output-dir "${OUTPUT_DIR}" \
  --sigma-screen "${SIGMA_SCREEN}" \
  "${RECENTER_FLAG}" \
  --extra-rotate-x-deg "${EXTRA_ROTATE_X_DEG}" \
  --override-fov-deg "${OVERRIDE_FOV_DEG}" \
  2>&1 | tee "${OUTPUT_DIR}/${PILOT_MODEL}_run.log"

echo "[run_meshmamba_baseline_screen_space] done. results in ${OUTPUT_DIR}"
