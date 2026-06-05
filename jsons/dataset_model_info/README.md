# Dataset Model Info

This directory contains generated JSON indexes that describe how each dataset
model connects to:

- the canonical object-placement JSON in `jsons/object_placement/`;
- participant gaze CSV files;
- mesh files;
- GT/saliency files;
- compact camera, model, animation, and video metadata.

The raw participant observations are not stored here as JSON. They are stored as
CSV files in the paths listed in each index under `participant_data`.

Regenerate these files with:

```bash
python3 test/tools/generate_dataset_model_info.py
```
