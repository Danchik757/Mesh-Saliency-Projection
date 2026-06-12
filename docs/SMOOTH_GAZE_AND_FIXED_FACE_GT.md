# SAL3D Smooth Gaze and fixed-face GT

Reference for the two SAL3D ground-truth assets shipped in the release
(`sal3d_smooth_gaze.zip`, `sal3d_fixed_face_gt.zip`): what they contain, how the
code consumes them, the known inventory mismatches, and how reproducible they
are.

## Smooth Gaze (`sal3d_smooth_gaze.zip`)

- **53 files**, one per model: `datasets/SAL3D/Smooth_Gaze/<model>_neighbors.txt`.
- **2.11 GB uncompressed / ~859 MB zipped.** Sizes per file range from ~9 MB
  (`AudiRS5`) to ~84 MB (`chair`).

### File format

Each line carries a trailing `<vertex_id> neighbors` marker; the integers before
the final `;`-separated field are that vertex's neighbour ids. The loader
(`reprojection_methods/screen_space_gaussian/eval_sal3d_screen_space.py`,
`load_smooth_gaze` / `apply_gt_smoothing`) parses every line, keeping `ids` and
`neighbor_lists` in lockstep, and returns `{vertex_id: [neighbor_ids...]}`.

Verified on `ringdragon`: **every record holds exactly 2000 neighbours**
(min = max = median = 2000), for the ~1200 fixated vertices in that model.

### 2000 stored, first 500 used

`apply_gt_smoothing(raw_gt, smooth_gaze, ratio=500)` clips each neighbour list
to its first `ratio` entries:

```python
nbrs_clipped = nbrs[:ratio]                 # ratio defaults to 500
r = np.linspace(0.9 * v, 0.0, len(nbrs_clipped))
for k, nb in enumerate(nbrs_clipped):
    smoothed[nb] += r[k]
```

The propagation weight decays linearly from `0.9 × (fixation value)` to `0` over
the kept neighbours. With the default `--smooth-ratio 500`, **75 % of the stored
neighbours (the 500th–2000th) are never read.** The 2.11 GB payload therefore
carries ~4× the data the current algorithm consumes; only the first 500 columns
affect any metric. The full 2000 is retained for provenance / future
experiments, not because the pipeline needs it.

`gt_column == 7` disables smoothing entirely (the column is treated as already
smoothed).

## Fixed-face GT (`sal3d_fixed_face_gt.zip`)

- **55 models.** Archive layout: `datasets/SAL3D_fixed/sal3d_benchmark_pkg/` with
  `Meshes/<model>.obj` (55), `<model>_faces.txt` per-face GT (55), and 4 metadata
  files (`SHA256SUMS`, `sal3d_checksums.md5`, `sal3d_manifest.csv`,
  `sal3d_manifest.md`) = **114 members**.
- GT domain is **per-face** (`gt_domain: face`, `gt_length == n_faces`); consumed
  via `utils/sal3d_fixed_gt.py:load_fixed_face_gt`.
- The repaired meshes resolve the raw-Gaze vertex-count mismatches that make the
  original `SAL3D/Gaze/*.txt` unusable for some models — e.g. `MaxPlanck`
  (19999 verts), `meca` (15000), `sofa` (15125). When `SAL3D_FIXED_GT_DIR` is set,
  metrics use this per-face GT and those models stop failing.

## Inventory mismatch (Smooth Gaze ↔ fixed-face GT)

- **Common to both:** 51 models.
- **Fixed-face GT only (no Smooth Gaze):** `MaxPlanck`, `dog`, `flowerpot`, `prot`.
- **Smooth Gaze only (no fixed-face GT):** `AudiRS5`, `bimba`.

`scripts/validate_release_candidate.py` asserts these exact sets so an
accidental drift in either archive is caught at release time.

## Reproducibility

- **Smooth Gaze** files appear to be original SAL3D-derived neighbour tables
  (uniform 2000-neighbour records, internally consistent). They are distributed
  as-is.
- **Fixed-face GT** is a *regenerated* artifact (manifest dates it 2026-06-10,
  generated from an external `SAL3D_almost_fixed` / `SAL3D_NPZ_almost` pipeline).
  **No in-repo script reproduces it.** It is verifiable only via the per-model
  `obj_md5` / `npz_md5` checksums in `sal3d_manifest.csv`. Reproducing it from
  scratch requires preserving that external repair+projection pipeline; the repo
  ships only the consumer (`utils/sal3d_fixed_gt.py`) and the release validator,
  not the generator. Treat the shipped artifact + its checksums as the source of
  truth.
