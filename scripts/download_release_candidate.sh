#!/usr/bin/env bash
# Download and validate a release candidate into an isolated data directory.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TAG="${TAG:-v2.0-data-rc4}"
REPO="${REPO:-Danchik757/Mesh-Saliency-Projection}"
DATA_ROOT="${1:-}"

if [[ -z "${DATA_ROOT}" ]]; then
    echo "Usage: TAG=v2.0-data-rc4 bash scripts/download_release_candidate.sh /path/to/release_data" >&2
    exit 2
fi

if [[ -e "${DATA_ROOT}" ]] && [[ -n "$(find "${DATA_ROOT}" -mindepth 1 -maxdepth 1 -print -quit)" ]]; then
    echo "ERROR: DATA_ROOT must be empty or absent: ${DATA_ROOT}" >&2
    exit 2
fi
mkdir -p "${DATA_ROOT}"
gh release download "${TAG}" --repo "${REPO}" --dir "${DATA_ROOT}"
python3 "${REPO_ROOT}/scripts/validate_release_candidate.py" "${DATA_ROOT}"

EXTRACT_ROOT="${DATA_ROOT}/extracted"
mkdir -p "${EXTRACT_ROOT}"
python3 -c 'import json,sys; print("\n".join(x["name"] for x in json.load(open(sys.argv[1]))["archives"]))' \
    "${DATA_ROOT}/release_manifest.json" |
while IFS= read -r archive; do
    unzip -q "${DATA_ROOT}/${archive}" -d "${EXTRACT_ROOT}"
done

echo "Validated release extracted to: ${EXTRACT_ROOT}"
