#!/usr/bin/env python3
"""Автопубликация роликов из queue.yaml в Telegram, VK, Instagram и YouTube.

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
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import requests
import yaml

HERE = Path(__file__).resolve().parent
CONTENT = HERE.parent
QUEUE = HERE / "queue.yaml"
STATE = HERE / "state.json"
TIMEOUT = 120

log = logging.getLogger("autopost")


class PublishError(RuntimeError):
    pass


@dataclass(frozen=True)
class Item:
    id: str
    video: Path
    title: str
    caption: str


def env(*names: str) -> dict[str, str] | None:
    values = {n: os.environ.get(n, "").strip() for n in names}
    return values if all(values.values()) else None


def check(resp: requests.Response, what: str) -> dict:
    try:
        data = resp.json()
    except ValueError:
        data = {}
    if resp.status_code >= 400 or (isinstance(data, dict) and data.get("error")):
        detail = data.get("error") if isinstance(data, dict) else None
        raise PublishError(f"{what}: HTTP {resp.status_code} {detail or resp.text[:300]}")
    return data


# ---------------------------------------------------------------- Telegram

def publish_telegram(item: Item, cfg: dict[str, str]) -> str:
    url = f"https://api.telegram.org/bot{cfg['TELEGRAM_BOT_TOKEN']}/sendVideo"
    with item.video.open("rb") as fh:
        resp = requests.post(
            url,
            data={
                "chat_id": cfg["TELEGRAM_CHAT_ID"],
                "caption": item.caption[:1024],
                "supports_streaming": "true",
            },
            files={"video": (item.video.name, fh, "video/mp4")},
            timeout=TIMEOUT,
        )
    data = check(resp, "Telegram sendVideo")
    if not data.get("ok"):
        raise PublishError(f"Telegram: {data.get('description')}")
    return str(data["result"]["message_id"])


# ---------------------------------------------------------------- VK

VK_API = "https://api.vk.com/method"
VK_VERSION = "5.199"


def publish_vk(item: Item, cfg: dict[str, str]) -> str:
    resp = requests.post(
        f"{VK_API}/video.save",
        data={
            "access_token": cfg["VK_TOKEN"],
            "v": VK_VERSION,
            "group_id": cfg["VK_GROUP_ID"].lstrip("-"),
            "name": item.title[:128],
            "description": item.caption,
            "wallpost": 1,
        },
        timeout=TIMEOUT,
    )
    data = check(resp, "VK video.save")
    if "error" in data or "response" not in data:
        raise PublishError(f"VK video.save: {data.get('error')}")
    upload_url = data["response"]["upload_url"]
    with item.video.open("rb") as fh:
        up = requests.post(upload_url, files={"video_file": (item.video.name, fh, "video/mp4")}, timeout=TIMEOUT)
    result = check(up, "VK upload")
    return str(result.get("video_id") or data["response"].get("video_id"))


# ---------------------------------------------------------------- Instagram

GRAPH = "https://graph.facebook.com/v21.0"


def publish_instagram(item: Item, cfg: dict[str, str]) -> str:
    token, user = cfg["IG_ACCESS_TOKEN"], cfg["IG_USER_ID"]
    auth = {"Authorization": f"OAuth {token}"}
    created = check(
        requests.post(
            f"{GRAPH}/{user}/media",
            headers=auth,
            data={"media_type": "REELS", "upload_type": "resumable", "caption": item.caption[:2200]},
            timeout=TIMEOUT,
        ),
        "Instagram media",
    )
    container = created["id"]
    upload_uri = created.get("uri") or f"https://rupload.facebook.com/ig-api-upload/v21.0/{container}"
    body = item.video.read_bytes()
    check(
        requests.post(
            upload_uri,
            headers={**auth, "offset": "0", "file_size": str(len(body))},
            data=body,
            timeout=TIMEOUT,
        ),
        "Instagram upload",
    )
    for _ in range(60):
        status = check(
            requests.get(f"{GRAPH}/{container}", headers=auth, params={"fields": "status_code,status"}, timeout=TIMEOUT),
            "Instagram status",
        )
        code = status.get("status_code")
        if code == "FINISHED":
            break
        if code in ("ERROR", "EXPIRED"):
            raise PublishError(f"Instagram обработка: {status.get('status')}")
        time.sleep(10)
    else:
        raise PublishError("Instagram: ролик не обработался за 10 минут")
    done = check(
        requests.post(f"{GRAPH}/{user}/media_publish", headers=auth, data={"creation_id": container}, timeout=TIMEOUT),
        "Instagram media_publish",
    )
    return str(done["id"])


# ---------------------------------------------------------------- YouTube

def publish_youtube(item: Item, cfg: dict[str, str]) -> str:
    tok = check(
        requests.post(
            "https://oauth2.googleapis.com/token",
            data={
                "client_id": cfg["YT_CLIENT_ID"],
                "client_secret": cfg["YT_CLIENT_SECRET"],
                "refresh_token": cfg["YT_REFRESH_TOKEN"],
                "grant_type": "refresh_token",
            },
            timeout=TIMEOUT,
        ),
        "YouTube token",
    )
    auth = {"Authorization": f"Bearer {tok['access_token']}"}
    title = item.title[:90].rstrip() + " #Shorts"
    meta = {
        "snippet": {"title": title, "description": item.caption, "categoryId": "27"},
        "status": {"privacyStatus": os.environ.get("YT_PRIVACY", "public"), "selfDeclaredMadeForKids": False},
    }
    init = requests.post(
        "https://www.googleapis.com/upload/youtube/v3/videos",
        params={"uploadType": "resumable", "part": "snippet,status"},
        headers={**auth, "Content-Type": "application/json; charset=UTF-8", "X-Upload-Content-Type": "video/mp4"},
        data=json.dumps(meta),
        timeout=TIMEOUT,
    )
    check(init, "YouTube init")
    location = init.headers.get("Location")
    if not location:
        raise PublishError("YouTube: нет адреса для загрузки")
    with item.video.open("rb") as fh:
        up = requests.put(location, headers={**auth, "Content-Type": "video/mp4"}, data=fh, timeout=TIMEOUT * 5)
    return str(check(up, "YouTube upload")["id"])


# ---------------------------------------------------------------- core

PLATFORMS = {
    "telegram": (publish_telegram, ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID")),
    "vk": (publish_vk, ("VK_TOKEN", "VK_GROUP_ID")),
    "instagram": (publish_instagram, ("IG_ACCESS_TOKEN", "IG_USER_ID")),
    "youtube": (publish_youtube, ("YT_CLIENT_ID", "YT_CLIENT_SECRET", "YT_REFRESH_TOKEN")),
}


def load_queue() -> list[Item]:
    raw = yaml.safe_load(QUEUE.read_text(encoding="utf-8")) or []
    items = []
    for r in raw:
        if r.get("skip"):
            continue
        items.append(Item(r["id"], CONTENT / r["video"], r.get("title", r["id"]), r.get("caption", "")))
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
