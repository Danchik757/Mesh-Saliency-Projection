#!/usr/bin/env bash
set -euo pipefail

REPO="${REPO:-/home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/Mesh-Saliency-Projection}"
START_AT="${START_AT:-01:00}"
SESSION="${SESSION:-kld_sweep_schedule_$(date +%Y%m%d)}"

cd "$REPO"

if tmux has-session -t "$SESSION" 2>/dev/null; then
  echo "[schedule] tmux session already exists: $SESSION"
  exit 0
fi

SLEEP_SECONDS="$(python3 - <<PY
from __future__ import annotations
from datetime import datetime, timedelta
start = "$START_AT"
now = datetime.now()
hour, minute = [int(part) for part in start.split(":", 1)]
target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
if target <= now:
    target += timedelta(days=1)
print(int((target - now).total_seconds()))
PY
)"

tmux new-session -d -s "$SESSION" \
  "cd '$REPO' && sleep '$SLEEP_SECONDS' && bash test/kld_parameter_sweep/server/run_nightly_vg_intellect.sh"

echo "[schedule] scheduled session=$SESSION start_at=$START_AT sleep_seconds=$SLEEP_SECONDS"
echo "[schedule] monitor scheduler: tmux attach -t $SESSION"
