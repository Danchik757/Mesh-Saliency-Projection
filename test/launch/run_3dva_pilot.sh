#!/usr/bin/env bash
# Pilot launch for 3DVA (Visual Attention for Rendered 3D Shapes).
#
# Usage (local or on vg-intellect inside tmux):
#   source configs/server_vg_intellect.env   # or set env vars manually
#   bash test/launch/run_3dva_pilot.sh
#
# Required env vars:
#   VISUAL_ATTENTION_3D_SHAPES_ROOT  — root of the published 3DVA dataset
#   OUTPUT_ROOT                      — writable output root
#
# Optional env vars (defaults shown):
#   WORKERS=8          — parallel worker count (increase carefully)
#   NICE_LEVEL=10      — nice priority for low-priority execution
#   PILOT_VIEWS="300"  — space-separated list of views to evaluate
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

# ---------- required env var checks ----------
: "${VISUAL_ATTENTION_3D_SHAPES_ROOT:?Set VISUAL_ATTENTION_3D_SHAPES_ROOT before running (see configs/server_vg_intellect.env)}"
: "${OUTPUT_ROOT:?Set OUTPUT_ROOT before running}"

# ---------- defaults ----------
WORKERS="${WORKERS:-8}"
NICE_LEVEL="${NICE_LEVEL:-10}"
PILOT_VIEWS="${PILOT_VIEWS:-300}"

OUTPUT_DIR="${OUTPUT_ROOT}/3DVA/pilot"
mkdir -p "${OUTPUT_DIR}"

PILOT_OBJECTS="bunny A380 dragon chair107 flowerpot car-vasa"

echo "[run_3dva_pilot] repo_root=${REPO_ROOT}"
echo "[run_3dva_pilot] dataset_root=${VISUAL_ATTENTION_3D_SHAPES_ROOT}"
echo "[run_3dva_pilot] output_dir=${OUTPUT_DIR}"
echo "[run_3dva_pilot] workers=${WORKERS}  nice=${NICE_LEVEL}"
echo "[run_3dva_pilot] views=${PILOT_VIEWS}  objects=${PILOT_OBJECTS}"

# ---------- cone_projection_on_mesh vs published GT ----------
for VIEW in ${PILOT_VIEWS}; do
  echo "[run_3dva_pilot] running cone_projection view=${VIEW} ..."
  nice -n "${NICE_LEVEL}" python "${REPO_ROOT}/reprojection_methods/cone_projection_on_mesh/eval_vs_gt_visual_attention.py" \
    --dataset-root "${VISUAL_ATTENTION_3D_SHAPES_ROOT}" \
    --objects ${PILOT_OBJECTS} \
    --view "${VIEW}" \
    --output-json "${OUTPUT_DIR}/cone_projection_view${VIEW}.json"
done

# ---------- cone_projection + geodesic_diffusion vs published GT ----------
for VIEW in ${PILOT_VIEWS}; do
  echo "[run_3dva_pilot] running geodesic_diffusion view=${VIEW} ..."
  nice -n "${NICE_LEVEL}" python "${REPO_ROOT}/reprojection_methods/cone_projection_on_mesh/eval_geodesic_diffusion.py" \
    --dataset-root "${VISUAL_ATTENTION_3D_SHAPES_ROOT}" \
    --objects ${PILOT_OBJECTS} \
    --view "${VIEW}" \
    --output-json "${OUTPUT_DIR}/geodesic_diffusion_view${VIEW}.json"
done

echo "[run_3dva_pilot] all done. results in ${OUTPUT_DIR}"
