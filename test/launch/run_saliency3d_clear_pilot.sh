#!/usr/bin/env bash
# Pilot launch for Saliency3D_clear (screen-space + cone-projection tracks).
#
# Usage (local or on vg-intellect inside tmux):
#   source configs/server_vg_intellect.env   # or set env vars manually
#   bash test/launch/run_saliency3d_clear_pilot.sh
#
# Required env vars:
#   SALIENCY3D_CLEAR_ROOT  — root of the Saliency3D_clear dataset
#   OUTPUT_ROOT            — writable output root
#
# Optional env vars (defaults shown):
#   NICE_LEVEL=10
#   PILOT_MODELS="hand bunny dragon"
#   TEST_PARTICIPANTS="zl zy"
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

# ---------- required env var checks ----------
: "${SALIENCY3D_CLEAR_ROOT:?Set SALIENCY3D_CLEAR_ROOT before running (see configs/server_vg_intellect.env)}"
: "${OUTPUT_ROOT:?Set OUTPUT_ROOT before running}"

# ---------- defaults ----------
NICE_LEVEL="${NICE_LEVEL:-10}"
PILOT_MODELS="${PILOT_MODELS:-hand bunny dragon}"
TEST_PARTICIPANTS="${TEST_PARTICIPANTS:-zl zy}"

OUTPUT_DIR_SS="${OUTPUT_ROOT}/Saliency3D_clear/screen_space_gaussian"
OUTPUT_DIR_CONE="${OUTPUT_ROOT}/Saliency3D_clear/cone_projection"
OUTPUT_DIR_VIZ="${OUTPUT_ROOT}/Saliency3D_clear/transfer_visualizations"
mkdir -p "${OUTPUT_DIR_SS}" "${OUTPUT_DIR_CONE}" "${OUTPUT_DIR_VIZ}"

echo "[run_saliency3d_clear_pilot] repo_root=${REPO_ROOT}"
echo "[run_saliency3d_clear_pilot] dataset_root=${SALIENCY3D_CLEAR_ROOT}"
echo "[run_saliency3d_clear_pilot] nice=${NICE_LEVEL}"

# ---------- screen_space_gaussian (per-model) ----------
for MODEL in ${PILOT_MODELS}; do
  echo "[run_saliency3d_clear_pilot] screen_space_gaussian model=${MODEL} ..."
  nice -n "${NICE_LEVEL}" python "${REPO_ROOT}/reprojection_methods/screen_space_gaussian/eval_holdout_screenspace.py" \
    --dataset-root "${SALIENCY3D_CLEAR_ROOT}" \
    --model "${MODEL}" \
    --test-participants ${TEST_PARTICIPANTS} \
    --output-dir "${OUTPUT_DIR_SS}"
done

# ---------- cone_projection_on_mesh (all pilot models at once) ----------
echo "[run_saliency3d_clear_pilot] cone_projection models=${PILOT_MODELS} ..."
nice -n "${NICE_LEVEL}" python "${REPO_ROOT}/reprojection_methods/cone_projection_on_mesh/eval_visual_attention_style_saliency3d_clear.py" \
  --dataset-root "${SALIENCY3D_CLEAR_ROOT}" \
  --models ${PILOT_MODELS} \
  --test-participants ${TEST_PARTICIPANTS} \
  --output-json "${OUTPUT_DIR_CONE}/cone_projection_pilot.json"

# ---------- transfer_visualizations (combined layout) ----------
echo "[run_saliency3d_clear_pilot] transfer_visualizations models=${PILOT_MODELS} ..."
nice -n "${NICE_LEVEL}" python "${REPO_ROOT}/video_creation/transfer_visualizations/make_transfer_visualizations.py" \
  --dataset-root "${SALIENCY3D_CLEAR_ROOT}" \
  --models ${PILOT_MODELS} \
  --test-participants ${TEST_PARTICIPANTS} \
  --output-dir "${OUTPUT_DIR_VIZ}" \
  --layout combined

echo "[run_saliency3d_clear_pilot] all done."
echo "  screen_space:   ${OUTPUT_DIR_SS}"
echo "  cone_projection: ${OUTPUT_DIR_CONE}"
echo "  visualizations:  ${OUTPUT_DIR_VIZ}"
