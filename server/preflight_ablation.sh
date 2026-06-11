#!/usr/bin/env bash
# Preflight checks for rc3 window/delay ablation.
# Run on EACH server before launching a shard.
#
# Usage:
#   export REPROJECT_SERVER_ROOT=/mnt/ssd1/29d_kon/acm_2026
#   export REPROJECT_WORKSPACE_NAME=coordinator   # default
#   bash server/preflight_ablation.sh
#
# Do NOT run a shard launch until this script prints "[preflight] ALL OK".

set -euo pipefail

REPROJECT_SERVER_ROOT="${REPROJECT_SERVER_ROOT:-/mnt/ssd1/29d_kon/acm_2026}"
REPROJECT_WORKSPACE_NAME="${REPROJECT_WORKSPACE_NAME:-coordinator}"
REPROJECT_RELEASE_TAG="v2.0-data-rc3"
TARGET_BRANCH="agent/rc3-release-and-ablation-infra"
TARGET_HEAD="b7b32a4"

REPO_ROOT="${REPROJECT_SERVER_ROOT}/agents/${REPROJECT_WORKSPACE_NAME}/Mesh-Saliency-Projection"
RELEASE_DOWNLOAD_ROOT="${REPROJECT_SERVER_ROOT}/shared_release_data/${REPROJECT_RELEASE_TAG}"
RELEASE_DATA_ROOT="${RELEASE_DOWNLOAD_ROOT}/extracted"

CONDA_ENVS_ROOT="${REPROJECT_SERVER_ROOT}/environments"
CONDA_ENV_NAME="${CONDA_ENV_NAME:-reproject-benchmark}"
REPROJECT_PYTHON="${CONDA_ENVS_ROOT}/${CONDA_ENV_NAME}/bin/python"

fail() { echo "[preflight] FAIL: $*" >&2; exit 1; }
ok()   { echo "[preflight] ok: $*"; }

echo "[preflight] server root: ${REPROJECT_SERVER_ROOT}"
echo "[preflight] repo: ${REPO_ROOT}"
echo "[preflight] release: ${RELEASE_DATA_ROOT}"

# ── 1. repo ────────────────────────────────────────────────────────────────

[[ -d "${REPO_ROOT}/.git" ]] || fail "repo not found at ${REPO_ROOT}"
cd "${REPO_ROOT}"

git fetch origin "${TARGET_BRANCH}" 2>&1 | tail -3

current_branch=$(git rev-parse --abbrev-ref HEAD)
if [[ "${current_branch}" != "${TARGET_BRANCH}" ]]; then
    echo "[preflight] checking out ${TARGET_BRANCH}"
    git checkout "${TARGET_BRANCH}"
fi

git merge --ff-only "origin/${TARGET_BRANCH}"
actual_head=$(git rev-parse --short HEAD)
[[ "${actual_head}" == "${TARGET_HEAD}" ]] \
    || fail "HEAD is ${actual_head}, expected ${TARGET_HEAD}"
ok "HEAD = ${actual_head}"

dirty=$(git status --short | grep -v '^??' || true)
[[ -z "${dirty}" ]] || fail "working tree is dirty:\n${dirty}"
ok "working tree clean"

# ── 2. python ─────────────────────────────────────────────────────────────

[[ -x "${REPROJECT_PYTHON}" ]] || fail "python not found: ${REPROJECT_PYTHON}"
ok "python: ${REPROJECT_PYTHON}"

# ── 3. pytest ─────────────────────────────────────────────────────────────

echo "[preflight] running pytest -q ..."
"${REPROJECT_PYTHON}" -m pytest -q 2>&1 | tail -3
ok "pytest passed"

# ── 4. compileall ──────────────────────────────────────────────────────────

"${REPROJECT_PYTHON}" -m compileall -q utils/ scripts/ test/ reprojection_methods/ server/ 2>&1 \
    || fail "compileall failed"
ok "compileall clean"

# ── 5. release assets ─────────────────────────────────────────────────────

[[ -d "${RELEASE_DATA_ROOT}" ]] || {
    echo "[preflight] release not extracted — running sync_release_rc3.sh"
    bash "${REPO_ROOT}/server/sync_release_rc3.sh" \
        --repo "Danchik757/Mesh-Saliency-Projection" \
        --tag "${REPROJECT_RELEASE_TAG}" \
        --extract-dir "${RELEASE_DATA_ROOT}"
}

SUMS_FILE="${RELEASE_DOWNLOAD_ROOT}/assets/SHA256SUMS"
[[ -f "${SUMS_FILE}" ]] || fail "SHA256SUMS not found: ${SUMS_FILE}"

echo "[preflight] verifying SHA256SUMS ..."
cd "${RELEASE_DOWNLOAD_ROOT}/assets"
sha256_failures=0
while IFS= read -r line; do
    [[ -z "${line}" ]] && continue
    expected="${line%%  *}"
    fname="${line#*  }"
    [[ -f "${fname}" ]] || { echo "[preflight] missing: ${fname}"; (( sha256_failures++ )) || true; continue; }
    if command -v sha256sum &>/dev/null; then
        actual="$(sha256sum "${fname}" | awk '{print $1}')"
    else
        actual="$(shasum -a 256 "${fname}" | awk '{print $1}')"
    fi
    [[ "${actual}" == "${expected}" ]] \
        || { echo "[preflight] SHA256 mismatch: ${fname}"; (( sha256_failures++ )) || true; }
done < "${SUMS_FILE}"
cd - >/dev/null
(( sha256_failures == 0 )) || fail "${sha256_failures} SHA256 verification failure(s)"
ok "SHA256SUMS verified"

# ── 6. fixation root ───────────────────────────────────────────────────────

FIXATION_ROOT="${RELEASE_DATA_ROOT}/participant_fixations_offset0_full_cleaned"
[[ -d "${FIXATION_ROOT}" ]] || fail "fixation root not found: ${FIXATION_ROOT}"
n_fix=$(find "${FIXATION_ROOT}" -name "fixations.json" | wc -l | tr -d ' ')
[[ "${n_fix}" -eq 298 ]] || fail "expected 298 fixations.json, found ${n_fix}"
ok "fixation root: ${n_fix} files"

# ── 7. SAL3D fixed GT ──────────────────────────────────────────────────────

SAL3D_FIXED_GT_DIR="${RELEASE_DATA_ROOT}/sal3d_fixed_face_gt"
[[ -d "${SAL3D_FIXED_GT_DIR}" ]] || fail "sal3d_fixed_face_gt not found: ${SAL3D_FIXED_GT_DIR}"
ok "sal3d_fixed_face_gt present"

# ── 8. dry-run shard (sigma sweep, 2 jobs only) ───────────────────────────

echo "[preflight] dry-run smoke check (sigma sweep, 2 jobs) ..."
"${REPROJECT_PYTHON}" test/launch/run_sigma_sweep_rc3.py \
    --dry-run \
    --datasets 3dva --models A380 \
    --methods screen_space \
    --ss-multipliers 1.00 1.15 \
    --workers 1 \
    --batch-output-dir "/tmp/preflight_smoke_$$" 2>&1 | grep -E "jobs:|done:"
ok "dry-run smoke OK"

echo ""
echo "[preflight] ALL OK — ready to launch shard"
