#!/usr/bin/env bash
# Template: scp archive transfers to vg-intellect.
# Run LOCALLY after pack_*.sh scripts have created the archives.
# DO NOT RUN without explicit confirmation from GPT that transfer is approved.
#
# SSH configuration note:
#   The SSH host alias "vg-intellect" must be configured in ~/.ssh/config:
#     Host vg-intellect
#         HostName <actual-ip-or-hostname>
#         User 29d_kon@lab.graphicon.ru
#   Then use:  scp file.tar.gz vg-intellect:/remote/path/
#
#   If SSH config is not available, scp requires special quoting because
#   the username contains '@'. Use the SSH_HOST env var to override.
#
# Required env vars:
#   LOCAL_PACK_DIR         — where archives were created (default: /tmp/reproject_side_inputs)
#   SSH_HOST               — SSH alias (default: vg-intellect)
#   DRY_RUN                — set to 1 to print scp commands without executing
#   REMOTE_SIDE_INPUTS     — absolute path on server for archives
#                            e.g. /home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/side_inputs
set -euo pipefail

: "${REMOTE_SIDE_INPUTS:?Set REMOTE_SIDE_INPUTS to the server-side path}"

LOCAL_PACK_DIR="${LOCAL_PACK_DIR:-/tmp/reproject_side_inputs}"
SSH_HOST="${SSH_HOST:-vg-intellect}"
DRY_RUN="${DRY_RUN:-0}"

echo "[scp_archives] local_pack_dir = ${LOCAL_PACK_DIR}"
echo "[scp_archives] ssh_host       = ${SSH_HOST}"
echo "[scp_archives] remote_path    = ${REMOTE_SIDE_INPUTS}"
echo "[scp_archives] dry_run        = ${DRY_RUN}"

run_scp() {
  local src="$1"
  if [ "${DRY_RUN}" = "1" ]; then
    echo "[scp_archives] dry-run: scp \"${src}\" \"${SSH_HOST}:${REMOTE_SIDE_INPUTS}/\""
    return 0
  fi
  scp "${src}" "${SSH_HOST}:${REMOTE_SIDE_INPUTS}/"
}

# ---------- 3DVA ----------
for ARCHIVE in 3dva_csv.tar.gz 3dva_json.tar.gz; do
  SRC="${LOCAL_PACK_DIR}/${ARCHIVE}"
  if [ ! -f "${SRC}" ]; then
    echo "[scp_archives] WARNING: archive not found, skipping: ${SRC}"
    echo "  Run test/side_inputs/pack_3dva.sh first."
    continue
  fi
  echo "[scp_archives] scp ${ARCHIVE} ..."
  run_scp "${SRC}"
done

# ---------- MeshMamba non_texture ----------
for ARCHIVE in meshmamba_non_texture_csv.tar.gz meshmamba_non_texture_json.tar.gz; do
  SRC="${LOCAL_PACK_DIR}/${ARCHIVE}"
  if [ ! -f "${SRC}" ]; then
    echo "[scp_archives] WARNING: archive not found, skipping: ${SRC}"
    echo "  Run test/side_inputs/pack_meshmamba_non_texture.sh first."
    continue
  fi
  echo "[scp_archives] scp ${ARCHIVE} ..."
  run_scp "${SRC}"
done

echo "[scp_archives] done. Run test/side_inputs/unpack_on_server.sh next."
