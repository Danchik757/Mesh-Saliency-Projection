# Server and Git Policy

## Servers

| Role | Host | Only allowed working root |
| --- | --- | --- |
| GPU rendering/debug | `vg-gpu-01.lab.graphicon.ru` | `/mnt/ssd1/29d_kon/acm_2026` |
| CPU metric benchmarks | `vg-intellect-1.lab.graphicon.ru` | `/mnt/ssd1/29d_kon/acm_2026` |

Nothing may be created or modified outside the allowed root. Do not use legacy
paths from historical logs, archived docs, or old launch scripts. Assume no
`sudo`.

## Server Layout

```text
/mnt/ssd1/29d_kon/acm_2026/
  shared_release_data/
  agents/
    reviewer/
    macos_claude/
    windows_claude/
  outputs/
    reviewer/
    macos_claude/
    windows_claude/
  logs/
    reviewer/
  environments/
```

Each role uses a separate clone, output directory, and environment. Windows/WSL
work uses separate Linux-side clones, not shared Windows checkouts.

All OBJ, GT, gaze, and placement data used for accepted results arrives through
reviewed Git commits or versioned GitHub Release assets. Never substitute an
untracked server-local dataset.

## Branches

| Role | Branch |
| --- | --- |
| macOS Claude worker | `agent/macos-ingestion-release` |
| Windows/WSL Claude worker | `agent/windows-geometry-metrics` |
| Reviewer/controller | reviews workers; integrates approved commits into `reproject-benchmark` |

Rules:

1. Workers start implementation from the published immutable base ref.
2. Workers never commit directly to `reproject-benchmark`.
3. Workers never merge/rebase another worker branch.
4. Use the existing human git identity.
5. Never mention AI, agents, or models in authorship, messages, or trailers.
6. Commit and push small coherent milestones with tests.
7. Append progress only to the assigned agent MD.
8. Do not edit `trash/*.md`, `md/archive/*`, or another role's log.
9. Stop and report if a required fix crosses ownership.

## Server Execution

All long jobs run in `tmux` and write a log plus machine-readable summary.

CPU defaults:

```bash
nice -n 10 <command>
```

Start conservatively. Increase parallelism only after checking load and memory.
Avoid nested pools. For process-parallel jobs:

```bash
export OMP_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export MKL_NUM_THREADS=1
```

GPU rules:

1. Inspect `nvidia-smi` immediately before a run.
2. Use only GPUs confirmed free by the user/reviewer.
3. Set `CUDA_VISIBLE_DEVICES` explicitly.
4. Never assume fixed GPU availability.
5. Keep outputs below the allowed root.

Accepted metric computations run on designated servers. The Windows workstation
GPU may be used for local render/debug smoke tests.

## Windows/WSL SSH Prerequisite

The user provides the private key. Agents must not invent, transmit, or commit it.

```sshconfig
Host vg-gpu-acm
    HostName vg-gpu-01.lab.graphicon.ru
    User 29d_kon
    IdentityFile ~/.ssh/<user-provided-key>
    IdentitiesOnly yes

Host vg-intellect-acm
    HostName vg-intellect-1.lab.graphicon.ru
    User 29d_kon
    IdentityFile ~/.ssh/<user-provided-key>
    IdentitiesOnly yes
```

```bash
chmod 700 ~/.ssh
chmod 600 ~/.ssh/<user-provided-key>
ssh vg-gpu-acm 'hostname; pwd'
ssh vg-intellect-acm 'hostname; pwd'
```

No release upload or server job starts before the reviewer/controller confirms
the required gate and the user approves the action.
