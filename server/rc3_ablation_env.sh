#!/usr/bin/env bash
# Shared environment for the rc3 window/delay ablation run.
# Source this from each shard launch script AFTER setting server-specific vars.
#
# Required before sourcing:
#   REPROJECT_SERVER_ROOT   — e.g. /mnt/ssd1/29d_kon/acm_2026
#   REPROJECT_WORKSPACE_NAME — e.g. coordinator (default below)
#   RUN_ID                  — rc3_window_delay_ablation_YYYYMMDD_HHMMSS (no default)
#   SHARD_INDEX             — 0 / 1 / 2 (set by caller)
#
# Do NOT source this file directly. Use a shard launch script.

set -euo pipefail

# ── release ───────────────────────────────────────────────────────────────────
export REPROJECT_RELEASE_TAG="v2.0-data-rc3"
export REPROJECT_WORKSPACE_NAME="${REPROJECT_WORKSPACE_NAME:-coordinator}"

export REPO_ROOT="${REPROJECT_SERVER_ROOT}/agents/${REPROJECT_WORKSPACE_NAME}/Mesh-Saliency-Projection"
export RELEASE_DOWNLOAD_ROOT="${REPROJECT_SERVER_ROOT}/shared_release_data/${REPROJECT_RELEASE_TAG}"
export RELEASE_DATA_ROOT="${RELEASE_DOWNLOAD_ROOT}/extracted"

# ── python ────────────────────────────────────────────────────────────────────
export CONDA_ENVS_ROOT="${REPROJECT_SERVER_ROOT}/environments"
export CONDA_ENV_NAME="${CONDA_ENV_NAME:-reproject-benchmark}"
export REPROJECT_PYTHON="${CONDA_ENVS_ROOT}/${CONDA_ENV_NAME}/bin/python"

# ── fixations (rc3) ───────────────────────────────────────────────────────────
export FIXATION_ROOT="${RELEASE_DATA_ROOT}/participant_fixations_offset0_full_cleaned"
export REPROJECT_PROCESSED_FIXATIONS_ROOT="${FIXATION_ROOT}"
export REPROJECT_FIXATION_DATA_TAG="processed_fixations_offset0_full_cleaned"
export REPROJECT_TIMING_CONTRACT="one_turn_from_start"

# ── 3DVA ─────────────────────────────────────────────────────────────────────
export VISUAL_ATTENTION_3D_SHAPES_ROOT="${RELEASE_DATA_ROOT}/datasets/3DVA"
export THREE_DVA_JSON_ROOT="${REPO_ROOT}/jsons/object_placement/3dva_jsons"
export THREE_DVA_COMBINED_GT_DIR="${VISUAL_ATTENTION_3D_SHAPES_ROOT}/CombinedGT"

# ── MeshMamba ─────────────────────────────────────────────────────────────────
export MESHMAMBA_NON_TEXTURE_ROOT="${RELEASE_DATA_ROOT}/datasets/MeshMamba"
export MESHMAMBA_RGB_TEXTURE_ROOT="${RELEASE_DATA_ROOT}/datasets/MeshMamba"
export MESHMAMBA_JSON_ROOT="${REPO_ROOT}/jsons/object_placement/mamba_non_jsons"
export MESHMAMBA_RGB_TEXTURE_JSON_ROOT="${REPO_ROOT}/jsons/object_placement/mamba_rgb_jsons"

# ── SAL3D ─────────────────────────────────────────────────────────────────────
# SAL3D_DATASET_ROOT and SAL3D_FIXED_GT_DIR both point into the fixed/repaired
# mesh package; the raw mesh root (datasets/SAL3D) has mismatched face counts.
export SAL3D_DATASET_ROOT="${RELEASE_DATA_ROOT}/datasets/SAL3D_fixed/sal3d_benchmark_pkg"
export SAL3D_JSON_ROOT="${REPO_ROOT}/jsons/object_placement/sal3d_jsons"
export SAL3D_FIXED_GT_DIR="${RELEASE_DATA_ROOT}/datasets/SAL3D_fixed/sal3d_benchmark_pkg/sal3d_fixed_face_gt"

# ── parallelism ───────────────────────────────────────────────────────────────
export OMP_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export MKL_NUM_THREADS=1

# ── output ────────────────────────────────────────────────────────────────────
export BATCH_OUTPUT_DIR="${REPROJECT_SERVER_ROOT}/outputs/ablation/${RUN_ID}/shard_${SHARD_INDEX}_of_3"
