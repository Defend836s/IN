#!/usr/bin/env python3
"""Автопубликация роликов, картинок и каруселей из queue.yaml во все подключённые соцсети.

    python3 content/autopost/autopost.py status
    python3 content/autopost/autopost.py run [--dry-run] [--platform telegram] [--kind carousel] [--count 1]

За один запуск `run` на каждую включённую площадку уходит следующий ролик
из очереди, который туда ещё не публиковался. Опубликованное пишется в
state.json, поэтому повторный запуск не дублирует посты.

Площадка включена, если заданы её переменные окружения (см. README.md).
Ключи читаются только из окружения и никуда не пишутся.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests
import yaml

from platforms import PLATFORMS, Item, PublishError, env

HERE = Path(__file__).resolve().parent
CONTENT = HERE.parent
QUEUE = HERE / "queue.yaml"
STATE = HERE / "state.json"

log = logging.getLogger("autopost")


def load_queue() -> list[Item]:
    raw = yaml.safe_load(QUEUE.read_text(encoding="utf-8")) or []
    items = []
    for r in raw:
        if r.get("skip"):
            continue
        if r.get("video"):
            kind, rels = "video", (r["video"],)
        else:
            rels = tuple(r.get("images") or ())
            if not rels:
                raise SystemExit(f"{r['id']}: нет ни video, ни images")
            kind = "image" if len(rels) == 1 else "carousel"
        items.append(Item(r["id"], kind, tuple(CONTENT / x for x in rels), rels,
                          r.get("title", r["id"]), r.get("caption", "")))
    return items


def load_state() -> dict[str, dict]:
    if STATE.exists():
        return json.loads(STATE.read_text(encoding="utf-8"))
    return {}


def save_state(state: dict) -> None:
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def missing(keys: tuple[str, ...]) -> list[str]:
    return [k for k in keys if not os.environ.get(k, "").strip()]


def cmd_status(_: argparse.Namespace) -> int:
    queue, state = load_queue(), load_state()
    for name, platform in PLATFORMS.items():
        done = state.get(name, {})
        parts = []
        for label, kind in (("ролики", "video"), ("картинки", "image")):
            _, keys = platform.handler(kind)
            if not keys:
                parts.append(f"{label}: не поддерживает")
            else:
                need = missing(keys)
                parts.append(f"{label}: " + ("вкл" if not need else "нет " + ", ".join(need)))
        left = [i for i in queue if i.id not in done and platform.handler(i.kind)[0]]
        print(f"{name:10} {'; '.join(parts)} | опубликовано {len(done)}, осталось {len(left)}"
              + (f", следующий {left[0].id}" if left else ""))
    return 0


def pick(queue: list[Item], done: dict, platform, kinds, count: int, dry_run: bool) -> list[Item]:
    """Следующие неопубликованные элементы, которые площадка умеет и для которых есть ключи."""
    out = []
    for item in queue:
        if len(out) >= count:
            break
        if item.id in done or (kinds and item.kind not in kinds):
            continue
        publish, keys = platform.handler(item.kind)
        if publish is None or (missing(keys) and not dry_run):
            continue
        out.append(item)
    return out


def cmd_run(args: argparse.Namespace) -> int:
    queue, state = load_queue(), load_state()
    failures = 0
    for name, platform in PLATFORMS.items():
        if args.platform and name not in args.platform:
            continue
        done = state.setdefault(name, {})
        todo = pick(queue, done, platform, args.kind, args.count, args.dry_run)
        if not todo:
            log.info("%s: нечего публиковать (очередь пуста, формат не поддерживается или нет ключей)", name)
        for item in todo:
            publish, keys = platform.handler(item.kind)
            lost = [f for f in item.files if not f.exists()]
            if lost:
                log.error("%s: %s - нет файлов %s", name, item.id, ", ".join(map(str, lost)))
                failures += 1
                continue
            if args.dry_run:
                log.info("%s: [проба] опубликовал бы %s %s (%d файл.)", name, item.kind, item.id, len(item.files))
                continue
            try:
                ref = publish(item, env(*keys))
            except (PublishError, requests.RequestException, KeyError) as exc:
                log.error("%s: %s не опубликован: %s", name, item.id, exc)
                failures += 1
                break
            done[item.id] = {"at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "ref": ref}
            save_state(state)
            log.info("%s: опубликован %s %s -> %s", name, item.kind, item.id, ref)
    return 1 if failures else 0


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status").set_defaults(func=cmd_status)
    r = sub.add_parser("run")
    r.add_argument("--dry-run", action="store_true", help="ничего не публиковать, только показать")
    r.add_argument("--platform", action="append", choices=list(PLATFORMS), help="только эта площадка")
    r.add_argument("--count", type=int, default=1, help="сколько публикаций на площадку за запуск")
    r.add_argument("--kind", action="append", choices=["video", "image", "carousel"],
                   help="только этот тип контента (можно несколько)")
    r.set_defaults(func=cmd_run)
    args = p.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
