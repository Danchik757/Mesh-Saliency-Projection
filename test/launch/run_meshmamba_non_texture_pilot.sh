#!/usr/bin/env bash
# Pilot launch stub for MeshMamba non_texture (face-level GT).
#
# IMPORTANT: The main MeshMamba pipeline (our_pipeline, +diffusion, +geodesic_kde)
# lives in an external repository (MAMBA_GAZE_ROOT). This wrapper checks env vars,
# confirms side inputs are present, and delegates to the external pipeline.
# In-repo reference method adapters are not yet implemented (status: needs_adaptation).
#
# Usage (on vg-intellect inside tmux):
#   source configs/server_vg_intellect.env
#   bash test/launch/run_meshmamba_non_texture_pilot.sh
#
# Required env vars:
#   MESHMAMBA_NON_TEXTURE_ROOT  — dataset root (mesh files + GT)
#   SIDE_INPUTS_ROOT            — root for mirrored CSV/JSON side inputs
#   MAMBA_GAZE_ROOT             — checked-out MAMBA_GAZE external repo
#   OUTPUT_ROOT                 — writable output root
#
# Optional env vars (defaults shown):
#   WORKERS=12
#   NICE_LEVEL=10
#   PILOT_MODEL=Starfruit_L3
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

# ---------- required env var checks ----------
: "${MESHMAMBA_NON_TEXTURE_ROOT:?Set MESHMAMBA_NON_TEXTURE_ROOT (see configs/server_vg_intellect.env)}"
: "${SIDE_INPUTS_ROOT:?Set SIDE_INPUTS_ROOT}"
: "${MAMBA_GAZE_ROOT:?Set MAMBA_GAZE_ROOT to the external MAMBA_GAZE checkout}"
: "${OUTPUT_ROOT:?Set OUTPUT_ROOT}"

# ---------- defaults ----------
WORKERS="${WORKERS:-12}"
NICE_LEVEL="${NICE_LEVEL:-10}"
PILOT_MODEL="${PILOT_MODEL:-Starfruit_L3}"

MESH_DIR="${MESHMAMBA_NON_TEXTURE_ROOT}/MeshFile/non_texture"
GT_DIR="${MESHMAMBA_NON_TEXTURE_ROOT}/SaliencyMap/non_texture"
CSV_DIR="${SIDE_INPUTS_ROOT}/MeshMamba_non_texture/csv"
JSON_DIR="${SIDE_INPUTS_ROOT}/MeshMamba_non_texture/json"
OUTPUT_DIR="${OUTPUT_ROOT}/MeshMamba_non_texture/pilot"
MAPPING_JSON="${OUTPUT_DIR}/meshmamba_non_texture_name_mapping.json"

# ---------- side-input presence check ----------
if [ ! -d "${CSV_DIR}" ]; then
  echo "[run_meshmamba_non_texture_pilot] ERROR: CSV_DIR not found: ${CSV_DIR}"
  echo "  Mirror side inputs first: bash test/launch/mirror_side_inputs.sh"
  exit 1
fi
if [ ! -d "${JSON_DIR}" ]; then
  echo "[run_meshmamba_non_texture_pilot] ERROR: JSON_DIR not found: ${JSON_DIR}"
  echo "  Mirror side inputs first: bash test/launch/mirror_side_inputs.sh"
  exit 1
fi

mkdir -p "${OUTPUT_DIR}"

echo "[run_meshmamba_non_texture_pilot] repo_root=${REPO_ROOT}"
echo "[run_meshmamba_non_texture_pilot] mesh_dir=${MESH_DIR}"
echo "[run_meshmamba_non_texture_pilot] gt_dir=${GT_DIR}"
echo "[run_meshmamba_non_texture_pilot] csv_dir=${CSV_DIR}"
echo "[run_meshmamba_non_texture_pilot] json_dir=${JSON_DIR}"
echo "[run_meshmamba_non_texture_pilot] mamba_gaze_root=${MAMBA_GAZE_ROOT}"
echo "[run_meshmamba_non_texture_pilot] output_dir=${OUTPUT_DIR}"
echo "[run_meshmamba_non_texture_pilot] workers=${WORKERS}  nice=${NICE_LEVEL}"
echo "[run_meshmamba_non_texture_pilot] pilot_model=${PILOT_MODEL}"

# ---------- delegate to external MAMBA_GAZE pipeline ----------
PIPELINE_SCRIPT="${MAMBA_GAZE_ROOT}/run_meshmamba_gaze.py"
if [ ! -f "${PIPELINE_SCRIPT}" ]; then
  echo "[run_meshmamba_non_texture_pilot] PIPELINE_SCRIPT not found: ${PIPELINE_SCRIPT}"
  echo "  Verify MAMBA_GAZE_ROOT points to the MAMBA_GAZE checkout on this machine."
  exit 1
fi

nice -n "${NICE_LEVEL}" python3 "${PIPELINE_SCRIPT}" \
  --model "${PILOT_MODEL}" \
  --gaze-csv-dir "${CSV_DIR}" \
  --mesh-dir "${MESH_DIR}" \
  --json-dir "${JSON_DIR}" \
  --gt-dir "${GT_DIR}" \
  --output-dir "${OUTPUT_DIR}" \
  --mapping-json "${MAPPING_JSON}" \
  --device auto \
  --frame-alignment nearest \
  --point-weight-mode unit \
  --smoothing-mode diffusion \
  --recenter-to-bbox-center \
  --extra-rotate-x-deg 90 \
  --override-fov-deg 37.5

echo "[run_meshmamba_non_texture_pilot] done. results in ${OUTPUT_DIR}"
