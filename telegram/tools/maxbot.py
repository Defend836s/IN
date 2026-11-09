#!/usr/bin/env python3
"""Публикация в каналы мессенджера MAX - те же каналы и правила, что для Telegram.

    python3 telegram/tools/maxbot.py me                          # проверить ключ бота
    python3 telegram/tools/maxbot.py discover                    # id каналов, куда добавлен бот
    python3 telegram/tools/maxbot.py check kazan post.html       # только проверка правил
    python3 telegram/tools/maxbot.py post kazan post.html [--photo img.png] [--keys k1,k2] [--dry-run]

API: https://platform-api2.max.ru (документация dev.max.ru/docs-api). Ключ - переменная
MAX_BOT_TOKEN, передаётся заголовком Authorization (query-параметр MAX больше не принимает).
Домен подписан сертификатом Минцифры: он лежит в telegram/certs/ и добавляется к
доверенным только для запросов этого скрипта.

Канал MAX - поле max_chat в channels.yaml / cities.yaml (число). Получить его можно только
из события bot_added: добавьте бота администратором в канал и запустите discover.
Нет ключа или max_chat - пост сохраняется черновиком в telegram/drafts/max-<канал>/.
Правила проверки - те же, что в tg.py (telegram/RULES.md); лимит текста MAX - 4000 знаков.
Опросов в Bot API MAX нет. Лимиты MAX: 2 сообщения в секунду в канал, 30 запросов в секунду.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
import time
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
import feeds  # noqa: E402
import tg  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
API = "https://platform-api2.max.ru"
CERT = ROOT / "certs" / "russian_trusted_ca.pem"
TEXT_LIMIT = 4000
_last_send: dict[str, float] = {}


@lru_cache(maxsize=1)
def ca_bundle() -> str:
    """Обычный список доверенных (или прокси облака) + сертификат Минцифры - во временный файл."""
    base = os.environ.get("REQUESTS_CA_BUNDLE") or requests.certs.where()
    fd, path = tempfile.mkstemp(prefix="max-ca-", suffix=".pem")
    with os.fdopen(fd, "w") as out:
        out.write(Path(base).read_text() + "\n" + CERT.read_text())
    return path


def token() -> str | None:
    return os.environ.get("MAX_BOT_TOKEN", "").strip() or None


def call(method: str, path: str, *, params: dict | None = None, body: dict | None = None,
         files: dict | None = None, url: str | None = None) -> dict:
    headers = {"Authorization": token() or ""}
    data: dict = {}
    for attempt in range(6):
        resp = requests.request(method, url or API + path, params=params, json=body, files=files,
                                headers=headers, timeout=60, verify=ca_bundle())
        try:
            data = resp.json()
        except ValueError:
            data = {"raw": resp.text[:300]}
        code = data.get("code") if isinstance(data, dict) else None
        if resp.status_code == 429 or code == "attachment.not.ready":
            time.sleep(2 ** attempt)   # лимит или файл ещё обрабатывается - ждём и повторяем
            continue
        if resp.status_code >= 400:
            raise SystemExit(f"MAX {method} {path or url}: HTTP {resp.status_code} {data}")
        return data
    raise SystemExit(f"MAX {method} {path or url}: не удалось после повторов ({data})")


def upload_image(photo: str) -> dict:
    slot = call("POST", "/uploads", params={"type": "image"})
    with open(photo, "rb") as fh:
        uploaded = call("POST", "", url=slot["url"], files={"data": (Path(photo).name, fh)})
    payload = {"photos": uploaded["photos"]} if "photos" in uploaded else {"token": uploaded.get("token")}
    return {"type": "image", "payload": payload}


def target(cid: str) -> str | None:
    chat = str(feeds.channel(cid).get("max_chat") or "").strip()
    return chat if chat and token() else None


def check(cid: str, text: str, photo: bool = False) -> list[str]:
    errs = [e for e in tg.check(cid, text, photo) if not e.startswith("длина")]
    plain_len = len(re.sub(r"<[^>]+>", "", text))
    if plain_len > TEXT_LIMIT:
        errs.append(f"длина {plain_len} > {TEXT_LIMIT} (лимит MAX)")
    return errs


def draft(cid: str, text: str, photo: str | None, reason: str) -> None:
    folder = ROOT / "drafts" / f"max-{cid}"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / (datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S") + ".html")
    path.write_text((f"<!-- photo: {photo} -->\n" if photo else "") + text, encoding="utf-8")
    print(f"черновик: {path} ({reason})")


def post(a: argparse.Namespace) -> int:
    text = Path(a.file).read_text(encoding="utf-8").strip()
    errs = check(a.channel, text, bool(a.photo))
    if errs:
        print("НЕ ОПУБЛИКОВАНО:\n- " + "\n- ".join(errs))
        return 1
    keys = [k for k in (a.keys or "").split(",") if k]
    chat = target(a.channel)
    if not chat or a.dry_run:
        draft(a.channel, text, a.photo, "проба" if a.dry_run else "нет MAX_BOT_TOKEN или max_chat")
        if keys and not a.dry_run:
            feeds.mark_seen(a.channel, keys, "max")
        return 0
    wait = 0.6 - (time.time() - _last_send.get(chat, 0))   # не больше 2 сообщений в секунду в канал
    if wait > 0:
        time.sleep(wait)
    body = {"text": text, "format": "html"}
    if a.photo:
        body["attachments"] = [upload_image(a.photo)]
        time.sleep(1)                                        # MAX обрабатывает файл после загрузки
    res = call("POST", "/messages", params={"chat_id": chat}, body=body)
    _last_send[chat] = time.time()
    feeds.mark_seen(a.channel, keys, "max")
    mid = (res.get("message") or {}).get("body", {}).get("mid")
    log = ROOT / "state" / f"posts-max-{a.channel}.jsonl"
    log.parent.mkdir(exist_ok=True)
    with log.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "mid": mid,
                             "keys": keys}, ensure_ascii=False) + "\n")
    print(f"опубликовано в MAX: {a.channel} mid={mid}")
    return 0


def discover(_: argparse.Namespace) -> int:
    """Каналы и чаты, куда добавили бота (события bot_added из GET /updates)."""
    if not token():
        raise SystemExit("нет MAX_BOT_TOKEN")
    data = call("GET", "/updates", params={"types": "bot_added,bot_removed", "limit": 100, "timeout": 0})
    chats: dict[int, str] = {}
    for upd in data.get("updates", []):
        cid = upd.get("chat_id")
        if upd.get("update_type") == "bot_removed":
            chats.pop(cid, None)
        elif cid:
            chats[cid] = "канал" if upd.get("is_channel") else "чат"
    if not chats:
        print("событий bot_added нет: добавьте бота администратором в канал и запустите снова "
              "(MAX хранит события ограниченное время)")
    for cid, kind in chats.items():
        title = call("GET", f"/chats/{cid}").get("title", "")
        print(f"{cid}\t{kind}\t{title}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("me").set_defaults(func=lambda a: (print(json.dumps(call("GET", "/me"), ensure_ascii=False)), 0)[1])
    sub.add_parser("discover").set_defaults(func=discover)
    c = sub.add_parser("check"); c.add_argument("channel"); c.add_argument("file"); c.add_argument("--photo")
    c.set_defaults(func=lambda a: (print("\n".join(check(a.channel, Path(a.file).read_text(encoding="utf-8"),
                                                          bool(a.photo))) or "ок"), 0)[1])
    s = sub.add_parser("post"); s.add_argument("channel"); s.add_argument("file")
    s.add_argument("--photo"); s.add_argument("--keys"); s.add_argument("--dry-run", action="store_true")
    s.set_defaults(func=post)
    a = p.parse_args()
    return a.func(a)


if __name__ == "__main__":
    sys.exit(main())
