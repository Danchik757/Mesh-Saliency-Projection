# Side-Input Transfer

Scripts for packaging and transferring participant CSV side inputs to the server.
Datasets (OBJ meshes, GT saliency maps) are already on the server. Placement and
camera JSONs are stored in the repository under `jsons/object_placement/` and
arrive via `git pull`.

## Transfer policy

| Asset type       | How it moves                       |
|------------------|------------------------------------|
| Code             | GitHub → `git pull` on server      |
| Participant CSV  | local pack → `scp` → server unpack |
| Placement JSON   | GitHub → `git pull` on server      |
| Datasets (large) | already on server; not transferred |

## Side inputs per dataset

### 3DVA

| Kind | Local source | Files | Uncompressed size |
|------|-------------|-------|-------------------|
| CSV  | `GAZE_DATA/csv_for_models/3DVA/` | 32 `.csv` | ~38 MB |
| JSON | `jsons/object_placement/3dva_jsons/` | 32 `.json` | tracked by git |

Server destination under `SIDE_INPUTS_ROOT`:
```
side_inputs/3DVA/csv/   ← all 32 CSV files
```

**Note:** The in-repo 3DVA eval scripts (`eval_vs_gt_visual_attention.py`,
`eval_geodesic_diffusion.py`) do NOT need these CSVs — their data is inside the
published dataset. The CSVs here are needed for the external raw-gaze scripts
(`raycast_nearest_vertex`, `cone_gaussian_on_mesh`). Preview/reprojection JSON
metadata must be read from `jsons/object_placement/3dva_jsons`.

### MeshMamba non_texture

| Kind | Local source | Files | Uncompressed size |
|------|-------------|-------|-------------------|
| CSV  | `GAZE_DATA/csv_for_models/MeshMamba_non_texture/` | 105 `.csv` | ~81 MB |
| JSON | `jsons/object_placement/mamba_non_jsons/` | 105 `.json` | tracked by git |

Server destination under `SIDE_INPUTS_ROOT`:
```
side_inputs/MeshMamba_non_texture/csv/   ← all 105 CSV files
```

**JSON is mandatory** for preview rendering and reprojection, but it is no
longer a side-input archive. Use the repo-local canonical JSONs.

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

# 3. Pack CSV archives locally
LOCAL_PACK_DIR=/tmp/reproject_side_inputs bash test/side_inputs/pack_3dva.sh
LOCAL_PACK_DIR=/tmp/reproject_side_inputs bash test/side_inputs/pack_meshmamba_non_texture.sh

# 4. Transfer archives and unpack on server
bash test/launch/mirror_side_inputs.sh
```
