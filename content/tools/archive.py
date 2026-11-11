#!/usr/bin/env python3
"""Материалы для роликов-расследований истории из мировых архивов.

Источники (только то, что можно публиковать без разрешения правообладателя):
- Библиотека Конгресса США (loc.gov) - снимки с пометкой «No known restrictions on publication»;
- Wikimedia Commons (через API Википедии) - лицензии Public domain / PD-* / CC0.
Снимки с CC BY-SA, «все права защищены» и без указанных прав отбрасываются.

    python3 content/tools/archive.py facts "Братья Райт" content/history/media/01
        -> facts.md: текст статьи Википедии с адресом - основа сценария, факты только отсюда
    python3 content/tools/archive.py photos "Wright brothers flight" content/history/media/01 [--n 6]
        [--source loc|wikimedia]
        -> 01.jpg, 02.jpg ... и sources.yaml (название, автор, дата, лицензия, страница архива).
        Снимки дописываются к уже скачанным; не по теме - удалить файл и запись в sources.yaml.
    python3 content/tools/archive.py credit content/history/media/01
        -> строка для подписи к ролику: «Фото: Библиотека Конгресса США (общественное достояние)»

Запросы к снимкам лучше писать по-английски: в архивах так больше находок.
Если Wikimedia отвечает «слишком много запросов» (429), инструмент ждёт и повторяет.
"""
from __future__ import annotations

import io
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import yaml
from PIL import Image

UA = {"User-Agent": "ArchiveResearchTool/1.0 (educational short videos)"}
FREE = re.compile(r"public domain|^pd\b|^pd-|cc0|no known restrictions", re.I)
MIN_SIDE = 700                      # мельче - на весь экран будет мыло
MAX_SIDE = 2000                     # крупнее не нужно, ролик 1080 по ширине
THUMB_W = 1280                      # стандартная ширина миниатюр Wikimedia


def _get(url: str, tries: int = 4, binary: bool = False):
    delay = 5.0
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
                data = r.read()
            return data if binary else json.loads(data)
        except urllib.error.HTTPError as e:
            if e.code in (429, 503) and attempt < tries - 1:
                print(f"  архив просит подождать ({e.code}), жду {delay:.0f} с", file=sys.stderr)
                time.sleep(delay)
                delay *= 2
                continue
            raise
    raise RuntimeError(f"архив не ответил: {url}")


def _api(host: str, **params) -> dict:
    return _get(f"https://{host}/w/api.php?" + urllib.parse.urlencode({**params, "format": "json"}))


def _plain(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", html or "")).strip()


# ------------------------------------------------------------------ поиск снимков

def search_loc(query: str, n: int) -> list[dict]:
    url = ("https://www.loc.gov/photos/?" + urllib.parse.urlencode(
        {"q": query, "fo": "json", "c": max(n * 3, 15), "fa": "online-format:image"}))
    out = []
    for r in _get(url).get("results", []):
        rights = r.get("item", {}).get("rights_advisory") or r.get("rights_advisory") or ""
        rights = " ".join(rights) if isinstance(rights, list) else str(rights)   # бывает строкой и списком
        images = [u for u in r.get("image_url", []) if "tile.loc.gov" in u]
        if not FREE.search(rights) or not images:
            continue
        out.append({"source": "Библиотека Конгресса США", "title": r.get("title", ""),
                    "date": r.get("date", ""), "author": "", "license": "No known restrictions on publication",
                    "page": r.get("id", "").replace("http://", "https://"),
                    "url": images[-1].split("#")[0]})
    return out


def search_wikimedia(query: str, n: int) -> list[dict]:
    d = _api("en.wikipedia.org", action="query", generator="search", gsrsearch=f"{query} filetype:bitmap",
             gsrnamespace=6, gsrlimit=max(n * 3, 15), prop="imageinfo", iiprop="url|extmetadata|size")
    out = []
    for p in sorted(d.get("query", {}).get("pages", {}).values(), key=lambda p: p.get("index", 0)):
        ii = (p.get("imageinfo") or [{}])[0]
        meta = ii.get("extmetadata", {})
        lic = meta.get("LicenseShortName", {}).get("value", "")
        if not FREE.search(lic) or min(ii.get("width", 0), ii.get("height", 0)) < MIN_SIDE:
            continue
        out.append({"source": "Wikimedia Commons", "title": _plain(meta.get("ImageDescription", {}).get("value", ""))[:200]
                    or p["title"], "date": _plain(meta.get("DateTimeOriginal", {}).get("value", ""))[:40],
                    "author": _plain(meta.get("Artist", {}).get("value", ""))[:120], "license": lic,
                    "page": ii.get("descriptionurl", ""), "url": _thumb(ii.get("url", ""), ii.get("width", 0))})
    return out


def _thumb(url: str, width: int) -> str:
    """Wikimedia отдаёт ботам оригиналы с ограничением (429), а картинки стандартной ширины -
    свободно (https://w.wiki/GHai). Берём 1280 точек: для ролика 1080x1920 этого хватает."""
    url = url.split("?")[0]
    if width <= THUMB_W or "/commons/" not in url:
        return url
    head, name = url.rsplit("/", 1)
    return f"{head.replace('/commons/', '/commons/thumb/')}/{name}/{THUMB_W}px-{name}"


FINDERS = {"loc": "search_loc", "wikimedia": "search_wikimedia"}


def photos(query: str, folder: str, n: int = 6, source: str | None = None) -> list[dict]:
    """Скачать до n свободных снимков в folder (01.jpg...) и записать sources.yaml.
    source: loc | wikimedia | None (оба). Скачанные снимки обязательно посмотреть:
    не по теме - удалить файл и его запись в sources.yaml."""
    out_dir = Path(folder)
    out_dir.mkdir(parents=True, exist_ok=True)
    src_file = out_dir / "sources.yaml"
    sources = yaml.safe_load(src_file.read_text(encoding="utf-8")) if src_file.exists() else {}
    sources = sources or {}
    found = []
    for finder in [globals()[FINDERS[k]] for k in ([source] if source else FINDERS)]:
        try:
            found += finder(query, n)
        except Exception as e:  # один архив недоступен - берём из другого
            print(f"  {finder.__name__}: {e}", file=sys.stderr)
    known = {s["url"] for s in sources.values()} | {s["title"] for s in sources.values()}   # без повторов
    num = max([int(k) for k in sources] or [0])
    saved = []
    for item in found:
        if len(saved) >= n or item["url"] in known or item["title"] in known:
            continue
        known |= {item["url"], item["title"]}
        try:
            img = Image.open(io.BytesIO(_get(item["url"], binary=True))).convert("RGB")
        except Exception as e:
            print(f"  не скачалось {item['url']}: {e}", file=sys.stderr)
            continue
        if min(img.size) < MIN_SIDE * 0.9:
            continue
        img.thumbnail((MAX_SIDE, MAX_SIDE))
        num += 1
        key = f"{num:02d}"
        img.save(out_dir / f"{key}.jpg", quality=90)
        sources[key] = {**item, "query": query}
        saved.append(sources[key])
        print(f"{key}.jpg  {item['source']}: {item['title'][:70]} ({item['date']}) [{item['license']}]")
        time.sleep(1.0)        # бережно к архивам
    src_file.write_text(yaml.safe_dump(sources, allow_unicode=True, sort_keys=True), encoding="utf-8")
    if not saved:
        print("свободных снимков не нашлось - попробуйте другой запрос (по-английски, короче)", file=sys.stderr)
    return saved


# ------------------------------------------------------------------ факты

def facts(title: str, folder: str, lang: str = "ru") -> Path:
    """Текст статьи Википедии с адресом: из него и только из него берутся факты сценария."""
    d = _api(f"{lang}.wikipedia.org", action="query", prop="extracts|info", inprop="url", explaintext=1,
             redirects=1, titles=title)
    page = next(iter(d["query"]["pages"].values()))
    if "missing" in page:
        hits = _api(f"{lang}.wikipedia.org", action="query", list="search", srsearch=title, srlimit=5)
        names = [h["title"] for h in hits["query"]["search"]]
        raise SystemExit(f"статьи «{title}» нет. Похожие: {', '.join(names)}")
    text = page.get("extract", "")
    out = Path(folder) / "facts.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(f"# {page['title']}\n\nИсточник: {page['fullurl']}\n"
                   f"Получено: {time.strftime('%Y-%m-%d')}\n\n{text}\n", encoding="utf-8")
    print(f"{out}  ({len(text)} знаков) {page['fullurl']}")
    return out


def credit(folder: str) -> str:
    """Подпись об источниках для текста под роликом."""
    src_file = Path(folder) / "sources.yaml"
    sources = yaml.safe_load(src_file.read_text(encoding="utf-8")) if src_file.exists() else {}
    archives = sorted({s["source"] for s in (sources or {}).values()})
    fact_src = ""
    facts_file = Path(folder) / "facts.md"
    if facts_file.exists():
        m = re.search(r"^Источник: (\S+)", facts_file.read_text(encoding="utf-8"), re.M)
        fact_src = f"Факты: Википедия ({urllib.parse.unquote(m.group(1))}). " if m else ""
    photos_src = f"Фото: {', '.join(archives)} (общественное достояние)." if archives else ""
    return (fact_src + photos_src).strip()


if __name__ == "__main__":
    args = sys.argv[1:]
    if len(args) >= 3 and args[0] == "facts":
        facts(args[1], args[2], *(args[3:4]))
    elif len(args) >= 3 and args[0] == "photos":
        n = int(args[args.index("--n") + 1]) if "--n" in args else 6
        photos(args[1], args[2], n, args[args.index("--source") + 1] if "--source" in args else None)
    elif len(args) == 2 and args[0] == "credit":
        print(credit(args[1]))
    else:
        print(__doc__)
        sys.exit(2)
