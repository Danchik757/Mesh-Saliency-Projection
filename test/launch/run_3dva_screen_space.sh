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
#   PROJECTION_FOV_MODE    — vertical | horizontal_to_vertical | json (default: horizontal_to_vertical)
#   OVERRIDE_FOV_DEG       — optional FOV override interpreted by PROJECTION_FOV_MODE
#   VIDEO_ID               — optional CSV session filter, e.g. A380
#   WORKERS                — parallel workers (default: 4)
#   NICE_LEVEL             — nice priority (default: 10)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
EVAL_SCRIPT="${REPO_ROOT}/reprojection_methods/screen_space_gaussian/eval_3dva_screen_space.py"
PYTHON_BIN="${REPROJECT_PYTHON:-python3}"
THREE_DVA_JSON_ROOT="${THREE_DVA_JSON_ROOT:-${REPROJECT_GAZE_JSON_3DVA_ROOT:-${REPO_ROOT}/jsons/object_placement/3dva_jsons}}"

CSV_COMPAT="${CSV_COMPAT:-false}"
FIXATION_ROOT="${FIXATION_ROOT:-${REPROJECT_PROCESSED_FIXATIONS_ROOT:-${THREE_DVA_PROCESSED_FIXATIONS_ROOT:-${REPROJECT_FIXATION_ROOT:-}}}}"
: "${VISUAL_ATTENTION_3D_SHAPES_ROOT:?Need VISUAL_ATTENTION_3D_SHAPES_ROOT}"
: "${THREE_DVA_JSON_ROOT:?Need THREE_DVA_JSON_ROOT}"
: "${OUTPUT_ROOT:?Need OUTPUT_ROOT}"
if [ "${CSV_COMPAT}" = "true" ]; then
    : "${THREE_DVA_CSV_ROOT:?Need THREE_DVA_CSV_ROOT when CSV_COMPAT=true}"
else
    : "${FIXATION_ROOT:?Need FIXATION_ROOT (or set CSV_COMPAT=true for legacy CSV mode)}"
fi

# All 32 3DVA models
ALL_MODELS="A380 Harley Max-Planck bimba blade-200K bunny camel car-vasa carter casting chair107 cow dinosaur-40K dragon fandisk flowerpot gorgoile hand-35K horse-110k house igea-100K james jessi meca-15k michael3 michael8 octopus prot rockerarm torso turbine vase-15k"
PILOT_OBJECTS="${PILOT_OBJECTS:-${ALL_MODELS}}"
SIGMA_PX="${SIGMA_PX:-49.0}"
RECENTER_TO_BBOX_CENTER="${RECENTER_TO_BBOX_CENTER:-true}"
EXTRA_ROTATE_X_DEG="${EXTRA_ROTATE_X_DEG:-0}"
PROJECTION_FOV_MODE="${PROJECTION_FOV_MODE:-horizontal_to_vertical}"
OVERRIDE_FOV_DEG="${OVERRIDE_FOV_DEG:-}"
VIDEO_ID="${VIDEO_ID:-}"
WORKERS="${WORKERS:-4}"
NICE_LEVEL="${NICE_LEVEL:-10}"

if [ "${CSV_COMPAT}" = "true" ]; then
    GAZE_ARGS="--csv-compat --csv-root ${THREE_DVA_CSV_ROOT:-}"
else
    GAZE_ARGS="--fixation-root ${FIXATION_ROOT}"
fi

OUT_DIR="${OUTPUT_ROOT}/3DVA/screen_space"
mkdir -p "${OUT_DIR}"

# Build recenter flag
if [ "${RECENTER_TO_BBOX_CENTER}" = "true" ]; then
    RECENTER_FLAG="--recenter-to-bbox-center"
else
    RECENTER_FLAG="--no-recenter-to-bbox-center"
fi

# Build projection/video-id flags
PROJECTION_FLAGS=(--projection-fov-mode "${PROJECTION_FOV_MODE}")
if [ -n "${OVERRIDE_FOV_DEG}" ]; then
    PROJECTION_FLAGS+=(--override-fov-deg "${OVERRIDE_FOV_DEG}")
fi
VIDEO_ID_FLAG=""
if [ -n "${VIDEO_ID}" ]; then
    VIDEO_ID_FLAG="--video-id ${VIDEO_ID}"
fi

echo "=== 3DVA screen_space_gaussian v2 ==="
echo "  dataset_root : ${VISUAL_ATTENTION_3D_SHAPES_ROOT}"
echo "  gaze_args    : ${GAZE_ARGS}"
echo "  json_root    : ${THREE_DVA_JSON_ROOT}"
echo "  output_dir   : ${OUT_DIR}"
echo "  python_bin   : ${PYTHON_BIN}"
echo "  sigma_px     : ${SIGMA_PX}  (v2: absolute px at 1920px; 49=1° viz angle)"
echo "  recenter     : ${RECENTER_TO_BBOX_CENTER}"
echo "  extra_rot_x  : ${EXTRA_ROTATE_X_DEG}"
echo "  projection_fov_mode : ${PROJECTION_FOV_MODE}"
echo "  override_fov        : ${OVERRIDE_FOV_DEG:-<json/default>}"
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
        ${GAZE_ARGS} \
        --json-root "${THREE_DVA_JSON_ROOT}" \
        --output-dir "${OUT_DIR}" \
        --sigma-px "${SIGMA_PX}" \
        ${RECENTER_FLAG} \
        --extra-rotate-x-deg "${EXTRA_ROTATE_X_DEG}" \
        "${PROJECTION_FLAGS[@]}" \
        ${VIDEO_ID_FLAG} \
        >> "${log}" 2>&1
    echo "[$(date +%H:%M:%S)] DONE  ${model}" | tee -a "${log}"
}

export -f run_one
export OUT_DIR EVAL_SCRIPT PYTHON_BIN VISUAL_ATTENTION_3D_SHAPES_ROOT GAZE_ARGS \
       THREE_DVA_JSON_ROOT SIGMA_PX RECENTER_FLAG VIDEO_ID_FLAG EXTRA_ROTATE_X_DEG \
       PROJECTION_FOV_MODE OVERRIDE_FOV_DEG NICE_LEVEL

# Parallel pool
active=0
failures=0
for model in ${PILOT_OBJECTS}; do
    run_one "${model}" &
    active=$((active + 1))
    if [ "${active}" -ge "${WORKERS}" ]; then
        if ! wait -n; then
            failures=$((failures + 1))
        fi
        active=$((active - 1))
    fi
done
while [ "${active}" -gt 0 ]; do
    if ! wait -n; then
        failures=$((failures + 1))
    fi
    active=$((active - 1))
done

if [ "${failures}" -ne 0 ]; then
    echo "ERROR: ${failures} model run(s) failed. Inspect ${OUT_DIR}/*_run.log." >&2
    exit 1
fi

echo ""
echo "=== All done. Logs in ${OUT_DIR}/*_run.log ==="
