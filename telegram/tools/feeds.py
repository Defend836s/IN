#!/usr/bin/env python3
"""Свежие новости для канала: собирает RSS, отбирает по ключевым словам, убирает уже использованное.

    python3 telegram/tools/feeds.py kzn            # новости для канала kzn (JSON)
    python3 telegram/tools/feeds.py kzn --md       # то же, списком для чтения
    python3 telegram/tools/feeds.py --list         # все каналы из channels.yaml

Отдаёт заголовок, краткое описание, ссылку, источник и время. Сам пост агент пишет
своими словами по фактам из источника, со ссылкой на него (не копируя текст).
Использованные новости отмечает telegram/tools/tg.py после публикации.
"""
from __future__ import annotations

import argparse
import email.utils
import hashlib
import html
import json
import re
import sys
import time
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG = yaml.safe_load((ROOT / "channels.yaml").read_text(encoding="utf-8"))
STATE = ROOT / "state"
UA = {"User-Agent": "Mozilla/5.0 (compatible; VseKursyNewsroom/1.0)"}


def channel(cid: str) -> dict:
    for ch in CONFIG["channels"]:
        if ch["id"] == cid:
            return {**CONFIG["defaults"].get(ch["type"], {}), **ch}
    raise SystemExit(f"нет канала {cid}; есть: {', '.join(c['id'] for c in CONFIG['channels'])}")


def key(title: str) -> str:
    norm = re.sub(r"\W+", " ", title.lower()).strip()
    return hashlib.sha1(norm.encode()).hexdigest()[:16]


def seen(cid: str) -> set[str]:
    path = STATE / f"seen-{cid}.json"
    return set(json.loads(path.read_text())) if path.exists() else set()


def mark_seen(cid: str, keys: list[str]) -> None:
    STATE.mkdir(exist_ok=True)
    path = STATE / f"seen-{cid}.json"
    data = list(seen(cid) | set(keys))[-5000:]
    path.write_text(json.dumps(data))


def parse_date(text: str | None) -> datetime | None:
    if not text:
        return None
    try:
        return email.utils.parsedate_to_datetime(text).astimezone(timezone.utc)
    except (TypeError, ValueError):
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(timezone.utc)
        except ValueError:
            return None


def clean(text: str | None) -> str:
    text = html.unescape(re.sub(r"<[^>]+>", " ", text or ""))
    return re.sub(r"\s+", " ", text).strip()


def fetch(url: str, source: str) -> list[dict]:
    root = None
    for attempt in range(3):
        try:
            resp = requests.get(url, headers=UA, timeout=20, allow_redirects=True)
            if resp.status_code == 429:
                time.sleep(3 * (attempt + 1))
                continue
            resp.raise_for_status()
            root = ET.fromstring(resp.content)
            break
        except (requests.RequestException, ET.ParseError) as exc:
            if attempt == 2:
                print(f"{source}: не загрузилось ({exc})", file=sys.stderr)
            time.sleep(2)
    if root is None:
        return []
    items = []
    for it in root.iter("item"):
        src = it.find("source")
        items.append({
            "title": clean(it.findtext("title")),
            "summary": clean(it.findtext("description"))[:600],
            "link": (it.findtext("link") or "").strip(),
            "source": clean(src.text) if src is not None and src.text else source,
            "published": parse_date(it.findtext("pubDate")),
        })
    return items


def collect(cid: str) -> list[dict]:
    ch = channel(cid)
    items = []
    for name in ch.get("feeds", []):
        items += fetch(CONFIG["feeds"][name], name)
    if ch.get("google_news"):
        q = urllib.parse.quote(ch["google_news"])
        items += fetch(f"https://news.google.com/rss/search?q={q}&hl=ru&gl=RU&ceid=RU:ru", "google_news")
    include = [re.compile(p, re.I) for p in ch.get("include", [])]
    cutoff = datetime.now(timezone.utc) - timedelta(hours=ch.get("max_age_hours", 6))
    used, out, keys = seen(cid), [], set()
    for it in items:
        k = key(it["title"])
        if k in used or k in keys or not it["title"]:
            continue
        if it["published"] and it["published"] < cutoff:
            continue
        text = it["title"] + " " + it["summary"]
        from_search = it["link"].startswith("https://news.google.com")
        if include and not from_search and not any(p.search(text) for p in include):
            continue
        keys.add(k)
        out.append({**it, "key": k, "published": it["published"].isoformat() if it["published"] else None})
    out.sort(key=lambda x: x["published"] or "", reverse=True)
    return out


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("channel", nargs="?")
    p.add_argument("--md", action="store_true")
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--list", action="store_true")
    a = p.parse_args()
    if a.list or not a.channel:
        for ch in CONFIG["channels"]:
            print(f"{ch['id']:12} {ch['type']:12} {ch['title']:32} {ch.get('chat') or '(черновики)'}")
        return 0
    news = collect(a.channel)[: a.limit]
    if a.md:
        for n in news:
            print(f"- [{n['published'] or '?'}] {n['source']}: {n['title']}\n  {n['summary'][:200]}\n  {n['link']}")
    else:
        print(json.dumps(news, ensure_ascii=False, indent=1))
    print(f"\nсвежих: {len(news)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
