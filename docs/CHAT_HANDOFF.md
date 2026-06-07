# Handoff: продолжение диалога

> Этот документ создан 2026-06-07 для продолжения работы в новом чате.
> Содержит **всё необходимое** для понимания проекта без доступа к истории.

---

## 1. Что это за проект

Мы строим **воспроизводимый benchmark для методов репроекции взгляда на 3D-меш**.

Задача: у нас есть записи движения глаз участников, смотревших на **видео вращающихся 3D-объектов**. Нужно перевести эти 2D-координаты взгляда на экране в **per-vertex/per-face сaliency-карту на 3D-меше**, а затем сравнить результат с ground truth от авторов датасетов.

Два основных метода репроекции:
1. **cone_gaussian_on_mesh** — ray-cast гейза → попадание в меш → 3D Гауссиан вокруг hit-point
2. **screen_space_gaussian** — 2D density map на экране → проекция вершин меша → сэмплирование плотности

---

## 2. Репозиторий

```
GitHub: https://github.com/Danchik757/Mesh-Saliency-Projection
Branch: reproject-benchmark  (активная, НЕ main)
Last commit: 0fb5e10
```

**Локальный путь:** `/Users/admin/Documents/LAB/SALIENCY_code/#meshes_2.0/GITHUB/Mesh-Saliency-Projection/`

**Python venv с нужными зависимостями:**
```
/Users/admin/Documents/LAB/SALIENCY_code/GAZE_DATA/venv/bin/python3
```

---

## 3. Три датасета

### 3.1 3DVA — "Visual Attention for Rendered 3D Shapes" (Lavoué et al. 2018)

**Локальный путь:** `/Users/admin/Documents/LAB/SALIENCY_code/GAZE_DATA/datasets/3DVA/` (321 MB)

**Что это:** 32 3D-объекта (Animal/Human/Mechanical/Familiar), 19 участников, статичные рендеры.

**Структура GT:**
```
3DModels-Simplif-up/       32 OBJ (~20K вершин каждый, правильная ориентация)
                           ❌ НИКОГДА не использовать 3DModels-Simplif/ (неправильные оси)
FixationMaps/              96 GT-файлов = 32 модели × 3 вида
  bunny_300norm.txt        — 20 000 строк, одно float на вершину
  bunny_413norm.txt        — три вида = три РАЗНЫХ ракурса камеры
  bunny_599norm.txt        — overlap всех трёх: ~1-12% вершин
CentricityAndVisibilityMaps/
  bunny_300_visibility.txt — бинарная маска (0/1) видимых вершин из этого ракурса
  bunny_300_100_*.txt      — centricity maps (не нужны для eval)
CombinedGT/                NEW (создаётся build_3dva_combined_gt.py)
  bunny_combined_gt.txt    — объединённый GT, одно float на вершину
other/SaliencyAlgorithmMaps/  — НЕ GT, предсказания Lee/Leifman/Song/Tasse
```

**Критически важно о GT:**
- `_300norm`, `_413norm`, `_599norm` = три РАЗНЫХ угла обзора, не три типа GT
- Каждый файл = внимание людей к одной стороне модели
- CC между видами: ~0 или отрицательный → полностью независимые измерения
- Авторы проводили **статичный** эксперимент (7 сек/изображение)
- Наши данные — **динамические** (вращающееся видео) → cross-condition mismatch
- Сравнение с нашими данными: всегда `metrics_vs_gt_visible_only` (бумага: multiply by visibility)

**Особые случаи:**
- `turbine`: OBJ=20000 вершин, но GT=19999 строк → использовать длину GT
- `A380`: CSV содержит несколько video_id → нужно `--video-id 2365`

**Наши gaze данные:**
```
csv: /Users/admin/Documents/LAB/SALIENCY_code/GAZE_DATA/csv_for_models/3DVA/  (32 файла)
json: /Users/admin/Documents/LAB/SALIENCY_code/GAZE_DATA/jsons_for_models/3DVA_json/  (32 файла)
```

**Параметры камеры (3DVA):**
- FOV=60° horizontal → override_fov_deg=35.9834 (vertical для 16:9)
- `recenter_to_bbox_center=True`
- `extra_rotate_x_deg=0`
- Transform order: `base_rotZ → recenter → scale → rotZ_anim → extraX → extraY → translate`
- ❌ НЕ использовать `--projection-fov-mode horizontal_to_vertical` (это для MeshMamba/SAL3D)

**Sigma для screen_space на 3DVA:** σ=49px при 1920px (= 1° visual angle, Tobii TX-120, ~90cm, 30" Eizo)

---

### 3.2 MeshMamba — "MeshMamba Saliency"

**Локальный путь:** `/Users/admin/Documents/LAB/SALIENCY_code/GAZE_DATA/datasets/MeshMamba/` (922 MB)

**Что это:** 105 3D-объектов × 2 трека (non_texture + rgb_texture), GT в формате per-face.

**Структура:**
```
MeshFile/non_texture/<model>/<model>.obj   ← 105 OBJ
MeshFile/rgb_texture/<model>/<model>.obj   ← 105 OBJ
SaliencyMap/non_texture/<model>.csv        ← GT (per-face, один float на строку)
SaliencyMap/rgb_texture/<model>.csv        ← GT (per-face)
```

**Параметры камеры (MeshMamba):**
- `recenter_to_bbox_center=True`
- `extra_rotate_x_deg=90`
- `--projection-fov-mode horizontal_to_vertical` (h2v)
- `--transform-order blender_rig`
- **НЕТ** override_fov_deg (JSON содержит корректный lens_mm=31.18mm→60°)

**Sigma для screen_space на MeshMamba:** σ=26.3px при 1920px (= 0.5° visual angle, Saliency3D_clear)

**Наши gaze данные:**
```
csv non_texture: .../csv_for_models/MeshMamba_non_texture/  (105 файлов)
csv rgb_texture: .../csv_for_models/MeshMamba_rgb_texture/  (105 файлов)
json non_texture: .../jsons_for_models/Mamba_non_textured/  (105 файлов)
json rgb_texture: .../jsons_for_models/Mamba_rgb_textured/  (105 файлов)
```

**Особые случаи:**
- `stuffed_animal_v1_L2` в rgb_texture: OBJ содержит несколько sub-мешей → trimesh.load() возвращает Scene, не Trimesh → нужен `process=False` + конкатенация sub-мешей

---

### 3.3 SAL3D — "Saliency3D: A 3D Saliency Dataset Collected on Screen" (Wang et al. 2024)

**Локальный путь:** `/Users/admin/Documents/LAB/SALIENCY_code/GAZE_DATA/datasets/SAL3D/SAL3D_Dataset/` (2.9 GB)

**Что это:** 57 3D-объектов, наши участники смотрели на вращающиеся видео (аналогично нашему setup). **PRIMARY benchmark** — те же условия что и у нас.

**Структура:**
```
Meshes/<model>.obj          57 OBJ (20K-88K вершин)
Gaze/<model>.txt            58 GT файлов (20000×8: xyz, normals, smooth_sal, binary)
Smooth_Gaze/<model>_neighbors.txt   53 файла (KNN для сглаживания GT)
```

**GT формат (Gaze/*.txt):**
- 20 000 строк (GT всегда на 20K вершинах, даже для high-res OBJ)
- Колонки: x,y,z (вершины), nx,ny,nz (нормали), smooth_saliency, binary
- Для high-res OBJ (>20K вершин): GT покрывает только 20K → **ВСЕГДА использовать `metrics_vs_gt_covered_only`**
- 35 моделей: OBJ>20K ("subset"), 23 модели: OBJ=20K ("direct")

**Параметры камеры (SAL3D):**
- `recenter_to_bbox_center=True`
- `extra_rotate_x_deg=90`
- `--projection-fov-mode horizontal_to_vertical` (h2v)
- `--transform-order blender_rig`
- SAL3D JSONs **не содержат** view_matrix → скрипт сам строит через rotation_euler

**Sigma для screen_space на SAL3D:** σ=26.3px при 1920px (= 0.5° visual angle)

**Наши gaze данные:**
```
csv: .../csv_for_models/SAL3D/  (56 файлов — 4 модели без CSV: AudiRS5, bimba, blade, gorgoile)
json: .../jsons_for_models/SAL3D_json/  (57 файлов, формат Sal3D_<model>.json)
```

---

## 4. Скрипты и их назначение

### 4.1 Eval-скрипты (один модель за раз)

| Скрипт | Датасет | Метод | GT | Заметки |
|--------|---------|-------|-----|---------|
| `reprojection_methods/cone_projection_on_mesh/eval_3dva_raycast_cone.py` | 3DVA | raycast + cone | per-view (300/413/599) | metrics_vs_gt_full + visible_only |
| `reprojection_methods/screen_space_gaussian/eval_3dva_screen_space.py` | 3DVA | screen_space v2 | per-view (300/413/599) | sigma=49px, 1920px, bilinear |
| `reprojection_methods/cone_projection_on_mesh/eval_3dva_cone_combined.py` | 3DVA | raycast + cone | **combined GT** | NEW. metrics_covered_only |
| `reprojection_methods/screen_space_gaussian/eval_3dva_screen_space_combined.py` | 3DVA | screen_space v2 | **combined GT** | NEW. sigma=49px |
| `reprojection_methods/cone_projection_on_mesh/eval_meshmamba_cone.py` | MeshMamba | raycast + cone | per-face GT | h2v + blender_rig |
| `reprojection_methods/screen_space_gaussian/eval_meshmamba_screen_space_v2.py` | MeshMamba | screen_space v2 | per-face GT | sigma=26.3px, 1920px |
| `reprojection_methods/cone_projection_on_mesh/eval_sal3d_cone.py` | SAL3D | raycast + cone | per-vertex GT | metrics_covered_only, smooth GT |
| `reprojection_methods/screen_space_gaussian/eval_sal3d_screen_space.py` | SAL3D | screen_space v2 | per-vertex GT | sigma=26.3px, metrics_covered_only |
| `reprojection_methods/cone_projection_on_mesh/eval_meshmamba_geodesic.py` | MeshMamba | geodesic diffusion | per-face GT | после cone → Laplacian diffusion |
| `reprojection_methods/cone_projection_on_mesh/eval_sal3d_geodesic.py` | SAL3D | geodesic diffusion | per-vertex GT | то же |

### 4.2 Батч-раннеры (все модели сразу)

| Скрипт | Назначение |
|--------|-----------|
| `test/launch/run_meshmamba_reference_batch.py` | MeshMamba all-105, screen_space+cone, both tracks |
| `test/launch/run_sal3d_reference_batch.py` | SAL3D all-50, screen_space+cone |
| `test/launch/run_3dva_reference_batch.py` | **NEW.** 3DVA all-32, combined GT, screen_space+cone+raycast |

### 4.3 Вспомогательные

| Скрипт | Назначение |
|--------|-----------|
| `scripts/build_3dva_combined_gt.py` | **NEW.** Строит combined GT для 3DVA (запустить ПЕРЕД run_3dva_reference_batch.py) |
| `test/launch/run_3dva_screen_space.sh` | 3DVA screen_space v2 vs per-view GT (sigma=49px) |
| `test/launch/run_3dva_raycast_cone.sh` | 3DVA cone vs per-view GT |

---

## 5. Где лежат результаты

```
results/benchmark_runs/
  meshmamba/
    2026-06-01_non_texture_cone/         105 моделей, cone, non_texture ✅
    2026-06-01_non_texture_screen_space/  105 моделей, screen_space v1(!), non_texture ✅
    2026-06-01_rgb_texture_cone/          104 модели, cone, rgb_texture ✅
    2026-06-01_rgb_texture_screen_space/  104 модели, screen_space v1(!), rgb_texture ✅
    2026-06-02_meshmamba_reference/       (дополнительный прогон)
  sal3d/                   пусто (полный прогон ещё не выполнен)
  kld_diagnostic/          диагностические прогоны
```

**Важно о MeshMamba screen_space результатах:** результаты в `2026-06-01_*_screen_space/` — это v1 (sigma=0.05×256=96px, слишком широкое). v2 запускался только на Rubber_Duck (CC+0.117 по сравнению с v1). Нужен полный прогон v2.

---

## 6. Итоговые метрики (что уже известно)

### MeshMamba (105/104 моделей, полный прогон, `metrics_vs_gt`)

| Трек | Метод | CC mean | CC excl.<0 | CC<0 count |
|------|-------|---------|-----------|-----------|
| non_texture | screen_space v1 | 0.136 | 0.218 | 26 |
| non_texture | cone | **0.321** | 0.372 | 11 |
| rgb_texture | screen_space v1 | 0.130 | 0.219 | 29 |
| rgb_texture | cone | **0.274** | 0.343 | 15 |

### SAL3D (3 пилотных модели, `metrics_vs_gt_covered_only`, smoothed GT)

| Модель | gt_match | coverage | cone CC | screen_space CC |
|--------|---------|---------|---------|----------------|
| bunny | direct | 100% | 0.769 | 0.706 |
| lion | subset | 37% | 0.469 | 0.295 |
| A380 | subset | 42% | 0.438 | −0.015 (ожидаемо) |

### 3DVA combined GT (1 модель, `metrics_vs_gt_combined.metrics_covered_only`)

| Модель | coverage | cone CC | screen_space CC |
|--------|---------|---------|----------------|
| bunny | 79.3% | 0.031 | −0.046 |

*Низкие CC ожидаемы — cross-condition (наши: видео, GT авторов: статика)*

---

## 7. Ключевые правила и баги (критично не нарушать)

### Правила по GT

| Датасет | Секция для таблиц | Обоснование |
|---------|------------------|-------------|
| SAL3D | `metrics_vs_gt_covered_only` | 35 моделей: GT только на 20K, OBJ больше |
| 3DVA per-view | `metrics_vs_gt_visible_only` | бумага: multiply by visibility field |
| 3DVA combined | `metrics_covered_only` | combined_gt > 0 = GT-observed region |
| MeshMamba | `metrics_vs_gt` (напрямую) | GT покрывает все faces |

### Исправленные баги (не повторять!)

| Баг | Сессия | Правило |
|-----|--------|---------|
| Recenter order | 3 | `bbox_center` вычислять из ОРИГИНАЛЬНЫХ вершин ДО base_rotate_z |
| FOV для 3DVA | 9 | `--override-fov-deg 35.9834`, НЕ `--projection-fov-mode` |
| sigma screen_space 3DVA | 17 | σ=49px (не 26.3 = SAL3D, не 96 = v1 баг) |
| sigma screen_space MeshMamba/SAL3D | 13 | σ=26.3px, resolution=1920px, bilinear |
| Back-face filter screen_space | 9 | `screen_xy[w_clip <= 0] = -1.0` |
| Transform order 3DVA | 3 | `base_rotZ → recenter → scale → rotZ_anim → extraX → extraY → translate` |
| Transform order MeshMamba/SAL3D | 9 | `blender_rig` |
| FOV convention MeshMamba/SAL3D | 9 | `horizontal_to_vertical` (60°horiz → 35.98°vert) |
| Laplacian на raw OBJ | 16 | Применять scale из JSON перед Laplacian |
| turbine vertex mismatch | 17 | OBJ=20000, GT=19999 → использовать GT длину |
| A380 video_id | все | Всегда `--video-id 2365` для A380 в 3DVA |
| 3DModels-Simplif vs Simplif-up | 5 | ВСЕГДА использовать `3DModels-Simplif-up/` |

---

## 8. Pending задачи (что ещё не сделано)

### Высокий приоритет

1. **SAL3D полный прогон** (50 моделей × 2 метода)
   - Скрипт готов: `test/launch/run_sal3d_reference_batch.py`
   - Нужно: перенести Smooth_Gaze на сервер, запустить, скачать результаты
   - Инструкция: в `trash/Claude.md` (раздел "GPT INSTRUCTION: Run SAL3D reference benchmark")

2. **MeshMamba screen_space v2 полный прогон** (105 моделей)
   - v1 прогон уже есть, но sigma неправильная (96px)
   - Скрипт готов: `reprojection_methods/screen_space_gaussian/eval_meshmamba_screen_space_v2.py`
   - Батч-раннер поддерживает: `run_meshmamba_reference_batch.py`

3. **3DVA combined GT полный прогон** (32 модели)
   - Скрипт готов: `test/launch/run_3dva_reference_batch.py`
   - Сначала: `python3 scripts/build_3dva_combined_gt.py --dataset-root $VISUAL_ATTENTION_3D_SHAPES_ROOT --output-dir $VISUAL_ATTENTION_3D_SHAPES_ROOT/CombinedGT`
   - Затем: `python3 test/launch/run_3dva_reference_batch.py ...`
   - Полная инструкция: `docs/3DVA_COMBINED_GT_IMPLEMENTATION.md`

### Средний приоритет

4. **stuffed_animal_v1_L2** (MeshMamba rgb_texture): multi-mesh OBJ, нужен `process=False` + конкатенация

5. **Geodesic diffusion полный батч**: `eval_meshmamba_geodesic.py` и `eval_sal3d_geodesic.py` написаны, батч-раннеры не созданы

6. **3DVA vs SaliencyAlgorithmMaps**: сравнить наши методы с Lee/Leifman/Song/Tasse на том же averaged GT

### Открытые вопросы для GPT

- Должен ли v2 screen_space заменить v1 в основной таблице результатов MeshMamba?
- Включать ли 3DVA combined GT результаты в главную таблицу или как отдельный appendix?
- Добавить ли geodesic как метод в существующие batch runners?
- sigma_visual_deg=1.0 и vertex_angle_deg=0.1 для geodesic — нужна ли калибровка?

---

## 9. Быстрый старт для нового чата

### Переменные окружения

```bash
export VISUAL_ATTENTION_3D_SHAPES_ROOT="/Users/admin/Documents/LAB/SALIENCY_code/GAZE_DATA/datasets/3DVA"
export THREE_DVA_CSV_ROOT="/Users/admin/Documents/LAB/SALIENCY_code/GAZE_DATA/csv_for_models/3DVA"
export THREE_DVA_JSON_ROOT="/Users/admin/Documents/LAB/SALIENCY_code/GAZE_DATA/jsons_for_models/3DVA_json"
export THREE_DVA_COMBINED_GT_DIR="$VISUAL_ATTENTION_3D_SHAPES_ROOT/CombinedGT"

export REPROJECT_DATASET_MESHMAMBA_ROOT="/Users/admin/Documents/LAB/SALIENCY_code/GAZE_DATA/datasets/MeshMamba"
export REPROJECT_GAZE_CSV_MESHMAMBA_NON_TEXTURE_ROOT="/Users/admin/Documents/LAB/SALIENCY_code/GAZE_DATA/csv_for_models/MeshMamba_non_texture"
export REPROJECT_GAZE_JSON_MESHMAMBA_NON_TEXTURE_ROOT="/Users/admin/Documents/LAB/SALIENCY_code/GAZE_DATA/jsons_for_models/Mamba_non_textured"

export REPROJECT_DATASET_SAL3D_ROOT="/Users/admin/Documents/LAB/SALIENCY_code/GAZE_DATA/datasets/SAL3D/SAL3D_Dataset"
export SAL3D_CSV_ROOT="/Users/admin/Documents/LAB/SALIENCY_code/GAZE_DATA/csv_for_models/SAL3D"
export SAL3D_JSON_ROOT="/Users/admin/Documents/LAB/SALIENCY_code/GAZE_DATA/jsons_for_models/SAL3D_json"
```

### Python (с нужными зависимостями)

```bash
PYTHON="/Users/admin/Documents/LAB/SALIENCY_code/GAZE_DATA/venv/bin/python3"
REPO="/Users/admin/Documents/LAB/SALIENCY_code/#meshes_2.0/GITHUB/Mesh-Saliency-Projection"
```

### Тест одной модели (bunny, 3DVA cone combined)

```bash
# Шаг 1: убедиться, что combined GT построен
ls "$VISUAL_ATTENTION_3D_SHAPES_ROOT/CombinedGT/bunny_combined_gt.txt" || \
  "$PYTHON" "$REPO/scripts/build_3dva_combined_gt.py" \
    --dataset-root "$VISUAL_ATTENTION_3D_SHAPES_ROOT" \
    --output-dir "$VISUAL_ATTENTION_3D_SHAPES_ROOT/CombinedGT" \
    --models bunny

# Шаг 2: запуск eval
"$PYTHON" "$REPO/reprojection_methods/cone_projection_on_mesh/eval_3dva_cone_combined.py" \
  --model bunny \
  --dataset-root "$VISUAL_ATTENTION_3D_SHAPES_ROOT" \
  --csv-root "$THREE_DVA_CSV_ROOT" \
  --json-root "$THREE_DVA_JSON_ROOT" \
  --combined-gt-dir "$THREE_DVA_COMBINED_GT_DIR" \
  --output-dir /tmp/test_3dva
```

---

## 10. Архитектурные файлы для изучения

| Файл | Что содержит |
|------|-------------|
| `trash/Claude.md` | **История всех сессий** (сессии 1-18). НЕПРИКОСНОВЕНЕН — только дополнять снизу |
| `trash/GPT.md` | **История GPT-агента**. Тоже неприкосновенен |
| `datasets/README.md` | Описание всех 3 датасетов, форматы, размеры, IoU |
| `datasets/3DVA_DATASET.md` | Детальное описание 3DVA: GT формат, 3 вида, visibility, sigma |
| `docs/3DVA_COMBINED_GT_IMPLEMENTATION.md` | Инструкция для запуска 3DVA combined GT pipeline |
| `docs/EVAL_RUNBOOK.md` | Правильные команды для запуска eval на всех датасетах |
| `test/README.md` | Alignment validation, IoU tables, manifests |
| `configs/server_vg_intellect.env` | Переменные окружения для сервера vg-intellect |

---

## 11. Сервер vg-intellect

```
SSH: vg-intellect
Host: lab.graphicon.ru (точный адрес в ~/.ssh/config)
User: 29d_kon@lab.graphicon.ru
Repo path: /home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/Mesh-Saliency-Projection
Datasets: /home/29d_kon@lab.graphicon.ru/ssd1_link/datasets/{3DVA,MeshMambaSaliency,SAL3D}
Python env: conda activate reproject-benchmark
Запуск в: tmux
```

**Деплой кода:** только через `git push` на локальной машине → `git pull` на сервере.

**Переменные на сервере:** `source configs/server_vg_intellect.env`

Нужны алиасы перед запуском батч-раннеров:
```bash
export VISUAL_ATTENTION_3D_SHAPES_ROOT="$REPROJECT_DATASET_3DVA_ROOT"
export THREE_DVA_CSV_ROOT="$REPROJECT_GAZE_CSV_3DVA_ROOT"
export THREE_DVA_JSON_ROOT="$REPROJECT_GAZE_JSON_3DVA_ROOT"
```

---

## 12. GitHub Release с датасетами

Датасеты доступны для скачивания через GitHub Releases:
```
https://github.com/Danchik757/Mesh-Saliency-Projection/releases/tag/v1.0-data
```

Скрипт для скачивания на новой машине:
```bash
bash scripts/download_datasets.sh --data-root /path/to/data
```

---

## 13. Что изучить перед продолжением (приоритет)

1. Прочитать `trash/Claude.md` — полная история всех сессий, там всё
2. Посмотреть `docs/3DVA_COMBINED_GT_IMPLEMENTATION.md` — если нужно запустить 3DVA benchmark
3. Посмотреть раздел "GPT INSTRUCTION: Run SAL3D..." в `trash/Claude.md` — если нужно запустить SAL3D
4. Проверить `results/benchmark_runs/` — что уже есть
