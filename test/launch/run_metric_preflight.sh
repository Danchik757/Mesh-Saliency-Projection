#!/usr/bin/env bash
# Preflight checks before launching metric jobs locally or on vg-intellect.
#
# Usage:
#   source configs/server_vg_intellect.env
#   bash test/launch/run_metric_preflight.sh
#
# Optional env vars:
#   RUN_SCREEN_SPACE_SMOKE=1   run one MeshMamba screen-space smoke eval (default 1)
#   RUN_MAMBA_SMOKE=1          run one MAMBA_GAZE smoke eval (default 1)
#   RUN_3DVA_SMOKE=0           run one 3DVA smoke eval (default 0, heavier)
#   SMOKE_MODEL_MESHMAMBA=Starfruit_L3
#   SMOKE_MODEL_3DVA=bunny
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
PYTHON_BIN="${REPROJECT_PYTHON:-python3}"

RUN_SCREEN_SPACE_SMOKE="${RUN_SCREEN_SPACE_SMOKE:-1}"
RUN_MAMBA_SMOKE="${RUN_MAMBA_SMOKE:-1}"
RUN_3DVA_SMOKE="${RUN_3DVA_SMOKE:-0}"
SMOKE_MODEL_MESHMAMBA="${SMOKE_MODEL_MESHMAMBA:-Starfruit_L3}"
SMOKE_MODEL_3DVA="${SMOKE_MODEL_3DVA:-bunny}"

require_dir() {
  local path="$1"
  local label="$2"
  if [ ! -d "${path}" ]; then
    echo "[preflight] MISSING DIR: ${label}: ${path}" >&2
    exit 1
  fi
  echo "[preflight] ok dir: ${label}: ${path}"
}

require_file() {
  local path="$1"
  local label="$2"
  if [ ! -f "${path}" ]; then
    echo "[preflight] MISSING FILE: ${label}: ${path}" >&2
    exit 1
  fi
  echo "[preflight] ok file: ${label}: ${path}"
}

echo "[preflight] repo_root=${REPO_ROOT}"
echo "[preflight] python_bin=${PYTHON_BIN}"

require_file "${PYTHON_BIN}" "runtime python"

"${PYTHON_BIN}" - <<'PY'
import importlib
mods = ["numpy", "pandas", "scipy", "trimesh", "sklearn"]
missing = []
for name in mods:
    try:
        importlib.import_module(name)
    except Exception:
        missing.append(name)
if missing:
    raise SystemExit(f"Missing Python modules: {', '.join(missing)}")
print("[preflight] ok python imports:", ", ".join(mods))
try:
    importlib.import_module("rtree")
    print("[preflight] ok python import: rtree")
except Exception:
    print("[preflight] note: rtree missing; MeshMamba/3DVA cone ray backend may be blocked")
PY

require_dir "${SIDE_INPUTS_ROOT}" "SIDE_INPUTS_ROOT"
require_dir "${OUTPUT_ROOT}" "OUTPUT_ROOT"

require_dir "${MESHMAMBA_NON_TEXTURE_ROOT}/MeshFile/non_texture" "MeshMamba non_texture mesh dir"
require_dir "${MESHMAMBA_NON_TEXTURE_ROOT}/SaliencyMap/non_texture" "MeshMamba non_texture gt dir"
require_dir "${SIDE_INPUTS_ROOT}/MeshMamba_non_texture/csv" "MeshMamba csv side inputs"
require_dir "${SIDE_INPUTS_ROOT}/MeshMamba_non_texture/json" "MeshMamba json side inputs"
require_file "${SIDE_INPUTS_ROOT}/MeshMamba_non_texture/csv/${SMOKE_MODEL_MESHMAMBA}.csv" "MeshMamba smoke csv"
require_file "${SIDE_INPUTS_ROOT}/MeshMamba_non_texture/json/MeshMamba_non_texture_${SMOKE_MODEL_MESHMAMBA}.json" "MeshMamba smoke json"

require_dir "${VISUAL_ATTENTION_3D_SHAPES_ROOT}/3DModels-Simplif-up" "3DVA rotated obj dir"
require_dir "${VISUAL_ATTENTION_3D_SHAPES_ROOT}/FixationMaps" "3DVA gt dir"
require_dir "${THREE_DVA_CSV_ROOT}" "3DVA csv side inputs"
require_dir "${THREE_DVA_JSON_ROOT}" "3DVA json side inputs"
require_file "${THREE_DVA_CSV_ROOT}/${SMOKE_MODEL_3DVA}.csv" "3DVA smoke csv"
require_file "${THREE_DVA_JSON_ROOT}/3DVA_${SMOKE_MODEL_3DVA}.json" "3DVA smoke json"

if [ -n "${MAMBA_GAZE_ROOT:-}" ]; then
  require_file "${MAMBA_GAZE_ROOT}/run_meshmamba_gaze.py" "MAMBA_GAZE entrypoint"
fi

if [ "${RUN_SCREEN_SPACE_SMOKE}" = "1" ]; then
  echo "[preflight] running MeshMamba screen-space smoke..."
  PILOT_MODEL="${SMOKE_MODEL_MESHMAMBA}" \
  NICE_LEVEL="${NICE_LEVEL:-10}" \
  bash "${REPO_ROOT}/test/launch/run_meshmamba_baseline_screen_space.sh"
fi

if [ "${RUN_MAMBA_SMOKE}" = "1" ]; then
  echo "[preflight] running MeshMamba MAMBA_GAZE smoke..."
  PILOT_MODEL="${SMOKE_MODEL_MESHMAMBA}" \
  NICE_LEVEL="${NICE_LEVEL:-10}" \
  SMOOTHING_MODE=diffusion \
  bash "${REPO_ROOT}/test/launch/run_meshmamba_non_texture_pilot.sh"
fi

if [ "${RUN_3DVA_SMOKE}" = "1" ]; then
  echo "[preflight] running 3DVA smoke..."
  PILOT_OBJECTS="${SMOKE_MODEL_3DVA}" \
  WORKERS=1 \
  NICE_LEVEL="${NICE_LEVEL:-10}" \
  RECENTER_TO_BBOX_CENTER=true \
  bash "${REPO_ROOT}/test/launch/run_3dva_raycast_cone.sh"
fi

echo "[preflight] done"
