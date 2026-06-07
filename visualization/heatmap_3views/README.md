# Heatmap 3-view Rendering

Скрипты для визуализации per-face saliency на 3D-мешах в виде PNG с тремя (или четырьмя) ракурсами.

## Файлы

| Файл | Назначение |
|------|-----------|
| `render_heatmap_cmd.py` | Основной рендер: OBJ + saliency.txt → PNG (3–4 вида, PyVista off-screen) |
| `run_all.py` | Параллельный запуск screen_space + cone для всех моделей (32 задачи, multiprocessing) |
| `run_cone_retry.py` | Повтор только cone-задач (использовался после установки rtree) |
| `run_gt_heatmaps.py` | Рендер GT saliency для всех 16 моделей (MeshMamba RGB/non + SAL3D) |
| `run_rerender_correct_views.py` | Перерендер с ракурсом, учитывающим реальный угол съёмки из JSON |
| `setup_env.sh` | Создание venv и установка зависимостей на сервере |

## Зависимости

```
pyvista[all]>=0.43
trimesh>=4.0
scipy>=1.10
pandas>=2.0
matplotlib>=3.7
numpy>=1.24
rtree
```

## Использование

### Один меш
```bash
python render_heatmap_cmd.py \
  --obj /path/to/mesh.obj \
  --sal /path/to/saliency.txt \
  --output /path/to/output.png \
  --title "Model | method" \
  --rot-deg 180.0    # опционально: средний угол поворота из JSON
```

### Все модели (сервер)
```bash
# Установить окружение (один раз)
bash setup_env.sh

# Запустить все задачи параллельно
python run_all.py

# Только GT
python run_gt_heatmaps.py
```

## Формат saliency файла

- **Per-face**: одна строка = одно float-значение, строк = количество граней OBJ
- **Per-vertex** (SAL3D): одна строка = одно float-значение, строк = количество вершин → автоматически конвертируется в per-face через усреднение по смежным вершинам

## Выходной формат

PNG, ~2850×900 px (3 вида) или ~3800×900 px (4 вида с `--rot-deg`), dpi=150, тёмный фон.

## Примечание о ракурсах

Для моделей у которых `video_info.duration_seconds` в JSON меньше реальной длины видео (например Cat_v1 = 1s вместо 17s), гейз-данные некорректно сжимаются в последний кадр. Используй `--rot-deg` с реальным средним углом поворота, чтобы хотя бы один из видов совпадал с фактическим ракурсом наблюдателей.
