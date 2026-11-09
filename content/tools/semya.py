"""Енот Сёма: интерфейс как у globus.py / owl.py для рендереров видео и карточек.

    sprites()                     -> {(рот 0..4, моргание bool): RGBA 600x600}
    sprite(mouth, blink)          -> RGBA 600x600
    pose(mouth, eyes, brows)      -> RGBA 600x600, полный набор эмоций:
        eyes:  open | blink | happy | side | sly       brows: normal | up | frown
        mouth: 0..4 позы рта для речи, 5 - ухмылка

Спрайты рисуются из вектора (semya_svg.py) браузером Chromium (svg2png.js) и
кэшируются в content/characters/semya/sprites/. Закэшированные PNG лежат в git,
поэтому для рендера видео браузер не нужен; новые сочетания дорисовываются сами.

    python3 content/tools/semya.py            # перерисовать все спрайты и лист персонажа
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import semya_svg  # noqa: E402

SIZE = 600
CACHE = HERE.parent / "characters" / "semya" / "sprites"
CORE = [(m, e, "normal") for m in range(5) for e in ("open", "blink")]
EXTRA = [(m, e, b) for m in (0, 2, 4) for e, b in (("open", "up"), ("happy", "normal"), ("side", "normal"))]
EXTRA += [(5, "sly", "frown"), (2, "sly", "frown")]


def _name(mouth: int, eyes: str, brows: str) -> Path:
    return CACHE / f"m{mouth}-{eyes}-{brows}.png"


def render(poses: list[tuple[int, str, str]], force: bool = False) -> None:
    """Дорисовать недостающие спрайты одним запуском браузера."""
    todo = [p for p in poses if force or not _name(*p).exists()]
    if not todo:
        return
    CACHE.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        jobs = []
        for mouth, eyes, brows in todo:
            svg_path = Path(tmp) / f"{mouth}-{eyes}-{brows}.svg"
            svg_path.write_text(semya_svg.svg(mouth, eyes, brows, SIZE), encoding="utf-8")
            jobs.append({"svg": str(svg_path), "png": str(_name(mouth, eyes, brows))})
        job_file = Path(tmp) / "jobs.json"
        job_file.write_text(json.dumps(jobs), encoding="utf-8")
        subprocess.run(["node", str(HERE / "svg2png.js"), str(job_file)], check=True)


def pose(mouth: int = 0, eyes: str = "open", brows: str = "normal") -> Image.Image:
    path = _name(mouth, eyes, brows)
    if not path.exists():
        render([(mouth, eyes, brows)])
    return Image.open(path).convert("RGBA")


def sprite(mouth: int = 0, blink: bool = False) -> Image.Image:
    return pose(mouth, "blink" if blink else "open", "normal")


def sprites() -> dict[tuple[int, bool], Image.Image]:
    render(CORE)
    return {(m, b): sprite(m, b) for m in range(5) for b in (False, True)}


def model_sheet(out: Path) -> Path:
    """Лист персонажа: эмоции и позы рта на фоне бренда, с подписями."""
    from PIL import ImageDraw, ImageFont
    cells = [((0, "open", "normal"), "спокоен"), ((3, "open", "normal"), "говорит"),
             ((2, "happy", "normal"), "радуется"), ((4, "open", "up"), "удивлён"),
             ((5, "sly", "frown"), "хитрит"), ((2, "side", "normal"), "смотрит в сторону"),
             ((0, "blink", "normal"), "моргает"), ((1, "open", "up"), "объясняет")]
    render([c for c, _ in cells])
    cell, cols = 420, 4
    sheet = Image.new("RGB", (cell * cols, cell * 2 + 140), (10, 26, 79))
    d = ImageDraw.Draw(sheet)
    font_dir = "/usr/share/fonts/opentype/inter"
    d.text((40, 34), "Енот Сёма", font=ImageFont.truetype(f"{font_dir}/Inter-Black.otf", 58), fill=(255, 255, 255))
    d.text((420, 52), "маскот «Все курсы мира» · находит бесплатное там, где другие платят",
           font=ImageFont.truetype(f"{font_dir}/Inter-SemiBold.otf", 28), fill=(255, 205, 60))
    label = ImageFont.truetype(f"{font_dir}/Inter-SemiBold.otf", 26)
    for i, ((m, e, b), text) in enumerate(cells):
        x, y = (i % cols) * cell, 140 + (i // cols) * cell
        img = pose(m, e, b).resize((cell - 40, cell - 40), Image.LANCZOS)
        sheet.paste(img, (x + 20, y), img)
        w = d.textlength(text, font=label)
        d.text((x + (cell - w) / 2, y + cell - 46), text, font=label, fill=(178, 192, 230))
    sheet.save(out, optimize=True)
    return out


if __name__ == "__main__":
    render(CORE + EXTRA, force=True)
    print(model_sheet(CACHE.parent / "model-sheet.png"))
