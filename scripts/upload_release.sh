#!/usr/bin/env bash
# upload_release.sh — create a GitHub release and upload all ZIPs from release_assets/
#
# Prerequisites:
#   1. gh CLI installed and authenticated (gh auth login)
#   2. release_assets/*.zip exist (run package_datasets.sh first)
#
# Usage:
#   bash scripts/upload_release.sh [--tag v1.0-data] [--repo owner/repo]
#
# Default tag:  v1.0-data
# Default repo: inferred from git remote origin

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ASSETS_DIR="$REPO_ROOT/release_assets"

TAG="v1.0-data"
REPO=""
for arg in "$@"; do
    case "$arg" in
        --tag)  shift; TAG="$1" ;;
        --repo) shift; REPO="$1" ;;
    esac
done

if [[ -z "$REPO" ]]; then
    REPO=$(git -C "$REPO_ROOT" remote get-url origin 2>/dev/null \
        | sed 's|https://github.com/||; s|git@github.com:||; s|\.git$||')
fi

echo "Repo : $REPO"
echo "Tag  : $TAG"
echo "Assets: $ASSETS_DIR"
echo ""

# Verify assets exist
shopt -s nullglob
zips=("$ASSETS_DIR"/*.zip)
if [[ ${#zips[@]} -eq 0 ]]; then
    echo "ERROR: no .zip files in $ASSETS_DIR — run package_datasets.sh first."
    exit 1
fi

echo "ZIPs to upload (${#zips[@]} files):"
du -sh "${zips[@]}"
echo ""

# Create release if it doesn't exist
if gh release view "$TAG" --repo "$REPO" &>/dev/null; then
    echo "Release $TAG already exists — will upload/overwrite assets."
else
    echo "Creating release $TAG ..."
    gh release create "$TAG" \
        --repo "$REPO" \
        --title "Datasets v1.0" \
        --notes "$(cat <<'EOF'
## Dataset release

All components required to reproduce benchmark experiments.

| ZIP | Contents |
|-----|----------|
| 3dva_objs.zip | 3DVA OBJ meshes (corrected `-up` orientation, 32 models) |
| 3dva_gt.zip | 3DVA GT fixation maps + centricity maps |
| meshmamba_non_texture_objs.zip | MeshMamba non-texture OBJ (105 models) |
| meshmamba_rgb_texture_objs.zip | MeshMamba RGB-texture OBJ (105 models) |
| meshmamba_saliency_gt.zip | MeshMamba per-face GT saliency maps |
| sal3d_meshes.zip | SAL3D OBJ meshes (57 models) |
| sal3d_gaze.zip | SAL3D raw gaze data (58 models) |
| sal3d_smooth_gaze.zip | SAL3D smooth-gaze neighbour lists (optional auxiliary) |
| gaze_csv_3dva.zip | Our eye-tracker recordings for 3DVA (32 models) |
| gaze_csv_meshmamba.zip | Our eye-tracker recordings for MeshMamba (105+105 models) |
| camera_jsons.zip | Blender camera/animation params for all datasets |
| videos_3dva.zip | Rendered videos 3DVA (optional, for alignment check) |
| videos_meshmamba.zip | Rendered videos MeshMamba (optional) |
| videos_sal3d.zip | Rendered videos SAL3D (optional) |

## Setup on new machine

```bash
bash scripts/download_datasets.sh --data-root /path/to/data
cp test/env/new_machine.env.sh.template test/env/local_paths.sh
# edit DATA_ROOT in test/env/local_paths.sh
source test/env/local_paths.sh
```
EOF
)"
fi

# Upload each ZIP (--clobber replaces if already exists)
# cd into assets dir first so gh sees plain filenames, not the full path.
# This avoids gh mis-parsing '#' in the repo path as a label separator.
echo ""
echo "Uploading ..."
cd "$ASSETS_DIR"
for zip in "${zips[@]}"; do
    fname=$(basename "$zip")
    size=$(du -sh "$zip" | cut -f1)
    echo "  → $fname  ($size)"
    gh release upload "$TAG" "$fname" --repo "$REPO" --clobber
done

echo ""
echo "Done. Release URL:"
gh release view "$TAG" --repo "$REPO" --json url -q .url
