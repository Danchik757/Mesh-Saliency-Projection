#!/usr/bin/env bash
# Smoke test: render 4 heatmap-on-mesh videos (120 frames each) on vg-iai.
#
# Run from the repo root on the server:
#   cd /mnt/ssd1/29d_kon/acm_2026/agents/coordinator/Mesh-Saliency-Projection
#   bash video_creation/heatmap_on_mesh_video/run_server_heatmap_video_smoke.sh
#
# Expects:
#   REPROJECT_SERVER_ROOT   — default /mnt/ssd1/29d_kon/acm_2026
#   REPROJECT_WORKSPACE_NAME — default coordinator
#   CONDA_ENV_NAME          — default reproject-benchmark
#
# Outputs written to:
#   ${REPROJECT_SERVER_ROOT}/outputs/${REPROJECT_WORKSPACE_NAME}/heatmap_videos_smoke/

set -euo pipefail

SERVER_ROOT="${REPROJECT_SERVER_ROOT:-/mnt/ssd1/29d_kon/acm_2026}"
WORKSPACE="${REPROJECT_WORKSPACE_NAME:-coordinator}"
CONDA_ENV="${CONDA_ENV_NAME:-reproject-benchmark}"

REPO_ROOT="$(pwd)"
OUTPUTS_ROOT="${SERVER_ROOT}/outputs/${WORKSPACE}"
SMOKE_MAPS="${OUTPUTS_ROOT}/smoke_parallel_20260609"
DATASETS_ROOT="${SERVER_ROOT}/releases/v2.0-data-rc1"

VIDEO_OUT="${OUTPUTS_ROOT}/heatmap_videos_smoke"
MAX_FRAMES=120
WIDTH=960
HEIGHT=540

# Activate conda env
CONDA_BASE="$(conda info --base 2>/dev/null || echo "${HOME}/miniconda3")"
# shellcheck source=/dev/null
source "${CONDA_BASE}/etc/profile.d/conda.sh"
conda activate "${CONDA_ENV}"

RENDER="nice -n 15 ionice -c2 -n7 python video_creation/heatmap_on_mesh_video/render_heatmap_video.py"

# Helper: find most-recent matching map file in a tag-tagged subdirectory
find_map() {
    local model="$1" pattern="$2" base_dir="$3"
    # tag dir is auto-derived by the evaluator; locate by filename pattern
    find "${base_dir}/${model}" -maxdepth 2 -name "${pattern}" 2>/dev/null \
        | sort | tail -1
}

echo "=== smoke: MeshMamba non_texture Starfruit_L3 screen_space ==="
MAP=$(find_map "Starfruit_L3" "Starfruit_L3_screen_space_faces.txt" \
    "${SMOKE_MAPS}/screen_space_gaussian")
${RENDER} \
    --dataset MeshMamba --track non_texture --model Starfruit_L3 \
    --map-type screen_space \
    --map-file "${MAP}" \
    --mesh "${DATASETS_ROOT}/datasets/MeshMamba/MeshFile/non_texture/Starfruit_L3/Starfruit_L3.obj" \
    --placement-json "${REPO_ROOT}/jsons/object_placement/mamba_non_jsons/MeshMamba_non_texture_Starfruit_L3.json" \
    --output-dir "${VIDEO_OUT}" \
    --max-frames "${MAX_FRAMES}" --width "${WIDTH}" --height "${HEIGHT}"

echo "=== smoke: MeshMamba non_texture Starfruit_L3 cone ==="
MAP=$(find_map "Starfruit_L3" "Starfruit_L3_cone_faces.txt" \
    "${SMOKE_MAPS}/cone_projection_on_mesh")
${RENDER} \
    --dataset MeshMamba --track non_texture --model Starfruit_L3 \
    --map-type cone \
    --map-file "${MAP}" \
    --mesh "${DATASETS_ROOT}/datasets/MeshMamba/MeshFile/non_texture/Starfruit_L3/Starfruit_L3.obj" \
    --placement-json "${REPO_ROOT}/jsons/object_placement/mamba_non_jsons/MeshMamba_non_texture_Starfruit_L3.json" \
    --output-dir "${VIDEO_OUT}" \
    --max-frames "${MAX_FRAMES}" --width "${WIDTH}" --height "${HEIGHT}"

echo "=== smoke: SAL3D bunny screen_space ==="
MAP=$(find_map "bunny" "bunny_screen_space_vertices.txt" \
    "${SMOKE_MAPS}/screen_space_gaussian")
${RENDER} \
    --dataset SAL3D --track sal3d --model bunny \
    --map-type screen_space \
    --map-file "${MAP}" \
    --mesh "${DATASETS_ROOT}/datasets/SAL3D/OBJ/bunny/bunny.obj" \
    --placement-json "${REPO_ROOT}/jsons/object_placement/sal3d_jsons/Sal3D_bunny.json" \
    --output-dir "${VIDEO_OUT}" \
    --max-frames "${MAX_FRAMES}" --width "${WIDTH}" --height "${HEIGHT}"

echo "=== smoke: SAL3D bunny cone ==="
MAP=$(find_map "bunny" "bunny_cone_vertices.txt" \
    "${SMOKE_MAPS}/cone_projection_on_mesh")
${RENDER} \
    --dataset SAL3D --track sal3d --model bunny \
    --map-type cone \
    --map-file "${MAP}" \
    --mesh "${DATASETS_ROOT}/datasets/SAL3D/OBJ/bunny/bunny.obj" \
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
find "${VIDEO_OUT}" -name "manifest.json" | sort | xargs -I{} sh -c 'echo "--- {} ---"; python3 -c "import json,sys; d=json.load(open(sys.argv[1])); r=d[\"render\"]; print(f\"  frames={r[\"n_rendered_frames\"]} domain={r[\"map_domain\"]} {r[\"width\"]}x{r[\"height\"]}\")" "$@"' _ {}
