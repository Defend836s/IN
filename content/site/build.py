#!/usr/bin/env python3
"""Сайт-витрина роликов и каруселей + RSS-лента для импорта в Дзен.

    python3 content/site/build.py                 # собрать site/ (нужен base_url в site.yaml)
    python3 content/site/build.py --preview       # проба с base_url=http://localhost:8000 (во временной папке, без учёта)
    python3 content/site/build.py --check         # только проверить site/dzen.xml по требованиям Дзена

Что получается в site/ (загружается на хостинг как есть):
  index.html                  - главная со списком материалов
  p/<id>/index.html           - страница каждого ролика/карусели (ЧПУ-адрес, его Дзен берёт в <link>)
  media/...                   - mp4, слайды и обложки (обложка ролика - кадр 1080x1920, шире 700 px)
  dzen.xml                    - лента в формате Дзена (category format-post, native-draft/publish)
  robots.txt                  - открывает ленту роботу
Материалы берутся из content/autopost/queue.yaml по порядку очереди; что и когда ушло в
ленту - в content/site/state.json (Дзен просит не отправлять материал повторно и держать
в ленте только последние 2-3 дня). Перед добавлением каждый материал проходит
compliance_check (площадка dzen). Требования Дзена: dzen.ru/help/ru/website/rss-modify.html
"""
from __future__ import annotations

import argparse
import html
import json
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
CONTENT = HERE.parent
REPO = CONTENT.parent
OUT = REPO / "site"
STATE = HERE / "state.json"
CFG = yaml.safe_load((HERE / "site.yaml").read_text(encoding="utf-8"))
BRAND = yaml.safe_load((CONTENT / "brand.yaml").read_text(encoding="utf-8"))
MSK = timezone(timedelta(hours=3))

sys.path.insert(0, str(CONTENT / "tools"))
import compliance_check  # noqa: E402


def esc(s: str) -> str:
    return html.escape(s, quote=True)


def dzen_text(text: str) -> str:
    """Подпись для Дзена: без хэштегов в конце, «ссылка в профиле» -> «в описании канала»."""
    text = re.sub(r"(\s*#[\wё]+)+\s*$", "", text.strip(), flags=re.I)
    return text.replace(f"{BRAND['link_hint']}.", "Ссылки - в описании канала.")


def paragraphs(text: str) -> str:
    """Подпись -> <p>."""
    text = dzen_text(text)
    blocks = [b.strip() for b in re.split(r"\n\s*\n", text) if b.strip()]
    return "".join(f"<p>{esc(b).replace(chr(10), '<br>')}</p>" for b in blocks)


def load_state() -> dict:
    return json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {"sent": {}}


def poster(video: Path, dest: Path) -> None:
    if not dest.exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-ss", "1.0", "-i", str(video), "-frames:v", "1",
                        "-q:v", "3", str(dest)], check=True)


def copy(src: Path, dest: Path) -> None:
    if not dest.exists() or dest.stat().st_size != src.stat().st_size:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)


def materialize(item: dict, base: str) -> dict:
    """Копирует медиа в site/media и возвращает данные для страницы и ленты."""
    iid = item["id"]
    media = []
    if item.get("video"):
        src = CONTENT / item["video"]
        copy(src, OUT / "media" / iid / "video.mp4")
        poster(src, OUT / "media" / iid / "cover.jpg")
        media = [("video", f"{base}/media/{iid}/video.mp4")]
        cover = f"{base}/media/{iid}/cover.jpg"
    else:
        for i, rel in enumerate(item.get("images", []), 1):
            copy(CONTENT / rel, OUT / "media" / iid / f"{i:02d}.png")
            media.append(("image", f"{base}/media/{iid}/{i:02d}.png"))
        cover = media[0][1]
    return {"id": iid, "title": item.get("title", iid), "caption": item.get("caption", ""),
            "media": media, "cover": cover, "url": f"{base}/p/{iid}/"}


def media_html(m: dict) -> str:
    out = []
    for kind, url in m["media"]:
        if kind == "video":
            out.append(f'<video controls playsinline poster="{m["cover"]}"><source src="{url}" type="video/mp4"/></video>')
        else:
            out.append(f'<figure><img src="{url}"/></figure>')
    return "".join(out)


PAGE = """<!doctype html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">{verify}
<title>{title}</title><meta name="description" content="{desc}">
<link rel="alternate" type="application/rss+xml" href="{base}/dzen.xml">
<style>body{{font:18px/1.5 system-ui,sans-serif;max-width:720px;margin:0 auto;padding:24px;background:#0a1a4f;color:#fff}}
a{{color:#ffcd3c}}video,img{{max-width:100%;border-radius:16px;display:block;margin:16px auto}}
.card{{display:block;padding:16px 0;border-bottom:1px solid #26407f;text-decoration:none}}</style></head>
<body><header><a href="{base}/"><b>{site}</b></a></header>{body}
<footer><p>{updates}. {free}.</p></footer></body></html>"""


def page(title: str, desc: str, body: str, base: str) -> str:
    verify = (f'\n<meta name="zen-verification" content="{esc(CFG["dzen_verification"])}">'
              if CFG.get("dzen_verification") else "")
    return PAGE.format(verify=verify, title=esc(title), desc=esc(desc), base=base, site=esc(CFG["title"]),
                       body=body, updates=esc(BRAND["updates"]), free=esc(BRAND["free_channel"]["pitch"]))


def rss(entries: list[dict], state: dict, base: str) -> str:
    cat_mode = "native-draft" if CFG.get("mode", "draft") == "draft" else None
    items = []
    for m in entries:
        sent = datetime.fromisoformat(state["sent"][m["id"]])
        cats = "".join(f"<category>{c}</category>" for c in filter(None, [cat_mode, "format-post", "index",
                                                                         "comment-all"]))
        content = paragraphs(m["caption"]) + media_html(m)
        desc = esc(re.sub(r"\s+", " ", dzen_text(m["caption"]))[:300])
        ctype = "image/jpeg" if m["cover"].endswith(".jpg") else "image/png"
        items.append(f"""<item>
<title>{esc(m['title'])}</title>
<link>{m['url']}</link>
<guid>{esc(m['id'])}</guid>
<pubDate>{format_datetime(sent.astimezone(MSK))}</pubDate>
<media:rating scheme="urn:simple">nonadult</media:rating>
{cats}
<description>{desc}</description>
<enclosure url="{m['cover']}" type="{ctype}"/>
<content:encoded><![CDATA[{content}]]></content:encoded>
</item>""")
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/" '
            'xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:media="http://search.yahoo.com/mrss/" '
            'xmlns:atom="http://www.w3.org/2005/Atom" xmlns:georss="http://www.georss.org/georss">\n'
            f'<channel>\n<title>{esc(CFG["title"])}</title>\n<link>{base}/</link>\n<language>ru</language>\n'
            + "\n".join(items) + "\n</channel>\n</rss>\n")


def check_feed(path: Path) -> list[str]:
    ns = {"content": "http://purl.org/rss/1.0/modules/content/", "media": "http://search.yahoo.com/mrss/"}
    root = ET.parse(path).getroot()
    errs, items = [], root.findall("./channel/item")
    state = load_state()
    if len(state["sent"]) <= len(items) and len(items) < 10:
        errs.append(f"первая лента: {len(items)} материалов, Дзен требует минимум 10")
    if len(items) > 500:
        errs.append("больше 500 материалов за раз")
    guids = [i.findtext("guid") for i in items]
    if len(set(guids)) != len(guids):
        errs.append("повторяются guid")
    for it in items:
        gid = it.findtext("guid")
        for tag in ("title", "link", "guid", "pubDate", "enclosure", "content:encoded"):
            if it.find(tag, ns) is None:
                errs.append(f"{gid}: нет обязательного <{tag}>")
        link = it.findtext("link") or ""
        if "?" in link or "utm_" in link:
            errs.append(f"{gid}: адрес с параметрами - Дзен просит ЧПУ без UTM")
        if len(re.sub(r"<[^>]+>", "", it.findtext("content:encoded", "", ns))) < 50:
            errs.append(f"{gid}: слишком короткий текст")
    return errs


def build(base: str) -> int:
    queue = yaml.safe_load((CONTENT / "autopost" / "queue.yaml").read_text(encoding="utf-8")) or []
    state = load_state()
    now = datetime.now(timezone.utc)
    need = CFG["first_build"] if not state["sent"] else CFG["per_build"]
    added = 0
    for item in queue:
        if added >= need or item.get("skip") or item["id"] in state["sent"]:
            continue
        errs = compliance_check.errors(item, "dzen")
        if errs:
            print(f"{item['id']}: пропущен - {'; '.join(e.message for e in errs)}")
            continue
        state["sent"][item["id"]] = (now + timedelta(seconds=added)).isoformat()
        added += 1
    by_id = {i["id"]: i for i in queue}
    all_sent = [by_id[i] for i in state["sent"] if i in by_id]
    fresh_ids = {i for i, at in state["sent"].items()
                 if now - datetime.fromisoformat(at) <= timedelta(days=CFG["keep_days"])}
    pages = [materialize(i, base) for i in all_sent]
    for m in pages:
        body = f"<article><h1>{esc(m['title'])}</h1>{media_html(m)}{paragraphs(m['caption'])}</article>"
        (OUT / "p" / m["id"]).mkdir(parents=True, exist_ok=True)
        (OUT / "p" / m["id"] / "index.html").write_text(page(m["title"], m["caption"][:160], body, base), "utf-8")
    cards = "".join(f'<a class="card" href="{m["url"]}"><b>{esc(m["title"])}</b></a>' for m in reversed(pages))
    (OUT / "index.html").write_text(page(CFG["title"], CFG["description"],
                                         f"<p>{esc(CFG['description'])}</p>{cards}", base), "utf-8")
    (OUT / "dzen.xml").write_text(rss([m for m in pages if m["id"] in fresh_ids], state, base), "utf-8")
    (OUT / "robots.txt").write_text("User-agent: *\nAllow: /\nAllow: /dzen.xml\n", "utf-8")
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=1) + "\n", "utf-8")
    errs = check_feed(OUT / "dzen.xml")
    print(f"{OUT}: страниц {len(pages)}, в ленте dzen.xml {len(fresh_ids)} (новых {added}), режим {CFG['mode']}")
    print("лента по требованиям Дзена: " + ("ок" if not errs else "\n- " + "\n- ".join(errs)))
    return 1 if errs else 0


def main() -> int:
    global STATE, OUT
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--preview", action="store_true")
    p.add_argument("--check", action="store_true")
    a = p.parse_args()
    if a.check:
        errs = check_feed(OUT / "dzen.xml")
        print("ок" if not errs else "\n".join(errs))
        return 1 if errs else 0
    base = "http://localhost:8000" if a.preview else (CFG.get("base_url") or "").rstrip("/")
    if not base:
        raise SystemExit("в content/site/site.yaml не задан base_url (домен сайта, привязанного к каналу Дзена); "
                         "для пробы - --preview")
    if a.preview:   # проба не «расходует» материалы: отдельные папка и состояние во временном каталоге
        tmp = Path(tempfile.mkdtemp(prefix="site-preview-"))
        STATE, OUT = tmp / "state.json", tmp / "site"
        OUT.mkdir()
    return build(base)


if __name__ == "__main__":
    sys.exit(main())
