#!/usr/bin/env bash
# Smoke test: render gaze overlay videos for 3 models (one per dataset family).
#
# Run from repo root on the server:
#   cd /mnt/ssd1/29d_kon/acm_2026/agents/coordinator/Mesh-Saliency-Projection
#   bash video_creation/gaze_heatmap_overlays/run_smoke_gaze_overlay.sh
#
# Override REPROJECT_RELEASE_TAG for rc3:
#   REPROJECT_RELEASE_TAG=v2.0-data-rc3 \
#   bash video_creation/gaze_heatmap_overlays/run_smoke_gaze_overlay.sh
#
# Run both modes in one pass:
#   SMOKE_MODES="full_video_overlay benchmark_one_turn_overlay" \
#   bash video_creation/gaze_heatmap_overlays/run_smoke_gaze_overlay.sh

set -euo pipefail

# shellcheck source=configs/server_vg_intellect.env
source configs/server_vg_intellect.env

VENV="${CONDA_ENVS_ROOT}/reproject-benchmark"
# shellcheck source=/dev/null
source "${VENV}/bin/activate"

FIXATION_ROOT="${RELEASE_DATA_ROOT}/participant_fixations_offset0_full_cleaned"
VIDEO_ROOT="${RELEASE_DATA_ROOT}/source_videos"
SMOKE_OUT="${OUTPUT_ROOT}/gaze_overlay_smoke"
SMOKE_MODES="${SMOKE_MODES:-full_video_overlay benchmark_one_turn_overlay}"

# Smoke models: one from each dataset family
SMOKE_MODELS=(
    "3DVA_A380"
    "MeshMamba_non_texture_Starfruit_L3"
    "SAL3D_bunny"
)

echo "[INFO] REPROJECT_RELEASE_TAG = ${REPROJECT_RELEASE_TAG}"
echo "[INFO] FIXATION_ROOT         = ${FIXATION_ROOT}"
echo "[INFO] VIDEO_ROOT            = ${VIDEO_ROOT}"
echo "[INFO] SMOKE_OUT             = ${SMOKE_OUT}"
echo "[INFO] SMOKE_MODELS          = ${SMOKE_MODELS[*]}"
echo "[INFO] SMOKE_MODES           = ${SMOKE_MODES}"

RUNNER="nice -n 18 ionice -c2 -n7 python \
  video_creation/gaze_heatmap_overlays/run_batch_gaze_overlay.py"

for mode in ${SMOKE_MODES}; do
    echo ""
    echo "=== smoke mode: ${mode} ==="
    # shellcheck disable=SC2086
    ${RUNNER} \
        --fixation-root "${FIXATION_ROOT}" \
        --video-root    "${VIDEO_ROOT}" \
        --output-root   "${SMOKE_OUT}" \
        --mode          "${mode}" \
        --models        "${SMOKE_MODELS[@]}"
done

echo ""
echo "=== smoke done ==="
echo "Output root: ${SMOKE_OUT}"
echo ""
echo "MP4 files:"
find "${SMOKE_OUT}" -name "overlay.mp4" | sort
echo ""
echo "Manifests (combined):"
find "${SMOKE_OUT}" -maxdepth 2 -name "manifest.json" | sort | while read -r mf; do
    echo "--- ${mf} ---"
    python3 -c "
import json, sys
rows = json.load(open(sys.argv[1]))
if isinstance(rows, list):
    for r in rows:
        print(f'  {r.get(\"model_key\",\"?\"):45s}  status={r.get(\"status\",\"?\")}  frames={r.get(\"frame_count\",\"?\")}')
else:
    r = rows
    print(f'  {r.get(\"model_key\",\"?\"):45s}  status=ok  frames={r.get(\"frame_count\",\"?\")}')
" "${mf}" 2>/dev/null || echo "  (json parse failed)"
done
