#!/usr/bin/env python3
"""Автопубликация роликов из queue.yaml во все подключённые соцсети.

    python3 content/autopost/autopost.py status
    python3 content/autopost/autopost.py run [--dry-run] [--platform telegram] [--count 1]

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
        items.append(Item(r["id"], CONTENT / r["video"], r["video"], r.get("title", r["id"]), r.get("caption", "")))
    return items


def load_state() -> dict[str, dict]:
    if STATE.exists():
        return json.loads(STATE.read_text(encoding="utf-8"))
    return {}


def save_state(state: dict) -> None:
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def cmd_status(_: argparse.Namespace) -> int:
    queue, state = load_queue(), load_state()
    for name, (_, keys) in PLATFORMS.items():
        done = state.get(name, {})
        enabled = "вкл" if env(*keys) else "выкл (нет " + ", ".join(k for k in keys if not os.environ.get(k)) + ")"
        left = [i.id for i in queue if i.id not in done]
        print(f"{name:10} {enabled}; опубликовано {len(done)}, осталось {len(left)}"
              + (f", следующий {left[0]}" if left else ""))
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    queue, state = load_queue(), load_state()
    failures = 0
    for name, (publish, keys) in PLATFORMS.items():
        if args.platform and name not in args.platform:
            continue
        cfg = env(*keys)
        if cfg is None and not args.dry_run:
            log.info("%s: пропуск, не заданы ключи", name)
            continue
        done = state.setdefault(name, {})
        todo = [i for i in queue if i.id not in done][: args.count]
        if not todo:
            log.info("%s: очередь пуста", name)
        for item in todo:
            if not item.video.exists():
                log.error("%s: нет файла %s", name, item.video)
                failures += 1
                continue
            if args.dry_run:
                log.info("%s: [проба] опубликовал бы %s (%s)", name, item.id, item.video.name)
                continue
            try:
                ref = publish(item, cfg)
            except (PublishError, requests.RequestException) as exc:
                log.error("%s: %s не опубликован: %s", name, item.id, exc)
                failures += 1
                break
            done[item.id] = {"at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "ref": ref}
            save_state(state)
            log.info("%s: опубликован %s -> %s", name, item.id, ref)
    return 1 if failures else 0


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status").set_defaults(func=cmd_status)
    r = sub.add_parser("run")
    r.add_argument("--dry-run", action="store_true", help="ничего не публиковать, только показать")
    r.add_argument("--platform", action="append", choices=list(PLATFORMS), help="только эта площадка")
    r.add_argument("--count", type=int, default=1, help="сколько роликов на площадку за запуск")
    r.set_defaults(func=cmd_run)
    args = p.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
