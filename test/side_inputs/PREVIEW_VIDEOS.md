# Preview Videos For Blender Search

For Blender-based mask alignment on another machine, the dataset meshes/JSON are not enough.
The original source `mp4` files used for comparison must also be present on that machine.

Recommended transfer policy:
- Code: via GitHub.
- Preview source videos: as a small `tar.gz` archive built from the manifests you actually plan to validate.

Current key manifests for preview validation:
- `test/manifests/preview_3dva_bunny.json`
- `test/manifests/preview_meshmamba_non_texture_starfruit.json`
- `test/manifests/preview_meshmamba_rgb_texture_starfruit.json`
- `test/manifests/preview_meshmamba_non_texture_mango.json`
- `test/manifests/preview_meshmamba_rgb_texture_mango.json`
- `test/manifests/preview_meshmamba_non_texture_pear.json`
- `test/manifests/preview_meshmamba_rgb_texture_pear.json`
- `test/manifests/preview_meshmamba_non_texture_rubber_duck.json`
- `test/manifests/preview_meshmamba_rgb_texture_rubber_duck.json`

Build archive locally:

```bash
source "/Users/admin/Documents/LAB/SALIENCY_code/#meshes_2.0/GITHUB/Mesh-Saliency-Projection/test/env/local_paths.example.sh"
python3 "/Users/admin/Documents/LAB/SALIENCY_code/#meshes_2.0/GITHUB/Mesh-Saliency-Projection/test/side_inputs/pack_preview_videos.py" \
  --archive "/tmp/reproject_preview_videos.tar.gz" \
  --manifest \
  "/Users/admin/Documents/LAB/SALIENCY_code/#meshes_2.0/GITHUB/Mesh-Saliency-Projection/test/manifests/preview_3dva_bunny.json" \
  "/Users/admin/Documents/LAB/SALIENCY_code/#meshes_2.0/GITHUB/Mesh-Saliency-Projection/test/manifests/preview_meshmamba_non_texture_starfruit.json" \
  "/Users/admin/Documents/LAB/SALIENCY_code/#meshes_2.0/GITHUB/Mesh-Saliency-Projection/test/manifests/preview_meshmamba_rgb_texture_starfruit.json"
```

Then transfer to the server, for example into:

`/home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/side_inputs/preview_videos/`

After unpacking on the server, point the corresponding `REPROJECT_VIDEO_*_ROOT` variables to those directories.
