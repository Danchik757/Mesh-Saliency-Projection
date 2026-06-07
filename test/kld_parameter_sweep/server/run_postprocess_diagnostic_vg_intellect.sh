#!/usr/bin/env bash
set -euo pipefail

REPO="${REPO:-/home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/Mesh-Saliency-Projection}"
REQUESTED_NICE_LEVEL="${NICE_LEVEL:-}"
cd "$REPO"
source configs/server_vg_intellect.env

RUN_ID="${RUN_ID:-20260602_$(date +%H%M%S)}"
SESSION="${SESSION:-kld_postprocess_${RUN_ID}}"
OUT="${OUT:-/home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/outputs/KLD_postprocess_${RUN_ID}}"
LAUNCH_ROOT="${LAUNCH_ROOT:-/home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/tmp_launchers}"
LOG="${LOG:-${LAUNCH_ROOT}/${SESSION}.log}"
RUN_SCRIPT="${RUN_SCRIPT:-${LAUNCH_ROOT}/${SESSION}_run.sh}"

REFERENCE_CSV="${REFERENCE_CSV:-/home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/outputs/MeshMamba_reference_batch_20260601/meshmamba_reference_long.csv}"
KLD_SWEEP_CSV="${KLD_SWEEP_CSV:-/home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/outputs/KLD_diagnostic_20260602_064256/kld_sweep_long.csv}"
MESHMAMBA_ROOT="${MESHMAMBA_ROOT:-/home/29d_kon@lab.graphicon.ru/ssd1_link/datasets/MeshMambaSaliency}"

NICE_LEVEL="${REQUESTED_NICE_LEVEL:-${NICE_LEVEL:-15}}"
MAX_INPUT_ROWS="${MAX_INPUT_ROWS:-}"
SKIP_DIFFUSION="${SKIP_DIFFUSION:-false}"

if tmux has-session -t "$SESSION" 2>/dev/null; then
  echo "[kld_postprocess] session already exists: $SESSION"
  echo "[kld_postprocess] output=$OUT"
  echo "[kld_postprocess] log=$LOG"
  exit 0
fi

mkdir -p "$OUT" "$LAUNCH_ROOT"

cat > "$RUN_SCRIPT" <<EOF
#!/usr/bin/env bash
set -euo pipefail
cd "$REPO"
source configs/server_vg_intellect.env

export OMP_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export MKL_NUM_THREADS=1
export NUMEXPR_NUM_THREADS=1

ARGS=()
if [[ -n "$MAX_INPUT_ROWS" ]]; then
  ARGS+=(--max-input-rows "$MAX_INPUT_ROWS")
fi
if [[ "$SKIP_DIFFUSION" == "true" ]]; then
  ARGS+=(--skip-diffusion)
fi

exec nice -n "$NICE_LEVEL" "\$REPROJECT_PYTHON" test/kld_parameter_sweep/run_kld_postprocess_diagnostics.py \\
  --input-csv "reference:$REFERENCE_CSV" \\
  --input-csv "kld_sweep:$KLD_SWEEP_CSV" \\
  --output-dir "$OUT" \\
  --meshmamba-root "$MESHMAMBA_ROOT" \\
  --methods screen_space,cone \\
  --texture-types non_texture,rgb_texture \\
  --alphas "0,1e-10,1e-9,1e-8,1e-7,1e-6,1e-5,1e-4,1e-3,1e-2" \\
  --support-masks "pred_positive,pred_above_1e_8,pred_above_1e_6,gt_positive,intersection_positive,union_positive" \\
  --area-modes "none,multiply_area,divide_area" \\
  --diffusion-steps "1,3,5,10,20,40" \\
  --diffusion-blend 0.5 \\
  --top-face-count 50 \\
  --write-every 10 \\
  "\${ARGS[@]}"
EOF

chmod +x "$RUN_SCRIPT"
tmux new-session -d -s "$SESSION" "$RUN_SCRIPT > \"$LOG\" 2>&1"

echo "[kld_postprocess] started session=$SESSION"
echo "[kld_postprocess] output=$OUT"
echo "[kld_postprocess] log=$LOG"
echo "[kld_postprocess] run_script=$RUN_SCRIPT"
echo "[kld_postprocess] nice=$NICE_LEVEL max_input_rows=${MAX_INPUT_ROWS:-all} skip_diffusion=$SKIP_DIFFUSION"
