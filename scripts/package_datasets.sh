#!/usr/bin/env bash
# package_datasets.sh — zip all local dataset components into release_assets/
#
# Run on the machine that has the data. Creates release_assets/*.zip ready
# for upload to a GitHub release with upload_release.sh.
#
# Usage:
#   bash scripts/package_datasets.sh [--with-smooth-gaze] [--with-videos]
#
# Flags:
#   --with-smooth-gaze   Include SAL3D/Smooth_Gaze (~2 GB). Skipped by default
#                        because it's auxiliary (not GT) and may exceed GitHub 2 GB limit.
#   --with-videos        Include per-dataset rendered videos (~256 MB). Skipped by default.
#
# Output directory: release_assets/   (created next to this script's repo root)
# Each ZIP extracts under $DATA_ROOT with the structure expected by
# test/env/new_machine.env.sh.template

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ASSETS_DIR="$REPO_ROOT/release_assets"
mkdir -p "$ASSETS_DIR"

WITH_SMOOTH_GAZE=0
WITH_VIDEOS=0
for arg in "$@"; do
    [[ "$arg" == "--with-smooth-gaze" ]] && WITH_SMOOTH_GAZE=1
    [[ "$arg" == "--with-videos"      ]] && WITH_VIDEOS=1
done

# ── Source paths on this machine ──────────────────────────────────────────────
DVA_ROOT="/Users/admin/Documents/LAB/Dataset/3DVA"
GAZE_DATA="/Users/admin/Documents/LAB/SALIENCY_code/GAZE_DATA"
VIDEOS_ROOT="/Users/admin/Documents/LAB/SALIENCY_code/videos"

echo "Output dir: $ASSETS_DIR"
echo ""

_zip() {
    local name="$1" src_dir="$2" zip_prefix="$3"
    local out="$ASSETS_DIR/${name}.zip"
    if [[ -f "$out" ]]; then
        echo "  [skip] $name.zip already exists"
        return
    fi
    if [[ ! -d "$src_dir" ]]; then
        echo "  [missing] $src_dir  →  skipping $name.zip"
        return
    fi
    echo "  [zip] $name.zip  (from $src_dir)"
    # cd to parent of zip_prefix so the ZIP stores path starting at zip_prefix
    local parent="${src_dir%/"${zip_prefix##*/}"}"
    (cd "$parent" && zip -r "$out" "${zip_prefix##*/}" -x "*.DS_Store" -x "__MACOSX/*")
    local size
    size=$(du -sh "$out" | cut -f1)
    echo "        → $size"
}

_zip_subdir() {
    # zip multiple subdirs into one ZIP, all under a common base
    local name="$1" base_dir="$2" zip_base="$3"
    shift 3
    local out="$ASSETS_DIR/${name}.zip"
    if [[ -f "$out" ]]; then
        echo "  [skip] $name.zip already exists"
        return
    fi
    echo "  [zip] $name.zip  (from $base_dir / $*)"
    (cd "$base_dir" && zip -r "$out" "$@" -x "*.DS_Store" -x "__MACOSX/*")
    local size
    size=$(du -sh "$out" | cut -f1)
    echo "        → $size"
}

# ── 3DVA ──────────────────────────────────────────────────────────────────────
echo "=== 3DVA ==="
(cd "$DVA_ROOT/.." && zip -r "$ASSETS_DIR/3dva_objs.zip" \
    "3DVA/3DModels-Simplif-up" \
    -x "*.DS_Store" -x "__MACOSX/*") \
    && echo "  3dva_objs.zip → $(du -sh "$ASSETS_DIR/3dva_objs.zip" | cut -f1)" \
    || echo "  [skip] 3dva_objs.zip already exists or failed"

(cd "$DVA_ROOT/.." && zip -r "$ASSETS_DIR/3dva_gt.zip" \
    "3DVA/FixationMaps" \
    "3DVA/CentricityAndVisibilityMaps" \
    -x "*.DS_Store" -x "__MACOSX/*") \
    && echo "  3dva_gt.zip → $(du -sh "$ASSETS_DIR/3dva_gt.zip" | cut -f1)" \
    || echo "  [skip] 3dva_gt.zip already exists or failed"

# ── MeshMamba ─────────────────────────────────────────────────────────────────
echo ""
echo "=== MeshMamba ==="
MAMBA_SRC="$GAZE_DATA/datasets/MeshMamba/MeshMambaSaliency"

(cd "$MAMBA_SRC/MeshFile" && zip -r "$ASSETS_DIR/meshmamba_non_texture_objs.zip" \
    "non_texture" -x "*.DS_Store" -x "__MACOSX/*") \
    && echo "  meshmamba_non_texture_objs.zip → $(du -sh "$ASSETS_DIR/meshmamba_non_texture_objs.zip" | cut -f1)" \
    || echo "  [skip/fail] meshmamba_non_texture_objs"

(cd "$MAMBA_SRC/MeshFile" && zip -r "$ASSETS_DIR/meshmamba_rgb_texture_objs.zip" \
    "rgb_texture" -x "*.DS_Store" -x "__MACOSX/*") \
    && echo "  meshmamba_rgb_texture_objs.zip → $(du -sh "$ASSETS_DIR/meshmamba_rgb_texture_objs.zip" | cut -f1)" \
    || echo "  [skip/fail] meshmamba_rgb_texture_objs"

(cd "$MAMBA_SRC" && zip -r "$ASSETS_DIR/meshmamba_saliency_gt.zip" \
    "SaliencyMap" -x "*.DS_Store" -x "__MACOSX/*") \
    && echo "  meshmamba_saliency_gt.zip → $(du -sh "$ASSETS_DIR/meshmamba_saliency_gt.zip" | cut -f1)" \
    || echo "  [skip/fail] meshmamba_saliency_gt"

# ── SAL3D ─────────────────────────────────────────────────────────────────────
echo ""
echo "=== SAL3D ==="
SAL3D_SRC="$GAZE_DATA/datasets/SAL3D/SAL3D_Dataset"

(cd "$SAL3D_SRC" && zip -r "$ASSETS_DIR/sal3d_meshes.zip" \
    "Meshes" -x "*.DS_Store" -x "__MACOSX/*") \
    && echo "  sal3d_meshes.zip → $(du -sh "$ASSETS_DIR/sal3d_meshes.zip" | cut -f1)" \
    || echo "  [skip/fail] sal3d_meshes"

(cd "$SAL3D_SRC" && zip -r "$ASSETS_DIR/sal3d_gaze.zip" \
    "Gaze" -x "*.DS_Store" -x "__MACOSX/*") \
    && echo "  sal3d_gaze.zip → $(du -sh "$ASSETS_DIR/sal3d_gaze.zip" | cut -f1)" \
    || echo "  [skip/fail] sal3d_gaze"

if [[ $WITH_SMOOTH_GAZE -eq 1 ]]; then
    echo "  [smooth_gaze] packing ~2 GB ..."
    (cd "$SAL3D_SRC" && zip -r "$ASSETS_DIR/sal3d_smooth_gaze.zip" \
        "Smooth_Gaze" -x "*.DS_Store" -x "__MACOSX/*") \
        && echo "  sal3d_smooth_gaze.zip → $(du -sh "$ASSETS_DIR/sal3d_smooth_gaze.zip" | cut -f1)"
else
    echo "  [skipped] sal3d_smooth_gaze.zip  (add --with-smooth-gaze to include)"
fi

# ── Gaze CSVs ─────────────────────────────────────────────────────────────────
echo ""
echo "=== Gaze CSVs ==="
CSV_SRC="$GAZE_DATA/csv_for_models"

(cd "$CSV_SRC" && zip -r "$ASSETS_DIR/gaze_csv_3dva.zip" \
    "3DVA" -x "*.DS_Store" -x "__MACOSX/*") \
    && echo "  gaze_csv_3dva.zip → $(du -sh "$ASSETS_DIR/gaze_csv_3dva.zip" | cut -f1)" \
    || echo "  [skip/fail] gaze_csv_3dva"

(cd "$CSV_SRC" && zip -r "$ASSETS_DIR/gaze_csv_meshmamba.zip" \
    "MeshMamba_non_texture" "MeshMamba_rgb_texture" \
    -x "*.DS_Store" -x "__MACOSX/*") \
    && echo "  gaze_csv_meshmamba.zip → $(du -sh "$ASSETS_DIR/gaze_csv_meshmamba.zip" | cut -f1)" \
    || echo "  [skip/fail] gaze_csv_meshmamba"

# ── Camera JSONs ──────────────────────────────────────────────────────────────
echo ""
echo "=== Camera JSONs ==="
JSON_SRC="$GAZE_DATA/jsons_for_models"

(cd "$JSON_SRC/.." && zip -r "$ASSETS_DIR/camera_jsons.zip" \
    "jsons_for_models" -x "*.DS_Store" -x "__MACOSX/*") \
    && echo "  camera_jsons.zip → $(du -sh "$ASSETS_DIR/camera_jsons.zip" | cut -f1)" \
    || echo "  [skip/fail] camera_jsons"

# ── Videos (optional) ─────────────────────────────────────────────────────────
if [[ $WITH_VIDEOS -eq 1 ]]; then
    echo ""
    echo "=== Videos ==="
    (cd "$VIDEOS_ROOT/.." && zip -r "$ASSETS_DIR/videos_3dva.zip" \
        "videos/3DVA" -x "*.DS_Store" -x "__MACOSX/*") \
        && echo "  videos_3dva.zip → $(du -sh "$ASSETS_DIR/videos_3dva.zip" | cut -f1)"

    (cd "$VIDEOS_ROOT/.." && zip -r "$ASSETS_DIR/videos_meshmamba.zip" \
        "videos/MeshMamba_non_texture" "videos/MeshMamba_rgb_texture" \
        -x "*.DS_Store" -x "__MACOSX/*") \
        && echo "  videos_meshmamba.zip → $(du -sh "$ASSETS_DIR/videos_meshmamba.zip" | cut -f1)"

    (cd "$VIDEOS_ROOT/.." && zip -r "$ASSETS_DIR/videos_sal3d.zip" \
        "videos/SAL3D" -x "*.DS_Store" -x "__MACOSX/*") \
        && echo "  videos_sal3d.zip → $(du -sh "$ASSETS_DIR/videos_sal3d.zip" | cut -f1)"
else
    echo ""
    echo "=== Videos: skipped (add --with-videos to include) ==="
fi

echo ""
echo "Done. All assets:"
du -sh "$ASSETS_DIR"/*.zip 2>/dev/null || echo "(none)"
echo ""
echo "Next: bash scripts/upload_release.sh"
