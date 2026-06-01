#!/usr/bin/env bash
# download_datasets.sh — download and extract all datasets from GitHub release
#
# Run on a NEW machine to set up all data for the benchmark pipeline.
#
# Prerequisites:
#   gh CLI installed and authenticated (gh auth login)
#   OR: pass --no-gh to use direct curl download (requires GITHUB_TOKEN env var
#       for private repos, or nothing for public repos).
#
# Usage:
#   bash scripts/download_datasets.sh --data-root /path/to/data [OPTIONS]
#
# Options:
#   --data-root DIR       Where to extract all datasets. Required.
#   --tag TAG             Release tag to download from. Default: v1.0-data
#   --repo OWNER/REPO     GitHub repo. Default: inferred from git remote.
#   --with-smooth-gaze    Also download sal3d_smooth_gaze.zip (~2 GB auxiliary).
#   --with-videos         Also download rendered videos (~256 MB).
#   --only PATTERN        Download only ZIPs matching pattern (e.g. "3dva*").
#   --list                Print all available release assets and exit.
#
# After download, set up env vars:
#   cp test/env/new_machine.env.sh.template test/env/local_paths.sh
#   # edit DATA_ROOT in that file
#   source test/env/local_paths.sh

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

DATA_ROOT=""
TAG="v1.0-data"
REPO=""
WITH_SMOOTH_GAZE=0
WITH_VIDEOS=0
ONLY_PATTERN=""
LIST_ONLY=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --data-root)       DATA_ROOT="$2"; shift 2 ;;
        --tag)             TAG="$2";       shift 2 ;;
        --repo)            REPO="$2";      shift 2 ;;
        --with-smooth-gaze) WITH_SMOOTH_GAZE=1; shift ;;
        --with-videos)     WITH_VIDEOS=1;  shift ;;
        --only)            ONLY_PATTERN="$2"; shift 2 ;;
        --list)            LIST_ONLY=1;    shift ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

if [[ -z "$REPO" ]]; then
    REPO=$(git -C "$REPO_ROOT" remote get-url origin 2>/dev/null \
        | sed 's|https://github.com/||; s|git@github.com:||; s|\.git$||')
fi

if [[ $LIST_ONLY -eq 1 ]]; then
    echo "Assets in release $TAG ($REPO):"
    gh release view "$TAG" --repo "$REPO" --json assets -q '.assets[].name'
    exit 0
fi

if [[ -z "$DATA_ROOT" ]]; then
    echo "ERROR: --data-root is required."
    echo "Usage: bash scripts/download_datasets.sh --data-root /path/to/data"
    exit 1
fi

mkdir -p "$DATA_ROOT"
TMP_DIR=$(mktemp -d)
trap 'rm -rf "$TMP_DIR"' EXIT

echo "Repo     : $REPO"
echo "Tag      : $TAG"
echo "Data root: $DATA_ROOT"
echo ""

# ── decide which ZIPs to download ────────────────────────────────────────────
ALL_ZIPS=(
    "3dva_objs.zip"
    "3dva_gt.zip"
    "meshmamba_non_texture_objs.zip"
    "meshmamba_rgb_texture_objs.zip"
    "meshmamba_saliency_gt.zip"
    "sal3d_meshes.zip"
    "sal3d_gaze.zip"
    "gaze_csv_3dva.zip"
    "gaze_csv_meshmamba.zip"
    "camera_jsons.zip"
)

if [[ $WITH_SMOOTH_GAZE -eq 1 ]]; then
    ALL_ZIPS+=("sal3d_smooth_gaze.zip")
fi
if [[ $WITH_VIDEOS -eq 1 ]]; then
    ALL_ZIPS+=("videos_3dva.zip" "videos_meshmamba.zip" "videos_sal3d.zip")
fi

# apply --only filter
SELECTED_ZIPS=()
for z in "${ALL_ZIPS[@]}"; do
    if [[ -z "$ONLY_PATTERN" ]] || [[ "$z" == $ONLY_PATTERN ]]; then
        SELECTED_ZIPS+=("$z")
    fi
done

echo "Will download ${#SELECTED_ZIPS[@]} ZIP(s):"
for z in "${SELECTED_ZIPS[@]}"; do echo "  $z"; done
echo ""

# ── extraction helper (must be defined before the download loop) ──────────────
_extract() {
    local zip_file="$1" target="$2" zip_name="$3"
    # Each ZIP was created with the internal path structure that matches
    # $DATA_ROOT layout. See package_datasets.sh for the mapping.
    case "$zip_name" in
        3dva_objs.zip)
            unzip -q "$zip_file" -d "$target"
            # Result: $target/3DVA/3DModels-Simplif-up/
            ;;
        3dva_gt.zip)
            unzip -q "$zip_file" -d "$target"
            # Result: $target/3DVA/FixationMaps/ + CentricityAndVisibilityMaps/
            ;;
        meshmamba_non_texture_objs.zip)
            mkdir -p "$target/MeshMamba/MeshFile"
            unzip -q "$zip_file" -d "$target/MeshMamba/MeshFile"
            # Result: $target/MeshMamba/MeshFile/non_texture/
            ;;
        meshmamba_rgb_texture_objs.zip)
            mkdir -p "$target/MeshMamba/MeshFile"
            unzip -q "$zip_file" -d "$target/MeshMamba/MeshFile"
            ;;
        meshmamba_saliency_gt.zip)
            mkdir -p "$target/MeshMamba"
            unzip -q "$zip_file" -d "$target/MeshMamba"
            # Result: $target/MeshMamba/SaliencyMap/
            ;;
        sal3d_meshes.zip|sal3d_gaze.zip|sal3d_smooth_gaze.zip)
            mkdir -p "$target/SAL3D"
            unzip -q "$zip_file" -d "$target/SAL3D"
            ;;
        gaze_csv_3dva.zip)
            mkdir -p "$target/gaze_csv"
            unzip -q "$zip_file" -d "$target/gaze_csv"
            ;;
        gaze_csv_meshmamba.zip)
            mkdir -p "$target/gaze_csv"
            unzip -q "$zip_file" -d "$target/gaze_csv"
            ;;
        camera_jsons.zip)
            unzip -q "$zip_file" -d "$target"
            # Result: $target/jsons_for_models/
            ;;
        videos_*.zip)
            unzip -q "$zip_file" -d "$target"
            # Result: $target/videos/
            ;;
    esac
    touch "$target/.downloaded_${zip_name%.zip}"
    echo "       done."
}

# ── download + extract ────────────────────────────────────────────────────────
for zip_name in "${SELECTED_ZIPS[@]}"; do
    dest="$TMP_DIR/$zip_name"

    # skip if marker file present (already extracted in a previous run)
    marker="$DATA_ROOT/.downloaded_${zip_name%.zip}"
    if [[ -f "$marker" ]]; then
        echo "[skip] $zip_name (already extracted)"
        continue
    fi

    echo "[download] $zip_name ..."
    gh release download "$TAG" --repo "$REPO" --pattern "$zip_name" --dir "$TMP_DIR" --clobber

    echo "[extract] $zip_name → $DATA_ROOT"
    _extract "$dest" "$DATA_ROOT" "$zip_name"
done

echo ""
echo "All done. Data root: $DATA_ROOT"
echo ""
echo "Next steps:"
echo "  1. cp test/env/new_machine.env.sh.template test/env/local_paths.sh"
echo "  2. Set DATA_ROOT=\"$DATA_ROOT\" in test/env/local_paths.sh"
echo "  3. source test/env/local_paths.sh"
