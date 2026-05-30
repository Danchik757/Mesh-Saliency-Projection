#!/usr/bin/env bash
# Pack MeshMamba_non_texture side inputs into tar.gz archives for scp transfer.
# Run LOCALLY. No server access.
#
# Creates in LOCAL_PACK_DIR:
#   meshmamba_non_texture_csv.tar.gz   (uncompressed: ~81 MB, 105 files)
#   meshmamba_non_texture_json.tar.gz  (uncompressed: ~8.6 MB, 105 files)
#
# Required env var:
#   LOCAL_GAZE_DATA_ROOT  — local GAZE_DATA directory
#
# Optional:
#   LOCAL_PACK_DIR  — output dir for archives (default: /tmp/reproject_side_inputs)
#
# Example:
#   LOCAL_GAZE_DATA_ROOT=/path/to/GAZE_DATA \
#   LOCAL_PACK_DIR=/tmp/reproject_side_inputs \
#     bash test/side_inputs/pack_meshmamba_non_texture.sh
set -euo pipefail

: "${LOCAL_GAZE_DATA_ROOT:?Set LOCAL_GAZE_DATA_ROOT}"
LOCAL_PACK_DIR="${LOCAL_PACK_DIR:-/tmp/reproject_side_inputs}"

CSV_DIR="${LOCAL_GAZE_DATA_ROOT}/csv_for_models/MeshMamba_non_texture"
JSON_DIR="${LOCAL_GAZE_DATA_ROOT}/jsons_for_models/Mamba_non_textured"

if [ ! -d "${CSV_DIR}" ]; then
  echo "[pack_meshmamba_non_texture] ERROR: CSV_DIR not found: ${CSV_DIR}"
  exit 1
fi
if [ ! -d "${JSON_DIR}" ]; then
  echo "[pack_meshmamba_non_texture] ERROR: JSON_DIR not found: ${JSON_DIR}"
  exit 1
fi

mkdir -p "${LOCAL_PACK_DIR}"

echo "[pack_meshmamba_non_texture] packing CSV files from ${CSV_DIR} ..."
tar -czf "${LOCAL_PACK_DIR}/meshmamba_non_texture_csv.tar.gz" \
  -C "${LOCAL_GAZE_DATA_ROOT}/csv_for_models" \
  MeshMamba_non_texture

echo "[pack_meshmamba_non_texture] packing JSON files from ${JSON_DIR} ..."
tar -czf "${LOCAL_PACK_DIR}/meshmamba_non_texture_json.tar.gz" \
  -C "${LOCAL_GAZE_DATA_ROOT}/jsons_for_models" \
  Mamba_non_textured

echo "[pack_meshmamba_non_texture] done:"
ls -lh \
  "${LOCAL_PACK_DIR}/meshmamba_non_texture_csv.tar.gz" \
  "${LOCAL_PACK_DIR}/meshmamba_non_texture_json.tar.gz"

echo ""
echo "Server unpack commands (run on vg-intellect after scp):"
echo "  cd \${SIDE_INPUTS_ROOT}"
echo "  mkdir -p MeshMamba_non_texture/csv"
echo "  tar -xzf meshmamba_non_texture_csv.tar.gz  -C MeshMamba_non_texture/csv  --strip-components=1"
echo "  mkdir -p MeshMamba_non_texture/json"
echo "  tar -xzf meshmamba_non_texture_json.tar.gz -C MeshMamba_non_texture/json --strip-components=1"
echo ""
echo "WARNING: JSON files are mandatory for preview rendering and reprojection."
