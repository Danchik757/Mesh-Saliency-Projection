# Sigma Ablation Run Log — 2026-06-18

Дата: 2026-06-18  
Сервер: vg-iai  
Ветка: `orchestra/metric-ablation-lab`  
Релиз данных: `v2.0-data-rc3`

---

## 1. Что запускалось: задача sigma ablation

Для каждой комбинации **датасет × метод проекции** подбирается оптимальная sigma Гауссового ядра, которое сглаживает heatmap saliency перед сравнением с ground truth.

**4 датасета:**
- `3dva` — 3D-объекты, 32 модели (после исключений — 31 модель в request)
- `sal3d` — SAL3D объекты, 54+ моделей
- `meshmamba_non_texture` (mnon) — 105 моделей, без текстур
- `meshmamba_rgb_texture` (mrg) — 105 моделей, с RGB текстурами

**2 метода проекции:**
- `screen_space` — гауссово сглаживание в пространстве экрана (быстро)
- `cone` — конусная проекция с ray casting (медленно, ~2 ч/кандидат)

**Процедура подбора sigma (для каждой ветки):**
1. **5 coarse кандидатов** — gridsearch по sigma_multiplier: {0.5, 0.7, 1.0, 1.3, 1.5}
2. **Выбор лучшего** по mean CC на **common model set** (пересечение моделей с `status=ok` во ВСЕХ кандидатах)
3. **4 refined кандидата** вокруг лучшего coarse
4. Финальный победитель → `branch_best.json` (PROMOTED)

---

## 2. Проблемы и как решались

### Проблема 1: env-переменные не доходят до evaluator subprocess

**Симптом:**  
Все запуски 3dva и mamba_rgb HELD с `empty_common_set`, n_ok=0.  
Ошибка в `metrics_long.jsonl`:
```
FileNotFoundError: OBJ file not found for model 'A380' in e.g. /srv/datasets/3DVA/3DModels-Simplif-up
```
Evaluator падал на дефолтный путь `/srv/datasets/3DVA` вместо актуального `/mnt/ssd1/...`.

**Диагностика:**  
Commit `e861eed` добавил `VISUAL_ATTENTION_3D_SHAPES_ROOT` в `resolved_env` request JSON.  
Commit `c66fb9b` исправил имя переменной (`THREE_DVA_CSV_ROOT`).  
Оба фикса **не работали** — env-переменная была в JSON, но не доходила до subprocess.

**Корневая причина:**  
`build_evaluator_command()` в `test/launch/run_evaluator_sweep.py` передавал env dict в `subprocess.run(env=...)`, но `argparse` defaults вызывали `os.environ.get(key)` при *создании парсера*, а не при выполнении. Python-subprocess читает env только через `os.environ`, но только если он *унаследовал* новый env до инициализации argparse. Этого не происходило.

**Решение (commit `972db10`, GPT):**  
Добавлена функция `_dataset_specific_cli_args(point, env)` — преобразует env dict в явные CLI-флаги:
```python
# test/launch/run_evaluator_sweep.py, строки 85-134
def _dataset_specific_cli_args(point, env):
    if dataset == "3dva":
        args += ["--dataset-root", dataset_root]   # вместо env var
        args += ["--json-root",    json_root]
        args += ["--combined-gt-dir", combined_gt]
    if dataset == "meshmamba_rgb_texture":
        args += ["--dataset-root", dataset_root]
        args += ["--json-root",    json_root]
        args += ["--texture-type", "rgb_texture"]
    # аналогично для meshmamba_non_texture и sal3d
```
Это обходит argparse env-inheritance проблему: пути передаются как явные аргументы командной строки.

**Проверка:**  
После фикса первый rev4 run для 3dva/ss: `A380 status=ok CC=0.394` ✅

---

### Проблема 2: CombinedGT — case sensitivity (blade-200K, rockerarm)

**Симптом (в rev4 runs после фикса env):**
```
FileNotFoundError: Combined GT not found for model 'blade-200K'
  in .../3DVA/CombinedGT
FileNotFoundError: Combined GT not found for model 'rockerarm'
  in .../3DVA/CombinedGT
```

**Диагностика:**  
В директории `CombinedGT` присутствовали файлы:
- `blade-200k_combined_gt.txt` (lowercase k) — без метаданных для uppercase
- `rockerArm_combined_gt.txt` (mixed case) — без lowercase варианта

Evaluator (`_load_combined_gt`) генерирует варианты имён через `_candidate_model_names`:  
`["blade-200K", "blade-200k", "BLADE-200K"]` — и проверяет `Path.is_file()`.  
Несмотря на то что функция поддерживает разные регистры, файл `blade-200k_combined_gt.txt` EXISTS, но `blade-200K_combined_gt.txt` НЕ существовал до фикса.

**Решение (GPT, без коммита — действие на сервере):**  
Создание симлинков на `vg-iai` в 11:18 UTC:
```bash
blade-200K_combined_gt.txt -> blade-200k_combined_gt.txt
rockerarm_combined_gt.txt  -> rockerArm_combined_gt.txt
```

**Последствия timing:**  
Симлинки созданы *после* завершения первых 4 из 5 coarse кандидатов для 3dva/ss.  
Поскольку `common_model_set = пересечение ok-моделей по ВСЕМ кандидатам`, blade-200K и rockerarm исключены из текущего run (провалились в кандидатах 1–4 до появления симлинков).  
**Для будущих runs** (timing ablation, финальные) — оба работают корректно.

---

### Проблема 3: jessi — недостаточно fixation данных (known blocker)

**Симптом:**
```
InvalidFixationError: Invalid processed fixation for '3DVA_jessi':
fixation frames 41 < required 450
(turn_frames=450, gaze_start=0, delay_frames=0, frame_offset=0)
This model is a known blocker. Do not fall back to CSV.
```

**Диагностика:**  
`/participant_fixations_offset0_full_cleaned/3DVA_jessi/fixations.json` содержит список из **41 фрейма**.  
Timing contract `one_turn_from_start` требует минимум 450 фреймов (полный оборот).  
Данные для 3DVA_jessi были записаны с недостаточным охватом — это не ошибка кода, а пробел в данных.

**Проверка других датасетов:**  
`SAL3D_jessi/fixations.json` — **720 фреймов** — достаточно, jessi в sal3d работает.

**Решение (commit `6d36f4d`):**  
Удалена `"jessi"` из model list в обоих 3dva request JSON:
- `coordination/requests/dmlab/vg_iai/3dva_screen_space_sigma.json`
- `coordination/requests/dmlab/vg_iai/3dva_cone_sigma.json`

3dva теперь: 31 модель (была 32). jessi в sal3d/mamba JSONs не тронута.

---

### Проблема 4: competing old launcher (race condition)

**Симптом:**  
После запуска новых launchers с фиксом (PIDs 3885866–3885869) обнаружены старые launchers (PIDs 3872881, 3872957) — запущены *без* GPT-фикса, вычисляли те же sigma-кандидаты.

**Риск:**  
Старый launcher мог перезаписать `branch_best.json` / `_held.json` с некорректными результатами (все модели falling-back на `/srv/datasets/3DVA`).

**Решение:**  
Верификация: оба старых PID принадлежат пользователю `29d_kon`, тот же repo path.  
Убиты с подтверждения пользователя. Новые launchers продолжили работу.

---

### Проблема 5: неправильное имя env-переменной для mamba_rgb

**Commit `e861eed`:** добавил `MESHMAMBA_NON_TEXTURE_ROOT` в mamba_rgb request JSON.  
Это **неверно** — для rgb_texture датасета нужен `MESHMAMBA_RGB_TEXTURE_ROOT`.

**Исправлено в commit `972db10`** (`_dataset_specific_cli_args`):
```python
# для meshmamba_rgb_texture:
dataset_root = _env_get(env, "MESHMAMBA_RGB_TEXTURE_ROOT", "MESHMAMBA_NON_TEXTURE_ROOT")
json_root    = _env_get(env, "MESHMAMBA_RGB_TEXTURE_JSON_ROOT", "MESHMAMBA_JSON_ROOT")
```
Fallback на NON_TEXTURE_ROOT остался для совместимости если RGB-ROOT не задан.

---

## 3. Метрики качества

Все метрики считаются на **common model set** (пересечение моделей с status=ok по всем sigma-кандидатам).

| Метрика | Описание | Направление | Используется для выбора sigma |
|---|---|---|---|
| **CC** | Pearson Correlation Coefficient | ↑ больше = лучше | ✅ **основная** |
| **SIM** | Structural Similarity (гистограммная) | ↑ | вторичная |
| **KLD** | KL-дивергенция (saliency↔GT) | ↓ | вторичная |
| **Spearman** | Ранговая корреляция | ↑ | вторичная |
| **AUC@10%** | AUC при 10% threshold | ↑ | вторичная |
| **AUC@5%** | AUC при 5% threshold | ↑ | вторичная |
| **AUC@1%** | AUC при 1% threshold | ↑ | вторичная |
| **NSS@10%** | Normalized Scanpath Saliency @10% | ↑ | вторичная |
| **NSS@5%** | — @5% | ↑ | вторичная |
| **NSS@1%** | — @1% | ↑ | вторичная |
| **MSE** | Mean Squared Error | ↓ | не для отбора |
| **MAE** | Mean Absolute Error | ↓ | не для отбора |
| **Cosine** | Косинусное сходство | ↑ | не для отбора |

**Sigma выбирается по:** `mean(CC)` на common model set.  
**Storing:** все метрики сохраняются в `metrics_long.jsonl` (per-model) и `aggregate_row.json` (mean).

---

## 4. Исключённые / проблемные модели

### 3dva (32 → 31 модель в request, 29 в common_set текущего run)

| Модель | Проблема | Статус |
|---|---|---|
| **jessi** | `fixations.json`: 41 фрейм < 450 required. Данных нет. Known blocker. | Удалена из request JSON (commit `6d36f4d`) |
| **blade-200K** | `CombinedGT` не найден — case mismatch (`blade-200k` vs `blade-200K`) | Исправлено симлинком на сервере (11:18). Будет работать в будущих runs. |
| **rockerarm** | Аналогично: `rockerArm_combined_gt.txt` vs `rockerarm` | Исправлено симлинком. |

> **Итог для текущего run:** blade-200K и rockerarm исправлены слишком поздно (после 4/5 coarse кандидатов) → они исключены из common_set текущего sigma run (n=29 вместо 31). Для timing ablation и финальных runs — оба будут работать.

### sal3d
Нет исключений. jessi в sal3d: 720 фреймов — работает.

### meshmamba_non_texture / meshmamba_rgb_texture
Нет постоянных исключений. Все 105 моделей в common_set.

---

## 5. Результаты sigma ablation (screen_space — все PROMOTED)

| Датасет | σ_multiplier | σ_px | Stage | CC | SIM | KLD | Spearman | AUC@10% | NSS@10% | n_common |
|---|---|---|---|---|---|---|---|---|---|---|
| **sal3d** | **1.88** | 49.44 | refined | **0.3987** | 0.6689 | 0.6227 | 0.4469 | 0.7463 | 0.8601 | 54 |
| **3dva** | **0.61** | 29.89 | refined | **0.4809** | 0.6681 | 0.9425 | 0.4512 | 0.7714 | 1.0783 | 29 |
| **mnon** | **0.38** | — | refined | **0.2431** | 0.5790 | 1.9891 | 0.1933 | 0.6335 | 0.5398 | 105 |
| **mrg** | **0.38** | — | refined | **0.2086** | 0.5647 | 1.9913 | 0.1838 | 0.6085 | 0.4228 | 105 |

> **Наблюдение:** mrg (rgb texture) имеет более низкий CC чем mnon (non texture) — вероятно, rgb текстуры создают сложности для проекции (цветовой шум влияет на saliency). Обе mamba ветки выбрали одинаковую оптимальную sigma (0.38) — это согласуется.

### cone — в процессе (13:18 UTC)

| Датасет | Статус | Прогресс |
|---|---|---|
| 3dva/cone | 🔄 running | 2/7 coarse (≈ 10 ч до завершения) |
| mrg/cone | 🔄 running | 1/7 coarse (≈ 12 ч до завершения) |
| sal3d/cone | 🔄 running | — |
| mnon/cone | 🔄 running | — |

---

## 6. Файловая структура результатов

```
results/ablation/{family}/{dataset}/{method}/{cmp_signature}/
├── manifest.json          — параметры запроса, resolved_env, model list
├── branch_best.json       — PROMOTED: best_sigma, all metrics, common_model_set
├── _held.json             — HELD: hold_reason, n_common_models, timestamp
├── aggregate/
│   ├── ablation_runs.jsonl  — строка на кандидат: все параметры + mean metrics
│   ├── ablation_runs.csv    — то же в CSV
│   └── common_model_summary.json — per-candidate CC/SIM/... на common set
└── runs/{run_id}[__revN]/
    ├── metrics_long.jsonl   — PER MODEL: CC, SIM, KLD, ... для каждой модели
    ├── aggregate_row.json   — mean metrics + параметры прогона
    ├── metrics_summary.csv  — краткая сводка
    ├── params.json          — sigma_px, sigma_multiplier, timing, etc.
    └── stdout.log
```

**`__revN` суффикс:** при повторном запуске того же `run_id` создаётся новая директория `__rev2`, `__rev3`, ... Старые строки в `ablation_runs.jsonl` помечаются `status=superseded`.

---

## 7. Commits этой сессии

| Commit | Что сделано |
|---|---|
| `e861eed` | Добавлены env vars для 3dva и mamba_rgb в request JSON (неполный фикс) |
| `c66fb9b` | Исправлено имя переменной: `VISUAL_ATTENTION_3D_SHAPES_ROOT`, `THREE_DVA_CSV_ROOT` |
| `d725391` | Лог debug-сессии, передача хода GPT |
| `972db10` | **GPT:** `_dataset_specific_cli_args` — явная передача путей как CLI-флагов (основной фикс) |
| `cdef09b` | Задача GPT: расследовать 3 failing модели 3dva |
| `0747715` | Задача GPT: удалить jessi из 3dva model lists |
| `6d36f4d` | Удалена `jessi` из обоих 3dva request JSON (known blocker) |

---

## 8. Что не работает / ограничения

| Проблема | Статус |
|---|---|
| **jessi/3DVA** — 41 fixation frame, min 450 required | Постоянное ограничение данных. Модель исключена из 3dva. В sal3d работает (720 фреймов). |
| **blade-200K, rockerarm** в текущем 3dva sigma run | Исключены из common_set (симлинки созданы после 4/5 coarse кандидатов). В будущих runs — OK. |
| **Cone branches** — все 4 ещё running | Медленно из-за ray casting (~2 ч/кандидат × 7 кандидатов = ~14 ч). |
| **server_manifest.json** файлы | Стареют при каждом rerun — не обновляются автоматически. |

---

## 9. Следующий шаг: timing ablation

После того как все 8 sigma-веток получат `branch_best.json`, запустить:
```bash
python3 build_downstream_request.py timing \
  --from-sigma-best results/ablation/.../branch_best.json \
  --output coordination/requests/dmlab/vg_iai/...
```

Для screen_space веток можно запускать **уже сейчас** (все 4 PROMOTED).  
Для cone веток — ждать завершения.

> **Требует явного подтверждения** перед запуском на сервере.
