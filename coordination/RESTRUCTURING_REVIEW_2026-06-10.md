# Restructuring Review - 2026-06-10

This note defines the safe restructuring boundary before any physical moves are
made. The goal is to keep the metric benchmark stable while identifying helper
tooling that can later become a separate submodule or companion repository.

## Current integration branch

```text
branch: reproject-benchmark
known HEAD during this review: 15eb036
release data: v2.0-data-rc2
```

Local merged branches removed during the review:

```text
agent/heatmap-six-view
agent/macos-fixation-format-v2
agent/sal3d-fixed-face-gt
```

Branches intentionally kept:

```text
reproject-benchmark
main
agent/macos-ingestion-release  # active worktree branch
origin/agent/windows-geometry-metrics  # do not touch while Windows worker state is unresolved
```

Remote branch deletion is deferred until all agents confirm they no longer need
those refs.

## Do not move before the current metric run finishes

These paths are part of the production benchmark contract or are referenced by
server runbooks and launchers:

```text
configs/
jsons/
metrics/
reprojection_methods/
scripts/
test/launch/
utils/
requirements/
coordination/
```

The running rc2 metric jobs on `vg-iai` use these paths from the
`reproject-benchmark` checkout. Moving them before the jobs complete would make
the run harder to reproduce and compare.

## Candidate paths for a future helper/submodule split

These directories are useful, but they are auxiliary validation,
visualization, or report tooling rather than the core metric path:

```text
gt_visualizations/
test/blender_canonical/
test/overlay_alignment/
test/tools/
validation/alignment_preview/
video_creation/
visualization/
```

Recommended future target name:

```text
mesh-saliency-tools
```

Recommended future layout inside that repo:

```text
alignment/
heatmaps/
video_overlays/
render_reference/
debug_projection/
docs/
tests/
```

## Compatibility rule

Before moving any candidate path, add one of the following:

1. A compatibility wrapper at the old path that imports/runs the new path.
2. A documented breaking-change commit that updates every README, server
   command, test, and agent instruction in the same commit.

For this project, wrappers are preferred until the full rc2 metrics and sigma
sweep runs are complete.

## Current untracked files to classify

```text
coordination/PROJECT_STATE_2026-06-10.md
coordination/agents/MACOS_HEATMAP_SIX_VIEW_TASK.md
coordination/agents/WINDOWS_HEATMAP_VIDEO_TASK.md
test/manifests/debug_3dva_a380_frame54.json
test/tools/compare_processed_timing_preview.py
video_creation/gaze_heatmap_overlays/render_participant_marker_overlay.py
```

Recommended classification:

```text
coordination/PROJECT_STATE_2026-06-10.md                keep in coordination/
coordination/agents/MACOS_HEATMAP_SIX_VIEW_TASK.md      keep until task is closed, then archive under md/archive/
coordination/agents/WINDOWS_HEATMAP_VIDEO_TASK.md       keep until task is closed, then archive under md/archive/
test/manifests/debug_3dva_a380_frame54.json             move later with debug_projection tools or archive
test/tools/compare_processed_timing_preview.py          candidate for debug_projection/
video_creation/gaze_heatmap_overlays/render_participant_marker_overlay.py candidate for video_overlays/
```

## Review checklist for macOS worker

1. Confirm the production path list above is complete.
2. Confirm the candidate path list above contains only auxiliary tooling.
3. Search for hardcoded references to candidate paths in production launchers.
4. Run tests after documentation-only changes.
5. Do not physically move code until the reviewer/controller approves the final
   move plan.
