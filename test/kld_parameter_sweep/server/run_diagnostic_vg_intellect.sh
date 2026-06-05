#!/usr/bin/env bash
set -euo pipefail

REPO="${REPO:-/home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/Mesh-Saliency-Projection}"
cd "$REPO"
source configs/server_vg_intellect.env

RUN_ID="${RUN_ID:-20260602_$(date +%H%M%S)}"
SESSION="${SESSION:-kld_diag_${RUN_ID}}"
OUT="${OUT:-/home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/outputs/KLD_diagnostic_${RUN_ID}}"
LAUNCH_ROOT="${LAUNCH_ROOT:-/home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/tmp_launchers}"
LOG="${LOG:-${LAUNCH_ROOT}/${SESSION}.log}"
RUN_SCRIPT="${RUN_SCRIPT:-${LAUNCH_ROOT}/${SESSION}_run.sh}"

if tmux has-session -t "$SESSION" 2>/dev/null; then
  echo "[kld_diag] session already exists: $SESSION"
  echo "[kld_diag] output=$OUT"
  echo "[kld_diag] log=$LOG"
  exit 0
fi

cat > "$RUN_SCRIPT" <<EOF
#!/usr/bin/env bash
set -euo pipefail
cd "$REPO"
source configs/server_vg_intellect.env

export SAL3D_DATASET_ROOT="/home/29d_kon@lab.graphicon.ru/ssd1_link/datasets/reproject_release_v1/SAL3D"
export SAL3D_CSV_ROOT="/home/29d_kon@lab.graphicon.ru/ssd1_link/datasets/reproject_release_v1/gaze_csv/SAL3D"
export SAL3D_JSON_ROOT="\$REPO_ROOT/jsons/sal3d_jsons"
export SAL3D_SMOOTH_GAZE_DIR="/home/29d_kon@lab.graphicon.ru/ssd1_link/datasets/reproject_release_v1/SAL3D/Smooth_Gaze"

export OMP_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export MKL_NUM_THREADS=1
export NUMEXPR_NUM_THREADS=1

exec "\$REPROJECT_PYTHON" test/kld_parameter_sweep/run_kld_parameter_sweep.py \\
  --datasets sal3d meshmamba \\
  --methods screen_space cone \\
  --texture-types non_texture rgb_texture \\
  --sal3d-models bunny A380 dog flowerpot dragon \\
  --meshmamba-models Starfruit_L3 Flying_saucer_v1_L3 Spinning_Top_v1_L3 MushroomShitake_L3 ball_car_v1_L3 football_v2_L3 \\
  --sal3d-screen-sigma-px "6.575,13.15,26.3,39.45,52.6,78.9" \\
  --meshmamba-screen-sigma "0.025,0.05,0.075,0.1,0.15,0.2" \\
  --cone-sigma-deg "1,2,3,5" \\
  --cone-radius-sigma-mult "3,5,7" \\
  --workers 32 \\
  --nice-level 15 \\
  --batch-output-dir "$OUT" \\
  --smooth-gaze-dir "\$SAL3D_SMOOTH_GAZE_DIR"
EOF

mkdir -p "$OUT" "$LAUNCH_ROOT"
chmod +x "$RUN_SCRIPT"
tmux new-session -d -s "$SESSION" "$RUN_SCRIPT > \"$LOG\" 2>&1"

echo "[kld_diag] started session=$SESSION"
echo "[kld_diag] output=$OUT"
echo "[kld_diag] log=$LOG"
echo "[kld_diag] run_script=$RUN_SCRIPT"
echo "[kld_diag] tasks=306 workers=32 nice=15"
