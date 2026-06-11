#!/usr/bin/env bash
# rc3 sigma sweep — shard 2 of 3 — vg-gml02
#
# Shard:   2 / 3  (1630 jobs)
# Workers: 40
# Session: rc3_sigma_shard2
#
# Sigma grids:
#   screen_space sigma_screen: 0.006 0.008 0.010 0.014 0.020 0.025 0.035 0.050 0.065 0.080 0.100 0.125
#   cone sigma_deg:            0.15 0.25 0.35 0.50 0.75 1.00 1.50 2.00 3.00 4.00
#   cone radius_sigma_mult:    2.0 3.0 4.0
#
# Fixed timing: one_turn_from_start, delay=0.0, frame_offset=0, cut_tail
#
# REQUIRES:
#   1. preflight_ablation.sh ran without errors on this server.
#   2. RUN_ID agreed with controller and exported identically on all servers.
#   3. Reviewer/controller explicit start authorisation.
#
# Usage:
#   export REPROJECT_SERVER_ROOT=/mnt/ssd1/29d_kon/acm_2026
#   export RUN_ID=rc3_sigma_sweep_YYYYMMDD_HHMMSS
#   bash server/launch_sigma_shard2_vg_gml02.sh
#
# Do NOT execute before reviewer says "start".

set -euo pipefail

: "${REPROJECT_SERVER_ROOT:?Set REPROJECT_SERVER_ROOT before running}"
: "${RUN_ID:?Set RUN_ID=rc3_sigma_sweep_YYYYMMDD_HHMMSS before running}"

SHARD_INDEX=2
NUM_SHARDS=3
WORKERS=40
SESSION="rc3_sigma_shard2"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPROJECT_WORKSPACE_NAME="${REPROJECT_WORKSPACE_NAME:-coordinator}"

export REPROJECT_SERVER_ROOT REPROJECT_WORKSPACE_NAME
export RUN_ID SHARD_INDEX

source "${SCRIPT_DIR}/rc3_ablation_env.sh"

# Override output dir for sigma sweep
export BATCH_OUTPUT_DIR="${REPROJECT_SERVER_ROOT}/outputs/sigma_sweep/${RUN_ID}/shard_${SHARD_INDEX}_of_3"

mkdir -p "${BATCH_OUTPUT_DIR}"
echo "[launch] server:      vg-gml02"
echo "[launch] session:     ${SESSION}"
echo "[launch] run_id:      ${RUN_ID}"
echo "[launch] shard:       ${SHARD_INDEX} / ${NUM_SHARDS}  (1630 jobs)"
echo "[launch] workers:     ${WORKERS}"
echo "[launch] output:      ${BATCH_OUTPUT_DIR}"
echo "[launch] head:        $(git -C "${REPO_ROOT}" rev-parse --short HEAD)"
echo "[launch] fixation:    ${FIXATION_ROOT}"
echo "[launch] release:     ${REPROJECT_RELEASE_TAG} → ${RELEASE_DATA_ROOT}"
echo ""

echo "[launch] command: nice -n 0 ${REPROJECT_PYTHON} ${REPO_ROOT}/test/launch/run_sigma_sweep_rc3.py \\"
echo "  --workers ${WORKERS} --shard-index ${SHARD_INDEX} --num-shards ${NUM_SHARDS} \\"
echo "  --batch-output-dir ${BATCH_OUTPUT_DIR}"
echo ""

if tmux has-session -t "${SESSION}" 2>/dev/null; then
    echo "[launch] tmux session '${SESSION}' already exists — attach with:"
    echo "  tmux attach -t ${SESSION}"
    exit 1
fi

INNER_CMD="cd '${REPO_ROOT}' && \
  export FIXATION_ROOT='${FIXATION_ROOT}' && \
  export REPROJECT_PROCESSED_FIXATIONS_ROOT='${FIXATION_ROOT}' && \
  export REPROJECT_FIXATION_DATA_TAG='${REPROJECT_FIXATION_DATA_TAG}' && \
  export REPROJECT_TIMING_CONTRACT='${REPROJECT_TIMING_CONTRACT}' && \
  export THREE_DVA_JSON_ROOT='${THREE_DVA_JSON_ROOT}' && \
  export THREE_DVA_COMBINED_GT_DIR='${THREE_DVA_COMBINED_GT_DIR}' && \
  export VISUAL_ATTENTION_3D_SHAPES_ROOT='${VISUAL_ATTENTION_3D_SHAPES_ROOT}' && \
  export MESHMAMBA_NON_TEXTURE_ROOT='${MESHMAMBA_NON_TEXTURE_ROOT}' && \
  export MESHMAMBA_RGB_TEXTURE_ROOT='${MESHMAMBA_RGB_TEXTURE_ROOT}' && \
  export MESHMAMBA_JSON_ROOT='${MESHMAMBA_JSON_ROOT}' && \
  export MESHMAMBA_RGB_TEXTURE_JSON_ROOT='${MESHMAMBA_RGB_TEXTURE_JSON_ROOT}' && \
  export SAL3D_DATASET_ROOT='${SAL3D_DATASET_ROOT}' && \
  export SAL3D_JSON_ROOT='${SAL3D_JSON_ROOT}' && \
  export SAL3D_FIXED_GT_DIR='${SAL3D_FIXED_GT_DIR}' && \
  export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 && \
  nice -n 0 '${REPROJECT_PYTHON}' test/launch/run_sigma_sweep_rc3.py \
    --workers ${WORKERS} \
    --shard-index ${SHARD_INDEX} \
    --num-shards ${NUM_SHARDS} \
    --batch-output-dir '${BATCH_OUTPUT_DIR}' \
    2>&1 | tee '${BATCH_OUTPUT_DIR}/runner.log'"

tmux new-session -d -s "${SESSION}" bash -c "${INNER_CMD}"

echo "[launch] started — attach with: tmux attach -t ${SESSION}"
echo "[launch] log: ${BATCH_OUTPUT_DIR}/runner.log"
