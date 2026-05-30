#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

if [ "$#" -gt 0 ]; then
  manifests=("$@")
else
  manifests=()
  while IFS= read -r manifest; do
    manifests+=("$manifest")
  done < <(find "$REPO_ROOT/test/manifests" -maxdepth 1 -type f -name 'preview_*.json' | sort)
fi

if [ "${#manifests[@]}" -eq 0 ]; then
  echo "no preview manifests found" >&2
  exit 1
fi

for manifest in "${manifests[@]}"; do
  echo "=== preview manifest: $manifest ==="
  "$REPO_ROOT/test/launch/run_preview_manifest.sh" "$manifest"
done
