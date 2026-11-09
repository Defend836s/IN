#!/usr/bin/env python3
"""Собирает queue.yaml из готовых роликов и их сценариев.

Ролики берутся из серий в content/, подпись - из сценария rNN.txt с тем же
номером. Серии чередуются: 1-й ролик каждой серии, потом 2-й и так далее.
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
    "kanal": ("kanal/videos", "kanal/scripts", "#курсы #обучение #самообразование #бесплатно"),
    "motivaciya": ("motivaciya/с-баннером", "motivaciya/scripts", "#мотивация #саморазвитие #привычки"),
    "pravda-ili-mif": ("pravda-ili-mif/с-баннером", "pravda-ili-mif/scripts", "#правдаилимиф #обучение #факты"),
    "citaty": ("citaty/с-баннером", "citaty/scripts", "#цитаты #классика #литература"),
}

CTA = "Все курсы мира - ссылка в профиле."
PREFIX = re.compile(r"^[A-ZА-ЯЁ]+:\s*")


def caption_from_script(path: Path, tags: str) -> tuple[str, str]:
    lines = [PREFIX.sub("", l).strip() for l in path.read_text(encoding="utf-8").splitlines()]
    lines = [l for l in lines if l and not l.lower().startswith("как думаешь")]
    title = lines[0] if lines else path.stem
    body = "\n".join(lines[:4])
    return title, f"{body}\n\n{CTA}\n\n{tags}"


def _str_repr(dumper: yaml.SafeDumper, value: str) -> yaml.Node:
    style = "|" if "\n" in value else None
    return dumper.represent_scalar("tag:yaml.org,2002:str", value, style=style)


yaml.SafeDumper.add_representer(str, _str_repr)


def main() -> int:
    existing = []
    if QUEUE.exists():
        existing = yaml.safe_load(QUEUE.read_text(encoding="utf-8")) or []
    known = {item["id"] for item in existing}

    per_series: list[list[dict]] = []
    for name, (vdir, sdir, tags) in SERIES.items():
        items = []
        for video in sorted((CONTENT / vdir).glob("*.mp4")):
            num = video.name.split("-", 1)[0]
            script = CONTENT / sdir / f"r{num}.txt"
            if not script.exists():
                print(f"нет сценария для {video}, пропускаю", file=sys.stderr)
                continue
            title, caption = caption_from_script(script, tags)
            items.append({
                "id": f"{name}-{num}",
                "video": str(video.relative_to(CONTENT)),
                "title": title,
                "caption": caption,
            })
        per_series.append(items)

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
