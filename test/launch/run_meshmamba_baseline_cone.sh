#!/usr/bin/env bash
# Pilot launch for MeshMamba non_texture baseline:
#   raycast_nearest_face + cone_gaussian_on_mesh (face-level).
#
# Wraps reprojection_methods/cone_projection_on_mesh/eval_meshmamba_cone.py.
# Each model run produces a JSON report with metrics vs per-face GT and saves
# per-face saliency maps.
#
# Usage (on vg-intellect inside tmux):
#   source configs/server_vg_intellect.env
#   bash test/launch/run_meshmamba_baseline_cone.sh
#
# Required env vars:
#   MESHMAMBA_NON_TEXTURE_ROOT  — dataset root (MeshFile/non_texture, SaliencyMap/non_texture)
#   SIDE_INPUTS_ROOT            — root for mirrored CSV/JSON side inputs
#   OUTPUT_ROOT                 — writable output root
#
# Optional env vars (defaults shown):
#   WORKERS=4              — max parallel model evaluations
#   NICE_LEVEL=10
#   PILOT_MODEL=Starfruit_L3
#   SIGMA_DEG=1.0
#   RADIUS_SIGMA_MULT=3.0
#   RECENTER_TO_BBOX_CENTER=true
#   BASE_ROTATE_Z_DEG=0
#   EXTRA_ROTATE_X_DEG=90
#   OVERRIDE_FOV_DEG=37.5
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
EVAL_SCRIPT="${REPO_ROOT}/reprojection_methods/cone_projection_on_mesh/eval_meshmamba_cone.py"
PYTHON_BIN="${REPROJECT_PYTHON:-python3}"

# ---------- required env var checks ----------
: "${MESHMAMBA_NON_TEXTURE_ROOT:?Set MESHMAMBA_NON_TEXTURE_ROOT (see configs/server_vg_intellect.env)}"
: "${SIDE_INPUTS_ROOT:?Set SIDE_INPUTS_ROOT}"
: "${OUTPUT_ROOT:?Set OUTPUT_ROOT}"

# ---------- defaults ----------
WORKERS="${WORKERS:-4}"
NICE_LEVEL="${NICE_LEVEL:-10}"
PILOT_MODEL="${PILOT_MODEL:-Starfruit_L3}"
SIGMA_DEG="${SIGMA_DEG:-1.0}"
RADIUS_SIGMA_MULT="${RADIUS_SIGMA_MULT:-3.0}"
RECENTER_TO_BBOX_CENTER="${RECENTER_TO_BBOX_CENTER:-true}"
BASE_ROTATE_Z_DEG="${BASE_ROTATE_Z_DEG:-0}"
EXTRA_ROTATE_X_DEG="${EXTRA_ROTATE_X_DEG:-90}"
OVERRIDE_FOV_DEG="${OVERRIDE_FOV_DEG:-37.5}"

CSV_DIR="${SIDE_INPUTS_ROOT}/MeshMamba_non_texture/csv"
JSON_DIR="${SIDE_INPUTS_ROOT}/MeshMamba_non_texture/json"
OUTPUT_DIR="${OUTPUT_ROOT}/MeshMamba_non_texture/baseline_cone"
mkdir -p "${OUTPUT_DIR}"

echo "[run_meshmamba_baseline_cone] repo_root=${REPO_ROOT}"
echo "[run_meshmamba_baseline_cone] dataset_root=${MESHMAMBA_NON_TEXTURE_ROOT}"
echo "[run_meshmamba_baseline_cone] csv_dir=${CSV_DIR}"
echo "[run_meshmamba_baseline_cone] json_dir=${JSON_DIR}"
echo "[run_meshmamba_baseline_cone] output_dir=${OUTPUT_DIR}"
echo "[run_meshmamba_baseline_cone] python_bin=${PYTHON_BIN}"
echo "[run_meshmamba_baseline_cone] workers=${WORKERS}  nice=${NICE_LEVEL}"
echo "[run_meshmamba_baseline_cone] sigma_deg=${SIGMA_DEG}  radius_sigma_mult=${RADIUS_SIGMA_MULT}"
echo "[run_meshmamba_baseline_cone] recenter=${RECENTER_TO_BBOX_CENTER}  base_rotate_z=${BASE_ROTATE_Z_DEG}  extra_rotate_x=${EXTRA_ROTATE_X_DEG}  override_fov=${OVERRIDE_FOV_DEG}"
echo "[run_meshmamba_baseline_cone] pilot_model=${PILOT_MODEL}"

if [ "${RECENTER_TO_BBOX_CENTER}" = "true" ]; then
  RECENTER_FLAG="--recenter-to-bbox-center"
else
  RECENTER_FLAG="--no-recenter-to-bbox-center"
fi

nice -n "${NICE_LEVEL}" "${PYTHON_BIN}" "${EVAL_SCRIPT}" \
  --model "${PILOT_MODEL}" \
  --dataset-root "${MESHMAMBA_NON_TEXTURE_ROOT}" \
  --csv-root "${CSV_DIR}" \
  --json-root "${JSON_DIR}" \
  --output-dir "${OUTPUT_DIR}" \
  --sigma-deg "${SIGMA_DEG}" \
  --radius-sigma-mult "${RADIUS_SIGMA_MULT}" \
  "${RECENTER_FLAG}" \
  --base-rotate-z-deg "${BASE_ROTATE_Z_DEG}" \
  --extra-rotate-x-deg "${EXTRA_ROTATE_X_DEG}" \
  --override-fov-deg "${OVERRIDE_FOV_DEG}" \
  2>&1 | tee "${OUTPUT_DIR}/${PILOT_MODEL}_run.log"

echo "[run_meshmamba_baseline_cone] done. results in ${OUTPUT_DIR}"
