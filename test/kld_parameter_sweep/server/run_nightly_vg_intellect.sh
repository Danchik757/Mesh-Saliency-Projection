#!/usr/bin/env bash
set -euo pipefail

REPO="${REPO:-/home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/Mesh-Saliency-Projection}"
SESSION="${SESSION:-kld_sweep_nightly_$(date +%Y%m%d)}"
WAIT_FOR_SESSIONS="${WAIT_FOR_SESSIONS:-sal3d_full_20260601 meshmamba_full_20260601}"
WAIT_POLL_SECONDS="${WAIT_POLL_SECONDS:-300}"

cd "$REPO"
source configs/server_vg_intellect.env
source test/kld_parameter_sweep/configs/nightly_params.env

if tmux has-session -t "$SESSION" 2>/dev/null; then
  echo "[nightly] tmux session already exists: $SESSION"
  exit 0
fi

export SAL3D_DATASET_ROOT="${SAL3D_DATASET_ROOT:-/home/29d_kon@lab.graphicon.ru/ssd1_link/datasets/reproject_release_v1/SAL3D}"
export SAL3D_CSV_ROOT="${SAL3D_CSV_ROOT:-/home/29d_kon@lab.graphicon.ru/ssd1_link/datasets/reproject_release_v1/gaze_csv/SAL3D}"
export SAL3D_JSON_ROOT="${SAL3D_JSON_ROOT:-/home/29d_kon@lab.graphicon.ru/ssd1_link/datasets/reproject_release_v1/jsons_for_models/SAL3D_json}"
export SAL3D_SMOOTH_GAZE_DIR="${SAL3D_SMOOTH_GAZE_DIR:-/home/29d_kon@lab.graphicon.ru/ssd1_link/datasets/reproject_release_v1/SAL3D/Smooth_Gaze}"

export OMP_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export MKL_NUM_THREADS=1
export NUMEXPR_NUM_THREADS=1

mapfile -t SAL3D_MODELS < test/kld_parameter_sweep/configs/sal3d_nightly_models.txt
mapfile -t MESHMAMBA_MODELS < test/kld_parameter_sweep/configs/meshmamba_non_texture_nightly_models.txt

RUN_ID="$(date +%Y%m%d_%H%M%S)"
OUT="${OUT:-/home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/outputs/KLD_sweep_nightly_${RUN_ID}}"
LOG="${LOG:-/tmp/${SESSION}.log}"
RUN_SCRIPT="/tmp/${SESSION}.sh"

cat > "$RUN_SCRIPT" <<EOF
#!/usr/bin/env bash
set -euo pipefail
cd "$REPO"
source configs/server_vg_intellect.env
WAIT_FOR_SESSIONS="$WAIT_FOR_SESSIONS"
WAIT_POLL_SECONDS="$WAIT_POLL_SECONDS"
if [[ -n "\$WAIT_FOR_SESSIONS" ]]; then
  while true; do
    active=0
    for wait_session in \$WAIT_FOR_SESSIONS; do
      if tmux has-session -t "\$wait_session" 2>/dev/null; then
        echo "[nightly] waiting for existing tmux session: \$wait_session"
        active=1
      fi
    done
    if [[ "\$active" == "0" ]]; then
      break
    fi
    sleep "\$WAIT_POLL_SECONDS"
  done
fi
export SAL3D_DATASET_ROOT="$SAL3D_DATASET_ROOT"
export SAL3D_CSV_ROOT="$SAL3D_CSV_ROOT"
export SAL3D_JSON_ROOT="$SAL3D_JSON_ROOT"
export SAL3D_SMOOTH_GAZE_DIR="$SAL3D_SMOOTH_GAZE_DIR"
export OMP_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export MKL_NUM_THREADS=1
export NUMEXPR_NUM_THREADS=1

"$REPROJECT_PYTHON" test/kld_parameter_sweep/run_kld_parameter_sweep.py \\
  --datasets $DATASETS \\
  --methods $METHODS \\
  --texture-types $TEXTURE_TYPES \\
  --sal3d-models ${SAL3D_MODELS[*]} \\
  --meshmamba-models ${MESHMAMBA_MODELS[*]} \\
  --sal3d-screen-sigma-px "$SAL3D_SCREEN_SIGMA_PX" \\
  --meshmamba-screen-sigma "$MESHMAMBA_SCREEN_SIGMA" \\
  --cone-sigma-deg "$CONE_SIGMA_DEG" \\
  --cone-radius-sigma-mult "$CONE_RADIUS_SIGMA_MULT" \\
  --workers "$WORKERS" \\
  --nice-level "$NICE_LEVEL" \\
  --batch-output-dir "$OUT" \\
  --smooth-gaze-dir "$SAL3D_SMOOTH_GAZE_DIR"
EOF
chmod +x "$RUN_SCRIPT"

tmux new-session -d -s "$SESSION" "$RUN_SCRIPT > '$LOG' 2>&1"

echo "[nightly] started session=$SESSION"
echo "[nightly] output=$OUT"
echo "[nightly] log=$LOG"
echo "[nightly] wait_for_sessions=$WAIT_FOR_SESSIONS"
echo "[nightly] monitor: bash test/kld_parameter_sweep/server/monitor_vg_intellect.sh OUT='$OUT' LOG='$LOG'"
