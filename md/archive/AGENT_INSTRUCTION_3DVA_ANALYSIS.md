# Инструкция для агента: анализ результатов 3DVA

> Самодостаточный документ. Никакого предыдущего контекста не требуется.
> Созданный: 2026-06-07. Репозиторий: `reproject-benchmark`, коммит `2d79c1f`.

---

## Контекст проекта (1 абзац)

Мы строим benchmark для методов репроекции 2D-взгляда на 3D-меш. Участники
смотрели на видео вращающихся 3D-объектов; их gaze-координаты на экране (x,y,t)
нужно превратить в per-vertex saliency-карту на меше. Есть два метода:
**cone_gaussian** (ray-cast → 3D Gaussian) и **screen_space_gaussian** (2D density
map → проекция вершин → сэмплирование). Результаты сравниваются с авторским GT.

---

## Что нужно выяснить (4 вопроса)

1. **Где лежат новые GT и что они из себя представляют?**
2. **Какие сейчас значения метрик для двух методов?**
3. **Почему значения корреляции такие низкие?**
4. MeshMamba — **не трогать** (метод уже прогонялся ранее, результаты в репо).

---

## 1. Новые GT: Combined GT для 3DVA

### Откуда берётся

Датасет 3DVA (Lavoué et al. 2018) содержит **три независимых GT-файла** на каждую
из 32 моделей — по одному на каждый из 3 статичных ракурсов камеры авторов:

```
$VISUAL_ATTENTION_3D_SHAPES_ROOT/FixationMaps/
  bunny_300norm.txt   — 20 000 строк, float/вершина, ракурс "300"
  bunny_413norm.txt   — тот же меш, другая сторона (ракурс "413")
  bunny_599norm.txt   — третья сторона (ракурс "599")
```

- **Что означает "300", "413", "599":** это не расстояния и не типы — это три
  разных положения камеры в 3D Studio Max, выбранных вручную чтобы покрыть
  разные стороны модели.
- **Overlap всех трёх видов:** 1–12% вершин. Три файла = три независимых
  измерения трёх сторон объекта.
- **GT-значение:** floating-point плотность фиксаций, накопленная с 19 участников
  за 7 секунд просмотра статичного рендера.

### Почему создан combined GT

Наши данные — из **вращающегося видео** (17 сек, ~374° поворот). Авторский GT —
из **статичных изображений** с 3 фиксированных углов. Прямое сравнение = cross-
condition mismatch. Объединение трёх видов даёт "multi-view GT", который ближе
к нашей ротационной карте: оба интегрируют внимание по нескольким ракурсам.

### Формула объединения (per_view_l1)

Для каждой модели:
```python
for view in ('300', '413', '599'):
    gt  = load("FixationMaps/{model}_{view}norm.txt")       # (N,)
    vis = load("CentricityAndVisibilityMaps/{model}_{view}_visibility.txt").astype(bool)
    visible_sum = gt[vis].sum()
    gt_norm = gt / visible_sum if visible_sum > 0 else gt   # normalize to sum=1
    combined_num += gt_norm * vis                           # weight by visibility
    combined_den += vis.astype(float)

gt_combined = where(combined_den > 0, combined_num / combined_den, 0.0)
```

**Эффект:** каждый вид вносит равный суммарный "вес внимания" независимо от
числа видимых вершин.

### Где лежит

```
$VISUAL_ATTENTION_3D_SHAPES_ROOT/CombinedGT/
  bunny_combined_gt.txt         20 000 строк, coverage=79.3%
  bunny_combined_gt_meta.json   статистика (суммы по видам, coverage, etc.)
  A380_combined_gt.txt          47 756 строк, coverage=42.3%
  turbine_combined_gt.txt       19 999 строк (turbine: OBJ=20000, GT=19999 — known mismatch)
  ...
  build_summary.json            все 32 модели
```

Локальный путь: `/Users/admin/Documents/LAB/SALIENCY_code/GAZE_DATA/datasets/3DVA/CombinedGT/`

**Скрипт для генерации:**
```bash
PYTHON="/Users/admin/Documents/LAB/SALIENCY_code/GAZE_DATA/venv/bin/python3"
REPO="/Users/admin/Documents/LAB/SALIENCY_code/#meshes_2.0/GITHUB/Mesh-Saliency-Projection"

"$PYTHON" "$REPO/scripts/build_3dva_combined_gt.py" \
  --dataset-root /Users/admin/Documents/LAB/SALIENCY_code/GAZE_DATA/datasets/3DVA \
  --output-dir   /Users/admin/Documents/LAB/SALIENCY_code/GAZE_DATA/datasets/3DVA/CombinedGT
```

**Что хранится в meta JSON:**
```json
{
  "model": "bunny",
  "n_verts": 20000,
  "normalization": "per_view_l1",
  "views_used": ["300","413","599"],
  "gt_sum_per_view": {"300": 9775.8, "413": 10559.0, "599": 7347.7},
  "n_visible_per_view": {"300": 8633, "413": 6800, "599": 7605},
  "n_combined_nonzero": 15856,
  "combined_coverage_pct": 79.28
}
```

---

## 2. Текущие значения метрик (на момент создания этого документа)

### Единственная протестированная модель: bunny

**Методы, которые уже запускались:**

| Метод | Скрипт | Результаты |
|-------|--------|-----------|
| cone_gaussian_on_mesh | `eval_3dva_cone_combined.py` | см. ниже |
| screen_space_gaussian v2 | `eval_3dva_screen_space_combined.py` | см. ниже (с фиксом back-face) |

**Метрики (из `metrics_vs_gt_combined.{method}.metrics_covered_only`):**

> ⚠️ Всегда использовать `metrics_covered_only`, не `metrics_full`.
> Combined GT покрывает 79% вершин. Оставшиеся 21% — невидимы ни с одного из
> трёх авторских ракурсов. Метрика по всем вершинам (`metrics_full`) завышает
> CC из-за двойных нулей (GT=0 и pred≈0 на "никогда невидимых" вершинах).

**bunny, combined GT, `metrics_covered_only` (n=15,856 вершин):**

| Метрика | cone_gaussian | screen_space |
|---------|--------------|-------------|
| CC | 0.031 | 0.023 |
| SIM | 0.559 | 0.523 |
| KLD | 0.577 | 0.940 |
| Spearman | 0.035 | 0.006 |
| AUC_top10% | 0.439 | 0.452 |
| NSS_top10% | −0.181 | −0.230 |
| hit_rate | 0.808 | N/A |

> NB: screen_space метрики — **после исправления back-face bug** (коммит 2d79c1f).
> До исправления: CC=−0.046 (screen_space), CC=0.031 (cone). Фикс: +0.069 CC.

**Сравнение full vs covered (почему full выше для cone):**

| Секция | cone CC | screen_space CC |
|--------|---------|----------------|
| metrics_full (20,000 вершин) | 0.110 | 0.104 |
| metrics_covered_only (15,856) | 0.031 | 0.023 |

`metrics_full` выше потому что 4,144 "никогда невидимых" вершин имеют GT=0
И prediction≈0 (cone не может попасть в невидимую вершину, screen_space после
фикса тоже не проецирует туда). Эти двойные нули искусственно повышают CC.

**Статистика по 4 построенным моделям (из build_summary.json):**

| Модель | Вершин | Coverage |
|--------|--------|---------|
| bunny | 20,000 | 79.3% |
| A380 | 47,756 | 42.3% |
| meca-15k | 15,000 | 88.8% |
| turbine | 19,999 | 50.2% |

*Полный прогон (все 32 модели) ещё не запускался.*

---

## 3. Почему CC такой низкий?

### Главная причина: cross-condition mismatch

**Наши данные (динамические):**
- Участники смотрят на вращающееся видео 17 секунд
- Объект успевает повернуться ~374° (≈1.04 полных оборота)
- Gaze накапливается по всем углам обзора → per-vertex карта = "интеграл по 360°"

**GT авторов (статичные):**
- 19 участников смотрят на статичное изображение 7 секунд с ОДНОГО угла
- Три GT-файла = три РАЗНЫХ статичных эксперимента с разных сторон
- Combined GT = средневзвешенное трёх экспериментов

**Что говорит сама бумага (Section 4.5, Section 5.2.1):**
> "fixations resulting from a dynamic scene are significantly different from
> those resulting from a static scene" (p < 0.0001)
>
> "Another problem of dynamic scenes is that their fixations are really hard to
> predict... as they are not directly related to 3D geometry, but rather to the
> changes in shadowing/reflection that occur during the camera movements."

Авторы **сами** отказались от динамического GT именно по этой причине.

### Дополнительные факторы снижающие CC

1. **Center bias.** В статичных экспериментах люди смотрят ближе к центру
   изображения. В нашем вращающемся видео объект постоянно движется → center
   bias распределяется по-другому.

2. **Material/lighting effect.** Авторы использовали intermediate Phong material
   + top-left lighting. Наш рендер может отличаться. Бумага показывает, что
   материал и освещение значимо влияют на GT (p < 0.0001 для многих условий).

3. **Small n_pilots.** Мы проверили только 1 модель (bunny). Для одной модели CC
   очень нестабилен. Нужен прогон всех 32 моделей.

4. **CC как метрика.** CC = Pearson correlation, линейная. Для скудных,
   непохожих распределений (наша per-vertex карта из ротации vs статичный GT)
   CC будет низким даже если rank-correlation (Spearman) выше.

### Что является "нормальным" CC на этих данных

Для **геометрических** методов (Lee, Leifman, Song, Tasse) в том же датасете:
- Лучший результат: Song, CC ≈ 0.47 (на per-view GT, с blurring + center bias)
- Human upper bound: CC ≈ 0.81 (10 vs 10 split)

Но важно: те сравнения идут на per-view GT, не combined. И методы оптимизируют
blurring и center bias отдельно для каждого вида и модели.

**Для нас корректное сравнение:** методы с похожими условиями (gaze-based,
без per-view оптимизации). По нашим combined GT метрикам CC≈0.03 для 1 модели —
это пока ни о чём не говорит, нужен полный прогон.

---

## 4. Как запустить полный прогон (задача для агента)

### Шаг 1: Проверить/построить combined GT для всех 32 моделей

```bash
PYTHON="/Users/admin/Documents/LAB/SALIENCY_code/GAZE_DATA/venv/bin/python3"
REPO="/Users/admin/Documents/LAB/SALIENCY_code/#meshes_2.0/GITHUB/Mesh-Saliency-Projection"
DATA3DVA="/Users/admin/Documents/LAB/SALIENCY_code/GAZE_DATA/datasets/3DVA"

# Проверить что уже есть
ls "$DATA3DVA/CombinedGT/" | grep combined_gt.txt | wc -l
# Ожидаем: 32 (или меньше, если не все построены)

# Если нужно достроить:
"$PYTHON" "$REPO/scripts/build_3dva_combined_gt.py" \
  --dataset-root "$DATA3DVA" \
  --output-dir   "$DATA3DVA/CombinedGT"
# Ожидаем: "32 ok  0 failed"
```

### Шаг 2: Запустить batch runner (все 32 модели, оба метода)

```bash
export VISUAL_ATTENTION_3D_SHAPES_ROOT="$DATA3DVA"
export THREE_DVA_CSV_ROOT="/Users/admin/Documents/LAB/SALIENCY_code/GAZE_DATA/csv_for_models/3DVA"
export THREE_DVA_JSON_ROOT="$REPO/jsons/object_placement/3dva_jsons"
export THREE_DVA_COMBINED_GT_DIR="$DATA3DVA/CombinedGT"

"$PYTHON" "$REPO/test/launch/run_3dva_reference_batch.py" \
  --methods screen_space cone \
  --workers 4 \
  --dataset-root    "$VISUAL_ATTENTION_3D_SHAPES_ROOT" \
  --csv-root        "$THREE_DVA_CSV_ROOT" \
  --json-root       "$THREE_DVA_JSON_ROOT" \
  --combined-gt-dir "$THREE_DVA_COMBINED_GT_DIR" \
  --batch-output-dir "$REPO/results/benchmark_runs/3dva_combined/$(date +%Y-%m-%d)_3dva_combined"
```

**Ожидаемые выходные файлы:**
```
results/benchmark_runs/3dva_combined/2026-06-07_3dva_combined/
  3dva_combined_long.csv       — одна строка на (модель × метод)
  3dva_combined_wide.csv       — одна строка на модель, методы рядом
  3dva_combined_summary.csv    — mean/median по методу
  baseline_screen_space/
    bunny/sigpx49p0_recenter_fovh2v_combined/bunny_report.json
    ...
  baseline_cone/
    bunny/recenter_fovh2v_combined/bunny_report.json
    ...
```

**Время: ~2–4 часа** (32 × 2 методa × ~4 мин/модель для cone + ~3 мин для ss).

### Шаг 3: Проанализировать результаты

```python
import csv, statistics

long_csv = "results/benchmark_runs/3dva_combined/ДАТА/3dva_combined_long.csv"

with open(long_csv) as f:
    rows = list(csv.DictReader(f))

# По методу
for method in ("screen_space", "cone", "raycast"):
    ok = [r for r in rows if r["method"] == method and r["status"] == "ok"]
    ccs = [float(r["CC"]) for r in ok if r["CC"]]
    print(f"{method}: n_ok={len(ok)}  CC_mean={statistics.mean(ccs):.4f}  CC_median={statistics.median(ccs):.4f}")
```

**Ключевые вопросы для анализа:**
- Какой CC_mean у cone vs screen_space по всем 32 моделям?
- Есть ли модели с CC > 0.1? Какие именно?
- Совпадает ли паттерн с MeshMamba (cone стабильно > screen_space)?

---

## 5. Дополнительный контекст

### Что уже работает (не трогать)

- **MeshMamba full run** (105 моделей × 2 трека × 2 метода): результаты в
  `results/benchmark_runs/meshmamba/2026-06-01_*/`. Нотируется: screen_space там
  v1 (sigma=96px, устаревший). Но трогать не надо.

- **SAL3D pipeline**: eval scripts написаны и проверены, полный прогон ещё не
  запускался (нужен сервер + Smooth_Gaze файлы).

### Критические правила для 3DVA (нарушить = неправильные результаты)

| Правило | Значение |
|---------|---------|
| OBJ: `3DModels-Simplif-up/` | ❌ Никогда `3DModels-Simplif/` (неправильные оси) |
| FOV: `--projection-fov-mode horizontal_to_vertical` | Для диагностики допустим эквивалент `--override-fov-deg 35.9834 --projection-fov-mode vertical` |
| sigma: 49px | ❌ Не 26.3px (SAL3D) и не 96px (старый баг) |
| Метрики: `metrics_covered_only` | ❌ Не `metrics_full` для итоговых таблиц |
| A380: `--video-id 2365` | Без этого данные участников перемешаются |
| Back-face culling: ЕСТЬ в v2 | Исправлено в коммите 2d79c1f |

### Файлы для изучения

| Файл | Зачем |
|------|-------|
| `trash/Claude.md` | Полная история сессий 1–19 (неприкосновенен) |
| `docs/3DVA_COMBINED_GT_IMPLEMENTATION.md` | Полное описание GT и batch runner |
| `docs/README.md` | Точка входа в актуальную документацию проекта |
| `datasets/3DVA_DATASET.md` | Подробное описание 3DVA: структура, GT, paper |

### Вопрос к GPT (если нужна консультация)

После получения full-run результатов (32 модели) можно спросить GPT:
- Стоит ли включать 3DVA combined GT в основную таблицу benchmark вместе с
  MeshMamba и SAL3D, или держать отдельно как "cross-condition reference"?
- Нужно ли добавить сравнение наших методов с Lee/Leifman/Song/Tasse на том же
  combined GT?
