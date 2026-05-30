#!/usr/bin/env bash
# Pilot launch for 3DVA raycast_nearest_vertex and cone_gaussian_on_mesh methods.
#
# Wraps reprojection_methods/cone_projection_on_mesh/eval_3dva_raycast_cone.py.
# Each model run produces a JSON report comparing both methods against GT views
# 300, 413, 599 and saves per-vertex saliency maps.
#
# Usage (local or on vg-intellect inside tmux):
#   source configs/server_vg_intellect.env
#   bash test/launch/run_3dva_raycast_cone.sh
#
# Required env vars:
#   VISUAL_ATTENTION_3D_SHAPES_ROOT  — root of the published 3DVA dataset
#   THREE_DVA_CSV_ROOT               — directory with per-model 3DVA CSV gaze files
#   THREE_DVA_JSON_ROOT              — directory with per-model 3DVA JSON camera files
#   OUTPUT_ROOT                      — writable output root
#
# Optional env vars (defaults shown):
#   WORKERS=4              — max parallel model evaluations (each eval is CPU-heavy)
#   NICE_LEVEL=10          — nice priority
#   PILOT_OBJECTS="bunny"
#   SIGMA_DEG=1.0          — cone Gaussian angular sigma (degrees)
#   RADIUS_SIGMA_MULT=3.0  — cone Gaussian query radius multiplier
#   RECENTER_TO_BBOX_CENTER=false
#   EXTRA_ROTATE_X_DEG=0.0
#   OVERRIDE_FOV_DEG=""    — leave empty to use JSON FOV
#
# Per-model geometry calibration notes:
#   Per-model overrides must currently be applied by running the script once per
#   model with the appropriate env vars set, or by calling eval_3dva_raycast_cone.py
#   directly with --recenter-to-bbox-center / --extra-rotate-x-deg / --override-fov-deg.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
EVAL_SCRIPT="${REPO_ROOT}/reprojection_methods/cone_projection_on_mesh/eval_3dva_raycast_cone.py"

# ---------- required env var checks ----------
: "${VISUAL_ATTENTION_3D_SHAPES_ROOT:?Set VISUAL_ATTENTION_3D_SHAPES_ROOT (see configs/server_vg_intellect.env)}"
: "${THREE_DVA_CSV_ROOT:?Set THREE_DVA_CSV_ROOT to the directory with per-model 3DVA CSV gaze files}"
: "${THREE_DVA_JSON_ROOT:?Set THREE_DVA_JSON_ROOT to the directory with per-model 3DVA JSON camera files}"
: "${OUTPUT_ROOT:?Set OUTPUT_ROOT}"

# ---------- defaults ----------
WORKERS="${WORKERS:-4}"
NICE_LEVEL="${NICE_LEVEL:-10}"
# Keep the default to a single validated model. Other 3DVA objects still need
# per-model geometry verification before their metrics are comparable.
PILOT_OBJECTS="${PILOT_OBJECTS:-bunny}"
SIGMA_DEG="${SIGMA_DEG:-1.0}"
RADIUS_SIGMA_MULT="${RADIUS_SIGMA_MULT:-3.0}"
RECENTER_TO_BBOX_CENTER="${RECENTER_TO_BBOX_CENTER:-false}"
EXTRA_ROTATE_X_DEG="${EXTRA_ROTATE_X_DEG:-0.0}"
OVERRIDE_FOV_DEG="${OVERRIDE_FOV_DEG:-}"

OUTPUT_DIR="${OUTPUT_ROOT}/3DVA/raycast_cone"
mkdir -p "${OUTPUT_DIR}"

echo "[run_3dva_raycast_cone] repo_root=${REPO_ROOT}"
echo "[run_3dva_raycast_cone] dataset_root=${VISUAL_ATTENTION_3D_SHAPES_ROOT}"
echo "[run_3dva_raycast_cone] csv_root=${THREE_DVA_CSV_ROOT}"
echo "[run_3dva_raycast_cone] json_root=${THREE_DVA_JSON_ROOT}"
echo "[run_3dva_raycast_cone] output_dir=${OUTPUT_DIR}"
echo "[run_3dva_raycast_cone] workers=${WORKERS}  nice=${NICE_LEVEL}"
echo "[run_3dva_raycast_cone] sigma_deg=${SIGMA_DEG}  radius_sigma_mult=${RADIUS_SIGMA_MULT}"
echo "[run_3dva_raycast_cone] recenter=${RECENTER_TO_BBOX_CENTER}  extra_rotate_x=${EXTRA_ROTATE_X_DEG}  override_fov=${OVERRIDE_FOV_DEG:-<from_json>}"
echo "[run_3dva_raycast_cone] objects=${PILOT_OBJECTS}"

build_recenter_flag() {
  if [ "${RECENTER_TO_BBOX_CENTER}" = "true" ]; then
    echo "--recenter-to-bbox-center"
  else
    echo "--no-recenter-to-bbox-center"
  fi
}

run_model() {
  local model="$1"
  local extra_args=()

  if [ -n "${OVERRIDE_FOV_DEG}" ]; then
    extra_args+=(--override-fov-deg "${OVERRIDE_FOV_DEG}")
  fi

  echo "[run_3dva_raycast_cone] starting model=${model} ..."
  nice -n "${NICE_LEVEL}" python3 "${EVAL_SCRIPT}" \
    --model "${model}" \
    --dataset-root "${VISUAL_ATTENTION_3D_SHAPES_ROOT}" \
    --csv-root "${THREE_DVA_CSV_ROOT}" \
    --json-root "${THREE_DVA_JSON_ROOT}" \
    --output-dir "${OUTPUT_DIR}" \
    --sigma-deg "${SIGMA_DEG}" \
    --radius-sigma-mult "${RADIUS_SIGMA_MULT}" \
    "$(build_recenter_flag)" \
    --extra-rotate-x-deg "${EXTRA_ROTATE_X_DEG}" \
    "${extra_args[@]}" \
    2>&1 | tee "${OUTPUT_DIR}/${model}_run.log"
  echo "[run_3dva_raycast_cone] finished model=${model}"
}

for MODEL in ${PILOT_OBJECTS}; do
  while [ "$(jobs -pr | wc -l | tr -d ' ')" -ge "${WORKERS}" ]; do
    sleep 2
  done
  run_model "${MODEL}" &
done
wait

echo "[run_3dva_raycast_cone] all done. results in ${OUTPUT_DIR}"
