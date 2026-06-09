# Dataset Model Info

This directory contains generated, platform-independent JSON indexes that
describe how each dataset model connects to:

- the canonical object-placement JSON in `jsons/object_placement/`;
- the new processed fixation JSON used by default;
- the old participant CSV retained for explicit compatibility diagnostics;
- release-relative mesh and GT/saliency paths;
- compact camera, model, animation, and video metadata.

The indexes never contain machine-specific macOS, WSL, or server paths. Both
participant formats are listed separately and automatic fallback is forbidden.
The large participant payloads are staged under `participant_data/` and
distributed through GitHub Release assets.

Regenerate these files with:

```bash
python3 test/tools/generate_dataset_model_info.py
```
