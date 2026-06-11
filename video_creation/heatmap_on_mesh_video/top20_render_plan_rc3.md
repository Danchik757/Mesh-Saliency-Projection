# Top-20 RC3 Render Plan (GT + Cone)

Source: compact benchmark CSVs (rc3 batch — 2026-06-01/02).
Selection: top-7 MeshMamba non_texture + top-7 MeshMamba rgb_texture + top-6 SAL3D by cone CC.
Provenance: cone maps = rc3_full_metrics (server); GT = local dataset files.
Cone maps must be transferred from server before rendering.
**No rendering has been done.** This is a pre-render path resolution plan.

## Model list

| # | Dataset | Track | Model | CC |
|---|---------|-------|-------|----|
| 1 | MeshMamba | non_texture | Watermelon_V1_L3 | 0.9900 |
| 2 | MeshMamba | non_texture | Soda_Can_v3_L3 | 0.8698 |
| 3 | MeshMamba | non_texture | Apple_Red_v1_L3 | 0.8643 |
| 4 | MeshMamba | non_texture | Pear_L3 | 0.8365 |
| 5 | MeshMamba | non_texture | egypt_sphinx_V2_L3 | 0.8025 |
| 6 | MeshMamba | non_texture | barbiegirl_V1_L3 | 0.7828 |
| 7 | MeshMamba | non_texture | Peach_L3 | 0.7812 |
| 8 | MeshMamba | rgb_texture | Watermelon_V1_L3 | 0.9625 |
| 9 | MeshMamba | rgb_texture | Kangaroo_v1_L3 | 0.8603 |
| 10 | MeshMamba | rgb_texture | Apple_Red_v1_L3 | 0.8595 |
| 11 | MeshMamba | rgb_texture | Military_Action_Figure_SG_v2_L3 | 0.7681 |
| 12 | MeshMamba | rgb_texture | Jukebox_bubbler_style_V2_L1 | 0.7525 |
| 13 | MeshMamba | rgb_texture | Cat_v1_L3 | 0.7378 |
| 14 | MeshMamba | rgb_texture | Cardigan_Welsh_Corgi_v1_L3 | 0.7173 |
| 15 | SAL3D | sal3d | torso | 0.8396 |
| 16 | SAL3D | sal3d | car | 0.7929 |
| 17 | SAL3D | sal3d | cow | 0.7852 |
| 18 | SAL3D | sal3d | bunny | 0.7692 |
| 19 | SAL3D | sal3d | gorilla | 0.7659 |
| 20 | SAL3D | sal3d | igea | 0.7587 |

## Resolved paths

Cone map status: **SERVER** (not available locally — see `top20_cone_maps_to_fetch.txt`).
GT / Mesh / JSON: all **present locally**.

### 1. MeshMamba / non_texture / Watermelon_V1_L3 (CC=0.9900)

- **GT map:** `/mnt/f/ClaudeCode/MeshMamba-main/dataset/SaliencyMap/non_texture/Watermelon_v1-L3.csv`
- **Cone map (server):** `/home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/outputs/MeshMamba_reference_batch_20260601/non_texture/baseline_cone/Watermelon_V1_L3/recenter_rotx90p0_horizontaltovertical_blender_rig/Watermelon_V1_L3_cone_vertex_avg_faces.txt`
- **Cone map (local target):** `/mnt/f/ClaudeCode/rc3_cone_maps/meshmamba/non_texture/Watermelon_V1_L3/Watermelon_V1_L3_cone_vertex_avg_faces.txt`
- **Mesh OBJ:** `/mnt/f/ClaudeCode/MeshMamba-main/dataset/MeshFile/non_texture/Watermelon_V1_L3/Watermelon_v1-L3.obj`
- **Placement JSON:** `jsons/object_placement/mamba_non_jsons/MeshMamba_non_texture_Watermelon_V1_L3.json`
- **Output dir:** `<OUTPUT_DIR>/meshmamba/non_texture/Watermelon_V1_L3/gt/` and `<OUTPUT_DIR>/meshmamba/non_texture/Watermelon_V1_L3/cone/`

### 2. MeshMamba / non_texture / Soda_Can_v3_L3 (CC=0.8698)

- **GT map:** `/mnt/f/ClaudeCode/MeshMamba-main/dataset/SaliencyMap/non_texture/Soda_Can_v3_l3.csv`
- **Cone map (server):** `/home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/outputs/MeshMamba_reference_batch_20260601/non_texture/baseline_cone/Soda_Can_v3_L3/recenter_rotx90p0_horizontaltovertical_blender_rig/Soda_Can_v3_L3_cone_vertex_avg_faces.txt`
- **Cone map (local target):** `/mnt/f/ClaudeCode/rc3_cone_maps/meshmamba/non_texture/Soda_Can_v3_L3/Soda_Can_v3_L3_cone_vertex_avg_faces.txt`
- **Mesh OBJ:** `/mnt/f/ClaudeCode/MeshMamba-main/dataset/MeshFile/non_texture/Soda_Can_v3_L3/Soda_Can_v3_l3.obj`
- **Placement JSON:** `jsons/object_placement/mamba_non_jsons/MeshMamba_non_texture_Soda_Can_v3_L3.json`
- **Output dir:** `<OUTPUT_DIR>/meshmamba/non_texture/Soda_Can_v3_L3/gt/` and `<OUTPUT_DIR>/meshmamba/non_texture/Soda_Can_v3_L3/cone/`

### 3. MeshMamba / non_texture / Apple_Red_v1_L3 (CC=0.8643)

- **GT map:** `/mnt/f/ClaudeCode/MeshMamba-main/dataset/SaliencyMap/non_texture/Apple_v01_l3.csv`
- **Cone map (server):** `/home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/outputs/MeshMamba_reference_batch_20260601/non_texture/baseline_cone/Apple_Red_v1_L3/recenter_rotx90p0_horizontaltovertical_blender_rig/Apple_Red_v1_L3_cone_vertex_avg_faces.txt`
- **Cone map (local target):** `/mnt/f/ClaudeCode/rc3_cone_maps/meshmamba/non_texture/Apple_Red_v1_L3/Apple_Red_v1_L3_cone_vertex_avg_faces.txt`
- **Mesh OBJ:** `/mnt/f/ClaudeCode/MeshMamba-main/dataset/MeshFile/non_texture/Apple_Red_v1_L3/Apple_v01_l3.obj`
- **Placement JSON:** `jsons/object_placement/mamba_non_jsons/MeshMamba_non_texture_Apple_Red_v1_L3.json`
- **Output dir:** `<OUTPUT_DIR>/meshmamba/non_texture/Apple_Red_v1_L3/gt/` and `<OUTPUT_DIR>/meshmamba/non_texture/Apple_Red_v1_L3/cone/`

### 4. MeshMamba / non_texture / Pear_L3 (CC=0.8365)

- **GT map:** `/mnt/f/ClaudeCode/MeshMamba-main/dataset/SaliencyMap/non_texture/Pear.csv`
- **Cone map (server):** `/home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/outputs/MeshMamba_reference_batch_20260601/non_texture/baseline_cone/Pear_L3/recenter_rotx90p0_horizontaltovertical_blender_rig/Pear_L3_cone_vertex_avg_faces.txt`
- **Cone map (local target):** `/mnt/f/ClaudeCode/rc3_cone_maps/meshmamba/non_texture/Pear_L3/Pear_L3_cone_vertex_avg_faces.txt`
- **Mesh OBJ:** `/mnt/f/ClaudeCode/MeshMamba-main/dataset/MeshFile/non_texture/Pear_L3/Pear.obj`
- **Placement JSON:** `jsons/object_placement/mamba_non_jsons/MeshMamba_non_texture_Pear_L3.json`
- **Output dir:** `<OUTPUT_DIR>/meshmamba/non_texture/Pear_L3/gt/` and `<OUTPUT_DIR>/meshmamba/non_texture/Pear_L3/cone/`

### 5. MeshMamba / non_texture / egypt_sphinx_V2_L3 (CC=0.8025)

- **GT map:** `/mnt/f/ClaudeCode/MeshMamba-main/dataset/SaliencyMap/non_texture/egypt_sphinx_iterations-2.csv`
- **Cone map (server):** `/home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/outputs/MeshMamba_reference_batch_20260601/non_texture/baseline_cone/egypt_sphinx_V2_L3/recenter_rotx90p0_horizontaltovertical_blender_rig/egypt_sphinx_V2_L3_cone_vertex_avg_faces.txt`
- **Cone map (local target):** `/mnt/f/ClaudeCode/rc3_cone_maps/meshmamba/non_texture/egypt_sphinx_V2_L3/egypt_sphinx_V2_L3_cone_vertex_avg_faces.txt`
- **Mesh OBJ:** `/mnt/f/ClaudeCode/MeshMamba-main/dataset/MeshFile/non_texture/egypt_sphinx_V2_L3/egypt_sphinx_iterations-2.obj`
- **Placement JSON:** `jsons/object_placement/mamba_non_jsons/MeshMamba_non_texture_egypt_sphinx_V2_L3.json`
- **Output dir:** `<OUTPUT_DIR>/meshmamba/non_texture/egypt_sphinx_V2_L3/gt/` and `<OUTPUT_DIR>/meshmamba/non_texture/egypt_sphinx_V2_L3/cone/`

### 6. MeshMamba / non_texture / barbiegirl_V1_L3 (CC=0.7828)

- **GT map:** `/mnt/f/ClaudeCode/MeshMamba-main/dataset/SaliencyMap/non_texture/barbiedoll_v1_L3.csv`
- **Cone map (server):** `/home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/outputs/MeshMamba_reference_batch_20260601/non_texture/baseline_cone/barbiegirl_V1_L3/recenter_rotx90p0_horizontaltovertical_blender_rig/barbiegirl_V1_L3_cone_vertex_avg_faces.txt`
- **Cone map (local target):** `/mnt/f/ClaudeCode/rc3_cone_maps/meshmamba/non_texture/barbiegirl_V1_L3/barbiegirl_V1_L3_cone_vertex_avg_faces.txt`
- **Mesh OBJ:** `/mnt/f/ClaudeCode/MeshMamba-main/dataset/MeshFile/non_texture/barbiegirl_V1_L3/barbiedoll_v1_L3.obj`
- **Placement JSON:** `jsons/object_placement/mamba_non_jsons/MeshMamba_non_texture_barbiegirl_V1_L3.json`
- **Output dir:** `<OUTPUT_DIR>/meshmamba/non_texture/barbiegirl_V1_L3/gt/` and `<OUTPUT_DIR>/meshmamba/non_texture/barbiegirl_V1_L3/cone/`

### 7. MeshMamba / non_texture / Peach_L3 (CC=0.7812)

- **GT map:** `/mnt/f/ClaudeCode/MeshMamba-main/dataset/SaliencyMap/non_texture/Peach.csv`
- **Cone map (server):** `/home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/outputs/MeshMamba_reference_batch_20260601/non_texture/baseline_cone/Peach_L3/recenter_rotx90p0_horizontaltovertical_blender_rig/Peach_L3_cone_vertex_avg_faces.txt`
- **Cone map (local target):** `/mnt/f/ClaudeCode/rc3_cone_maps/meshmamba/non_texture/Peach_L3/Peach_L3_cone_vertex_avg_faces.txt`
- **Mesh OBJ:** `/mnt/f/ClaudeCode/MeshMamba-main/dataset/MeshFile/non_texture/Peach_L3/Peach.obj`
- **Placement JSON:** `jsons/object_placement/mamba_non_jsons/MeshMamba_non_texture_Peach_L3.json`
- **Output dir:** `<OUTPUT_DIR>/meshmamba/non_texture/Peach_L3/gt/` and `<OUTPUT_DIR>/meshmamba/non_texture/Peach_L3/cone/`

### 8. MeshMamba / rgb_texture / Watermelon_V1_L3 (CC=0.9625)

- **GT map:** `/mnt/f/ClaudeCode/MeshMamba-main/dataset/SaliencyMap/rgb_texture/Watermelon_v1-L3.csv`
- **Cone map (server):** `/home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/outputs/MeshMamba_reference_batch_20260601/rgb_texture/baseline_cone/Watermelon_V1_L3/recenter_rotx90p0_horizontaltovertical_blender_rig/Watermelon_V1_L3_cone_vertex_avg_faces.txt`
- **Cone map (local target):** `/mnt/f/ClaudeCode/rc3_cone_maps/meshmamba/rgb_texture/Watermelon_V1_L3/Watermelon_V1_L3_cone_vertex_avg_faces.txt`
- **Mesh OBJ:** `/mnt/f/ClaudeCode/MeshMamba-main/dataset/MeshFile/rgb_texture/Watermelon_V1_L3/Watermelon_v1-L3.obj`
- **Placement JSON:** `jsons/object_placement/mamba_rgb_jsons/MeshMamba_rgb_texture_Watermelon_V1_L3.json`
- **Output dir:** `<OUTPUT_DIR>/meshmamba/rgb_texture/Watermelon_V1_L3/gt/` and `<OUTPUT_DIR>/meshmamba/rgb_texture/Watermelon_V1_L3/cone/`

### 9. MeshMamba / rgb_texture / Kangaroo_v1_L3 (CC=0.8603)

- **GT map:** `/mnt/f/ClaudeCode/MeshMamba-main/dataset/SaliencyMap/rgb_texture/Kangaroo_v1_L3.csv`
- **Cone map (server):** `/home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/outputs/MeshMamba_reference_batch_20260601/rgb_texture/baseline_cone/Kangaroo_v1_L3/recenter_rotx90p0_horizontaltovertical_blender_rig/Kangaroo_v1_L3_cone_vertex_avg_faces.txt`
- **Cone map (local target):** `/mnt/f/ClaudeCode/rc3_cone_maps/meshmamba/rgb_texture/Kangaroo_v1_L3/Kangaroo_v1_L3_cone_vertex_avg_faces.txt`
- **Mesh OBJ:** `/mnt/f/ClaudeCode/MeshMamba-main/dataset/MeshFile/rgb_texture/Kangaroo_v1_L3/Kangaroo_v1_L3.obj`
- **Placement JSON:** `jsons/object_placement/mamba_rgb_jsons/MeshMamba_rgb_texture_Kangaroo_v1_L3.json`
- **Output dir:** `<OUTPUT_DIR>/meshmamba/rgb_texture/Kangaroo_v1_L3/gt/` and `<OUTPUT_DIR>/meshmamba/rgb_texture/Kangaroo_v1_L3/cone/`

### 10. MeshMamba / rgb_texture / Apple_Red_v1_L3 (CC=0.8595)

- **GT map:** `/mnt/f/ClaudeCode/MeshMamba-main/dataset/SaliencyMap/rgb_texture/Apple_v01_l3.csv`
- **Cone map (server):** `/home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/outputs/MeshMamba_reference_batch_20260601/rgb_texture/baseline_cone/Apple_Red_v1_L3/recenter_rotx90p0_horizontaltovertical_blender_rig/Apple_Red_v1_L3_cone_vertex_avg_faces.txt`
- **Cone map (local target):** `/mnt/f/ClaudeCode/rc3_cone_maps/meshmamba/rgb_texture/Apple_Red_v1_L3/Apple_Red_v1_L3_cone_vertex_avg_faces.txt`
- **Mesh OBJ:** `/mnt/f/ClaudeCode/MeshMamba-main/dataset/MeshFile/rgb_texture/Apple_Red_v1_L3/Apple_v01_l3.obj`
- **Placement JSON:** `jsons/object_placement/mamba_rgb_jsons/MeshMamba_rgb_texture_Apple_Red_v1_L3.json`
- **Output dir:** `<OUTPUT_DIR>/meshmamba/rgb_texture/Apple_Red_v1_L3/gt/` and `<OUTPUT_DIR>/meshmamba/rgb_texture/Apple_Red_v1_L3/cone/`

### 11. MeshMamba / rgb_texture / Military_Action_Figure_SG_v2_L3 (CC=0.7681)

- **GT map:** `/mnt/f/ClaudeCode/MeshMamba-main/dataset/SaliencyMap/rgb_texture/Military_Action_Figure_SG_v2_L3.csv`
- **Cone map (server):** `/home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/outputs/MeshMamba_reference_batch_20260601/rgb_texture/baseline_cone/Military_Action_Figure_SG_v2_L3/recenter_rotx90p0_horizontaltovertical_blender_rig/Military_Action_Figure_SG_v2_L3_cone_vertex_avg_faces.txt`
- **Cone map (local target):** `/mnt/f/ClaudeCode/rc3_cone_maps/meshmamba/rgb_texture/Military_Action_Figure_SG_v2_L3/Military_Action_Figure_SG_v2_L3_cone_vertex_avg_faces.txt`
- **Mesh OBJ:** `/mnt/f/ClaudeCode/MeshMamba-main/dataset/MeshFile/rgb_texture/Military_Action_Figure_SG_v2_L3/Military_Action_Figure_SG_v2_L3.obj`
- **Placement JSON:** `jsons/object_placement/mamba_rgb_jsons/MeshMamba_rgb_texture_Military_Action_Figure_SG_v2_L3.json`
- **Output dir:** `<OUTPUT_DIR>/meshmamba/rgb_texture/Military_Action_Figure_SG_v2_L3/gt/` and `<OUTPUT_DIR>/meshmamba/rgb_texture/Military_Action_Figure_SG_v2_L3/cone/`

### 12. MeshMamba / rgb_texture / Jukebox_bubbler_style_V2_L1 (CC=0.7525)

- **GT map:** `/mnt/f/ClaudeCode/MeshMamba-main/dataset/SaliencyMap/rgb_texture/Jukebox_bubbler_style_V2_Textured.csv`
- **Cone map (server):** `/home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/outputs/MeshMamba_reference_batch_20260601/rgb_texture/baseline_cone/Jukebox_bubbler_style_V2_L1/recenter_rotx90p0_horizontaltovertical_blender_rig/Jukebox_bubbler_style_V2_L1_cone_vertex_avg_faces.txt`
- **Cone map (local target):** `/mnt/f/ClaudeCode/rc3_cone_maps/meshmamba/rgb_texture/Jukebox_bubbler_style_V2_L1/Jukebox_bubbler_style_V2_L1_cone_vertex_avg_faces.txt`
- **Mesh OBJ:** `/mnt/f/ClaudeCode/MeshMamba-main/dataset/MeshFile/rgb_texture/Jukebox_bubbler_style_V2_L1/Jukebox_bubbler_style_V2_Textured.obj`
- **Placement JSON:** `jsons/object_placement/mamba_rgb_jsons/MeshMamba_rgb_texture_Jukebox_bubbler_style_V2_L1.json`
- **Output dir:** `<OUTPUT_DIR>/meshmamba/rgb_texture/Jukebox_bubbler_style_V2_L1/gt/` and `<OUTPUT_DIR>/meshmamba/rgb_texture/Jukebox_bubbler_style_V2_L1/cone/`

### 13. MeshMamba / rgb_texture / Cat_v1_L3 (CC=0.7378)

- **GT map:** `/mnt/f/ClaudeCode/MeshMamba-main/dataset/SaliencyMap/rgb_texture/Cat_v1_l3.csv`
- **Cone map (server):** `/home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/outputs/MeshMamba_reference_batch_20260601/rgb_texture/baseline_cone/Cat_v1_L3/recenter_rotx90p0_horizontaltovertical_blender_rig/Cat_v1_L3_cone_vertex_avg_faces.txt`
- **Cone map (local target):** `/mnt/f/ClaudeCode/rc3_cone_maps/meshmamba/rgb_texture/Cat_v1_L3/Cat_v1_L3_cone_vertex_avg_faces.txt`
- **Mesh OBJ:** `/mnt/f/ClaudeCode/MeshMamba-main/dataset/MeshFile/rgb_texture/Cat_v1_L3/Cat_v1_l3.obj`
- **Placement JSON:** `jsons/object_placement/mamba_rgb_jsons/MeshMamba_rgb_texture_Cat_v1_L3.json`
- **Output dir:** `<OUTPUT_DIR>/meshmamba/rgb_texture/Cat_v1_L3/gt/` and `<OUTPUT_DIR>/meshmamba/rgb_texture/Cat_v1_L3/cone/`

### 14. MeshMamba / rgb_texture / Cardigan_Welsh_Corgi_v1_L3 (CC=0.7173)

- **GT map:** `/mnt/f/ClaudeCode/MeshMamba-main/dataset/SaliencyMap/rgb_texture/Cardigan_Welsh_Corgi_v1_L3.csv`
- **Cone map (server):** `/home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/outputs/MeshMamba_reference_batch_20260601/rgb_texture/baseline_cone/Cardigan_Welsh_Corgi_v1_L3/recenter_rotx90p0_horizontaltovertical_blender_rig/Cardigan_Welsh_Corgi_v1_L3_cone_vertex_avg_faces.txt`
- **Cone map (local target):** `/mnt/f/ClaudeCode/rc3_cone_maps/meshmamba/rgb_texture/Cardigan_Welsh_Corgi_v1_L3/Cardigan_Welsh_Corgi_v1_L3_cone_vertex_avg_faces.txt`
- **Mesh OBJ:** `/mnt/f/ClaudeCode/MeshMamba-main/dataset/MeshFile/rgb_texture/Cardigan_Welsh_Corgi_v1_L3/Cardigan_Welsh_Corgi_v1_L3.obj`
- **Placement JSON:** `jsons/object_placement/mamba_rgb_jsons/MeshMamba_rgb_texture_Cardigan_Welsh_Corgi_v1_L3.json`
- **Output dir:** `<OUTPUT_DIR>/meshmamba/rgb_texture/Cardigan_Welsh_Corgi_v1_L3/gt/` and `<OUTPUT_DIR>/meshmamba/rgb_texture/Cardigan_Welsh_Corgi_v1_L3/cone/`

### 15. SAL3D / sal3d / torso (CC=0.8396)

- **GT map:** `/mnt/f/ClaudeCode/sal3d_benchmark_pkg/sal3d_fixed_face_gt/torso_faces.txt`
- **Cone map (server):** `/home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/outputs/SAL3D_reference_batch_20260601/baseline_cone/torso/recenter_rotx90p0_horizontaltovertical_blender_rig/torso_cone_baseline_vertices.txt`
- **Cone map (local target):** `/mnt/f/ClaudeCode/rc3_cone_maps/sal3d/torso/torso_cone_baseline_vertices.txt`
- **Mesh OBJ:** `/mnt/f/ClaudeCode/sal3d_benchmark_pkg/Meshes/torso.obj`
- **Placement JSON:** `jsons/object_placement/sal3d_jsons/Sal3D_torso.json`
- **Output dir:** `<OUTPUT_DIR>/sal3d/torso/gt/` and `<OUTPUT_DIR>/sal3d/torso/cone/`

### 16. SAL3D / sal3d / car (CC=0.7929)

- **GT map:** `/mnt/f/ClaudeCode/sal3d_benchmark_pkg/sal3d_fixed_face_gt/car_faces.txt`
- **Cone map (server):** `/home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/outputs/SAL3D_reference_batch_20260601/baseline_cone/car/recenter_rotx90p0_horizontaltovertical_blender_rig/car_cone_baseline_vertices.txt`
- **Cone map (local target):** `/mnt/f/ClaudeCode/rc3_cone_maps/sal3d/car/car_cone_baseline_vertices.txt`
- **Mesh OBJ:** `/mnt/f/ClaudeCode/sal3d_benchmark_pkg/Meshes/car.obj`
- **Placement JSON:** `jsons/object_placement/sal3d_jsons/Sal3D_car.json`
- **Output dir:** `<OUTPUT_DIR>/sal3d/car/gt/` and `<OUTPUT_DIR>/sal3d/car/cone/`

### 17. SAL3D / sal3d / cow (CC=0.7852)

- **GT map:** `/mnt/f/ClaudeCode/sal3d_benchmark_pkg/sal3d_fixed_face_gt/cow_faces.txt`
- **Cone map (server):** `/home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/outputs/SAL3D_reference_batch_20260601/baseline_cone/cow/recenter_rotx90p0_horizontaltovertical_blender_rig/cow_cone_baseline_vertices.txt`
- **Cone map (local target):** `/mnt/f/ClaudeCode/rc3_cone_maps/sal3d/cow/cow_cone_baseline_vertices.txt`
- **Mesh OBJ:** `/mnt/f/ClaudeCode/sal3d_benchmark_pkg/Meshes/cow.obj`
- **Placement JSON:** `jsons/object_placement/sal3d_jsons/Sal3D_cow.json`
- **Output dir:** `<OUTPUT_DIR>/sal3d/cow/gt/` and `<OUTPUT_DIR>/sal3d/cow/cone/`

### 18. SAL3D / sal3d / bunny (CC=0.7692)

- **GT map:** `/mnt/f/ClaudeCode/sal3d_benchmark_pkg/sal3d_fixed_face_gt/bunny_faces.txt`
- **Cone map (server):** `/home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/outputs/SAL3D_reference_batch_20260601/baseline_cone/bunny/recenter_rotx90p0_horizontaltovertical_blender_rig/bunny_cone_baseline_vertices.txt`
- **Cone map (local target):** `/mnt/f/ClaudeCode/rc3_cone_maps/sal3d/bunny/bunny_cone_baseline_vertices.txt`
- **Mesh OBJ:** `/mnt/f/ClaudeCode/sal3d_benchmark_pkg/Meshes/bunny.obj`
- **Placement JSON:** `jsons/object_placement/sal3d_jsons/Sal3D_bunny.json`
- **Output dir:** `<OUTPUT_DIR>/sal3d/bunny/gt/` and `<OUTPUT_DIR>/sal3d/bunny/cone/`

### 19. SAL3D / sal3d / gorilla (CC=0.7659)

- **GT map:** `/mnt/f/ClaudeCode/sal3d_benchmark_pkg/sal3d_fixed_face_gt/gorilla_faces.txt`
- **Cone map (server):** `/home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/outputs/SAL3D_reference_batch_20260601/baseline_cone/gorilla/recenter_rotx90p0_horizontaltovertical_blender_rig/gorilla_cone_baseline_vertices.txt`
- **Cone map (local target):** `/mnt/f/ClaudeCode/rc3_cone_maps/sal3d/gorilla/gorilla_cone_baseline_vertices.txt`
- **Mesh OBJ:** `/mnt/f/ClaudeCode/sal3d_benchmark_pkg/Meshes/gorilla.obj`
- **Placement JSON:** `jsons/object_placement/sal3d_jsons/Sal3D_gorilla.json`
- **Output dir:** `<OUTPUT_DIR>/sal3d/gorilla/gt/` and `<OUTPUT_DIR>/sal3d/gorilla/cone/`

### 20. SAL3D / sal3d / igea (CC=0.7587)

- **GT map:** `/mnt/f/ClaudeCode/sal3d_benchmark_pkg/sal3d_fixed_face_gt/igea_faces.txt`
- **Cone map (server):** `/home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/outputs/SAL3D_reference_batch_20260601/baseline_cone/igea/recenter_rotx90p0_horizontaltovertical_blender_rig/igea_cone_baseline_vertices.txt`
- **Cone map (local target):** `/mnt/f/ClaudeCode/rc3_cone_maps/sal3d/igea/igea_cone_baseline_vertices.txt`
- **Mesh OBJ:** `/mnt/f/ClaudeCode/sal3d_benchmark_pkg/Meshes/igea.obj`
- **Placement JSON:** `jsons/object_placement/sal3d_jsons/Sal3D_igea.json`
- **Output dir:** `<OUTPUT_DIR>/sal3d/igea/gt/` and `<OUTPUT_DIR>/sal3d/igea/cone/`

## Render commands (template — run after cone maps transferred)

Replace `<OUTPUT_DIR>` with the actual output path.
Each model gets two renders: GT and cone.

```bash
# MeshMamba non_texture Watermelon_V1_L3
python video_creation/heatmap_on_mesh_video/render_heatmap_video.py \
  --dataset meshmamba --texture-type non_texture --model Watermelon_V1_L3 \
  --map-type gt --map-path /mnt/f/ClaudeCode/MeshMamba-main/dataset/SaliencyMap/non_texture/Watermelon_v1-L3.csv \
  --mesh /mnt/f/ClaudeCode/MeshMamba-main/dataset/MeshFile/non_texture/Watermelon_V1_L3/Watermelon_v1-L3.obj --placement jsons/object_placement/mamba_non_jsons/MeshMamba_non_texture_Watermelon_V1_L3.json \
  --output-dir <OUTPUT_DIR>/meshmamba/non_texture/Watermelon_V1_L3/gt \
  --background-color white --full-turn --map-provenance-note rc3_vis_gt

python video_creation/heatmap_on_mesh_video/render_heatmap_video.py \
  --dataset meshmamba --texture-type non_texture --model Watermelon_V1_L3 \
  --map-type cone --map-path /mnt/f/ClaudeCode/rc3_cone_maps/meshmamba/non_texture/Watermelon_V1_L3/Watermelon_V1_L3_cone_vertex_avg_faces.txt \
  --mesh /mnt/f/ClaudeCode/MeshMamba-main/dataset/MeshFile/non_texture/Watermelon_V1_L3/Watermelon_v1-L3.obj --placement jsons/object_placement/mamba_non_jsons/MeshMamba_non_texture_Watermelon_V1_L3.json \
  --output-dir <OUTPUT_DIR>/meshmamba/non_texture/Watermelon_V1_L3/cone \
  --background-color white --full-turn --map-provenance-note rc3_full_metrics

# MeshMamba non_texture Soda_Can_v3_L3
python video_creation/heatmap_on_mesh_video/render_heatmap_video.py \
  --dataset meshmamba --texture-type non_texture --model Soda_Can_v3_L3 \
  --map-type gt --map-path /mnt/f/ClaudeCode/MeshMamba-main/dataset/SaliencyMap/non_texture/Soda_Can_v3_l3.csv \
  --mesh /mnt/f/ClaudeCode/MeshMamba-main/dataset/MeshFile/non_texture/Soda_Can_v3_L3/Soda_Can_v3_l3.obj --placement jsons/object_placement/mamba_non_jsons/MeshMamba_non_texture_Soda_Can_v3_L3.json \
  --output-dir <OUTPUT_DIR>/meshmamba/non_texture/Soda_Can_v3_L3/gt \
  --background-color white --full-turn --map-provenance-note rc3_vis_gt

python video_creation/heatmap_on_mesh_video/render_heatmap_video.py \
  --dataset meshmamba --texture-type non_texture --model Soda_Can_v3_L3 \
  --map-type cone --map-path /mnt/f/ClaudeCode/rc3_cone_maps/meshmamba/non_texture/Soda_Can_v3_L3/Soda_Can_v3_L3_cone_vertex_avg_faces.txt \
  --mesh /mnt/f/ClaudeCode/MeshMamba-main/dataset/MeshFile/non_texture/Soda_Can_v3_L3/Soda_Can_v3_l3.obj --placement jsons/object_placement/mamba_non_jsons/MeshMamba_non_texture_Soda_Can_v3_L3.json \
  --output-dir <OUTPUT_DIR>/meshmamba/non_texture/Soda_Can_v3_L3/cone \
  --background-color white --full-turn --map-provenance-note rc3_full_metrics

# MeshMamba non_texture Apple_Red_v1_L3
python video_creation/heatmap_on_mesh_video/render_heatmap_video.py \
  --dataset meshmamba --texture-type non_texture --model Apple_Red_v1_L3 \
  --map-type gt --map-path /mnt/f/ClaudeCode/MeshMamba-main/dataset/SaliencyMap/non_texture/Apple_v01_l3.csv \
  --mesh /mnt/f/ClaudeCode/MeshMamba-main/dataset/MeshFile/non_texture/Apple_Red_v1_L3/Apple_v01_l3.obj --placement jsons/object_placement/mamba_non_jsons/MeshMamba_non_texture_Apple_Red_v1_L3.json \
  --output-dir <OUTPUT_DIR>/meshmamba/non_texture/Apple_Red_v1_L3/gt \
  --background-color white --full-turn --map-provenance-note rc3_vis_gt

python video_creation/heatmap_on_mesh_video/render_heatmap_video.py \
  --dataset meshmamba --texture-type non_texture --model Apple_Red_v1_L3 \
  --map-type cone --map-path /mnt/f/ClaudeCode/rc3_cone_maps/meshmamba/non_texture/Apple_Red_v1_L3/Apple_Red_v1_L3_cone_vertex_avg_faces.txt \
  --mesh /mnt/f/ClaudeCode/MeshMamba-main/dataset/MeshFile/non_texture/Apple_Red_v1_L3/Apple_v01_l3.obj --placement jsons/object_placement/mamba_non_jsons/MeshMamba_non_texture_Apple_Red_v1_L3.json \
  --output-dir <OUTPUT_DIR>/meshmamba/non_texture/Apple_Red_v1_L3/cone \
  --background-color white --full-turn --map-provenance-note rc3_full_metrics

# MeshMamba non_texture Pear_L3
python video_creation/heatmap_on_mesh_video/render_heatmap_video.py \
  --dataset meshmamba --texture-type non_texture --model Pear_L3 \
  --map-type gt --map-path /mnt/f/ClaudeCode/MeshMamba-main/dataset/SaliencyMap/non_texture/Pear.csv \
  --mesh /mnt/f/ClaudeCode/MeshMamba-main/dataset/MeshFile/non_texture/Pear_L3/Pear.obj --placement jsons/object_placement/mamba_non_jsons/MeshMamba_non_texture_Pear_L3.json \
  --output-dir <OUTPUT_DIR>/meshmamba/non_texture/Pear_L3/gt \
  --background-color white --full-turn --map-provenance-note rc3_vis_gt

python video_creation/heatmap_on_mesh_video/render_heatmap_video.py \
  --dataset meshmamba --texture-type non_texture --model Pear_L3 \
  --map-type cone --map-path /mnt/f/ClaudeCode/rc3_cone_maps/meshmamba/non_texture/Pear_L3/Pear_L3_cone_vertex_avg_faces.txt \
  --mesh /mnt/f/ClaudeCode/MeshMamba-main/dataset/MeshFile/non_texture/Pear_L3/Pear.obj --placement jsons/object_placement/mamba_non_jsons/MeshMamba_non_texture_Pear_L3.json \
  --output-dir <OUTPUT_DIR>/meshmamba/non_texture/Pear_L3/cone \
  --background-color white --full-turn --map-provenance-note rc3_full_metrics

# MeshMamba non_texture egypt_sphinx_V2_L3
python video_creation/heatmap_on_mesh_video/render_heatmap_video.py \
  --dataset meshmamba --texture-type non_texture --model egypt_sphinx_V2_L3 \
  --map-type gt --map-path /mnt/f/ClaudeCode/MeshMamba-main/dataset/SaliencyMap/non_texture/egypt_sphinx_iterations-2.csv \
  --mesh /mnt/f/ClaudeCode/MeshMamba-main/dataset/MeshFile/non_texture/egypt_sphinx_V2_L3/egypt_sphinx_iterations-2.obj --placement jsons/object_placement/mamba_non_jsons/MeshMamba_non_texture_egypt_sphinx_V2_L3.json \
  --output-dir <OUTPUT_DIR>/meshmamba/non_texture/egypt_sphinx_V2_L3/gt \
  --background-color white --full-turn --map-provenance-note rc3_vis_gt

python video_creation/heatmap_on_mesh_video/render_heatmap_video.py \
  --dataset meshmamba --texture-type non_texture --model egypt_sphinx_V2_L3 \
  --map-type cone --map-path /mnt/f/ClaudeCode/rc3_cone_maps/meshmamba/non_texture/egypt_sphinx_V2_L3/egypt_sphinx_V2_L3_cone_vertex_avg_faces.txt \
  --mesh /mnt/f/ClaudeCode/MeshMamba-main/dataset/MeshFile/non_texture/egypt_sphinx_V2_L3/egypt_sphinx_iterations-2.obj --placement jsons/object_placement/mamba_non_jsons/MeshMamba_non_texture_egypt_sphinx_V2_L3.json \
  --output-dir <OUTPUT_DIR>/meshmamba/non_texture/egypt_sphinx_V2_L3/cone \
  --background-color white --full-turn --map-provenance-note rc3_full_metrics

# MeshMamba non_texture barbiegirl_V1_L3
python video_creation/heatmap_on_mesh_video/render_heatmap_video.py \
  --dataset meshmamba --texture-type non_texture --model barbiegirl_V1_L3 \
  --map-type gt --map-path /mnt/f/ClaudeCode/MeshMamba-main/dataset/SaliencyMap/non_texture/barbiedoll_v1_L3.csv \
  --mesh /mnt/f/ClaudeCode/MeshMamba-main/dataset/MeshFile/non_texture/barbiegirl_V1_L3/barbiedoll_v1_L3.obj --placement jsons/object_placement/mamba_non_jsons/MeshMamba_non_texture_barbiegirl_V1_L3.json \
  --output-dir <OUTPUT_DIR>/meshmamba/non_texture/barbiegirl_V1_L3/gt \
  --background-color white --full-turn --map-provenance-note rc3_vis_gt

python video_creation/heatmap_on_mesh_video/render_heatmap_video.py \
  --dataset meshmamba --texture-type non_texture --model barbiegirl_V1_L3 \
  --map-type cone --map-path /mnt/f/ClaudeCode/rc3_cone_maps/meshmamba/non_texture/barbiegirl_V1_L3/barbiegirl_V1_L3_cone_vertex_avg_faces.txt \
  --mesh /mnt/f/ClaudeCode/MeshMamba-main/dataset/MeshFile/non_texture/barbiegirl_V1_L3/barbiedoll_v1_L3.obj --placement jsons/object_placement/mamba_non_jsons/MeshMamba_non_texture_barbiegirl_V1_L3.json \
  --output-dir <OUTPUT_DIR>/meshmamba/non_texture/barbiegirl_V1_L3/cone \
  --background-color white --full-turn --map-provenance-note rc3_full_metrics

# MeshMamba non_texture Peach_L3
python video_creation/heatmap_on_mesh_video/render_heatmap_video.py \
  --dataset meshmamba --texture-type non_texture --model Peach_L3 \
  --map-type gt --map-path /mnt/f/ClaudeCode/MeshMamba-main/dataset/SaliencyMap/non_texture/Peach.csv \
  --mesh /mnt/f/ClaudeCode/MeshMamba-main/dataset/MeshFile/non_texture/Peach_L3/Peach.obj --placement jsons/object_placement/mamba_non_jsons/MeshMamba_non_texture_Peach_L3.json \
  --output-dir <OUTPUT_DIR>/meshmamba/non_texture/Peach_L3/gt \
  --background-color white --full-turn --map-provenance-note rc3_vis_gt

python video_creation/heatmap_on_mesh_video/render_heatmap_video.py \
  --dataset meshmamba --texture-type non_texture --model Peach_L3 \
  --map-type cone --map-path /mnt/f/ClaudeCode/rc3_cone_maps/meshmamba/non_texture/Peach_L3/Peach_L3_cone_vertex_avg_faces.txt \
  --mesh /mnt/f/ClaudeCode/MeshMamba-main/dataset/MeshFile/non_texture/Peach_L3/Peach.obj --placement jsons/object_placement/mamba_non_jsons/MeshMamba_non_texture_Peach_L3.json \
  --output-dir <OUTPUT_DIR>/meshmamba/non_texture/Peach_L3/cone \
  --background-color white --full-turn --map-provenance-note rc3_full_metrics

# MeshMamba rgb_texture Watermelon_V1_L3
python video_creation/heatmap_on_mesh_video/render_heatmap_video.py \
  --dataset meshmamba --texture-type rgb_texture --model Watermelon_V1_L3 \
  --map-type gt --map-path /mnt/f/ClaudeCode/MeshMamba-main/dataset/SaliencyMap/rgb_texture/Watermelon_v1-L3.csv \
  --mesh /mnt/f/ClaudeCode/MeshMamba-main/dataset/MeshFile/rgb_texture/Watermelon_V1_L3/Watermelon_v1-L3.obj --placement jsons/object_placement/mamba_rgb_jsons/MeshMamba_rgb_texture_Watermelon_V1_L3.json \
  --output-dir <OUTPUT_DIR>/meshmamba/rgb_texture/Watermelon_V1_L3/gt \
  --background-color white --full-turn --map-provenance-note rc3_vis_gt

python video_creation/heatmap_on_mesh_video/render_heatmap_video.py \
  --dataset meshmamba --texture-type rgb_texture --model Watermelon_V1_L3 \
  --map-type cone --map-path /mnt/f/ClaudeCode/rc3_cone_maps/meshmamba/rgb_texture/Watermelon_V1_L3/Watermelon_V1_L3_cone_vertex_avg_faces.txt \
  --mesh /mnt/f/ClaudeCode/MeshMamba-main/dataset/MeshFile/rgb_texture/Watermelon_V1_L3/Watermelon_v1-L3.obj --placement jsons/object_placement/mamba_rgb_jsons/MeshMamba_rgb_texture_Watermelon_V1_L3.json \
  --output-dir <OUTPUT_DIR>/meshmamba/rgb_texture/Watermelon_V1_L3/cone \
  --background-color white --full-turn --map-provenance-note rc3_full_metrics

# MeshMamba rgb_texture Kangaroo_v1_L3
python video_creation/heatmap_on_mesh_video/render_heatmap_video.py \
  --dataset meshmamba --texture-type rgb_texture --model Kangaroo_v1_L3 \
  --map-type gt --map-path /mnt/f/ClaudeCode/MeshMamba-main/dataset/SaliencyMap/rgb_texture/Kangaroo_v1_L3.csv \
  --mesh /mnt/f/ClaudeCode/MeshMamba-main/dataset/MeshFile/rgb_texture/Kangaroo_v1_L3/Kangaroo_v1_L3.obj --placement jsons/object_placement/mamba_rgb_jsons/MeshMamba_rgb_texture_Kangaroo_v1_L3.json \
  --output-dir <OUTPUT_DIR>/meshmamba/rgb_texture/Kangaroo_v1_L3/gt \
  --background-color white --full-turn --map-provenance-note rc3_vis_gt

python video_creation/heatmap_on_mesh_video/render_heatmap_video.py \
  --dataset meshmamba --texture-type rgb_texture --model Kangaroo_v1_L3 \
  --map-type cone --map-path /mnt/f/ClaudeCode/rc3_cone_maps/meshmamba/rgb_texture/Kangaroo_v1_L3/Kangaroo_v1_L3_cone_vertex_avg_faces.txt \
  --mesh /mnt/f/ClaudeCode/MeshMamba-main/dataset/MeshFile/rgb_texture/Kangaroo_v1_L3/Kangaroo_v1_L3.obj --placement jsons/object_placement/mamba_rgb_jsons/MeshMamba_rgb_texture_Kangaroo_v1_L3.json \
  --output-dir <OUTPUT_DIR>/meshmamba/rgb_texture/Kangaroo_v1_L3/cone \
  --background-color white --full-turn --map-provenance-note rc3_full_metrics

# MeshMamba rgb_texture Apple_Red_v1_L3
python video_creation/heatmap_on_mesh_video/render_heatmap_video.py \
  --dataset meshmamba --texture-type rgb_texture --model Apple_Red_v1_L3 \
  --map-type gt --map-path /mnt/f/ClaudeCode/MeshMamba-main/dataset/SaliencyMap/rgb_texture/Apple_v01_l3.csv \
  --mesh /mnt/f/ClaudeCode/MeshMamba-main/dataset/MeshFile/rgb_texture/Apple_Red_v1_L3/Apple_v01_l3.obj --placement jsons/object_placement/mamba_rgb_jsons/MeshMamba_rgb_texture_Apple_Red_v1_L3.json \
  --output-dir <OUTPUT_DIR>/meshmamba/rgb_texture/Apple_Red_v1_L3/gt \
  --background-color white --full-turn --map-provenance-note rc3_vis_gt

python video_creation/heatmap_on_mesh_video/render_heatmap_video.py \
  --dataset meshmamba --texture-type rgb_texture --model Apple_Red_v1_L3 \
  --map-type cone --map-path /mnt/f/ClaudeCode/rc3_cone_maps/meshmamba/rgb_texture/Apple_Red_v1_L3/Apple_Red_v1_L3_cone_vertex_avg_faces.txt \
  --mesh /mnt/f/ClaudeCode/MeshMamba-main/dataset/MeshFile/rgb_texture/Apple_Red_v1_L3/Apple_v01_l3.obj --placement jsons/object_placement/mamba_rgb_jsons/MeshMamba_rgb_texture_Apple_Red_v1_L3.json \
  --output-dir <OUTPUT_DIR>/meshmamba/rgb_texture/Apple_Red_v1_L3/cone \
  --background-color white --full-turn --map-provenance-note rc3_full_metrics

# MeshMamba rgb_texture Military_Action_Figure_SG_v2_L3
python video_creation/heatmap_on_mesh_video/render_heatmap_video.py \
  --dataset meshmamba --texture-type rgb_texture --model Military_Action_Figure_SG_v2_L3 \
  --map-type gt --map-path /mnt/f/ClaudeCode/MeshMamba-main/dataset/SaliencyMap/rgb_texture/Military_Action_Figure_SG_v2_L3.csv \
  --mesh /mnt/f/ClaudeCode/MeshMamba-main/dataset/MeshFile/rgb_texture/Military_Action_Figure_SG_v2_L3/Military_Action_Figure_SG_v2_L3.obj --placement jsons/object_placement/mamba_rgb_jsons/MeshMamba_rgb_texture_Military_Action_Figure_SG_v2_L3.json \
  --output-dir <OUTPUT_DIR>/meshmamba/rgb_texture/Military_Action_Figure_SG_v2_L3/gt \
  --background-color white --full-turn --map-provenance-note rc3_vis_gt

python video_creation/heatmap_on_mesh_video/render_heatmap_video.py \
  --dataset meshmamba --texture-type rgb_texture --model Military_Action_Figure_SG_v2_L3 \
  --map-type cone --map-path /mnt/f/ClaudeCode/rc3_cone_maps/meshmamba/rgb_texture/Military_Action_Figure_SG_v2_L3/Military_Action_Figure_SG_v2_L3_cone_vertex_avg_faces.txt \
  --mesh /mnt/f/ClaudeCode/MeshMamba-main/dataset/MeshFile/rgb_texture/Military_Action_Figure_SG_v2_L3/Military_Action_Figure_SG_v2_L3.obj --placement jsons/object_placement/mamba_rgb_jsons/MeshMamba_rgb_texture_Military_Action_Figure_SG_v2_L3.json \
  --output-dir <OUTPUT_DIR>/meshmamba/rgb_texture/Military_Action_Figure_SG_v2_L3/cone \
  --background-color white --full-turn --map-provenance-note rc3_full_metrics

# MeshMamba rgb_texture Jukebox_bubbler_style_V2_L1
python video_creation/heatmap_on_mesh_video/render_heatmap_video.py \
  --dataset meshmamba --texture-type rgb_texture --model Jukebox_bubbler_style_V2_L1 \
  --map-type gt --map-path /mnt/f/ClaudeCode/MeshMamba-main/dataset/SaliencyMap/rgb_texture/Jukebox_bubbler_style_V2_Textured.csv \
  --mesh /mnt/f/ClaudeCode/MeshMamba-main/dataset/MeshFile/rgb_texture/Jukebox_bubbler_style_V2_L1/Jukebox_bubbler_style_V2_Textured.obj --placement jsons/object_placement/mamba_rgb_jsons/MeshMamba_rgb_texture_Jukebox_bubbler_style_V2_L1.json \
  --output-dir <OUTPUT_DIR>/meshmamba/rgb_texture/Jukebox_bubbler_style_V2_L1/gt \
  --background-color white --full-turn --map-provenance-note rc3_vis_gt

python video_creation/heatmap_on_mesh_video/render_heatmap_video.py \
  --dataset meshmamba --texture-type rgb_texture --model Jukebox_bubbler_style_V2_L1 \
  --map-type cone --map-path /mnt/f/ClaudeCode/rc3_cone_maps/meshmamba/rgb_texture/Jukebox_bubbler_style_V2_L1/Jukebox_bubbler_style_V2_L1_cone_vertex_avg_faces.txt \
  --mesh /mnt/f/ClaudeCode/MeshMamba-main/dataset/MeshFile/rgb_texture/Jukebox_bubbler_style_V2_L1/Jukebox_bubbler_style_V2_Textured.obj --placement jsons/object_placement/mamba_rgb_jsons/MeshMamba_rgb_texture_Jukebox_bubbler_style_V2_L1.json \
  --output-dir <OUTPUT_DIR>/meshmamba/rgb_texture/Jukebox_bubbler_style_V2_L1/cone \
  --background-color white --full-turn --map-provenance-note rc3_full_metrics

# MeshMamba rgb_texture Cat_v1_L3
python video_creation/heatmap_on_mesh_video/render_heatmap_video.py \
  --dataset meshmamba --texture-type rgb_texture --model Cat_v1_L3 \
  --map-type gt --map-path /mnt/f/ClaudeCode/MeshMamba-main/dataset/SaliencyMap/rgb_texture/Cat_v1_l3.csv \
  --mesh /mnt/f/ClaudeCode/MeshMamba-main/dataset/MeshFile/rgb_texture/Cat_v1_L3/Cat_v1_l3.obj --placement jsons/object_placement/mamba_rgb_jsons/MeshMamba_rgb_texture_Cat_v1_L3.json \
  --output-dir <OUTPUT_DIR>/meshmamba/rgb_texture/Cat_v1_L3/gt \
  --background-color white --full-turn --map-provenance-note rc3_vis_gt

python video_creation/heatmap_on_mesh_video/render_heatmap_video.py \
  --dataset meshmamba --texture-type rgb_texture --model Cat_v1_L3 \
  --map-type cone --map-path /mnt/f/ClaudeCode/rc3_cone_maps/meshmamba/rgb_texture/Cat_v1_L3/Cat_v1_L3_cone_vertex_avg_faces.txt \
  --mesh /mnt/f/ClaudeCode/MeshMamba-main/dataset/MeshFile/rgb_texture/Cat_v1_L3/Cat_v1_l3.obj --placement jsons/object_placement/mamba_rgb_jsons/MeshMamba_rgb_texture_Cat_v1_L3.json \
  --output-dir <OUTPUT_DIR>/meshmamba/rgb_texture/Cat_v1_L3/cone \
  --background-color white --full-turn --map-provenance-note rc3_full_metrics

# MeshMamba rgb_texture Cardigan_Welsh_Corgi_v1_L3
python video_creation/heatmap_on_mesh_video/render_heatmap_video.py \
  --dataset meshmamba --texture-type rgb_texture --model Cardigan_Welsh_Corgi_v1_L3 \
  --map-type gt --map-path /mnt/f/ClaudeCode/MeshMamba-main/dataset/SaliencyMap/rgb_texture/Cardigan_Welsh_Corgi_v1_L3.csv \
  --mesh /mnt/f/ClaudeCode/MeshMamba-main/dataset/MeshFile/rgb_texture/Cardigan_Welsh_Corgi_v1_L3/Cardigan_Welsh_Corgi_v1_L3.obj --placement jsons/object_placement/mamba_rgb_jsons/MeshMamba_rgb_texture_Cardigan_Welsh_Corgi_v1_L3.json \
  --output-dir <OUTPUT_DIR>/meshmamba/rgb_texture/Cardigan_Welsh_Corgi_v1_L3/gt \
  --background-color white --full-turn --map-provenance-note rc3_vis_gt

python video_creation/heatmap_on_mesh_video/render_heatmap_video.py \
  --dataset meshmamba --texture-type rgb_texture --model Cardigan_Welsh_Corgi_v1_L3 \
  --map-type cone --map-path /mnt/f/ClaudeCode/rc3_cone_maps/meshmamba/rgb_texture/Cardigan_Welsh_Corgi_v1_L3/Cardigan_Welsh_Corgi_v1_L3_cone_vertex_avg_faces.txt \
  --mesh /mnt/f/ClaudeCode/MeshMamba-main/dataset/MeshFile/rgb_texture/Cardigan_Welsh_Corgi_v1_L3/Cardigan_Welsh_Corgi_v1_L3.obj --placement jsons/object_placement/mamba_rgb_jsons/MeshMamba_rgb_texture_Cardigan_Welsh_Corgi_v1_L3.json \
  --output-dir <OUTPUT_DIR>/meshmamba/rgb_texture/Cardigan_Welsh_Corgi_v1_L3/cone \
  --background-color white --full-turn --map-provenance-note rc3_full_metrics

# SAL3D sal3d torso
python video_creation/heatmap_on_mesh_video/render_heatmap_video.py \
  --dataset sal3d --model torso \
  --map-type gt --map-path /mnt/f/ClaudeCode/sal3d_benchmark_pkg/sal3d_fixed_face_gt/torso_faces.txt \
  --mesh /mnt/f/ClaudeCode/sal3d_benchmark_pkg/Meshes/torso.obj --placement jsons/object_placement/sal3d_jsons/Sal3D_torso.json \
  --output-dir <OUTPUT_DIR>/sal3d/torso/gt \
  --background-color white --full-turn --map-provenance-note rc3_vis_gt

python video_creation/heatmap_on_mesh_video/render_heatmap_video.py \
  --dataset sal3d --model torso \
  --map-type cone --map-path /mnt/f/ClaudeCode/rc3_cone_maps/sal3d/torso/torso_cone_baseline_vertices.txt \
  --mesh /mnt/f/ClaudeCode/sal3d_benchmark_pkg/Meshes/torso.obj --placement jsons/object_placement/sal3d_jsons/Sal3D_torso.json \
  --output-dir <OUTPUT_DIR>/sal3d/torso/cone \
  --background-color white --full-turn --map-provenance-note rc3_full_metrics

# SAL3D sal3d car
python video_creation/heatmap_on_mesh_video/render_heatmap_video.py \
  --dataset sal3d --model car \
  --map-type gt --map-path /mnt/f/ClaudeCode/sal3d_benchmark_pkg/sal3d_fixed_face_gt/car_faces.txt \
  --mesh /mnt/f/ClaudeCode/sal3d_benchmark_pkg/Meshes/car.obj --placement jsons/object_placement/sal3d_jsons/Sal3D_car.json \
  --output-dir <OUTPUT_DIR>/sal3d/car/gt \
  --background-color white --full-turn --map-provenance-note rc3_vis_gt

python video_creation/heatmap_on_mesh_video/render_heatmap_video.py \
  --dataset sal3d --model car \
  --map-type cone --map-path /mnt/f/ClaudeCode/rc3_cone_maps/sal3d/car/car_cone_baseline_vertices.txt \
  --mesh /mnt/f/ClaudeCode/sal3d_benchmark_pkg/Meshes/car.obj --placement jsons/object_placement/sal3d_jsons/Sal3D_car.json \
  --output-dir <OUTPUT_DIR>/sal3d/car/cone \
  --background-color white --full-turn --map-provenance-note rc3_full_metrics

# SAL3D sal3d cow
python video_creation/heatmap_on_mesh_video/render_heatmap_video.py \
  --dataset sal3d --model cow \
  --map-type gt --map-path /mnt/f/ClaudeCode/sal3d_benchmark_pkg/sal3d_fixed_face_gt/cow_faces.txt \
  --mesh /mnt/f/ClaudeCode/sal3d_benchmark_pkg/Meshes/cow.obj --placement jsons/object_placement/sal3d_jsons/Sal3D_cow.json \
  --output-dir <OUTPUT_DIR>/sal3d/cow/gt \
  --background-color white --full-turn --map-provenance-note rc3_vis_gt

python video_creation/heatmap_on_mesh_video/render_heatmap_video.py \
  --dataset sal3d --model cow \
  --map-type cone --map-path /mnt/f/ClaudeCode/rc3_cone_maps/sal3d/cow/cow_cone_baseline_vertices.txt \
  --mesh /mnt/f/ClaudeCode/sal3d_benchmark_pkg/Meshes/cow.obj --placement jsons/object_placement/sal3d_jsons/Sal3D_cow.json \
  --output-dir <OUTPUT_DIR>/sal3d/cow/cone \
  --background-color white --full-turn --map-provenance-note rc3_full_metrics

# SAL3D sal3d bunny
python video_creation/heatmap_on_mesh_video/render_heatmap_video.py \
  --dataset sal3d --model bunny \
  --map-type gt --map-path /mnt/f/ClaudeCode/sal3d_benchmark_pkg/sal3d_fixed_face_gt/bunny_faces.txt \
  --mesh /mnt/f/ClaudeCode/sal3d_benchmark_pkg/Meshes/bunny.obj --placement jsons/object_placement/sal3d_jsons/Sal3D_bunny.json \
  --output-dir <OUTPUT_DIR>/sal3d/bunny/gt \
  --background-color white --full-turn --map-provenance-note rc3_vis_gt

python video_creation/heatmap_on_mesh_video/render_heatmap_video.py \
  --dataset sal3d --model bunny \
  --map-type cone --map-path /mnt/f/ClaudeCode/rc3_cone_maps/sal3d/bunny/bunny_cone_baseline_vertices.txt \
  --mesh /mnt/f/ClaudeCode/sal3d_benchmark_pkg/Meshes/bunny.obj --placement jsons/object_placement/sal3d_jsons/Sal3D_bunny.json \
  --output-dir <OUTPUT_DIR>/sal3d/bunny/cone \
  --background-color white --full-turn --map-provenance-note rc3_full_metrics

# SAL3D sal3d gorilla
python video_creation/heatmap_on_mesh_video/render_heatmap_video.py \
  --dataset sal3d --model gorilla \
  --map-type gt --map-path /mnt/f/ClaudeCode/sal3d_benchmark_pkg/sal3d_fixed_face_gt/gorilla_faces.txt \
  --mesh /mnt/f/ClaudeCode/sal3d_benchmark_pkg/Meshes/gorilla.obj --placement jsons/object_placement/sal3d_jsons/Sal3D_gorilla.json \
  --output-dir <OUTPUT_DIR>/sal3d/gorilla/gt \
  --background-color white --full-turn --map-provenance-note rc3_vis_gt

python video_creation/heatmap_on_mesh_video/render_heatmap_video.py \
  --dataset sal3d --model gorilla \
  --map-type cone --map-path /mnt/f/ClaudeCode/rc3_cone_maps/sal3d/gorilla/gorilla_cone_baseline_vertices.txt \
  --mesh /mnt/f/ClaudeCode/sal3d_benchmark_pkg/Meshes/gorilla.obj --placement jsons/object_placement/sal3d_jsons/Sal3D_gorilla.json \
  --output-dir <OUTPUT_DIR>/sal3d/gorilla/cone \
  --background-color white --full-turn --map-provenance-note rc3_full_metrics

# SAL3D sal3d igea
python video_creation/heatmap_on_mesh_video/render_heatmap_video.py \
  --dataset sal3d --model igea \
  --map-type gt --map-path /mnt/f/ClaudeCode/sal3d_benchmark_pkg/sal3d_fixed_face_gt/igea_faces.txt \
  --mesh /mnt/f/ClaudeCode/sal3d_benchmark_pkg/Meshes/igea.obj --placement jsons/object_placement/sal3d_jsons/Sal3D_igea.json \
  --output-dir <OUTPUT_DIR>/sal3d/igea/gt \
  --background-color white --full-turn --map-provenance-note rc3_vis_gt

python video_creation/heatmap_on_mesh_video/render_heatmap_video.py \
  --dataset sal3d --model igea \
  --map-type cone --map-path /mnt/f/ClaudeCode/rc3_cone_maps/sal3d/igea/igea_cone_baseline_vertices.txt \
  --mesh /mnt/f/ClaudeCode/sal3d_benchmark_pkg/Meshes/igea.obj --placement jsons/object_placement/sal3d_jsons/Sal3D_igea.json \
  --output-dir <OUTPUT_DIR>/sal3d/igea/cone \
  --background-color white --full-turn --map-provenance-note rc3_full_metrics

```
