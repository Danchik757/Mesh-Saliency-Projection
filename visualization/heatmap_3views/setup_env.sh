#!/bin/bash
# Создаёт виртуальное окружение и устанавливает зависимости.
# Запуск: bash /mnt/ssd1/29d_kon/heatmap_renders/code/setup_env.sh

set -e
BASE="/mnt/ssd1/29d_kon/heatmap_renders"
ENV="$BASE/env"

echo "=== Создаём venv: $ENV ==="
python3 -m venv "$ENV"

PIP="$ENV/bin/pip"
"$PIP" install --upgrade pip --quiet

echo "=== Устанавливаем пакеты ==="
# pyvista[all] включает headless VTK (osmesa)
"$PIP" install \
    "numpy>=1.24" \
    "scipy>=1.10" \
    "pandas>=2.0" \
    "matplotlib>=3.7" \
    "trimesh>=4.0" \
    "pyvista[all]>=0.43" \
    --quiet

echo ""
echo "=== Проверка ==="
"$ENV/bin/python3" -c "
import pyvista, trimesh, scipy, pandas, matplotlib, numpy
print(f'  numpy     {numpy.__version__}')
print(f'  scipy     {scipy.__version__}')
print(f'  pandas    {pandas.__version__}')
print(f'  matplotlib{matplotlib.__version__}')
print(f'  trimesh   {trimesh.__version__}')
print(f'  pyvista   {pyvista.__version__}')
print('OK — все пакеты установлены.')
"
echo "=== setup_env.sh завершён ==="
