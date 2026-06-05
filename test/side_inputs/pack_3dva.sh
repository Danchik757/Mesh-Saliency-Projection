#!/usr/bin/env bash
# Pack 3DVA participant CSV side inputs into a tar.gz archive for scp transfer.
# Run LOCALLY. No server access.
#
# Creates in LOCAL_PACK_DIR:
#   3dva_csv.tar.gz   (uncompressed: ~38 MB, 32 files)
#
# Placement/camera JSONs are stored in-repo under:
#   jsons/object_placement/3dva_jsons
# They move to the server via git, not via side-input archives.
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
#     bash test/side_inputs/pack_3dva.sh
set -euo pipefail

: "${LOCAL_GAZE_DATA_ROOT:?Set LOCAL_GAZE_DATA_ROOT}"
LOCAL_PACK_DIR="${LOCAL_PACK_DIR:-/tmp/reproject_side_inputs}"

CSV_DIR="${LOCAL_GAZE_DATA_ROOT}/csv_for_models/3DVA"

if [ ! -d "${CSV_DIR}" ]; then
  echo "[pack_3dva] ERROR: CSV_DIR not found: ${CSV_DIR}"
  exit 1
fi

mkdir -p "${LOCAL_PACK_DIR}"

echo "[pack_3dva] packing CSV files from ${CSV_DIR} ..."
tar -czf "${LOCAL_PACK_DIR}/3dva_csv.tar.gz" \
  -C "${LOCAL_GAZE_DATA_ROOT}/csv_for_models" \
  3DVA

echo "[pack_3dva] done:"
ls -lh "${LOCAL_PACK_DIR}/3dva_csv.tar.gz"

echo ""
echo "Server unpack commands (run on vg-intellect after scp):"
echo "  cd \${SIDE_INPUTS_ROOT}"
echo "  mkdir -p 3DVA/csv  && tar -xzf 3dva_csv.tar.gz  -C 3DVA/csv  --strip-components=1"
echo ""
echo "JSON placement metadata comes from git:"
echo "  \${REPO_ROOT}/jsons/object_placement/3dva_jsons"
