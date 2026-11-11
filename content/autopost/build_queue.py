#!/usr/bin/env python3
"""Собирает queue.yaml из готовых роликов и их сценариев.

Ролики берутся из серий в content/, подпись - из сценария rNN.txt с тем же
номером. Карусели и картинки-посты - из content/carousels/<слаг>/spec.yaml. Серии чередуются: 1-й ролик каждой серии, потом 2-й и так далее.
Уже существующие записи (по id) не перезаписываются, чтобы ручные правки
подписей сохранялись.

    python3 content/autopost/build_queue.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
CONTENT = HERE.parent
QUEUE = HERE / "queue.yaml"

# серия -> (папка с роликами, папка со сценариями, хэштеги)
SERIES = {
    "semya": ("semya/videos", "semya/scripts", "#курсы #обучение #самообразование #бесплатно #енот"),
    "kanal": ("kanal/videos", "kanal/scripts", "#курсы #обучение #самообразование #бесплатно"),
    "motivaciya": ("motivaciya/с-баннером", "motivaciya/scripts", "#мотивация #саморазвитие #привычки"),
    "pravda-ili-mif": ("pravda-ili-mif/с-баннером", "pravda-ili-mif/scripts", "#правдаилимиф #обучение #факты"),
    "citaty": ("citaty/с-баннером", "citaty/scripts", "#цитаты #классика #литература"),
    "history": ("history/videos", "history/scripts", "#история #архив #фактыизистории #обучение"),
}

BRAND = yaml.safe_load((CONTENT / "brand.yaml").read_text(encoding="utf-8"))
OLD_CTA = "Все курсы мира - ссылка в профиле."
CTA = (f"{BRAND['updates']}. {BRAND['free_channel']['pitch']}. "
       f"{BRAND['link_hint']}.")
PREFIX = re.compile(r"^[A-ZА-ЯЁ]+:\s*")
# разметка render_pro: [эмоция], [фото N], «Ника: », {1903|тысяча девятьсот третьего}, *акцент*
MARKUP = [(re.compile(r"\[[^\]]*\]\s*"), ""), (re.compile(r"\{([^|{}]+)\|[^{}]+\}"), r"\1"),
          (re.compile(r"\*"), "")]
sys.path.insert(0, str(CONTENT / "tools"))


def clean_line(line: str) -> str:
    for rx, sub in MARKUP:
        line = rx.sub(sub, line)
    m = re.match(r"^([А-ЯЁA-Z][\w ]{1,24}):\s+", line.strip())
    if m:
        import characters
        if characters.by_alias(m.group(1)):
            line = line.strip()[m.end():]
    return PREFIX.sub("", line).strip()


def caption_from_script(path: Path, tags: str) -> tuple[str, str]:
    lines = [clean_line(l) for l in path.read_text(encoding="utf-8").splitlines()]
    lines = [l for l in lines if l and not l.lower().startswith("как думаешь")]
    title = lines[0] if lines else path.stem
    body = "\n".join(lines[:4])
    media = path.parent.parent / "media" / re.sub(r"\D", "", path.stem)
    if media.is_dir():          # история: источники фактов и снимков - обязательно в подписи
        import archive
        body += "\n\n" + archive.credit(str(media))
    return title, f"{body}\n\n{CTA}\n\n{tags}"


def _str_repr(dumper: yaml.SafeDumper, value: str) -> yaml.Node:
    style = "|" if "\n" in value else None
    return dumper.represent_scalar("tag:yaml.org,2002:str", value, style=style)


yaml.SafeDumper.add_representer(str, _str_repr)


def carousels() -> list[dict]:
    """Карусели и картинки-посты из content/carousels/<слаг>/spec.yaml (render_carousel.py)."""
    items = []
    for spec_path in sorted((CONTENT / "carousels").glob("*/spec.yaml")):
        spec = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
        images = sorted(spec_path.parent.glob("[0-9][0-9].png"))
        if not images:
            print(f"{spec_path.parent.name}: нет картинок, сначала render_carousel.py", file=sys.stderr)
            continue
        items.append({
            "id": f"carousel-{spec_path.parent.name}",
            "images": [str(p.relative_to(CONTENT)) for p in images],
            "title": spec.get("title", spec_path.parent.name),
            "caption": spec.get("caption", ""),
        })
    return items


def main() -> int:
    existing = []
    if QUEUE.exists():
        existing = yaml.safe_load(QUEUE.read_text(encoding="utf-8")) or []
    known = {item["id"] for item in existing}
    for item in existing:   # старый призыв -> актуальный из brand.yaml (опубликованное это не меняет)
        item["caption"] = item.get("caption", "").replace(OLD_CTA, CTA)
        if item.get("video"):   # чистая версия для площадок Meta, если появилась
            clean = (CONTENT / item["video"]).with_name(Path(item["video"]).stem + "-clean.mp4")
            if clean.exists():
                item["video_clean"] = str(clean.relative_to(CONTENT))

    per_series: list[list[dict]] = []
    for name, (vdir, sdir, tags) in SERIES.items():
        items = []
        for video in sorted(v for v in (CONTENT / vdir).glob("*.mp4") if not v.stem.endswith("-clean")):
            num = video.name.split("-", 1)[0]
            script = CONTENT / sdir / f"r{num}.txt"
            if not script.exists():
                print(f"нет сценария для {video}, пропускаю", file=sys.stderr)
                continue
            title, caption = caption_from_script(script, tags)
            clean = video.with_name(video.stem + "-clean.mp4")
            items.append({
                "id": f"{name}-{num}",
                "video": str(video.relative_to(CONTENT)),
                **({"video_clean": str(clean.relative_to(CONTENT))} if clean.exists() else {}),
                "title": title,
                "caption": caption,
            })
        per_series.append(items)

    per_series.append(carousels())

    added = 0
    for i in range(max(len(s) for s in per_series)):
        for series in per_series:
            if i < len(series) and series[i]["id"] not in known:
                existing.append(series[i])
                added += 1

    QUEUE.write_text(
        yaml.safe_dump(existing, allow_unicode=True, sort_keys=False, width=1000),
        encoding="utf-8",
    )
    print(f"в очереди {len(existing)} роликов, добавлено {added}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
