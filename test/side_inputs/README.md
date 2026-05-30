# Side-Input Transfer

Scripts for packaging and transferring participant CSV and JSON camera metadata
to the server. Datasets (OBJ meshes, GT saliency maps) are already on the server.

## Transfer policy

| Asset type       | How it moves                       |
|------------------|------------------------------------|
| Code             | GitHub → `git pull` on server      |
| Side inputs      | local pack → `scp` → server unpack |
| Datasets (large) | already on server; not transferred |

## Side inputs per dataset

### 3DVA

| Kind | Local source | Files | Uncompressed size |
|------|-------------|-------|-------------------|
| CSV  | `GAZE_DATA/csv_for_models/3DVA/` | 32 `.csv` | ~38 MB |
| JSON | `GAZE_DATA/jsons_for_models/3DVA_json/` | 32 `.json` | ~2.6 MB |

Server destination under `SIDE_INPUTS_ROOT`:
```
side_inputs/3DVA/csv/   ← all 32 CSV files
side_inputs/3DVA/json/  ← all 32 JSON files
```

**Note:** The in-repo 3DVA eval scripts (`eval_vs_gt_visual_attention.py`,
`eval_geodesic_diffusion.py`) do NOT need these CSVs — their data is inside the
published dataset. The CSVs/JSONs here are needed for the external raw-gaze
scripts (`raycast_nearest_vertex`, `cone_gaussian_on_mesh`) and for the
preview render tool.

### MeshMamba non_texture

| Kind | Local source | Files | Uncompressed size |
|------|-------------|-------|-------------------|
| CSV  | `GAZE_DATA/csv_for_models/MeshMamba_non_texture/` | 105 `.csv` | ~81 MB |
| JSON | `GAZE_DATA/jsons_for_models/Mamba_non_textured/` | 105 `.json` | ~8.6 MB |

Server destination under `SIDE_INPUTS_ROOT`:
```
side_inputs/MeshMamba_non_texture/csv/   ← all 105 CSV files
side_inputs/MeshMamba_non_texture/json/  ← all 105 JSON files
```

**JSON is mandatory** — without it, preview rendering and reprojection break
because camera/object metadata is read from JSON.

### MeshMamba rgb_texture (deferred)

Transfer only after non_texture protocol is stable.
Scripts: pack and scp commands are commented out in `mirror_side_inputs.sh`.

### SAL3D (blocked)

Blocked until dense GT reconstruction is implemented.

## Workflow

```bash
# 1. Set local env (edit example file or set vars manually)
source test/env/local_paths.example.sh
export SSH_HOST="vg-intellect"
export REMOTE_SIDE_INPUTS="/home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/side_inputs"

# 2. Check what will be transferred (dry run, no scp)
bash test/side_inputs/inventory_3dva.sh
bash test/side_inputs/inventory_meshmamba_non_texture.sh

# 3. Pack archives locally
LOCAL_PACK_DIR=/tmp/reproject_side_inputs bash test/side_inputs/pack_3dva.sh
LOCAL_PACK_DIR=/tmp/reproject_side_inputs bash test/side_inputs/pack_meshmamba_non_texture.sh

# 4. Transfer archives and unpack on server
bash test/launch/mirror_side_inputs.sh
```
