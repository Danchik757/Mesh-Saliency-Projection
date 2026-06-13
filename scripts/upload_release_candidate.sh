#!/usr/bin/env bash
# Validate and upload a versioned release candidate. Never overwrites v1.0-data.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TAG="${TAG:-v2.0-data-rc4}"
ASSETS_DIR="${ASSETS_DIR:-${REPO_ROOT}/release_assets/${TAG}}"
REPO="${REPO:-Danchik757/Mesh-Saliency-Projection}"

if [[ "${TAG}" == "v1.0-data" ]]; then
    echo "ERROR: refusing to overwrite historical release v1.0-data" >&2
    exit 2
fi

# The candidate validator verifies the embedded data_contract_validation.json,
# archive SHA-256 values, ZIP CRCs, inventories, and release contracts. Do not
# re-run validate_data_contract.py here against machine-local source defaults:
# the upload operator may only have the completed release candidate.
python3 "${REPO_ROOT}/scripts/validate_release_candidate.py" "${ASSETS_DIR}"

if gh release view "${TAG}" --repo "${REPO}" >/dev/null 2>&1; then
    echo "ERROR: release ${TAG} already exists; choose a new candidate tag" >&2
    exit 2
fi

gh release create "${TAG}" \
    --repo "${REPO}" \
    --title "Benchmark data release candidate ${TAG}" \
    --prerelease \
    --notes-file "${REPO_ROOT}/docs/RELEASE_BUILD_AND_VALIDATION.md"

for asset in "${ASSETS_DIR}"/*.zip \
    "${ASSETS_DIR}/release_manifest.json" \
    "${ASSETS_DIR}/data_contract_validation.json" \
    "${ASSETS_DIR}/SHA256SUMS"; do
    gh release upload "${TAG}" "${asset}" --repo "${REPO}"
done

gh release view "${TAG}" --repo "${REPO}" --json url -q .url
