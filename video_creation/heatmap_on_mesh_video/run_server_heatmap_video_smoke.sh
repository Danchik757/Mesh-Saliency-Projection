#!/usr/bin/env bash
# Smoke test: render 4 heatmap-on-mesh videos (120 frames each) on vg-iai.
#
# Run from the repo root on the server:
#   cd /mnt/ssd1/29d_kon/acm_2026/agents/coordinator/Mesh-Saliency-Projection
#   bash video_creation/heatmap_on_mesh_video/run_server_heatmap_video_smoke.sh
#
# Release tag is controlled by REPROJECT_RELEASE_TAG (default v2.0-data-rc1).
# Override before sourcing to target rc2-staging or final:
#   REPROJECT_RELEASE_TAG=v2.0-data-rc2-staging \
#   bash video_creation/heatmap_on_mesh_video/run_server_heatmap_video_smoke.sh
#
# Outputs:
#   ${OUTPUT_ROOT}/heatmap_videos_smoke/{dataset}/{track}/{model}/{map_type}/

set -euo pipefail

# shellcheck source=configs/server_vg_intellect.env
source configs/server_vg_intellect.env

VENV="${CONDA_ENVS_ROOT}/reproject-benchmark"
# shellcheck source=/dev/null
source "${VENV}/bin/activate"

SMOKE_MAPS="${OUTPUT_ROOT}/smoke_parallel_20260609"
VIDEO_OUT="${OUTPUT_ROOT}/heatmap_videos_smoke"
MAX_FRAMES=120
WIDTH=960
HEIGHT=540

echo "[INFO] REPROJECT_RELEASE_TAG = ${REPROJECT_RELEASE_TAG}"
echo "[INFO] RELEASE_DATA_ROOT     = ${RELEASE_DATA_ROOT}"
echo "[INFO] SMOKE_MAPS            = ${SMOKE_MAPS}"
echo "[INFO] VIDEO_OUT             = ${VIDEO_OUT}"

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
    --mesh "${MESHMAMBA_NON_TEXTURE_ROOT}/MeshFile/non_texture/Starfruit_L3/Starfruit_L3.obj" \
    --placement-json "${MESHMAMBA_JSON_ROOT}/MeshMamba_non_texture_Starfruit_L3.json" \
    --output-dir "${VIDEO_OUT}" \
    --max-frames "${MAX_FRAMES}" --width "${WIDTH}" --height "${HEIGHT}"

echo "=== smoke: MeshMamba non_texture Starfruit_L3 cone ==="
MAP=$(find_map "${SMOKE_MAPS}" "Starfruit_L3" "Starfruit_L3_cone_faces.txt")
echo "  map: ${MAP}"
${RENDER} \
    --dataset MeshMamba --track non_texture --model Starfruit_L3 \
    --map-type cone \
    --map-file "${MAP}" \
    --mesh "${MESHMAMBA_NON_TEXTURE_ROOT}/MeshFile/non_texture/Starfruit_L3/Starfruit_L3.obj" \
    --placement-json "${MESHMAMBA_JSON_ROOT}/MeshMamba_non_texture_Starfruit_L3.json" \
    --output-dir "${VIDEO_OUT}" \
    --max-frames "${MAX_FRAMES}" --width "${WIDTH}" --height "${HEIGHT}"

echo "=== smoke: SAL3D bunny screen_space ==="
MAP=$(find_map "${SMOKE_MAPS}" "bunny" "bunny_screen_space_vertices.txt")
echo "  map: ${MAP}"
${RENDER} \
    --dataset SAL3D --track sal3d --model bunny \
    --map-type screen_space \
    --map-file "${MAP}" \
    --mesh "${SAL3D_DATASET_ROOT}/Meshes/bunny.obj" \
    --placement-json "${SAL3D_JSON_ROOT}/Sal3D_bunny.json" \
    --output-dir "${VIDEO_OUT}" \
    --max-frames "${MAX_FRAMES}" --width "${WIDTH}" --height "${HEIGHT}"

echo "=== smoke: SAL3D bunny cone ==="
MAP=$(find_map "${SMOKE_MAPS}" "bunny" "bunny_cone_vertices.txt")
echo "  map: ${MAP}"
${RENDER} \
    --dataset SAL3D --track sal3d --model bunny \
    --map-type cone \
    --map-file "${MAP}" \
    --mesh "${SAL3D_DATASET_ROOT}/Meshes/bunny.obj" \
    --placement-json "${SAL3D_JSON_ROOT}/Sal3D_bunny.json" \
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
print(f'  timing_used={d[\"placement_json_timing_used\"]} placement[{tc[\"start_frame_idx\"]}:{tc[\"end_frame_idx\"]}]')
" "${mf}"
done
