#!/usr/bin/env python3
"""
Объединяет три PNG (GT / screen_space / cone_gaussian) одной модели
в вертикальный коллаж для удобного сравнения.

Структура выходного файла:
  ┌─────────────────────────────────┐
  │  GT                             │
  ├─────────────────────────────────┤
  │  screen_space                   │
  ├─────────────────────────────────┤
  │  cone_gaussian                  │
  └─────────────────────────────────┘

Запуск:
  python make_collages.py --input DIR --output DIR
  python make_collages.py --input DIR --output DIR --datasets rgb non --models Cat_v1_l3 ...
"""

import argparse
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import re


METHODS    = ["GT", "screen_space", "cone_gaussian"]
METHOD_LABELS = {
    "GT":             "GT  (ground truth)",
    "screen_space":   "Screen-space Gaussian",
    "cone_gaussian":  "Cone Gaussian",
}
LABEL_HEIGHT = 36          # px высота строки с подписью метода
LABEL_BG     = (17, 17, 17)
LABEL_FG     = (220, 220, 220)
SEP_HEIGHT   = 3           # px разделитель между строками
SEP_COLOR    = (60, 60, 60)
FONT_SIZE    = 22


def load_font(size: int):
    try:
        return ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", size)
    except Exception:
        try:
            return ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", size)
        except Exception:
            return ImageFont.load_default()


def discover_models(input_dir: Path):
    """Возвращает список (dataset, model) из имён файлов в input_dir."""
    pattern = re.compile(r"^(.+?)__(.+?)__(?:GT|screen_space|cone_gaussian)__heatmap_(?:4|6)views\.png$")
    pairs = set()
    for f in input_dir.glob("*.png"):
        m = pattern.match(f.name)
        if m:
            pairs.add((m.group(1), m.group(2)))
    return sorted(pairs)


def make_collage(input_dir: Path, output_dir: Path, dataset: str, model: str) -> bool:
    """Создаёт вертикальный коллаж из трёх PNG одной модели."""
    imgs = {}
    for method in METHODS:
        p = next((input_dir / f"{dataset}__{model}__{method}__heatmap_{n}views.png"
                  for n in (6, 4) if (input_dir / f"{dataset}__{model}__{method}__heatmap_{n}views.png").exists()), None)
        if p is None:
            p = input_dir / f"{dataset}__{model}__{method}__heatmap_4views.png"  # trigger not found
        if not p.exists():
            print(f"  [SKIP] {p.name} not found")
            return False
        imgs[method] = Image.open(p).convert("RGB")

    W = imgs["GT"].width
    row_h = imgs["GT"].height

    # Выравниваем ширину если вдруг разная
    for m in METHODS:
        if imgs[m].width != W:
            imgs[m] = imgs[m].resize((W, int(imgs[m].height * W / imgs[m].width)), Image.LANCZOS)
            row_h = imgs[m].height

    total_h = len(METHODS) * (LABEL_HEIGHT + row_h + SEP_HEIGHT) + SEP_HEIGHT
    canvas  = Image.new("RGB", (W, total_h), LABEL_BG)
    draw    = ImageDraw.Draw(canvas)
    font    = load_font(FONT_SIZE)

    y = SEP_HEIGHT
    for method in METHODS:
        # Подпись метода
        label = METHOD_LABELS[method]
        draw.rectangle([(0, y), (W, y + LABEL_HEIGHT)], fill=LABEL_BG)
        draw.text((14, y + (LABEL_HEIGHT - FONT_SIZE) // 2), label, fill=LABEL_FG, font=font)
        y += LABEL_HEIGHT

        # Картинка
        canvas.paste(imgs[method], (0, y))
        y += row_h

        # Разделитель
        draw.rectangle([(0, y), (W, y + SEP_HEIGHT)], fill=SEP_COLOR)
        y += SEP_HEIGHT

    out_path = output_dir / f"{dataset}__{model}__collage.png"
    canvas.save(str(out_path), "PNG")
    print(f"  [OK] {out_path.name}")
    return True


def main():
    ap = argparse.ArgumentParser(description="Make GT/SS/cone comparison collages.")
    ap.add_argument("--input",    type=Path, required=True, help="Папка с PNG heatmap")
    ap.add_argument("--output",   type=Path, default=None,  help="Папка для коллажей (default: input/collages)")
    ap.add_argument("--datasets", nargs="+", default=None,  help="Фильтр датасетов (например: meshmamba_rgb meshmamba_non)")
    ap.add_argument("--models",   nargs="+", default=None,  help="Фильтр моделей")
    args = ap.parse_args()

    out_dir = args.output or (args.input / "collages")
    out_dir.mkdir(parents=True, exist_ok=True)

    pairs = discover_models(args.input)
    if args.datasets:
        pairs = [(ds, m) for ds, m in pairs if any(f in ds for f in args.datasets)]
    if args.models:
        pairs = [(ds, m) for ds, m in pairs if m in args.models]

    print(f"Collages to make: {len(pairs)}  →  {out_dir}")
    n_ok = 0
    for dataset, model in pairs:
        print(f"\n{dataset}  |  {model}")
        if make_collage(args.input, out_dir, dataset, model):
            n_ok += 1

    print(f"\nDone: {n_ok}/{len(pairs)}")


if __name__ == "__main__":
    main()
