#!/usr/bin/env bash
# Smoke test: render 4 heatmap-on-mesh videos (120 frames each) on vg-iai.
#
# Run from the repo root on the server:
#   cd /mnt/ssd1/29d_kon/acm_2026/agents/coordinator/Mesh-Saliency-Projection
#   bash video_creation/heatmap_on_mesh_video/run_server_heatmap_video_smoke.sh
#
# Environment variables (set before running or override here):
#   REPROJECT_SERVER_ROOT   — default /mnt/ssd1/29d_kon/acm_2026
#   REPROJECT_WORKSPACE_NAME — default coordinator
#
# Outputs written to:
#   ${REPROJECT_SERVER_ROOT}/outputs/${REPROJECT_WORKSPACE_NAME}/heatmap_videos_smoke/

set -euo pipefail

SERVER_ROOT="${REPROJECT_SERVER_ROOT:-/mnt/ssd1/29d_kon/acm_2026}"
WORKSPACE="${REPROJECT_WORKSPACE_NAME:-coordinator}"

VENV="${SERVER_ROOT}/environments/reproject-benchmark"
# shellcheck source=/dev/null
source "${VENV}/bin/activate"

REPO_ROOT="$(pwd)"
OUTPUTS_ROOT="${SERVER_ROOT}/outputs/${WORKSPACE}"
SMOKE_MAPS="${OUTPUTS_ROOT}/smoke_parallel_20260609"
RELEASE_ROOT="${SERVER_ROOT}/shared_release_data/v2.0-data-rc1/extracted"

VIDEO_OUT="${OUTPUTS_ROOT}/heatmap_videos_smoke"
MAX_FRAMES=120
WIDTH=960
HEIGHT=540

# Find the most-recent map file anywhere in the smoke tree.
# Args: <smoke_root> <model> <filename>
find_map() {
    local smoke_root="$1" model="$2" filename="$3"
    local result
    result=$(find "${smoke_root}" -name "${filename}" 2>/dev/null \
        | grep "/${model}/" | sort | tail -1)
    if [[ -z "${result}" ]]; then
        echo "[ERROR] map not found: ${filename} for model ${model} under ${smoke_root}" >&2
        exit 1
    fi
    echo "${result}"
}

RENDER="nice -n 15 ionice -c2 -n7 python video_creation/heatmap_on_mesh_video/render_heatmap_video.py"

echo "=== smoke: MeshMamba non_texture Starfruit_L3 screen_space ==="
MAP=$(find_map "${SMOKE_MAPS}" "Starfruit_L3" "Starfruit_L3_screen_space_faces.txt")
echo "  map: ${MAP}"
${RENDER} \
    --dataset MeshMamba --track non_texture --model Starfruit_L3 \
    --map-type screen_space \
    --map-file "${MAP}" \
    --mesh "${RELEASE_ROOT}/datasets/MeshMamba/MeshFile/non_texture/Starfruit_L3/Starfruit_L3.obj" \
    --placement-json "${REPO_ROOT}/jsons/object_placement/mamba_non_jsons/MeshMamba_non_texture_Starfruit_L3.json" \
    --output-dir "${VIDEO_OUT}" \
    --max-frames "${MAX_FRAMES}" --width "${WIDTH}" --height "${HEIGHT}"

echo "=== smoke: MeshMamba non_texture Starfruit_L3 cone ==="
MAP=$(find_map "${SMOKE_MAPS}" "Starfruit_L3" "Starfruit_L3_cone_faces.txt")
echo "  map: ${MAP}"
${RENDER} \
    --dataset MeshMamba --track non_texture --model Starfruit_L3 \
    --map-type cone \
    --map-file "${MAP}" \
    --mesh "${RELEASE_ROOT}/datasets/MeshMamba/MeshFile/non_texture/Starfruit_L3/Starfruit_L3.obj" \
    --placement-json "${REPO_ROOT}/jsons/object_placement/mamba_non_jsons/MeshMamba_non_texture_Starfruit_L3.json" \
    --output-dir "${VIDEO_OUT}" \
    --max-frames "${MAX_FRAMES}" --width "${WIDTH}" --height "${HEIGHT}"

echo "=== smoke: SAL3D bunny screen_space ==="
MAP=$(find_map "${SMOKE_MAPS}" "bunny" "bunny_screen_space_vertices.txt")
echo "  map: ${MAP}"
${RENDER} \
    --dataset SAL3D --track sal3d --model bunny \
    --map-type screen_space \
    --map-file "${MAP}" \
    --mesh "${RELEASE_ROOT}/datasets/SAL3D/Meshes/bunny.obj" \
    --placement-json "${REPO_ROOT}/jsons/object_placement/sal3d_jsons/Sal3D_bunny.json" \
    --output-dir "${VIDEO_OUT}" \
    --max-frames "${MAX_FRAMES}" --width "${WIDTH}" --height "${HEIGHT}"

echo "=== smoke: SAL3D bunny cone ==="
MAP=$(find_map "${SMOKE_MAPS}" "bunny" "bunny_cone_vertices.txt")
echo "  map: ${MAP}"
${RENDER} \
    --dataset SAL3D --track sal3d --model bunny \
    --map-type cone \
    --map-file "${MAP}" \
    --mesh "${RELEASE_ROOT}/datasets/SAL3D/Meshes/bunny.obj" \
    --placement-json "${REPO_ROOT}/jsons/object_placement/sal3d_jsons/Sal3D_bunny.json" \
    --output-dir "${VIDEO_OUT}" \
    --max-frames "${MAX_FRAMES}" --width "${WIDTH}" --height "${HEIGHT}"

echo ""
echo "=== smoke done ==="
echo "Output root: ${VIDEO_OUT}"
echo ""
echo "MP4 files:"
find "${VIDEO_OUT}" -name "heatmap_video.mp4" | sort
echo ""
echo "Manifests:"
find "${VIDEO_OUT}" -name "manifest.json" | sort | while read -r mf; do
    echo "--- ${mf} ---"
    python3 -c "
import json, sys
d = json.load(open(sys.argv[1]))
r = d['render']
tc = d['timing_contract']
print(f'  dataset={d[\"dataset\"]} track={d[\"track\"]} model={d[\"model\"]} map_type={d[\"map_type\"]}')
print(f'  frames={r[\"n_rendered_frames\"]} domain={r[\"map_domain\"]} {r[\"width\"]}x{r[\"height\"]}')
print(f'  timing_used={d[\"placement_json_timing_used\"]} crop=[{tc[\"start_frame_idx\"]},{tc[\"end_frame_idx\"]})')
" "${mf}"
done
