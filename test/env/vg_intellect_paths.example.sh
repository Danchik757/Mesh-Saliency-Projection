#!/usr/bin/env bash
# Backward-compatible entry point. Prefer sourcing configs/server_vg_intellect.env.

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
# shellcheck source=../../configs/server_vg_intellect.env
source "${REPO_ROOT}/configs/server_vg_intellect.env"
