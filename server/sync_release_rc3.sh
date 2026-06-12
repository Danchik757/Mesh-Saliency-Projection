#!/usr/bin/env bash
# Sync v2.0-data-rc3 release assets to shared_release_data/v2.0-data-rc3/extracted.
#
# Usage:
#   ./server/sync_release_rc3.sh [--extract-dir <path>] [--repo <owner/repo>] [--tag <tag>]
#
# Requirements: gh (preferred) or curl/wget. No sudo required.
# Sets up: shared_release_data/v2.0-data-rc3/{assets,extracted}
#
# Do NOT run this script without reviewer/controller authorization.

set -euo pipefail

REPO="${REPO:-Danchik757/Mesh-Saliency-Projection}"
TAG="${TAG:-v2.0-data-rc3}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
EXTRACT_DIR="${EXTRACT_DIR:-${REPO_ROOT}/shared_release_data/${TAG}/extracted}"
ASSETS_DIR="${REPO_ROOT}/shared_release_data/${TAG}/assets"

REQUIRED_ARCHIVES=(
    participant_gaze_csv_original.zip
    participant_fixations_offset0_full_cleaned.zip
    object_placement_json_canonical.zip
    3dva_objs_corrected.zip
    3dva_gt.zip
    3dva_combined_gt.zip
    meshmamba_non_texture_objs.zip
    meshmamba_rgb_texture_objs.zip
    meshmamba_saliency_gt.zip
    sal3d_meshes.zip
    sal3d_gaze_gt.zip
    sal3d_fixed_face_gt.zip
    release_manifest.json
    SHA256SUMS
    data_contract_validation.json
)

# Parse arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        --extract-dir) EXTRACT_DIR="$2"; shift 2 ;;
        --repo)        REPO="$2";        shift 2 ;;
        --tag)         TAG="$2";         shift 2 ;;
        *) echo "[error] unknown argument: $1" >&2; exit 1 ;;
    esac
done

mkdir -p "${ASSETS_DIR}" "${EXTRACT_DIR}"
echo "[sync] tag=${TAG}  repo=${REPO}"
echo "[sync] assets  → ${ASSETS_DIR}"
echo "[sync] extract → ${EXTRACT_DIR}"

# ── download phase ────────────────────────────────────────────────────────────

_gh_available() { command -v gh &>/dev/null; }

_gh_auth_ok() {
    gh auth status &>/dev/null 2>&1
}

_download_with_gh() {
    echo "[sync] gh found — downloading assets via gh release download"
    cd "${ASSETS_DIR}"
    gh release download "${TAG}" \
        --repo "${REPO}" \
        --skip-existing \
        --dir "."
    cd - >/dev/null
}

_get_release_base_url() {
    echo "https://github.com/${REPO}/releases/download/${TAG}"
}

_download_one_curl() {
    local name="$1"
    local dest="${ASSETS_DIR}/${name}"
    if [[ -f "${dest}" ]]; then
        echo "[sync] skip (exists): ${name}"
        return 0
    fi
    local url
    url="$(_get_release_base_url)/${name}"
    echo "[sync] curl: ${name}"
    curl --fail --location --retry 3 --retry-delay 5 \
        --progress-bar \
        -o "${dest}.tmp" "${url}" && mv "${dest}.tmp" "${dest}"
}

_download_fallback_curl() {
    echo "[sync] gh not available — falling back to curl"
    for name in "${REQUIRED_ARCHIVES[@]}"; do
        _download_one_curl "${name}"
    done
}

if _gh_available && _gh_auth_ok; then
    _download_with_gh
else
    _download_fallback_curl
fi

# ── verify SHA256SUMS ─────────────────────────────────────────────────────────

SUMS_FILE="${ASSETS_DIR}/SHA256SUMS"
if [[ ! -f "${SUMS_FILE}" ]]; then
    echo "[error] SHA256SUMS not found at ${SUMS_FILE}" >&2
    exit 1
fi

echo "[sync] verifying SHA256SUMS"
cd "${ASSETS_DIR}"
sha256_failures=0
while IFS= read -r line; do
    [[ -z "${line}" ]] && continue
    expected_hash="${line%%  *}"
    fname="${line#*  }"
    if [[ ! -f "${fname}" ]]; then
        echo "[error] missing: ${fname}" >&2
        (( sha256_failures++ )) || true
        continue
    fi
    if command -v sha256sum &>/dev/null; then
        actual_hash="$(sha256sum "${fname}" | awk '{print $1}')"
    else
        actual_hash="$(shasum -a 256 "${fname}" | awk '{print $1}')"
    fi
    if [[ "${actual_hash}" != "${expected_hash}" ]]; then
        echo "[error] SHA256 mismatch: ${fname}" >&2
        echo "  expected: ${expected_hash}" >&2
        echo "  actual:   ${actual_hash}" >&2
        (( sha256_failures++ )) || true
    else
        echo "[ok] ${fname}"
    fi
done < "${SUMS_FILE}"
cd - >/dev/null

if (( sha256_failures > 0 )); then
    echo "[error] ${sha256_failures} SHA256 verification failure(s) — aborting extraction" >&2
    exit 1
fi
echo "[sync] all checksums OK"

# ── extract phase ─────────────────────────────────────────────────────────────

echo "[sync] extracting archives to ${EXTRACT_DIR}"

for name in "${REQUIRED_ARCHIVES[@]}"; do
    src="${ASSETS_DIR}/${name}"
    [[ "${name}" == *.zip ]] || continue
    [[ -f "${src}" ]] || continue
    dest_marker="${EXTRACT_DIR}/.extracted_${name%.zip}"
    if [[ -f "${dest_marker}" ]]; then
        echo "[sync] skip (already extracted): ${name}"
        continue
    fi
    echo "[sync] unzip: ${name}"
    unzip -q "${src}" -d "${EXTRACT_DIR}"
    touch "${dest_marker}"
done

echo "[sync] done"
echo "[sync] extracted data: ${EXTRACT_DIR}"
