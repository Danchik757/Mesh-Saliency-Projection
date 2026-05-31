#!/usr/bin/env bash
# Run screen_space_gaussian on 3DVA models (per-vertex output).
# Usage:
#   PILOT_OBJECTS="bunny A380 dragon" bash test/launch/run_3dva_screen_space.sh
#
# Required env vars (or set via configs/server_vg_intellect.env):
#   VISUAL_ATTENTION_3D_SHAPES_ROOT
#   THREE_DVA_CSV_ROOT
#   THREE_DVA_JSON_ROOT
#   OUTPUT_ROOT
#
# Optional:
#   PILOT_OBJECTS          — space-separated model list (default: top10 set)
#   SIGMA_SCREEN           — Gaussian sigma as fraction of image width (default: 0.05)
#   RECENTER_TO_BBOX_CENTER— true/false (default: true)
#   EXTRA_ROTATE_X_DEG     — extra X rotation in degrees (default: 0)
#   OVERRIDE_FOV_DEG       — override JSON FOV; empty = use JSON (default: empty)
#   WORKERS                — parallel workers (default: 4)
#   NICE_LEVEL             — nice priority (default: 10)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
EVAL_SCRIPT="${REPO_ROOT}/reprojection_methods/screen_space_gaussian/eval_3dva_screen_space.py"
PYTHON_BIN="${REPROJECT_PYTHON:-python3}"

: "${VISUAL_ATTENTION_3D_SHAPES_ROOT:?Need VISUAL_ATTENTION_3D_SHAPES_ROOT}"
: "${THREE_DVA_CSV_ROOT:?Need THREE_DVA_CSV_ROOT}"
: "${THREE_DVA_JSON_ROOT:?Need THREE_DVA_JSON_ROOT}"
: "${OUTPUT_ROOT:?Need OUTPUT_ROOT}"

PILOT_OBJECTS="${PILOT_OBJECTS:-A380 bunny car-vasa casting chair107 dragon fandisk flowerpot hand-35K turbine}"
SIGMA_SCREEN="${SIGMA_SCREEN:-0.05}"
RECENTER_TO_BBOX_CENTER="${RECENTER_TO_BBOX_CENTER:-true}"
EXTRA_ROTATE_X_DEG="${EXTRA_ROTATE_X_DEG:-0}"
OVERRIDE_FOV_DEG="${OVERRIDE_FOV_DEG:-}"
WORKERS="${WORKERS:-4}"
NICE_LEVEL="${NICE_LEVEL:-10}"

OUT_DIR="${OUTPUT_ROOT}/3DVA/screen_space"
mkdir -p "${OUT_DIR}"

# Build recenter flag
if [ "${RECENTER_TO_BBOX_CENTER}" = "true" ]; then
    RECENTER_FLAG="--recenter-to-bbox-center"
else
    RECENTER_FLAG="--no-recenter-to-bbox-center"
fi

# Build override-fov flag
FOV_FLAG=""
if [ -n "${OVERRIDE_FOV_DEG}" ]; then
    FOV_FLAG="--override-fov-deg ${OVERRIDE_FOV_DEG}"
fi

echo "=== 3DVA screen_space_gaussian ==="
echo "  dataset_root : ${VISUAL_ATTENTION_3D_SHAPES_ROOT}"
echo "  csv_root     : ${THREE_DVA_CSV_ROOT}"
echo "  json_root    : ${THREE_DVA_JSON_ROOT}"
echo "  output_dir   : ${OUT_DIR}"
echo "  python_bin   : ${PYTHON_BIN}"
echo "  sigma_screen : ${SIGMA_SCREEN}"
echo "  recenter     : ${RECENTER_TO_BBOX_CENTER}"
echo "  extra_rot_x  : ${EXTRA_ROTATE_X_DEG}"
echo "  override_fov : ${OVERRIDE_FOV_DEG:-<from JSON>}"
echo "  workers      : ${WORKERS}  nice : ${NICE_LEVEL}"
echo "  models       : ${PILOT_OBJECTS}"
echo ""

run_one() {
    local model="$1"
    local log="${OUT_DIR}/${model}_run.log"
    echo "[$(date +%H:%M:%S)] START ${model}" | tee -a "${log}"
    nice -n "${NICE_LEVEL}" "${PYTHON_BIN}" "${EVAL_SCRIPT}" \
        --model "${model}" \
        --dataset-root "${VISUAL_ATTENTION_3D_SHAPES_ROOT}" \
        --csv-root "${THREE_DVA_CSV_ROOT}" \
        --json-root "${THREE_DVA_JSON_ROOT}" \
        --output-dir "${OUT_DIR}" \
        --sigma-screen "${SIGMA_SCREEN}" \
        ${RECENTER_FLAG} \
        --extra-rotate-x-deg "${EXTRA_ROTATE_X_DEG}" \
        ${FOV_FLAG} \
        >> "${log}" 2>&1
    echo "[$(date +%H:%M:%S)] DONE  ${model}" | tee -a "${log}"
}

export -f run_one
export OUT_DIR EVAL_SCRIPT PYTHON_BIN VISUAL_ATTENTION_3D_SHAPES_ROOT THREE_DVA_CSV_ROOT \
       THREE_DVA_JSON_ROOT SIGMA_SCREEN RECENTER_FLAG FOV_FLAG EXTRA_ROTATE_X_DEG NICE_LEVEL

# Parallel pool
active=0
for model in ${PILOT_OBJECTS}; do
    run_one "${model}" &
    active=$((active + 1))
    if [ "${active}" -ge "${WORKERS}" ]; then
        wait -n 2>/dev/null || wait
        active=$((active - 1))
    fi
done
wait

echo ""
echo "=== All done. Logs in ${OUT_DIR}/*_run.log ==="
