#!/usr/bin/env python3
"""Проверка роликов, сценариев и подписей на правила соцсетей и закон о рекламе.

    python3 content/tools/compliance_check.py                       # вся очередь, все площадки
    python3 content/tools/compliance_check.py --platform tiktok     # одна площадка
    python3 content/tools/compliance_check.py content/semya/scripts/r02.txt   # сценарий до рендера

Уровни: ОШИБКА - публиковать нельзя (autopost пропустит элемент на этой площадке),
ВНИМАНИЕ - риск понижения показов или претензии, лучше исправить, ИНФО - напоминание.
Правила собраны в content/compliance/RULES.md. Это не юридическая консультация:
спорные пункты помечены, их стоит один раз проверить с юристом.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import yaml

CONTENT = Path(__file__).resolve().parent.parent
BRAND = yaml.safe_load((CONTENT / "brand.yaml").read_text(encoding="utf-8"))

META = ("instagram", "facebook", "threads")
ALL = ("telegram", "vk", "ok", "instagram", "facebook", "threads", "youtube", "tiktok", "pinterest", "rutube", "dzen")

# Жёсткие лимиты подписи (знаков) и длительности видео (секунд) по площадкам.
CAPTION_LIMIT = {"telegram": 1024, "instagram": 2200, "facebook": 63206, "threads": 500, "tiktok": 2200,
                 "youtube": 5000, "vk": 15000, "ok": 15000, "pinterest": 800, "rutube": 5000}
TITLE_LIMIT = {"youtube": 100, "pinterest": 100, "rutube": 100, "vk": 128}
VIDEO_MAX = {"instagram": 180, "facebook": 90, "threads": 300, "youtube": 180, "tiktok": 600,
             "vk": 180, "ok": 600, "pinterest": 300, "rutube": 600, "telegram": 3600}
HASHTAG_MAX = {"instagram": 30, "tiktok": 30, "youtube": 15, "threads": 1}
TG_FILE_LIMIT = 50 * 1024 * 1024   # Bot API не загружает файлы больше 50 МБ


@dataclass(frozen=True)
class Issue:
    level: str      # ОШИБКА | ВНИМАНИЕ | ИНФО
    code: str
    message: str


def rx(pattern: str) -> re.Pattern:
    return re.compile(pattern, re.I)


PIRACY = rx(r"\bслив\w*|\bслит\w*|скача\w*\s+(бесплатно\s+)?(платн\w+\s+)?курс|торрент|\bвзлом\w*|\bкряк|"
            r"\bcrack|warez|без\s+разрешения\s+автор")
GUARANTEE = rx(r"гарант\w*\s+(доход|заработ|результат|трудоустрой|работ)|заработ\w*\s+без\s+вложен|"
               r"пассивн\w+\s+доход|разбогате|100\s?%\s*(результат|гарант|трудоустр)|"
               r"(миллион|\d+\s?000\s?000)\s*(₽|руб)\w*\s+за\s+(месяц|недел)|быстр\w+\s+деньг")
BAIT = rx(r"напиши\s+(в\s+комментари\w+\s+)?(слово|«|\")|(в\s+)?комментари\w+\s+(слово|«)|кодов\w+\s+слов|"
          r"поставь\s+лайк,?\s+если|отметь\s+друга|репост,?\s+если|лайк,?\s+если")
COMPETITORS = rx(r"skillbox|скилбокс|скиллбокс|geekbrains|гикбрейнс|нетологи|яндекс\W?практикум|skypro|"
                 r"скайпро|\botus\b|\bотус\b|coursera|курсер|stepik|степик|skyeng|скайенг|фоксфорд")
SUPERLATIVE = rx(r"\b(лучш\w+|самы\w+\s+дешёв\w+|номер\s+один|№\s?1)\b.{0,30}\b(курс|канал|школ)")
PROMO = rx(r"\bакци\w*|\bскидк\w*|временн\w+\s+(цен|акци|предлож)|только\s+сейчас|\b1\s?511\b")
_PRICES = [BRAND.get("closed_channel", {}).get("price", ""), BRAND.get("promo", {}).get("price", ""),
           BRAND.get("promo", {}).get("old_price", "")]
_PRICE_RX = "|".join(re.escape(re.sub(r"\D", "", p)[:-3]) + r"\s?" + re.escape(re.sub(r"\D", "", p)[-3:])
                     for p in _PRICES if len(re.sub(r"\D", "", p)) > 3)
# наш платный продукт: закрытый канал, подписка или наши цены (чужие суммы вроде «курс за 60 000 ₽» - не оффер)
PAID_OFFER = rx(r"закрыт\w+\s+канал|подписк\w+\s+за|руб\w*\s+в\s+месяц" + (f"|{_PRICE_RX}" if _PRICE_RX else ""))
HASHTAG = re.compile(r"(?<!\w)#[\wё]+", re.I)


def check_text(text: str, platform: str, title: str = "") -> list[Issue]:
    out: list[Issue] = []
    low = text.lower()
    if PIRACY.search(low):
        out.append(Issue("ОШИБКА", "piracy",
                         f"«{PIRACY.search(low).group(0)}» - намёк на пиратский контент. Все площадки удаляют такое "
                         "и блокируют аккаунт; курсы у нас по лицензии - так и пишите."))
    if GUARANTEE.search(low):
        out.append(Issue("ОШИБКА", "guarantee",
                         f"«{GUARANTEE.search(low).group(0)}» - обещание дохода или результата. Запрещено правилами "
                         "Meta, TikTok, YouTube и законом о рекламе (недостоверная реклама)."))
    if PROMO.search(low):
        promo = BRAND.get("promo", {})
        if not promo.get("enabled"):
            out.append(Issue("ОШИБКА", "promo-off",
                             "Упомянута акция или скидка, но в brand.yaml акция выключена: это недостоверная реклама."))
        elif not promo.get("until"):
            out.append(Issue("ВНИМАНИЕ", "promo-no-date",
                             "Временная акция без даты окончания. Укажите promo.until в brand.yaml "
                             "(«до 30 ноября») и выключите акцию, когда она закончится."))
    if SUPERLATIVE.search(low):
        out.append(Issue("ВНИМАНИЕ", "superlative",
                         f"«{SUPERLATIVE.search(low).group(0)}» - «лучший/самый» без доказательств запрещено "
                         "законом о рекламе (ст. 5). Уберите или подтвердите."))
    if COMPETITORS.search(low):
        out.append(Issue("ВНИМАНИЕ", "competitor",
                         f"Упомянута чужая школа/сервис («{COMPETITORS.search(low).group(0)}»). Сравнение с "
                         "конкурентом в рекламе - риск претензии (ст. 5 закона о рекламе, товарный знак)."))
    if BAIT.search(low) and platform in META + ("tiktok", "youtube"):
        out.append(Issue("ВНИМАНИЕ", "engagement-bait",
                         f"«{BAIT.search(low).group(0)}» - просьба о реакции. {platform} понижает показы за "
                         "engagement bait. Лучше: «сохрани», «перешли тому, кто...»."))
    if PAID_OFFER.search(low):
        if platform in META:
            out.append(Issue("ВНИМАНИЕ", "meta-ads-ru",
                             "Продвижение платного продукта в Instagram/Facebook/Threads: в РФ с 1.09.2025 запрещена "
                             "реклама на ресурсах организаций, признанных экстремистскими (Meta). Проверьте с "
                             "юристом, прежде чем упоминать цену и закрытый канал на этих площадках."))
        out.append(Issue("ИНФО", "ad-marking",
                         "Упомянут платный продукт. Если это реклама (а не информация о своём продукте в своём "
                         "аккаунте), по закону нужна маркировка «Реклама» и erid. Уточните один раз у юриста."))
    limit = CAPTION_LIMIT.get(platform)
    if limit and len(text) > limit:
        out.append(Issue("ВНИМАНИЕ", "caption-length",
                         f"Подпись {len(text)} знаков, лимит {platform} - {limit}: хвост с призывом обрежется."))
    tlimit = TITLE_LIMIT.get(platform)
    if tlimit and len(title) > tlimit:
        out.append(Issue("ВНИМАНИЕ", "title-length", f"Заголовок {len(title)} знаков, лимит {platform} - {tlimit}."))
    tags = HASHTAG.findall(text)
    hmax = HASHTAG_MAX.get(platform)
    if platform == "threads" and len(tags) > 1:
        out.append(Issue("ИНФО", "threads-tags", f"{len(tags)} хэштегов: Threads берёт одну тему, "
                                                 "autopost оставит первый хэштег сам."))
    elif hmax and len(tags) > hmax:
        out.append(Issue("ОШИБКА" if platform == "instagram" else "ВНИМАНИЕ", "hashtags",
                         f"{len(tags)} хэштегов, лимит {platform} - {hmax}."))
    elif platform in ("instagram", "tiktok") and len(tags) > 5:
        out.append(Issue("ВНИМАНИЕ", "hashtags-many", f"{len(tags)} хэштегов: площадки советуют 3-5 по теме."))
    return out


def probe(path: Path) -> dict:
    res = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream=width,height:format=duration,size", "-of", "json", str(path)],
                         capture_output=True, text=True)
    data = json.loads(res.stdout or "{}")
    st = (data.get("streams") or [{}])[0]
    fm = data.get("format", {})
    return {"w": st.get("width", 0), "h": st.get("height", 0),
            "dur": float(fm.get("duration", 0) or 0), "size": int(fm.get("size", 0) or 0)}


def check_video(path: Path, platform: str) -> list[Issue]:
    if not path.exists():
        return [Issue("ОШИБКА", "missing", f"нет файла {path}")]
    v = probe(path)
    out = []
    vmax = VIDEO_MAX.get(platform)
    if vmax and v["dur"] > vmax:
        out.append(Issue("ОШИБКА", "duration", f"Видео {v['dur']:.0f} с, лимит {platform} - {vmax} с."))
    if v["w"] and v["h"] and abs(v["w"] / v["h"] - 9 / 16) > 0.02:
        out.append(Issue("ВНИМАНИЕ", "aspect", f"Кадр {v['w']}x{v['h']}, для Reels/Shorts нужен 9:16."))
    if platform == "telegram" and v["size"] > TG_FILE_LIMIT:
        out.append(Issue("ОШИБКА", "tg-size", f"Файл {v['size'] / 2**20:.0f} МБ, бот Telegram берёт до 50 МБ."))
    if platform == "tiktok":
        out.append(Issue("ИНФО", "ai-label", "Голос синтезирован. Мультяшный персонаж не реалистичен, но при "
                                             "публикации можно включить метку «AI-generated» - это не снижает охват."))
    return out


def script_for(rel: str) -> Path | None:
    """content/<серия>/videos|с-баннером/NN-слаг.mp4 -> content/<серия>/scripts/rNN.txt"""
    parts = Path(rel).parts
    m = re.match(r"(\d+)-", Path(rel).name)
    if not m or len(parts) < 2:
        return None
    path = CONTENT / parts[0] / "scripts" / f"r{m.group(1)}.txt"
    return path if path.exists() else None


def check_item(item: dict, platform: str) -> list[Issue]:
    caption, title = item.get("caption", ""), item.get("title", "")
    issues = check_text(caption + "\n" + title, platform, title)
    if item.get("video"):
        script = script_for(item["video"])
        if script:
            spoken = re.sub(r"[\[\]*]", "", script.read_text(encoding="utf-8"))
            issues += [Issue(i.level, i.code, "в озвучке: " + i.message) for i in check_text(spoken, platform)
                       if i.code not in ("caption-length", "hashtags", "hashtags-many", "title-length")]
        video = item.get("video_clean") if platform in META and item.get("video_clean") else item["video"]
        issues += check_video(CONTENT / video, platform)
        if platform in META and not item.get("video_clean") and BRAND.get("promo", {}).get("enabled") \
                and "semya/" in item["video"]:
            issues.append(Issue("ВНИМАНИЕ", "meta-promo-banner",
                                "В ролике вшита плашка акции с ценой. Для Instagram/Facebook/Threads сделайте версию "
                                "без неё (PROMO=0) и укажите video_clean в очереди."))
    seen, uniq = set(), []
    for i in issues:
        if (i.level, i.code) not in seen:
            seen.add((i.level, i.code)); uniq.append(i)
    return uniq


def errors(item: dict, platform: str) -> list[Issue]:
    return [i for i in check_item(item, platform) if i.level == "ОШИБКА"]


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("files", nargs="*", help="сценарии .txt (по умолчанию - вся очередь autopost)")
    p.add_argument("--platform", action="append", choices=ALL)
    p.add_argument("--quiet", action="store_true", help="не показывать ИНФО")
    args = p.parse_args()
    platforms = args.platform or list(ALL)
    bad = 0
    if args.files:
        for f in args.files:
            text = re.sub(r"[\[\]*]", "", Path(f).read_text(encoding="utf-8"))
            for pl in platforms:
                for i in check_text(text, pl):
                    if args.quiet and i.level == "ИНФО":
                        continue
                    bad += i.level == "ОШИБКА"
                    print(f"{f} [{pl}] {i.level}: {i.message}")
    else:
        queue = yaml.safe_load((CONTENT / "autopost" / "queue.yaml").read_text(encoding="utf-8")) or []
        for item in queue:
            for pl in platforms:
                for i in check_item(item, pl):
                    if args.quiet and i.level == "ИНФО":
                        continue
                    bad += i.level == "ОШИБКА"
                    print(f"{item['id']} [{pl}] {i.level}: {i.message}")
    print(f"\nошибок: {bad}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
