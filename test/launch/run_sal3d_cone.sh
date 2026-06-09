#!/usr/bin/env bash
# Batch launcher for SAL3D cone+raycast evaluation.
#
# Wraps reprojection_methods/cone_projection_on_mesh/eval_sal3d_cone.py.
# Runs one or more models sequentially; each produces a JSON report with
# metrics_vs_gt_covered_only (the valid benchmark section).
#
# Usage (local):
#   source test/env/local_paths.example.sh
#   bash test/launch/run_sal3d_cone.sh
#
# Usage (server, inside tmux):
#   source configs/server_vg_intellect.env
#   bash test/launch/run_sal3d_cone.sh
#
# Required env vars:
#   REPROJECT_DATASET_SAL3D_ROOT    — root of SAL3D_Dataset/
#   REPROJECT_GAZE_CSV_SAL3D_ROOT   — per-model gaze CSV files
#   REPROJECT_GAZE_JSON_SAL3D_ROOT  — per-model Sal3D_*.json camera files
#   REPROJECT_OUTPUT_ROOT           — writable output root
#
# Optional env vars (defaults shown):
#   PILOT_MODELS="bunny camel cow"  — space-separated list of models to run
#   SMOOTH_GAZE_DIR                 — path to Smooth_Gaze/ directory.
#                                     Defaults to REPROJECT_SAL3D_SMOOTH_GAZE_ROOT.
#                                     Set to "" to disable smoothing (raw GT only).
#   SMOOTH_RATIO=500                — max neighbours per fixated vertex
#   SIGMA_DEG=1.0
#   RADIUS_SIGMA_MULT=3.0
#   NICE_LEVEL=10
#   REPROJECT_PYTHON=python3

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
EVAL_SCRIPT="${REPO_ROOT}/reprojection_methods/cone_projection_on_mesh/eval_sal3d_cone.py"
PYTHON_BIN="${REPROJECT_PYTHON:-python3}"
REPROJECT_GAZE_JSON_SAL3D_ROOT="${REPROJECT_GAZE_JSON_SAL3D_ROOT:-${SAL3D_JSON_ROOT:-${REPO_ROOT}/jsons/object_placement/sal3d_jsons}}"

# ── required env var checks ──────────────────────────────────────────────────
CSV_COMPAT="${CSV_COMPAT:-false}"
FIXATION_ROOT="${FIXATION_ROOT:-${REPROJECT_PROCESSED_FIXATIONS_ROOT:-${SAL3D_PROCESSED_FIXATIONS_ROOT:-${REPROJECT_FIXATION_ROOT:-}}}}"
: "${REPROJECT_DATASET_SAL3D_ROOT:?Set REPROJECT_DATASET_SAL3D_ROOT}"
: "${REPROJECT_GAZE_JSON_SAL3D_ROOT:?Set REPROJECT_GAZE_JSON_SAL3D_ROOT}"
: "${REPROJECT_OUTPUT_ROOT:?Set REPROJECT_OUTPUT_ROOT}"
if [ "${CSV_COMPAT}" = "true" ]; then
  : "${REPROJECT_GAZE_CSV_SAL3D_ROOT:?Set REPROJECT_GAZE_CSV_SAL3D_ROOT when CSV_COMPAT=true}"
else
  : "${FIXATION_ROOT:?Set FIXATION_ROOT (or set CSV_COMPAT=true for legacy CSV mode)}"
fi

# ── defaults ─────────────────────────────────────────────────────────────────
PILOT_MODELS="${PILOT_MODELS:-bunny camel cow}"
SMOOTH_GAZE_DIR="${SMOOTH_GAZE_DIR:-${REPROJECT_SAL3D_SMOOTH_GAZE_ROOT:-}}"
SMOOTH_RATIO="${SMOOTH_RATIO:-500}"
SIGMA_DEG="${SIGMA_DEG:-1.0}"
RADIUS_SIGMA_MULT="${RADIUS_SIGMA_MULT:-3.0}"
NICE_LEVEL="${NICE_LEVEL:-10}"

if [ "${CSV_COMPAT}" = "true" ]; then
  GAZE_ARGS="--csv-compat --csv-root ${REPROJECT_GAZE_CSV_SAL3D_ROOT:-}"
else
  GAZE_ARGS="--fixation-root ${FIXATION_ROOT}"
fi

OUTPUT_DIR="${REPROJECT_OUTPUT_ROOT}/SAL3D/cone_raycast"
mkdir -p "${OUTPUT_DIR}"

# ── log startup banner ────────────────────────────────────────────────────────
echo "[run_sal3d_cone] repo_root=${REPO_ROOT}"
echo "[run_sal3d_cone] dataset_root=${REPROJECT_DATASET_SAL3D_ROOT}"
echo "[run_sal3d_cone] gaze_args=${GAZE_ARGS}"
echo "[run_sal3d_cone] json_root=${REPROJECT_GAZE_JSON_SAL3D_ROOT}"
echo "[run_sal3d_cone] output_dir=${OUTPUT_DIR}"
echo "[run_sal3d_cone] smooth_gaze_dir=${SMOOTH_GAZE_DIR:-<disabled>}"
echo "[run_sal3d_cone] smooth_ratio=${SMOOTH_RATIO}"
echo "[run_sal3d_cone] sigma_deg=${SIGMA_DEG}  radius_sigma_mult=${RADIUS_SIGMA_MULT}"
echo "[run_sal3d_cone] models: ${PILOT_MODELS}"

# ── build optional smooth-gaze args ──────────────────────────────────────────
SMOOTH_ARGS=()
if [ -n "${SMOOTH_GAZE_DIR}" ] && [ -d "${SMOOTH_GAZE_DIR}" ]; then
  SMOOTH_ARGS+=(--smooth-gaze-dir "${SMOOTH_GAZE_DIR}" --smooth-ratio "${SMOOTH_RATIO}")
  echo "[run_sal3d_cone] smoothing: ENABLED (${SMOOTH_GAZE_DIR})"
else
  echo "[run_sal3d_cone] smoothing: DISABLED (no Smooth_Gaze dir)"
fi

# ── per-model loop ────────────────────────────────────────────────────────────
for MODEL in ${PILOT_MODELS}; do
  echo ""
  echo "[run_sal3d_cone] === ${MODEL} ==="
  nice -n "${NICE_LEVEL}" "${PYTHON_BIN}" "${EVAL_SCRIPT}" \
    --model "${MODEL}" \
    --dataset-root    "${REPROJECT_DATASET_SAL3D_ROOT}" \
    ${GAZE_ARGS} \
    --json-root       "${REPROJECT_GAZE_JSON_SAL3D_ROOT}" \
    --output-dir      "${OUTPUT_DIR}" \
    --sigma-deg       "${SIGMA_DEG}" \
    --radius-sigma-mult "${RADIUS_SIGMA_MULT}" \
    --recenter-to-bbox-center \
    --extra-rotate-x-deg 90.0 \
    --projection-fov-mode horizontal_to_vertical \
    --transform-order blender_rig \
    "${SMOOTH_ARGS[@]}" \
    2>&1 | tee "${OUTPUT_DIR}/${MODEL}_run.log"

  echo "[run_sal3d_cone] ${MODEL} done."
done

echo ""
echo "[run_sal3d_cone] all done. results in ${OUTPUT_DIR}"
