# references/

Read-only reference material kept for reproducibility. Do not import from here in eval code.

| Subfolder | Contents |
|-----------|----------|
| [render_scripts/](./render_scripts/README.md) | Original Blender scripts used to generate source videos and camera JSON files |

The render scripts (`3dva_render_1.py`, `mamba_render_2.py`) are the authoritative source
for understanding the camera and animation parameters stored in the JSON files used by
all eval scripts. If a transform or FOV value in the eval code seems wrong, cross-check
it here.
