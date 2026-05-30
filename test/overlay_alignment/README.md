Overlay alignment utilities for comparing a rendered mesh preview against a real video frame.

Purpose:
- visually verify whether the mesh pose, scale, and screen position match the source video
- diagnose reprojection errors before running metrics

Inputs:
- `video_frame.png`: frame extracted from the source video
- `preview.png`: rendered mesh preview from the same frame index and camera metadata

Algorithm:
1. Read both images and resize the preview if needed.
2. Estimate preview background color from the image corners.
3. Build an object mask by thresholding color distance from that background.
4. Create two diagnostic overlays:
   - alpha overlay: mesh preview blended over the video frame using the object mask
   - edge overlay: only the object contour is drawn over the video frame

Why this is better than plain side-by-side:
- side-by-side is useful for rough inspection
- overlay makes translation, silhouette, and scale errors immediately visible

Typical interpretation:
- good center but bad contour: pose/orientation mismatch
- good pose but wrong overall size: FOV / framing mismatch
- good shape but shifted position: translation / pivot / recenter mismatch

Current implementation:
- [overlay_video_and_preview.py](/Users/admin/Documents/LAB/SALIENCY_code/#meshes_2.0/GITHUB/Mesh-Saliency-Projection/test/overlay_alignment/overlay_video_and_preview.py)
