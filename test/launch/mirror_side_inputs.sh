#!/usr/bin/env bash
# Side-input mirror helper: transfer CSV and JSON side inputs to vg-intellect via scp.
#
# Run this LOCALLY (not on the server) before first pilot run.
# Datasets (OBJ meshes, GT arrays) are already on the server.
# This script transfers only participant CSVs and JSON camera metadata.
#
# Usage:
#   bash test/launch/mirror_side_inputs.sh
#
# Required env vars (set locally before running):
#   LOCAL_GAZE_DATA_ROOT    — local path to GAZE_DATA directory
#   SERVER_SIDE_INPUTS_ROOT — remote path: user@vg-intellect:<SIDE_INPUTS_ROOT>
#
# Example:
#   export LOCAL_GAZE_DATA_ROOT="/Users/admin/Documents/LAB/SALIENCY_code/GAZE_DATA"
#   export SERVER_SIDE_INPUTS_ROOT="29d_kon@lab.graphicon.ru@vg-intellect:/home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/side_inputs"
#   bash test/launch/mirror_side_inputs.sh
set -euo pipefail

: "${LOCAL_GAZE_DATA_ROOT:?Set LOCAL_GAZE_DATA_ROOT to your local GAZE_DATA directory}"
: "${SERVER_SIDE_INPUTS_ROOT:?Set SERVER_SIDE_INPUTS_ROOT to user@host:/path/to/side_inputs}"

echo "[mirror_side_inputs] local source: ${LOCAL_GAZE_DATA_ROOT}"
echo "[mirror_side_inputs] server dest:  ${SERVER_SIDE_INPUTS_ROOT}"

# ---------- 3DVA side inputs ----------
# Note: the in-repo 3DVA scripts (eval_vs_gt, eval_geodesic_diffusion) do NOT
# need extra CSVs — all data is inside the published dataset on the server.
# These lines are for the external raw-gaze scripts (raycast_nearest_vertex etc.)
# when they are transferred separately.
echo "[mirror_side_inputs] 3DVA csv ..."
scp -r "${LOCAL_GAZE_DATA_ROOT}/csv_for_models/3DVA" \
  "${SERVER_SIDE_INPUTS_ROOT}/3DVA/csv"

echo "[mirror_side_inputs] 3DVA json ..."
scp -r "${LOCAL_GAZE_DATA_ROOT}/jsons_for_models/3DVA_json" \
  "${SERVER_SIDE_INPUTS_ROOT}/3DVA/json"

# ---------- MeshMamba non_texture side inputs ----------
echo "[mirror_side_inputs] MeshMamba_non_texture csv ..."
scp -r "${LOCAL_GAZE_DATA_ROOT}/csv_for_models/MeshMamba_non_texture" \
  "${SERVER_SIDE_INPUTS_ROOT}/MeshMamba_non_texture/csv"

echo "[mirror_side_inputs] MeshMamba_non_texture json ..."
scp -r "${LOCAL_GAZE_DATA_ROOT}/jsons_for_models/Mamba_non_textured" \
  "${SERVER_SIDE_INPUTS_ROOT}/MeshMamba_non_texture/json"

# ---------- MeshMamba rgb_texture side inputs ----------
# Transfer only after non_texture protocol is stable.
# Uncomment when ready:
# echo "[mirror_side_inputs] MeshMamba_rgb_texture csv ..."
# scp -r "${LOCAL_GAZE_DATA_ROOT}/csv_for_models/MeshMamba_rgb_texture" \
#   "${SERVER_SIDE_INPUTS_ROOT}/MeshMamba_rgb_texture/csv"
# echo "[mirror_side_inputs] MeshMamba_rgb_texture json ..."
# scp -r "${LOCAL_GAZE_DATA_ROOT}/jsons_for_models/Mamba_rgb_textured" \
#   "${SERVER_SIDE_INPUTS_ROOT}/MeshMamba_rgb_texture/json"

# ---------- SAL3D side inputs ----------
# Blocked until dense GT reconstruction is complete.
# Uncomment when ready:
# echo "[mirror_side_inputs] SAL3D csv ..."
# scp -r "${LOCAL_GAZE_DATA_ROOT}/csv_for_models/SAL3D" \
#   "${SERVER_SIDE_INPUTS_ROOT}/SAL3D/csv"
# echo "[mirror_side_inputs] SAL3D json ..."
# scp -r "${LOCAL_GAZE_DATA_ROOT}/jsons_for_models/SAL3D_json" \
#   "${SERVER_SIDE_INPUTS_ROOT}/SAL3D/json"

echo "[mirror_side_inputs] done."
