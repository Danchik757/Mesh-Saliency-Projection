#!/usr/bin/env bash
# Template: unpack side-input archives on vg-intellect.
# Run ON THE SERVER (inside tmux) after archives have been transferred via scp.
#
# Expected server layout after unpack:
#   ${SIDE_INPUTS_ROOT}/
#     3DVA/
#       csv/    ← 32 CSV files (one per 3DVA model)
#       json/   ← 32 JSON files (camera metadata, prefix: 3DVA_<model>.json)
#     MeshMamba_non_texture/
#       csv/    ← 105 CSV files
#       json/   ← 105 JSON files (prefix: MeshMamba_non_texture_<model>.json)
#
# Required env var:
#   SIDE_INPUTS_ROOT  — server path set in configs/server_vg_intellect.env
set -euo pipefail

: "${SIDE_INPUTS_ROOT:?Set SIDE_INPUTS_ROOT (source configs/server_vg_intellect.env)}"

echo "[unpack_on_server] side_inputs_root = ${SIDE_INPUTS_ROOT}"
cd "${SIDE_INPUTS_ROOT}"

# ---------- 3DVA CSV ----------
if [ -f "3dva_csv.tar.gz" ]; then
  echo "[unpack_on_server] unpacking 3dva_csv.tar.gz ..."
  mkdir -p 3DVA/csv
  tar -xzf 3dva_csv.tar.gz -C 3DVA/csv --strip-components=1
  echo "  3DVA/csv: $(ls 3DVA/csv/*.csv 2>/dev/null | wc -l) files"
else
  echo "[unpack_on_server] WARNING: 3dva_csv.tar.gz not found — skipping"
fi

# ---------- 3DVA JSON ----------
if [ -f "3dva_json.tar.gz" ]; then
  echo "[unpack_on_server] unpacking 3dva_json.tar.gz ..."
  mkdir -p 3DVA/json
  tar -xzf 3dva_json.tar.gz -C 3DVA/json --strip-components=1
  echo "  3DVA/json: $(ls 3DVA/json/*.json 2>/dev/null | wc -l) files"
else
  echo "[unpack_on_server] WARNING: 3dva_json.tar.gz not found — skipping"
fi

# ---------- MeshMamba non_texture CSV ----------
if [ -f "meshmamba_non_texture_csv.tar.gz" ]; then
  echo "[unpack_on_server] unpacking meshmamba_non_texture_csv.tar.gz ..."
  mkdir -p MeshMamba_non_texture/csv
  tar -xzf meshmamba_non_texture_csv.tar.gz -C MeshMamba_non_texture/csv --strip-components=1
  echo "  MeshMamba_non_texture/csv: $(ls MeshMamba_non_texture/csv/*.csv 2>/dev/null | wc -l) files"
else
  echo "[unpack_on_server] WARNING: meshmamba_non_texture_csv.tar.gz not found — skipping"
fi

# ---------- MeshMamba non_texture JSON ----------
if [ -f "meshmamba_non_texture_json.tar.gz" ]; then
  echo "[unpack_on_server] unpacking meshmamba_non_texture_json.tar.gz ..."
  mkdir -p MeshMamba_non_texture/json
  tar -xzf meshmamba_non_texture_json.tar.gz -C MeshMamba_non_texture/json --strip-components=1
  echo "  MeshMamba_non_texture/json: $(ls MeshMamba_non_texture/json/*.json 2>/dev/null | wc -l) files"
else
  echo "[unpack_on_server] WARNING: meshmamba_non_texture_json.tar.gz not found — skipping"
fi

echo ""
echo "[unpack_on_server] final layout:"
echo "  3DVA/csv:                   $(ls 3DVA/csv/*.csv   2>/dev/null | wc -l) files"
echo "  3DVA/json:                  $(ls 3DVA/json/*.json 2>/dev/null | wc -l) files"
echo "  MeshMamba_non_texture/csv:  $(ls MeshMamba_non_texture/csv/*.csv   2>/dev/null | wc -l) files"
echo "  MeshMamba_non_texture/json: $(ls MeshMamba_non_texture/json/*.json 2>/dev/null | wc -l) files"
echo ""
echo "Expected: 3DVA=32 CSV + 32 JSON, MeshMamba=105 CSV + 105 JSON"
