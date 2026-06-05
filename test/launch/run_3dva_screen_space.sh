#!/usr/bin/env bash
# Run screen_space_gaussian (v2) on 3DVA models (per-vertex output).
#
# v2 changes vs v1:
#   - density image: 1920×1080  (was 256×144)
#   - sigma: SIGMA_PX absolute pixels at 1920px (was SIGMA_SCREEN fraction of width)
#   - default sigma: 49 px ≈ 1° visual angle, 3DVA paper setup (was 0.05×256 = 96 px equiv — too wide)
#   - bilinear deposition + bilinear sampling (was nearest-neighbour)
#   - visibility-masked metrics reported alongside full-mesh metrics
#
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
#   PILOT_OBJECTS          — space-separated model list (default: all 32)
#   SIGMA_PX               — Gaussian sigma in pixels at 1920×1080 (default: 49.0)
#   RECENTER_TO_BBOX_CENTER— true/false (default: true)
#   EXTRA_ROTATE_X_DEG     — extra X rotation in degrees (default: 0)
#   OVERRIDE_FOV_DEG       — authoritative vertical FOV; default 35.9834
#   VIDEO_ID               — optional CSV session filter, e.g. A380
#   WORKERS                — parallel workers (default: 4)
#   NICE_LEVEL             — nice priority (default: 10)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
EVAL_SCRIPT="${REPO_ROOT}/reprojection_methods/screen_space_gaussian/eval_3dva_screen_space.py"
PYTHON_BIN="${REPROJECT_PYTHON:-python3}"
THREE_DVA_JSON_ROOT="${THREE_DVA_JSON_ROOT:-${REPROJECT_GAZE_JSON_3DVA_ROOT:-${REPO_ROOT}/jsons/object_placement/3dva_jsons}}"

: "${VISUAL_ATTENTION_3D_SHAPES_ROOT:?Need VISUAL_ATTENTION_3D_SHAPES_ROOT}"
: "${THREE_DVA_CSV_ROOT:?Need THREE_DVA_CSV_ROOT}"
: "${THREE_DVA_JSON_ROOT:?Need THREE_DVA_JSON_ROOT}"
: "${OUTPUT_ROOT:?Need OUTPUT_ROOT}"

# All 32 3DVA models
ALL_MODELS="A380 Harley Max-Planck bimba blade-200K bunny camel car-vasa carter casting chair107 cow dinosaur-40K dragon fandisk flowerpot gorgoile hand-35K horse-110k house igea-100K james jessi meca-15k michael3 michael8 octopus prot rockerarm torso turbine vase-15k"
PILOT_OBJECTS="${PILOT_OBJECTS:-${ALL_MODELS}}"
SIGMA_PX="${SIGMA_PX:-49.0}"
RECENTER_TO_BBOX_CENTER="${RECENTER_TO_BBOX_CENTER:-true}"
EXTRA_ROTATE_X_DEG="${EXTRA_ROTATE_X_DEG:-0}"
OVERRIDE_FOV_DEG="${OVERRIDE_FOV_DEG:-35.9834}"
VIDEO_ID="${VIDEO_ID:-}"
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

# Build override-fov/video-id flags
FOV_FLAG=""
if [ -n "${OVERRIDE_FOV_DEG}" ]; then
    FOV_FLAG="--override-fov-deg ${OVERRIDE_FOV_DEG}"
fi
VIDEO_ID_FLAG=""
if [ -n "${VIDEO_ID}" ]; then
    VIDEO_ID_FLAG="--video-id ${VIDEO_ID}"
fi

echo "=== 3DVA screen_space_gaussian v2 ==="
echo "  dataset_root : ${VISUAL_ATTENTION_3D_SHAPES_ROOT}"
echo "  csv_root     : ${THREE_DVA_CSV_ROOT}"
echo "  json_root    : ${THREE_DVA_JSON_ROOT}"
echo "  output_dir   : ${OUT_DIR}"
echo "  python_bin   : ${PYTHON_BIN}"
echo "  sigma_px     : ${SIGMA_PX}  (v2: absolute px at 1920px; 49=1° viz angle)"
echo "  recenter     : ${RECENTER_TO_BBOX_CENTER}"
echo "  extra_rot_x  : ${EXTRA_ROTATE_X_DEG}"
echo "  override_fov : ${OVERRIDE_FOV_DEG}"
echo "  video_id     : ${VIDEO_ID:-<all>}"
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
        --sigma-px "${SIGMA_PX}" \
        ${RECENTER_FLAG} \
        --extra-rotate-x-deg "${EXTRA_ROTATE_X_DEG}" \
        ${FOV_FLAG} \
        ${VIDEO_ID_FLAG} \
        >> "${log}" 2>&1
    echo "[$(date +%H:%M:%S)] DONE  ${model}" | tee -a "${log}"
}

export -f run_one
export OUT_DIR EVAL_SCRIPT PYTHON_BIN VISUAL_ATTENTION_3D_SHAPES_ROOT THREE_DVA_CSV_ROOT \
       THREE_DVA_JSON_ROOT SIGMA_SCREEN RECENTER_FLAG FOV_FLAG VIDEO_ID_FLAG EXTRA_ROTATE_X_DEG NICE_LEVEL

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
