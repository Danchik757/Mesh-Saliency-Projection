# 3DVA — Visual Attention for Rendered 3D Shapes

Dataset from the Eurographics 2018 paper:

> Lavoué G., Cordier F., Seo H., Larabi M.-C.  
> *Visual Attention for Rendered 3D Shapes*, Computer Graphics Forum 37(2), 2018.  
> https://doi.org/10.1111/cgf.13375  
> Dataset homepage: http://liris.cnrs.fr/glavoue/data/saliency/

---

## What this dataset is

The paper ran two eye-tracking experiments on **rendered** (not printed) 3D shapes:

- **Experiment 1** — influence analysis: how shape, lighting, material, and camera movement affect human gaze. Used 3 objects (Igea, Dinosaur, Blade) × 3 materials × 3 lightings × 2 camera positions (static + 3 dynamic paths). **Not used for benchmarking.**

- **Experiment 2** — benchmark: 32 objects rendered under a single controlled condition (intermediate material, top-left illumination, 3 static camera distances). **This produces the 96 fixation maps that form our GT.**

---

## Eye-tracking experimental setup (Experiment 2)

| Parameter | Value |
|-----------|-------|
| Eye-tracker | Tobii TX-120 standalone |
| Accuracy | 0.5° under ideal conditions |
| Sampling rate | 120 Hz (8 ms/sample) |
| Observer distance | ~90 cm |
| Monitor | Eizo ColorEdge CG303W 30" |
| Resolution | 1920 × 1080 px |
| Refresh rate | 60 Hz |
| Task | Free-watching (no specific task) |
| Participants | 20 (one rejected → 19 valid) |
| Stimuli duration | 7 seconds per image |
| Total stimuli | 96 images (32 objects × 3 views) |
| Material | Intermediate (Phong specular=20, glossiness=30) |
| Lighting | Top-left (assumed light direction for shading perception) |

**Sigma used to map fixations to 3D:** 49 pixels at 1920×1080 = 1° of visual angle.

Formula: `σ_px = distance_cm × tan(1°) × px_per_cm ≈ 90 × 0.01745 × 3.0 ≈ 47–49 px`

---

## The three views (300 / 413 / 599)

The 32 objects are each rendered from **3 static camera distances** (3D Studio Max units):

| Label | Meaning | Object apparent size |
|-------|---------|---------------------|
| `300` | Closest view | Largest on screen |
| `413` | Medium view | Medium on screen |
| `599` | Farthest view | Smallest on screen |

32 objects × 3 views = **96 static images**. Each image has its own fixation map.

**The 300/413/599 suffixes in all filenames refer to these 3 camera distances, NOT to frame numbers or percentages.**

---

## Dataset packages and what they contain

### 1. `FixationMaps.zip` — **the ground truth** (2 MB)

```
FixationMaps/
  bunny_300norm.txt
  bunny_413norm.txt
  bunny_599norm.txt
  ...  (32 objects × 3 views = 96 files)
```

**Format:** one float per line. N lines = N vertices in the simplified mesh for that object.

**Meaning:** per-vertex fixation density, summed across all 19 subjects, for the specific static view. The `norm` in the filename means values are normalized (not raw counts).

**Key property (verified):** all non-zero GT values lie on vertices that are visible from that view. Back-face vertices always have GT = 0.

**How it was produced:** paper's ray+cone method (σ=49 px) maps each fixation pixel through the camera to the nearest visible mesh vertex, accumulates across all subjects.

---

### 2. `CentricityAndVisibilityMaps.zip` — auxiliary (32 MB)

```
CentricityAndVisibilityMaps/
  bunny_300_visibility.txt           # which vertices are visible from view 300
  bunny_413_visibility.txt
  bunny_599_visibility.txt
  bunny_300_100_CentricityObject_NewCalculation.txt   # center-proximity map, σ=100px
  bunny_300_150_CentricityObject_NewCalculation.txt   # σ=150px
  ...  (13 σ values × 96 views = 1248 centricity files, 96 visibility files)
```

**Visibility files:** binary (0 or 1) per vertex. `1` = vertex is visible from that camera position.  
Count: 96 files (one per view per object).

**Centricity files:** 2D Gaussian centered on the bounding-box projection, sampled at each vertex. Used by the paper to model center-bias. 13 different σ values (100–400 px range tested).  
Count: 1248 files.

**Why visibility matters for evaluation:** the paper explicitly multiplies all saliency maps by the visibility binary field before computing metrics. This ensures we only evaluate predictions on vertices the observer could actually see. Our eval scripts report both `metrics_vs_gt_full` (all vertices) and `metrics_vs_gt_visible_only` (visible only, matching paper protocol).

---

### 3. `PerSubjectData.zip` — per-subject fixations (236 MB)

```
PerSubjectFixations/
  A380_300.csv.T01.result     # subject T01, view 300
  A380_300.csv.T02.result
  ...  (32 objects × 3 views × ~19 subjects ≈ 1824 files)
```

**Format:** per-vertex fixation counts for ONE subject at ONE view. Format matches `FixationMaps` (one float per line, same vertex count).

**When to use:** for inter-subject agreement analysis (e.g., using 10 subjects to predict the remaining 10 — the paper's human-performance upper bound). Not needed for standard benchmarking.

**Not extracted into our dataset** — downloaded as raw ZIP from the paper's website. Extract only if needed for subject-level analysis.

---

### 4. `SaliencyAlgorithmMaps.zip` — algorithm predictions (36 MB, NOT ground truth)

```
SaliencyAlgorithmMaps/
  bunny_Lee_0.CSV        # Lee [LVJ05] algorithm, no blurring
  bunny_Lee_1.CSV        # Lee, blurring level 1 (10 smoothing iterations)
  bunny_Lee_2.CSV        # Lee, blurring level 2 (40 smoothing iterations)
  bunny_Leifman_0.CSV    # Leifman [LST12], no blurring
  ...  (32 objects × 4 algorithms × 3 blur levels = 384 files)
```

**Format:** one float per line, same vertex count as simplified mesh.

**The 4 algorithms:** Lee [LVJ05], Leifman [LST12], Song [SLMR14], Tasse [TKD15].

**Blur levels:** 0 = no blur, 1 = 10 iter, 2 = 40 iter. (The paper also tested 120 iter for some.)

**NOT ground truth** — these are the paper's mesh saliency baselines used for comparison. Their best CC values reached ~0.47 (Song) vs human upper bound ~0.81.

**When to use:** to compare our method directly against the paper's 4 baselines, or to understand the ceiling and floor of performance on this benchmark.

---

### 5. `3DModels-Orig.zip` — full-resolution original meshes (48 MB)

Original 3D shapes at their native vertex counts (35K–200K+). Used by the paper to compute the fixation maps (ray-casting on high-res mesh), then results are projected onto simplified meshes.

**Not needed for our evaluation** — we use `3DModels-Simplif-up/`.

---

### 6. `3DModels-Simplif.zip` — simplified meshes, WRONG orientation (13 MB)

32 objects simplified to ~20K vertices via isotropic remeshing (Vorpaline tool).

⚠️ **DO NOT USE** — these meshes have wrong axis alignment (Y-up instead of Z-up in our coordinate system). Alignment validation (canonical mask IoU) was done against `3DModels-Simplif-up/` which has corrected orientation.

---

## Our local dataset (`3DModels-Simplif-up/`)

Located at: `$VISUAL_ATTENTION_3D_SHAPES_ROOT/3DModels-Simplif-up/`

Contains the same 32 simplified OBJ meshes with corrected Z-up orientation:

| Object | Vertices | Notes |
|--------|----------|-------|
| Most models | 20,000 | Standard isotropic simplification |
| A380 | 47,756 | Complex concave parts, remeshed to higher count |
| Harley | 54,853 | Many fine details |
| House | 55,560 | Complex architecture |
| jessi | 25,645 | Slightly above 20K |
| car-vasa | 20,890 | Slightly above 20K |
| meca-15k | 15,000 | Sparser simplification |
| vase-15k | 15,000 | Sparser simplification |
| Max-Planck | 19,999 | ~20K |

**Confirmed:** for each model, `FixationMaps/*.txt` has exactly as many lines as the OBJ has vertices. The GT maps to the simplified mesh vertex ordering.

---

## Directory structure (local)

```
$VISUAL_ATTENTION_3D_SHAPES_ROOT/
├── 3DModels-Simplif-up/          ← USE THIS for OBJ meshes
│   ├── bunny.obj  (20,000 verts)
│   ├── A380.obj   (47,756 verts)
│   └── ...  (32 OBJ files)
├── FixationMaps/                  ← THE GROUND TRUTH
│   ├── bunny_300norm.txt  (20,000 lines)
│   ├── bunny_413norm.txt
│   ├── bunny_599norm.txt
│   └── ...  (96 files: 32 × 3 views)
├── CentricityAndVisibilityMaps/   ← VISIBILITY + CENTER BIAS
│   ├── bunny_300_visibility.txt   (binary: 0/1 per vertex)
│   ├── bunny_300_100_CentricityObject_NewCalculation.txt
│   └── ...  (96 visibility + 1248 centricity files)
└── other/
    └── SaliencyAlgorithmMaps/     ← baseline algorithm predictions (NOT GT)
        ├── bunny_Lee_0.CSV
        └── ...  (384 files)
```

---

## Differences between the 3DVA paper and our setup

| Aspect | 3DVA paper (original) | Our setup |
|--------|-----------------------|-----------|
| **Gaze source** | 19 subjects watching 3DVA stimuli | Our participants watching our rendered videos |
| **Camera** | 3 static viewpoints (300/413/599) | Dynamic rotating video (our Blender renders) |
| **Scene type** | Static 3D renders, 7s each | Animated rotation, 17s video |
| **Material** | Intermediate Phong, top-left light | Depends on render (may differ) |
| **Sigma (gaze→3D)** | 49 px at 1920px (1° visual angle) | cone: 1° angular; screen_space: 49 px |
| **Visibility masking** | Yes — applied before metrics | Now added (`metrics_vs_gt_visible_only`) |
| **Blurring** | 4 levels, pick best per model/view | No blurring of our outputs |
| **Center bias** | Combined with 2D Gaussian center model | Not applied |
| **Metrics** | CC (primary), AUC@20% (secondary) | CC, LCC, NSS, AUC, SIM, KLD, Spearman |

**Consequence:** Our metrics are not directly comparable to the paper's Fig. 11 (CC ~0.47 for Song, ~0.81 for human inter-observer). We report metrics for transparency but they reflect different experimental conditions.

**The most valid comparison** against the paper's protocol requires:
1. `metrics_vs_gt_visible_only` (not `metrics_vs_gt_full`)
2. Same σ=49 px for screen_space, or σ=1° for cone

---

## Evaluation protocol from the paper

The paper's benchmarking pipeline for each saliency algorithm:

1. Compute per-vertex saliency map on the **simplified** mesh
2. Create 4 blurred versions (0, 10, 40, 120 smoothing iterations)
3. For center bias: sample σ values 100–400px and fit a linear combination with the saliency map on the remaining objects of the same class
4. Multiply by the **visibility binary field** for each view
5. Compute **Pearson CC** and **AUC** (with 20% fixation threshold)
6. Select the best blurring level and best center-bias σ per view/object

Human inter-observer performance (upper bound): CC ≈ 0.81, AUC ≈ 0.91.

Best saliency algorithm (Leifman alone): CC ≈ 0.35, AUC ≈ 0.76.

---

## Our evaluation scripts

| Script | Purpose |
|--------|---------|
| `reprojection_methods/cone_projection_on_mesh/eval_3dva_raycast_cone.py` | Cone Gaussian + raycast nearest vertex, vs 3 GT views. Reports `metrics_vs_gt_full` and `metrics_vs_gt_visible_only`. |
| `reprojection_methods/screen_space_gaussian/eval_3dva_screen_space.py` | Screen-space Gaussian v2: 1920px, σ=49px, bilinear. Reports both metric sections. |
| `test/launch/run_3dva_raycast_cone.sh` | Batch runner — cone, all 32 models |
| `test/launch/run_3dva_screen_space.sh` | Batch runner — screen_space v2, all 32 models |

### Quick run (one model)

```bash
source configs/server_vg_intellect.env   # sets VISUAL_ATTENTION_3D_SHAPES_ROOT etc.

# Cone method
python3 reprojection_methods/cone_projection_on_mesh/eval_3dva_raycast_cone.py \
  --model bunny \
  --dataset-root $VISUAL_ATTENTION_3D_SHAPES_ROOT \
  --csv-root $THREE_DVA_CSV_ROOT \
  --json-root $THREE_DVA_JSON_ROOT \
  --sigma-deg 1.0

# Screen-space method (v2)
python3 reprojection_methods/screen_space_gaussian/eval_3dva_screen_space.py \
  --model bunny \
  --dataset-root $VISUAL_ATTENTION_3D_SHAPES_ROOT \
  --csv-root $THREE_DVA_CSV_ROOT \
  --json-root $THREE_DVA_JSON_ROOT \
  --sigma-px 49.0
```

### Full 32-model run

```bash
# Cone method
WORKERS=8 bash test/launch/run_3dva_raycast_cone.sh

# Screen-space method
WORKERS=8 bash test/launch/run_3dva_screen_space.sh
```

---

## Sigma choice for screen-space

| Sigma | Value | Meaning |
|-------|-------|---------|
| v1 (WRONG) | 0.05 × 256 = 12.8 px @ 256px = **96 px @ 1920px** | 3.6× too wide |
| v2 (CORRECT) | **49 px @ 1920px** | ≈ 1° visual angle in 3DVA paper setup |
| SAL3D (different dataset) | 26.3 px @ 1920px | SAL3D paper setup — do NOT use for 3DVA |

The correct value (49 px) comes from:
- Distance to screen: 90 cm
- 30" Eizo monitor: ~3.0 px/mm at 1920px width
- 1° of visual angle: `900 mm × tan(1°) × 3.0 px/mm ≈ 47–49 px`

---

## Object classes (from the paper, Table 3)

| Animals | Humans | Mechanical | Familiar objects |
|---------|--------|------------|-----------------|
| Horse (113K) | Igea (101K) | Casting (5K) | Vase (15K) |
| Dinosaur (42K) | Max-Planck (204K) | Meca (15K) | Car-vasa (17K) |
| Bunny (35K) | Bimba (75K) | Blade (200K) | House (196K) |
| Dragon (50K) | Torso (142K) | Rocker (40K) | Hand (37K) |
| Cow (46K) | James (51K) | Carter (25K) | A380 (173K) |
| Octopus (17K) | Jessi (70K) | Fandisk (6K) | Flowerpot (83K) |
| Gargoyle (150K) | Michael3 (53K) | Turbine (100K) | Chair (11K) |
| Camel (19K) | Michael8 (53K) | Protein (50K) | Harley (276K) |

Numbers are original mesh vertex counts (in thousands). Simplified versions are ~20K each (some models with many tiny parts are higher: A380→48K, Harley→55K, House→56K).

---

## Key findings from the paper (for context)

1. **Shape dominates**: observers look at semantically meaningful parts (faces, eyes, protrusions)
2. **Lighting has significant impact** on static scenes (front vs top-left lighting redirect attention)
3. **Material matters** for static scenes: glossy surfaces attract gaze to specular highlights
4. **Camera movement dominates** in dynamic scenes — overpowers lighting and material effects
5. **Center bias is strong**: observers tend to look near the rendered center of objects
6. **Saliency algorithms perform poorly** vs human inter-observer agreement (CC ~0.47 vs ~0.81)
7. **Schelling points ≠ human fixations**: correlation is weak (AUC 0.5–0.75)
