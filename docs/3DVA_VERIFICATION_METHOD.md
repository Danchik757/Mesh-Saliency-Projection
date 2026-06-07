# 3DVA Verification Method

## Scope

Этот документ фиксирует, **как именно у нас проверялся 3DVA-пайплайн**, какие файлы использовались, какая sigma применялась, как считались карты, с чем они сравнивались и где проходит граница применимости этого benchmark.

Важно:

- `3DVA` у нас использовался прежде всего как **benchmark с готовым GT**, а не как полностью воспроизведённый author-pipeline построения GT из скрытых eye-tracker логов.
- Основной проверяемый метод у нас: **`screen_space_gaussian v2`**.
- Второй метод: **`raycast + cone on mesh`**. Он полезен как альтернативная репроекция, но не является нашим основным validated path.


## Файлы, которые использовались

### Основной evaluator

- `/Users/admin/Documents/LAB/SALIENCY_code/#meshes_2.0/GITHUB/Mesh-Saliency-Projection/reprojection_methods/screen_space_gaussian/eval_3dva_screen_space.py`

### Альтернативный evaluator

- `/Users/admin/Documents/LAB/SALIENCY_code/#meshes_2.0/GITHUB/Mesh-Saliency-Projection/reprojection_methods/cone_projection_on_mesh/eval_3dva_raycast_cone.py`

### Служебные файлы и локальные результаты

- `/Users/admin/Documents/LAB/SALIENCY_code/GAZE_DATA/outputs/3DVA_eval/multi_model_recenter_fov37p5_summary.json`
- `/Users/admin/Documents/LAB/SALIENCY_code/GAZE_DATA/outputs/3DVA/comparison_with_gt.json`
- `/Users/admin/Documents/LAB/SALIENCY_code/GAZE_DATA/outputs/3DVA_eval/bunny/`
- `/Users/admin/Documents/LAB/SALIENCY_code/GAZE_DATA/outputs/3DVA_eval/car-vasa/`
- `/Users/admin/Documents/LAB/SALIENCY_code/GAZE_DATA/outputs/3DVA_eval/chair107/`
- `/Users/admin/Documents/LAB/SALIENCY_code/GAZE_DATA/outputs/3DVA_eval/dragon/`
- `/Users/admin/Documents/LAB/SALIENCY_code/GAZE_DATA/outputs/3DVA_eval/flowerpot/`


## Какие данные подавались на вход

### 1. GT и mesh из локального 3DVA dataset

- Dataset root:
  `/Users/admin/Documents/LAB/SALIENCY_code/GAZE_DATA/datasets/3DVA`
- Mesh:
  `/Users/admin/Documents/LAB/SALIENCY_code/GAZE_DATA/datasets/3DVA/3DModels-Simplif-up`
- GT:
  `/Users/admin/Documents/LAB/SALIENCY_code/GAZE_DATA/datasets/3DVA/FixationMaps`
- Visibility:
  `/Users/admin/Documents/LAB/SALIENCY_code/GAZE_DATA/datasets/3DVA/CentricityAndVisibilityMaps`

### 2. Raw gaze и camera/animation

В компактном локальном `3DVA` raw gaze нет. Он подавался отдельно:

- gaze CSV:
  `/Users/admin/Documents/LAB/SALIENCY_code/GAZE_DATA/csv_for_models/3DVA`
- camera / animation JSON:
  `/Users/admin/Documents/LAB/SALIENCY_code/GAZE_DATA/jsons_for_models/3DVA_json`

То есть проверка строилась так:

`raw gaze CSV + camera JSON + OBJ + published 3DVA GT`


## Что такое 3DVA GT

`3DVA` хранит **view-dependent per-vertex GT**.

Для каждой модели есть три GT-карты:

- `*_300norm.txt`
- `*_413norm.txt`
- `*_599norm.txt`

Это три разные saliency maps для трёх фиксированных ракурсов.

Также для этих view есть visibility masks:

- `*_300_visibility.txt`
- `*_413_visibility.txt`
- `*_599_visibility.txt`

Следствие:

- `3DVA GT` не является “одной общей GT-картой на весь объект”.
- Это **три статических view-conditioned benchmark target**.


## Основной метод: screen_space_gaussian v2

### Где лежит код

- `/Users/admin/Documents/LAB/SALIENCY_code/#meshes_2.0/GITHUB/Mesh-Saliency-Projection/reprojection_methods/screen_space_gaussian/eval_3dva_screen_space.py`

### Что делает метод

Идея метода:

1. взять raw gaze на экране;
2. построить 2D density map в screen-space;
3. размыть её Gaussian;
4. спроецировать mesh в экран для каждого кадра;
5. взять значение density map в экранной позиции каждой вершины;
6. накопить per-vertex saliency map;
7. сравнить её с published 3DVA GT.

### Почему именно этот метод считался основным

Потому что он:

- напрямую использует published screen-space scale;
- работает в тех же единицах, где изначально измерялась gaze uncertainty;
- использует corrected full-resolution density image;
- явно сравнивается с `FixationMaps` и `visibility` из 3DVA.

### Алгоритм по шагам

#### Шаг 1. Чтение gaze из CSV

CSV содержит `data_gazes`, где лежат траектории:

- `t`
- `x`
- `y`

В коде:

- берутся только точки, у которых `0 <= x <= 1` и `0 <= y <= 1`;
- точки группируются по кадрам:

```text
frame = floor(t * fps)
```

`fps` берётся из JSON.

#### Шаг 2. Построение 2D density image

Для каждого кадра строится density image размера:

```text
1920 x 1080
```

Это важный момент. Исправленный evaluator работает именно на полном разрешении, а не на уменьшенной картинке.

Gaze points кладутся в эту карту через **bilinear deposition**:

```text
H_t(x, y) = histogram of frame-t gaze points
```

#### Шаг 3. Gaussian blur

Потом применяется Gaussian blur:

```text
D_t(x, y) = Gaussian(H_t, sigma_px)
```

После blur карта нормализуется по сумме.

#### Шаг 4. Трансформация mesh

Для того же кадра вершины mesh:

- recenterятся по bbox, если флаг включён;
- масштабируются;
- вращаются по `rotation_z_radians` из JSON;
- затем могут получить extra runtime rotations;
- потом переносятся в world position.

То есть mesh не статичен, а трансформируется по animation/camera data из JSON.

#### Шаг 5. Проекция mesh в экран

Вершины проецируются через:

- `view_matrix`
- `projection_matrix`

из JSON камеры.

Получаем экранные координаты каждой вершины:

```text
u_t(v) = project_t(v)
```

#### Шаг 6. Семплирование density image в вершинах

Для каждой вершины берётся значение density map в её экранной позиции:

```text
s_t(v) = D_t(u_t(v))
```

Сэмплирование тоже bilinear.

#### Шаг 7. Агрегация по кадрам

Frame-level vertex values накапливаются с весом, равным числу gaze points в этом кадре:

```text
S(v) = weighted average over frames of s_t(v)
```

Именно `S(v)` и есть итоговая предсказанная `per-vertex saliency map`.

### Формула метода

В сжатом виде:

```text
H_t(x, y) = histogram(frame t gaze)
D_t(x, y) = G_sigma * H_t(x, y)
S(v) = average_t D_t(project_t(v))
```

где:

- `G_sigma` — Gaussian kernel,
- `project_t(v)` — экранная проекция вершины `v` в кадре `t`.


## Откуда взята sigma для screen-space метода

В этом evaluator используется:

```text
sigma_px = 49.0
```

Это взято из 3DVA / Visual Attention setup как:

```text
49 px ≈ 1° visual angle
```

В коде это прямо зафиксировано:

- `sigma = --sigma-px pixels (default 49 px ≈ 1° of visual angle in the 3DVA paper setup)`

### Что было ошибкой в старой версии

В старой логике был режим:

```text
sigma_screen = 0.05 at 256 px width
```

Это эквивалентно:

```text
0.05 * 1920 = 96 px
```

на полном разрешении, то есть blur был слишком широким.

Исправленная версия (`v2`) делает правильно:

- full `1920x1080`;
- `sigma_px = 49.0`.


## Как сравнивался результат с GT

Для каждого view из набора:

- `300`
- `413`
- `599`

загружалась соответствующая GT-карта:

```text
GT_view(v)
```

и далее считались два блока метрик:

1. `metrics_vs_gt_full`
   сравнение по всем вершинам mesh

2. `metrics_vs_gt_visible_only`
   сравнение только по вершинам, видимым из этого GT-view

Второй вариант ближе к paper protocol, потому что GT является view-dependent.


## Какие метрики считались

В `eval_3dva_screen_space.py` считаются:

- `CC / LCC`
- `Spearman`
- `SIM`
- `KLD`
- `MSE`
- `MAE`
- `Cosine`

Дополнительно считаются proxy fixation-like метрики.
Для этого из GT строится бинарная маска верхнего процентила:

- top 10%
- top 5%
- top 1%

И после этого считаются:

- `NSS_gt_top_*pct_proxy`
- `AUC_Judd_gt_top_*pct_proxy`

То есть AUC/NSS здесь считаются не по реальным fixation points, а по **GT-derived fixation proxy mask**.


## Альтернативный метод: raycast + cone on mesh

### Где лежит код

- `/Users/admin/Documents/LAB/SALIENCY_code/#meshes_2.0/GITHUB/Mesh-Saliency-Projection/reprojection_methods/cone_projection_on_mesh/eval_3dva_raycast_cone.py`

### Что он делает

Этот evaluator проверяет два object-space подхода:

1. `raycast_nearest_vertex`
2. `cone_gaussian_on_mesh`

### Raycast variant

Алгоритм:

1. gaze `x,y` превращается в camera ray;
2. ray пересекает mesh;
3. hit записывается в ближайшую вершину.

### Cone variant

После ray hit:

1. вычисляется глубина hit относительно camera origin;
2. angular sigma переводится в world-space:

```text
sigma_world = depth * tan(sigma_deg)
```

3. вокруг hit point берутся nearby vertices;
4. по ним распространяется Gaussian-вклад:

```text
w(v) = exp(-||v - p_hit||^2 / (2 * sigma_world^2))
```

### Какая sigma используется

Для cone evaluator:

```text
sigma_deg = 1.0
```

То есть это не `49 px`, а угловая sigma.  
Она уже внутри метода переводится в world-space через глубину конкретного hit.


## Что из этого считалось у нас основным

Основной verified path:

- `screen_space_gaussian v2`

Почему:

- он чище связан с исходным screen-space измерением gaze;
- sigma в нём фиксирована и понятна;
- он напрямую использует published 3DVA GT protocol.

`raycast + cone` мы использовали как альтернативную mesh-aware репроекцию, но не как основной reference path.


## Что реально показывали локальные результаты

Исторические локальные прогоны лежат в:

- `/Users/admin/Documents/LAB/SALIENCY_code/GAZE_DATA/outputs/3DVA_eval/multi_model_recenter_fov37p5_summary.json`
- `/Users/admin/Documents/LAB/SALIENCY_code/GAZE_DATA/outputs/3DVA/comparison_with_gt.json`

Из этих результатов видно важную вещь:

- сравнение с `3DVA GT` часто даёт слабые или нестабильные корреляции;
- это не обязательно означает, что сама репроекция сломана;
- чаще это означает **mismatch задачи**:
  у нас gaze динамический и может покрывать вращение, а `3DVA GT` фиксирован для трёх статических view.


## Главная граница применимости 3DVA GT

Это критический момент.

`3DVA GT` корректно использовать, если твоя постановка похожа на их benchmark:

- есть конкретный view;
- есть gaze именно в условиях этого view;
- ты хочешь сравнить `per-vertex saliency map` с GT для этого же view.

### Когда это корректно

Корректно:

- строить карту отдельно для view `300`, `413`, `599`;
- сравнивать с соответствующим `*_viewnorm.txt`;
- использовать `visibility` для masked evaluation.

### Когда это некорректно

Некорректно:

- агрегировать gaze равномерно по всей орбите вокруг объекта;
- строить одну общую omnidirectional карту;
- напрямую сравнивать её с одним из `300/413/599` GT.

Это уже другая задача.


## Что делать, если gaze покрывает весь объект со всех сторон

Если у тебя gaze собирается равномерно по всему объёму объекта, то есть три нормальных варианта:

1. **View-conditioned evaluation**
   Разбить свои кадры по ракурсам и сравнивать только те подмножества, которые близки к `300/413/599`.

2. **Project-to-view evaluation**
   Сначала построить общую 3D карту на mesh, затем рендерить её в те же canonical views и сравнивать с 3DVA GT по view.

3. **Build your own GT**
   Если у тебя действительно full-orbit exploration, честнее строить собственный omnidirectional GT, а `3DVA` использовать только как sanity-check benchmark на нескольких фиксированных ракурсах.


## Практический вывод

Если нужен один короткий ответ:

- **как у нас проверялся 3DVA**:
  через `screen_space_gaussian v2`, где raw gaze -> 2D density image -> Gaussian blur -> projection onto mesh -> comparison with published per-vertex GT.

- **какая sigma использовалась**:
  `49 px`, как `≈ 1° visual angle` в paper setup.

- **как использовался GT**:
  как `per-vertex view-dependent benchmark` для view `300`, `413`, `599`, с optional visibility masking.

- **можно ли этот GT напрямую использовать для full-orbit gaze**:
  нет, напрямую нельзя; нужно либо приводить свои данные к тем же canonical views, либо строить отдельный omnidirectional GT.
