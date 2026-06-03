# Dataset Structure Audit

Last checked: 2026-06-03 MSK.

This file records the actual dataset and side-input structure observed locally
and on `vg-intellect`. It is meant to prevent path/count mistakes when another
agent continues the project.

## 1. Important Counting Rule

On `vg-intellect`, some directories contain macOS AppleDouble files:

```text
._A380.csv
._Apple_Red_v1_L3.csv
._A380_neighbors.txt
```

These are not real data files. Logical file counts below exclude `._*`.

Use this pattern when counting data files:

```bash
find "$DIR" -maxdepth 1 -type f ! -name '._*' | wc -l
```

Do not infer duplicated gaze data from raw `find | wc -l` if `._*` files are
present.

## 2. Local Structure

Repo root:

```text
/Users/admin/Documents/LAB/SALIENCY_code/#meshes_2.0/GITHUB/Mesh-Saliency-Projection
```

Local side inputs:

| Logical data | Path | Count |
|---|---|---:|
| 3DVA gaze CSV | `/Users/admin/Documents/LAB/SALIENCY_code/GAZE_DATA/csv_for_models/3DVA` | 32 |
| 3DVA JSON | `/Users/admin/Documents/LAB/SALIENCY_code/GAZE_DATA/jsons_for_models/3DVA_json` | 32 |
| MeshMamba non_texture CSV | `/Users/admin/Documents/LAB/SALIENCY_code/GAZE_DATA/csv_for_models/MeshMamba_non_texture` | 105 |
| MeshMamba non_texture JSON | `/Users/admin/Documents/LAB/SALIENCY_code/GAZE_DATA/jsons_for_models/Mamba_non_textured` | 105 |
| MeshMamba rgb_texture CSV | `/Users/admin/Documents/LAB/SALIENCY_code/GAZE_DATA/csv_for_models/MeshMamba_rgb_texture` | 105 |
| MeshMamba rgb_texture JSON | `/Users/admin/Documents/LAB/SALIENCY_code/GAZE_DATA/jsons_for_models/Mamba_rgb_textured` | 105 |
| SAL3D gaze CSV | `/Users/admin/Documents/LAB/SALIENCY_code/GAZE_DATA/csv_for_models/SAL3D` | 56 |
| SAL3D JSON | `/Users/admin/Documents/LAB/SALIENCY_code/GAZE_DATA/jsons_for_models/SAL3D_json` | 57 |

Local dataset roots:

```text
/Users/admin/Documents/LAB/SALIENCY_code/GAZE_DATA/datasets/3DVA
/Users/admin/Documents/LAB/SALIENCY_code/GAZE_DATA/datasets/MeshMamba/MeshMambaSaliency
/Users/admin/Documents/LAB/SALIENCY_code/GAZE_DATA/datasets/SAL3D/SAL3D_Dataset
/Users/admin/Documents/LAB/Dataset/3DVA
```

Local 3DVA:

| Data | Path | Count |
|---|---|---:|
| Fixation maps | `/Users/admin/Documents/LAB/Dataset/3DVA/FixationMaps/*.txt` | 96 |
| Corrected OBJ | `/Users/admin/Documents/LAB/Dataset/3DVA/3DModels-Simplif-up/*.obj` | 32 |
| Visibility/centricity | `/Users/admin/Documents/LAB/Dataset/3DVA/CentricityAndVisibilityMaps` | present |
| Algorithm maps | `/Users/admin/Documents/LAB/Dataset/3DVA/SaliencyAlgorithmMaps` | present |

Local MeshMamba:

| Track | Data | Path | Count |
|---|---|---|---:|
| non_texture | model dirs | `MeshMambaSaliency/MeshFile/non_texture` | 105 |
| non_texture | GT CSV | `MeshMambaSaliency/SaliencyMap/non_texture` | 106 normal `*.csv` |
| rgb_texture | model dirs | `MeshMambaSaliency/MeshFile/rgb_texture` | 106 dirs |
| rgb_texture | GT CSV | `MeshMambaSaliency/SaliencyMap/rgb_texture` | 105 |

Local MeshMamba caveats:

- `SaliencyMap/non_texture` contains an extra file:
  - `Apple_v01_l3 copy.csv`
- `MeshFile/rgb_texture` contains an extra directory:
  - `Aquarium_Deep_Sea_Diver_v1_L1 2`
- Therefore do not use simple count equality as a correctness check locally.
  Use model/GT resolvers.

Local SAL3D:

| Data | Path | Count |
|---|---|---:|
| GT gaze TXT | `GAZE_DATA/datasets/SAL3D/SAL3D_Dataset/Gaze/*.txt` | 58 |
| Mesh OBJ | `GAZE_DATA/datasets/SAL3D/SAL3D_Dataset/Meshes/*.obj` | 57 |
| Smooth_Gaze files | `GAZE_DATA/datasets/SAL3D/SAL3D_Dataset/Smooth_Gaze/*` | 53 |

## 3. Server Structure

Server:

```bash
ssh vg-intellect
```

Server dataset root:

```text
/home/29d_kon@lab.graphicon.ru/ssd1_link/datasets
```

Observed entries:

```text
3DVA
3DVA.zip
Huawei
MeshMambaSaliency
MeshMambaSaliency-20251011T083035Z-1-001.zip
SAL3D
reproject_release_v1
```

Server repo:

```text
/home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/Mesh-Saliency-Projection
```

Server side-input root:

```text
/home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/side_inputs
```

Server side inputs, logical counts excluding `._*`:

| Logical data | Path | Count |
|---|---|---:|
| 3DVA gaze CSV | `side_inputs/3DVA/csv` | 32 |
| 3DVA JSON | `side_inputs/3DVA/json` | 32 |
| MeshMamba non_texture CSV | `side_inputs/MeshMamba_non_texture/csv` | 105 |
| MeshMamba non_texture JSON | `side_inputs/MeshMamba_non_texture/json` | 105 |
| MeshMamba rgb_texture CSV | `side_inputs/MeshMamba_rgb_texture/csv` | 105 |
| MeshMamba rgb_texture JSON | `side_inputs/MeshMamba_rgb_texture/json` | 105 |

Server side-input caveat:

- `side_inputs/3DVA/csv` physically had 64 files because of 32 `._*.csv`.
- `side_inputs/MeshMamba_non_texture/csv` physically had 210 files because of
  105 `._*.csv`.
- These AppleDouble files should be ignored.

Server MeshMamba:

| Track | Data | Path | Count |
|---|---|---|---:|
| non_texture | model dirs | `/home/29d_kon@lab.graphicon.ru/ssd1_link/datasets/MeshMambaSaliency/MeshFile/non_texture` | 105 |
| non_texture | GT CSV | `/home/29d_kon@lab.graphicon.ru/ssd1_link/datasets/MeshMambaSaliency/SaliencyMap/non_texture` | 105 |
| rgb_texture | model dirs | `/home/29d_kon@lab.graphicon.ru/ssd1_link/datasets/MeshMambaSaliency/MeshFile/rgb_texture` | 105 |
| rgb_texture | GT CSV | `/home/29d_kon@lab.graphicon.ru/ssd1_link/datasets/MeshMambaSaliency/SaliencyMap/rgb_texture` | 105 |

Server SAL3D release used by benchmark:

```text
/home/29d_kon@lab.graphicon.ru/ssd1_link/datasets/reproject_release_v1/SAL3D
```

Logical counts excluding `._*`:

| Data | Path | Count |
|---|---|---:|
| GT gaze TXT | `reproject_release_v1/SAL3D/Gaze/*.txt` | 58 |
| Mesh OBJ | `reproject_release_v1/SAL3D/Meshes/*.obj` | 57 |
| Smooth_Gaze | `reproject_release_v1/SAL3D/Smooth_Gaze/*` | 53 |
| Our SAL3D gaze CSV | `reproject_release_v1/gaze_csv/SAL3D/*.csv` | 56 |
| SAL3D JSON | `reproject_release_v1/jsons_for_models/SAL3D_json/*.json` | 57 |

Server SAL3D caveat:

- `gaze_csv/SAL3D` physically had 112 files because of 56 `._*.csv`.
- `SAL3D/Smooth_Gaze` physically had 106 files because of 53 `._*.txt`.
- Ignore `._*`.

Server 3DVA:

| Data | Path | Count |
|---|---|---:|
| Fixation maps | `/home/29d_kon@lab.graphicon.ru/ssd1_link/datasets/3DVA/FixationMaps/*.txt` | 96 |
| Corrected OBJ | `/home/29d_kon@lab.graphicon.ru/ssd1_link/datasets/3DVA/3DModels-Simplif-up/*.obj` | 32 |

## 4. Result Structure

Local benchmark result roots:

```text
results/benchmark_runs/meshmamba/2026-06-02_meshmamba_reference
results/benchmark_runs/sal3d/2026-06-01_sal3d_reference
results/benchmark_runs/kld_diagnostic/2026-06-02_kld_diagnostic_064256
results/benchmark_runs/kld_postprocess/2026-06-02_kld_postprocess_full_081351
```

Verified CSV row counts:

| File | Rows excluding header |
|---|---:|
| `meshmamba_reference_long.csv` | 420 |
| `meshmamba_reference_summary.csv` | 4 |
| `sal3d_overall_summary.csv` | 2 |
| `kld_sweep_long.csv` | 306 |
| `postprocess_long.csv` | 16536 |
| `meshmamba_selected_20_models_non_texture_metrics_compact.csv` | 21 |
| `meshmamba_selected_20_models_rgb_texture_metrics_compact.csv` | 21 |

## 5. Documentation Consistency Notes

These handoff docs were checked against the structure above:

- `PROJECT_CONTEXT_DATASETS_SERVERS.md`
- `BENCHMARK_PIPELINES_COMMANDS.md`
- `RESULTS_ISSUES_NEXT_STEPS.md`

If any future agent updates paths or moves result folders, update this audit
file first, then update the handoff docs.

