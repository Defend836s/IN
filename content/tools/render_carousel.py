#!/usr/bin/env python3
"""Карусели Instagram и картинки для постов Threads в стиле «Все курсы мира».

    python3 content/tools/render_carousel.py content/carousels/<слаг>/spec.yaml

Рядом со spec.yaml появляются 01.png, 02.png ... (1080x1350, 4:5). Формат spec:

    format: carousel          # carousel - листалка (2-10 слайдов), post - одна картинка
    character: semya          # semya | nika | borya | none (content/characters/registry.yaml) - персонаж на обложке и призыве
    title: Короткое название  # для очереди публикации
    caption: |                # подпись к посту (Instagram до 2200, Threads до 500 знаков)
      ...
    slides:
      - type: cover           # обложка: title - хук до 6 слов, text - строка обещания
        title: Не плати за курс
        text: 5 бесплатных замен
      - type: point           # одна мысль: title 3-7 слов, text до 25 слов
        title: ...
        text: ...
      - type: summary         # итог списком, слайд для скриншота
        title: Сохрани
        items: [первое, второе, третье]
      - type: cta             # призыв: одно действие
        title: Сохрани, чтобы не потерять
        text: Все курсы мира - ссылка в профиле

Текст держится в безопасной зоне (120 px от краёв), кегль подбирается сам,
чтобы всё влезло. Слайды карусели нумеруются (2/7).
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import yaml
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

W, H = 1080, 1350
MARGIN = 120
NAVY, NAVY_LT = (10, 26, 79), (26, 46, 116)
GOLD = (255, 205, 60)
WHITE, MUTED = (255, 255, 255), (178, 192, 230)
FONT_DIR = "/usr/share/fonts/opentype/inter"
BLACK = f"{FONT_DIR}/Inter-Black.otf"
BOLD = f"{FONT_DIR}/Inter-ExtraBold.otf"
SEMI = f"{FONT_DIR}/Inter-SemiBold.otf"
TAG = "ВСЕ КУРСЫ МИРА"
CHAR_SIZE = 420


def font(path: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, size)


NBSP = "\u00a0"


def glue(text: str) -> str:
    """Неразрывные пробелы: «60 000 ₽» и короткие предлоги не отрываются от соседей."""
    text = re.sub(r"(?<=\d) (?=\d{3}\b)", NBSP, str(text))
    text = re.sub(r"(?<=\d) (?=[₽%$€])", NBSP, text)
    return re.sub(r"(?<![\w-])(\w{1,2}) (?=\S)", lambda m: m.group(1) + NBSP, text)


def wrap(draw: ImageDraw.ImageDraw, text: str, fnt: ImageFont.FreeTypeFont, width: int) -> list[str]:
    lines: list[str] = []
    for para in glue(text).split("\n"):
        line = ""
        for word in para.split(" "):
            if not word:
                continue
            trial = f"{line} {word}".strip()
            if draw.textlength(trial, font=fnt) <= width or not line:
                line = trial
            else:
                lines.append(line)
                line = word
        lines.append(line)
    return lines


def fit(draw: ImageDraw.ImageDraw, text: str, path: str, width: int, height: int,
        start: int, low: int = 34, spacing: float = 1.15) -> tuple[ImageFont.FreeTypeFont, list[str], int]:
    """Самый крупный кегль, при котором текст влезает в рамку."""
    size = start
    while True:
        fnt = font(path, size)
        lines = wrap(draw, text, fnt, width)
        line_h = int(size * spacing)
        widest = max((draw.textlength(l, font=fnt) for l in lines), default=0)
        if (len(lines) * line_h <= height and widest <= width) or size <= low:
            return fnt, lines, line_h
        size -= 4


def draw_block(draw: ImageDraw.ImageDraw, lines: list[str], fnt, line_h: int, x: int, y: int,
               fill, center: bool = False) -> int:
    for line in lines:
        lx = (W - draw.textlength(line, font=fnt)) / 2 if center else x
        draw.text((lx, y), line, font=fnt, fill=fill)
        y += line_h
    return y


def character(name: str) -> Image.Image | None:
    if name in (None, "", "none"):
        return None
    import characters   # реестр content/characters/registry.yaml: semya, nika, borya, ...
    if name not in characters.registry()["characters"]:
        raise SystemExit(f"неизвестный персонаж: {name} ({' | '.join(characters.registry()['characters'])} | none)")
    characters.verify([name])
    img = characters.get(name).pose(0, "open", "normal")
    return img.resize((CHAR_SIZE, CHAR_SIZE), Image.LANCZOS)


def background(kind: str) -> Image.Image:
    img = Image.new("RGB", (W, H), NAVY)
    d = ImageDraw.Draw(img)
    for y in range(H):  # мягкий вертикальный градиент
        t = y / H
        c = tuple(int(NAVY[i] + (NAVY_LT[i] - NAVY[i]) * t) for i in range(3))
        d.line([(0, y), (W, y)], fill=c)
    if kind in ("cover", "cta"):
        d.rectangle([0, 0, W, 14], fill=GOLD)
    return img


def chrome(img: Image.Image, index: int, total: int) -> None:
    d = ImageDraw.Draw(img)
    tag = font(BOLD, 30)
    d.text((MARGIN, H - 92), TAG, font=tag, fill=GOLD)
    if total > 1:
        num = f"{index}/{total}"
        nf = font(SEMI, 30)
        d.text((W - MARGIN - d.textlength(num, font=nf), H - 92), num, font=nf, fill=MUTED)


def slide(spec: dict, index: int, total: int, char: Image.Image | None) -> Image.Image:
    kind = spec.get("type", "point")
    img = background(kind)
    d = ImageDraw.Draw(img)
    width = W - 2 * MARGIN
    title, text = spec.get("title", ""), spec.get("text", "")
    with_char = char is not None and kind in ("cover", "cta")
    bottom = H - 140 - (CHAR_SIZE - 40 if with_char else 0)

    if kind == "cover":
        f1, l1, h1 = fit(d, title, BLACK, width, int((bottom - 200) * 0.72), 150)
        f2, l2, h2 = fit(d, text, SEMI, width, 200, 52) if text else (None, [], 0)
        block = len(l1) * h1 + (64 + len(l2) * h2 if l2 else 0)
        y = max(MARGIN + 40, (MARGIN + bottom - block) // 2)
        y = draw_block(d, l1, f1, h1, MARGIN, y, WHITE)
        if l2:
            d.rectangle([MARGIN, y + 24, MARGIN + 120, y + 34], fill=GOLD)
            draw_block(d, l2, f2, h2, MARGIN, y + 64, GOLD)
    elif kind == "summary":
        items = spec.get("items", [])
        f1, l1, h1 = fit(d, title, BLACK, width, 220, 96)
        body = "\n".join(f"{i}. {it}" for i, it in enumerate(items, 1))
        room = bottom - MARGIN - len(l1) * h1 - 50
        f2, l2, h2 = fit(d, body, BOLD, width, room, 72, spacing=1.4)
        block = len(l1) * h1 + 50 + len(l2) * h2
        y = max(MARGIN, (MARGIN + bottom - block) // 2)
        y = draw_block(d, l1, f1, h1, MARGIN, y, GOLD) + 50
        draw_block(d, l2, f2, h2, MARGIN, y, WHITE)
    elif kind == "cta":
        f1, l1, h1 = fit(d, title, BLACK, width, 420, 104)
        f2, l2, h2 = fit(d, text, SEMI, width, 200, 46) if text else (None, [], 0)
        block = len(l1) * h1 + (36 + len(l2) * h2 if l2 else 0)
        y = max(MARGIN + 40, (MARGIN + bottom - block) // 2)
        y = draw_block(d, l1, f1, h1, MARGIN, y, WHITE, center=True)
        if l2:
            draw_block(d, l2, f2, h2, MARGIN, y + 36, GOLD, center=True)
    else:  # point
        f1, l1, h1 = fit(d, title, BLACK, width, 420, 112)
        room = bottom - MARGIN - len(l1) * h1 - 60
        f2, l2, h2 = fit(d, text, SEMI, width, room, 64, spacing=1.32) if text else (None, [], 0)
        block = len(l1) * h1 + (60 + len(l2) * h2 if l2 else 0)
        y = max(MARGIN + 30, (MARGIN + bottom - block) // 2)
        d.rectangle([MARGIN, y - 40, MARGIN + 90, y - 30], fill=GOLD)
        y = draw_block(d, l1, f1, h1, MARGIN, y, WHITE) + 60
        if l2:
            draw_block(d, l2, f2, h2, MARGIN, y, WHITE)

    if with_char:
        img.paste(char, ((W - CHAR_SIZE) // 2, H - 110 - CHAR_SIZE + 40), char)
    chrome(img, index, total)
    return img


def render(spec_path: Path) -> list[Path]:
    spec = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
    slides = spec.get("slides") or []
    fmt = spec.get("format", "carousel")
    if fmt == "post" and len(slides) != 1:
        raise SystemExit("format: post - ровно один слайд")
    if fmt == "carousel" and not 2 <= len(slides) <= 10:
        raise SystemExit("карусель - от 2 до 10 слайдов (лимит Instagram и Threads)")
    char = character(spec.get("character", "none"))
    for old in spec_path.parent.glob("[0-9][0-9].png"):
        old.unlink()
    out = []
    for i, s in enumerate(slides, 1):
        path = spec_path.parent / f"{i:02d}.png"
        slide(s, i, len(slides), char).save(path, optimize=True)
        out.append(path)
    return out


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    for arg in sys.argv[1:]:
        for p in render(Path(arg)):
            print(p)
    return 0


if __name__ == "__main__":
    sys.exit(main())
