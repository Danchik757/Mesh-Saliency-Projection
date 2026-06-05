#!/usr/bin/env bash
# Inventory: list all 3DVA participant CSV side-input files with sizes.
# Run LOCALLY from any directory. No scp, no server access.
#
# Required env var:
#   LOCAL_GAZE_DATA_ROOT  — local GAZE_DATA directory
#
# Example:
#   LOCAL_GAZE_DATA_ROOT=/Users/admin/Documents/LAB/SALIENCY_code/GAZE_DATA \
#     bash test/side_inputs/inventory_3dva.sh
set -euo pipefail

: "${LOCAL_GAZE_DATA_ROOT:?Set LOCAL_GAZE_DATA_ROOT}"

CSV_DIR="${LOCAL_GAZE_DATA_ROOT}/csv_for_models/3DVA"

echo "========================================================"
echo " 3DVA side-input inventory"
echo "========================================================"
echo ""

echo "--- CSV files (${CSV_DIR}) ---"
if [ ! -d "${CSV_DIR}" ]; then
  echo "  ERROR: directory not found"
else
  ls -lh "${CSV_DIR}"/*.csv 2>/dev/null | awk '{printf "  %-10s  %s\n", $5, $NF}' || echo "  (no csv files found)"
  CSV_COUNT=$(ls "${CSV_DIR}"/*.csv 2>/dev/null | wc -l | tr -d ' ')
  CSV_SIZE=$(du -sh "${CSV_DIR}" 2>/dev/null | cut -f1)
  echo "  ── total: ${CSV_COUNT} files, ${CSV_SIZE}"
fi

echo ""
echo "Server destination (relative to SIDE_INPUTS_ROOT):"
echo "  3DVA/csv/   ← ${CSV_COUNT:-?} CSV files"
echo ""
echo "Note: placement/camera JSONs are in the repository:"
echo "      jsons/object_placement/3dva_jsons"
