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
#   WORKERS=12         — parallel worker count (increase carefully)
#   NICE_LEVEL=10      — nice priority for low-priority execution
#   PILOT_VIEWS="300"  — space-separated list of views to evaluate
#   PILOT_OBJECTS="bunny A380 dragon chair107 flowerpot car-vasa"
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

# ---------- required env var checks ----------
: "${VISUAL_ATTENTION_3D_SHAPES_ROOT:?Set VISUAL_ATTENTION_3D_SHAPES_ROOT before running (see configs/server_vg_intellect.env)}"
: "${OUTPUT_ROOT:?Set OUTPUT_ROOT before running}"

# ---------- defaults ----------
WORKERS="${WORKERS:-12}"
NICE_LEVEL="${NICE_LEVEL:-10}"
PILOT_VIEWS="${PILOT_VIEWS:-300}"
PILOT_OBJECTS="${PILOT_OBJECTS:-bunny A380 dragon chair107 flowerpot car-vasa}"

OUTPUT_DIR="${OUTPUT_ROOT}/3DVA/pilot"
mkdir -p "${OUTPUT_DIR}"

echo "[run_3dva_pilot] repo_root=${REPO_ROOT}"
echo "[run_3dva_pilot] dataset_root=${VISUAL_ATTENTION_3D_SHAPES_ROOT}"
echo "[run_3dva_pilot] output_dir=${OUTPUT_DIR}"
echo "[run_3dva_pilot] workers=${WORKERS}  nice=${NICE_LEVEL}"
echo "[run_3dva_pilot] views=${PILOT_VIEWS}  objects=${PILOT_OBJECTS}"

run_pooled_eval() {
  local script_path="$1"
  local output_prefix="$2"
  local object_name="$3"
  local view_name="$4"

  while [ "$(jobs -pr | wc -l | tr -d ' ')" -ge "${WORKERS}" ]; do
    sleep 1
  done

  echo "[run_3dva_pilot] ${output_prefix} object=${object_name} view=${view_name} ..."
  nice -n "${NICE_LEVEL}" python3 "${script_path}" \
    --dataset-root "${VISUAL_ATTENTION_3D_SHAPES_ROOT}" \
    --objects "${object_name}" \
    --view "${view_name}" \
    --output-json "${OUTPUT_DIR}/${output_prefix}_${object_name}_view${view_name}.json" &
}

for VIEW in ${PILOT_VIEWS}; do
  for OBJECT in ${PILOT_OBJECTS}; do
    run_pooled_eval \
      "${REPO_ROOT}/reprojection_methods/cone_projection_on_mesh/eval_vs_gt_visual_attention.py" \
      "cone_projection" \
      "${OBJECT}" \
      "${VIEW}"
  done
done
wait

for VIEW in ${PILOT_VIEWS}; do
  for OBJECT in ${PILOT_OBJECTS}; do
    run_pooled_eval \
      "${REPO_ROOT}/reprojection_methods/cone_projection_on_mesh/eval_geodesic_diffusion.py" \
      "geodesic_diffusion" \
      "${OBJECT}" \
      "${VIEW}"
  done
done
wait

echo "[run_3dva_pilot] all done. results in ${OUTPUT_DIR}"
