#!/usr/bin/env bash
# Side-input transfer helper: pack archives locally and scp them to vg-intellect.
#
# Transfer policy:
#   CODE   — arrives via GitHub (git pull on server)
#   SIDE INPUTS (csv/json) — arrive via this script: local tar.gz → scp → server unpack
#
# Datasets (OBJ meshes, GT saliency maps) are already on the server.
# This script handles ONLY participant CSV files and JSON camera metadata.
#
# Run this LOCALLY (not on the server) before first pilot run.
#
# Prerequisite: run test/side_inputs/pack_*.sh first to create archives, or
# let this script call them automatically via --pack flag.
#
# Usage:
#   source test/env/local_paths.example.sh   # or set env vars manually
#   export SSH_HOST="vg-intellect"
#   export REMOTE_SIDE_INPUTS="/home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/side_inputs"
#   bash test/launch/mirror_side_inputs.sh
#
# SSH note:
#   The SSH host alias "vg-intellect" must be configured in ~/.ssh/config with:
#     Host vg-intellect
#         User 29d_kon@lab.graphicon.ru
#         HostName <actual-ip-or-hostname>
#   Then scp uses:  scp archive.tar.gz vg-intellect:/remote/path/
#
# Required env vars:
#   LOCAL_GAZE_DATA_ROOT  — local GAZE_DATA directory
#   LOCAL_PACK_DIR        — where archives are written (default: /tmp/reproject_side_inputs)
#   SSH_HOST              — SSH alias for the server (default: vg-intellect)
#   REMOTE_SIDE_INPUTS    — absolute path on server for side inputs
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

: "${LOCAL_GAZE_DATA_ROOT:?Set LOCAL_GAZE_DATA_ROOT (e.g. source test/env/local_paths.example.sh)}"
: "${REMOTE_SIDE_INPUTS:?Set REMOTE_SIDE_INPUTS to the absolute server path, e.g. /home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/side_inputs}"

SSH_HOST="${SSH_HOST:-vg-intellect}"
LOCAL_PACK_DIR="${LOCAL_PACK_DIR:-/tmp/reproject_side_inputs}"

echo "[mirror_side_inputs] local_gaze_data_root = ${LOCAL_GAZE_DATA_ROOT}"
echo "[mirror_side_inputs] local_pack_dir       = ${LOCAL_PACK_DIR}"
echo "[mirror_side_inputs] ssh_host             = ${SSH_HOST}"
echo "[mirror_side_inputs] remote_side_inputs   = ${REMOTE_SIDE_INPUTS}"

# ---------- 3DVA side inputs ----------
echo "[mirror_side_inputs] packing 3DVA archives..."
LOCAL_GAZE_DATA_ROOT="${LOCAL_GAZE_DATA_ROOT}" LOCAL_PACK_DIR="${LOCAL_PACK_DIR}" \
  bash "${REPO_ROOT}/test/side_inputs/pack_3dva.sh"

echo "[mirror_side_inputs] transferring 3DVA archives..."
scp "${LOCAL_PACK_DIR}/3dva_csv.tar.gz"  "${SSH_HOST}:${REMOTE_SIDE_INPUTS}/"
scp "${LOCAL_PACK_DIR}/3dva_json.tar.gz" "${SSH_HOST}:${REMOTE_SIDE_INPUTS}/"

# ---------- MeshMamba non_texture side inputs ----------
echo "[mirror_side_inputs] packing MeshMamba_non_texture archives..."
LOCAL_GAZE_DATA_ROOT="${LOCAL_GAZE_DATA_ROOT}" LOCAL_PACK_DIR="${LOCAL_PACK_DIR}" \
  bash "${REPO_ROOT}/test/side_inputs/pack_meshmamba_non_texture.sh"

echo "[mirror_side_inputs] transferring MeshMamba_non_texture archives..."
scp "${LOCAL_PACK_DIR}/meshmamba_non_texture_csv.tar.gz"  "${SSH_HOST}:${REMOTE_SIDE_INPUTS}/"
scp "${LOCAL_PACK_DIR}/meshmamba_non_texture_json.tar.gz" "${SSH_HOST}:${REMOTE_SIDE_INPUTS}/"

# ---------- server-side unpack ----------
echo "[mirror_side_inputs] unpacking archives on server..."
# shellcheck disable=SC2087
ssh "${SSH_HOST}" bash <<REMOTE
set -euo pipefail
cd "${REMOTE_SIDE_INPUTS}"

echo "[server] unpacking 3dva_csv ..."
mkdir -p 3DVA/csv
tar -xzf 3dva_csv.tar.gz -C 3DVA/csv --strip-components=1

echo "[server] unpacking 3dva_json ..."
mkdir -p 3DVA/json
tar -xzf 3dva_json.tar.gz -C 3DVA/json --strip-components=1

echo "[server] unpacking meshmamba_non_texture_csv ..."
mkdir -p MeshMamba_non_texture/csv
tar -xzf meshmamba_non_texture_csv.tar.gz -C MeshMamba_non_texture/csv --strip-components=1

echo "[server] unpacking meshmamba_non_texture_json ..."
mkdir -p MeshMamba_non_texture/json
tar -xzf meshmamba_non_texture_json.tar.gz -C MeshMamba_non_texture/json --strip-components=1

echo "[server] done. layout:"
ls -la 3DVA/ MeshMamba_non_texture/
REMOTE

# ---------- MeshMamba rgb_texture (deferred) ----------
# Transfer only after non_texture protocol is stable.
# Uncomment and run separately when ready:
#   LOCAL_GAZE_DATA_ROOT=... LOCAL_PACK_DIR=... bash test/side_inputs/pack_meshmamba_rgb_texture.sh
#   scp "${LOCAL_PACK_DIR}/meshmamba_rgb_texture_csv.tar.gz"  "${SSH_HOST}:${REMOTE_SIDE_INPUTS}/"
#   scp "${LOCAL_PACK_DIR}/meshmamba_rgb_texture_json.tar.gz" "${SSH_HOST}:${REMOTE_SIDE_INPUTS}/"

# ---------- SAL3D (blocked) ----------
# Blocked until dense GT reconstruction is complete.

echo "[mirror_side_inputs] all transfers done."
