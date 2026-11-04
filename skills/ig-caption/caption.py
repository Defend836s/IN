#!/usr/bin/env python3
"""
caption.py - проверяет подпись к посту в Instagram и показывает ровно то, что
видно в ленте до «... ещё».

В ленте Instagram показывает примерно 125 символов подписи, а остальное прячет
за тапом. Почти каждая неудачная подпись проваливается именно там: хук в
третьем предложении, первая строка - приветствие, или всё начинается с
хэштега. Скрипт печатает видимое окно в рамке, чтобы вы прочитали его так, как
читает незнакомый человек, листающий ленту, а потом проверяет то, что стоит
проверять.

Обрезка на 125 символах - приближение. Реальное число зависит от устройства,
размера шрифта и переносов строк, поэтому нужен запас, а не подпись, которая
ровно заканчивается на 125-м символе. Можно задать своё значение через
--truncate.

Понимает русский и английский текст.

Запуск
  python3 caption.py caption.txt
  python3 caption.py caption.txt --keywords "договор с клиентом,цены на дизайн"
  pbpaste | python3 caption.py -
  python3 caption.py caption.txt --json
"""

import argparse
import json
import re
import sys
import textwrap

LIMIT = 2200             # жёсткий лимит подписи в Instagram.
TRUNCATE = 125           # примерно здесь лента обрезает текст до «... ещё».
HASHTAG_LIMIT = 5        # лимит Instagram на пост или Reels с 18 декабря 2025
                         # (раньше было 30). Аккаунт @Creators объяснил это так:
                         # меньше (до 5) точных хэштегов вместо множества общих
                         # работает лучше и для контента, и для людей.

HASHTAG_RE = re.compile(r"(?:^|\s)(#\w+)")
MENTION_RE = re.compile(r"(?:^|\s)(@[A-Za-z0-9_.]+)")
LINK_RE = re.compile(r"https?://\S+|\bwww\.\S+|\b[a-zа-яё0-9-]+\.(?:com|co|io|net|org|ai|app|ru|рф|su|me|pro)/\S*",
                     re.IGNORECASE)
EMOJI_RE = re.compile(r"[\U0001F300-\U0001FAFF☀-➿←-⇿️]")
CONCRETE_RE = re.compile(r"[$€]\s?\d|\b\d[\d,.]*|(?<!^)(?<![.!?]\s)\b[A-ZА-ЯЁ][a-zа-яё]{2,}\b",
                         re.MULTILINE)

ASKS = [
    (re.compile(r"(?i)\bcomment (?:the word |\")?[A-Z0-9]{2,}\b"
                r"|\b(?:[Нн]апиш|[Пп]иш|[Оо]ставь)(?:и|ите|те)?\s+(?:мне\s+)?(?:в\s+(?:комментари\w*|комментах|комменты)\s+)?"
                r"(?:слово\s+)?[«\"]?(?-i:[A-ZА-ЯЁ0-9]{2,})\b"), "кодовое слово в комментариях"),
    (re.compile(r"(?i)\b(?:dm|message) me\b|\b(?:напиш|пиш)(?:и|ите)\s+(?:мне\s+)?в\s+(?:директ|личк\w*|лс|direct|сообщени\w*)\b"),
     "написать в директ"),
    (re.compile(r"(?i)\bsave (?:this|it)\b|\bсохран(?:и|ите|яй|яйте)\b"), "сохранить"),
    (re.compile(r"(?i)\bshare (?:this|it)\b|\b(?:отправь|отправьте|перешли|перешлите|поделись|поделитесь)\b"),
     "поделиться"),
    (re.compile(r"(?i)\bfollow (?:me|for)\b|\b(?:подпишись|подпишитесь|подписывайся|подписывайтесь)\b"),
     "подписаться"),
    (re.compile(r"(?i)\blink in (?:my )?bio\b|\bссылк\w* в (?:шапке|био|профиле|описании профиля)\b"),
     "ссылка в шапке"),
    (re.compile(r"(?i)\b(?:swipe|tap) (?:through|left|right|for|to)\b|\b(?:листай|листайте|свайпай|свайпайте|смахни|смахните)\b"),
     "листать карусель"),
    (re.compile(r"(?i)\btell me\b|\bwhat would you\b|\bwhich one\b"
                r"|\b(?:расскажи|расскажите)\b|\bа (?:ты|вы) как\b|\bкакой (?:вариант|бы)\b|\bчто (?:бы )?(?:выберешь|выберете)\b"),
     "ответить на вопрос"),
]

FILLER_TAGS = {"#viral", "#fyp", "#explore", "#explorepage", "#foryou", "#foryoupage",
               "#trending", "#instagood", "#love", "#follow", "#like4like", "#reels",
               "#reelsinstagram", "#viralreels", "#instadaily",
               "#рекомендации", "#рек", "#реки", "#рекомендация", "#вреки", "#врек",
               "#хочуврек", "#хочувтоп", "#хочуврекомендации", "#топ", "#тренды", "#тренд",
               "#рилс", "#рилсы", "#инстаграм", "#лайк", "#лайки", "#подписка",
               "#взаимныелайки", "#взаимнаяподписка", "#любовь", "#красота", "#жизнь",
               "#вирусное", "#популярное"}


PASS, WARN, FAIL = "ОК", "ВНИМ", "ОШИБКА"
VERDICT_READY, VERDICT_REVIEW, VERDICT_FIX = "ГОТОВО", "ПРОВЕРИТЬ", "ИСПРАВИТЬ"


def keyword_re(phrase):
    """Фраза с учётом склонения: «договор с клиентом» найдёт «договоре с клиентом».

    У каждого слова длиннее четырёх букв срезаем до двух букв окончания и
    разрешаем любое окончание. Грубо, но для поиска фразы в подписи хватает.
    """
    parts = []
    for w in phrase.lower().replace("ё", "е").split():
        if len(w) > 4 and w.isalpha():
            parts.append(re.escape(w[:len(w) - 2]).replace("е", "[её]") + r"\w{0,4}")
        else:
            parts.append(re.escape(w).replace("е", "[её]"))
    return re.compile(r"(?<!\w)" + r"\s+".join(parts) + r"(?!\w)", re.IGNORECASE)


def visible_window(text, cut):
    """То, что видно в ленте. Instagram режет посреди слова, и мы тоже."""
    flat = text.strip()
    return flat if len(flat) <= cut else flat[:cut]


def render_box(window, truncated, out=sys.stdout, width=52):
    print("\n  ЧТО ВИДНО В ЛЕНТЕ", file=out)
    print("  +" + "-" * (width + 2) + "+", file=out)
    lines = []
    for raw in window.split("\n"):
        lines.extend(textwrap.wrap(raw, width) or [""])
    for line in lines[:8]:
        print(f"  | {line:<{width}} |", file=out)
    tail = "... ещё" if truncated else "(подпись видна целиком)"
    print("  +" + "-" * (width + 2 - len(tail) - 2) + f" {tail} " + "+", file=out)


def analyse(text, cut=TRUNCATE, keywords=None):
    text = text.rstrip()
    stripped = text.strip()
    chars = len(stripped)
    lines = [l for l in stripped.split("\n")]
    first_line = lines[0].strip() if lines else ""
    tags = HASHTAG_RE.findall(stripped)
    mentions = MENTION_RE.findall(stripped)
    links = LINK_RE.findall(stripped)
    emoji = EMOJI_RE.findall(stripped)
    window = visible_window(stripped, cut)
    truncated = chars > cut
    asks = [name for pattern, name in ASKS if pattern.search(stripped)]
    filler = [t for t in tags if t.lower() in FILLER_TAGS]
    keywords = [k.strip() for k in (keywords or []) if k.strip()]

    checks = []

    def add(name, status, detail):
        checks.append({"check": name, "status": status, "detail": detail})

    add("ДЛИНА", FAIL if chars > LIMIT else PASS,
        f"{chars} / {LIMIT} символов" + (f", на {chars - LIMIT} больше лимита"
                                         if chars > LIMIT else ""))

    if not first_line:
        add("ПЕРВАЯ СТРОКА", FAIL, "подпись начинается с пустой строки")
    elif first_line.startswith("#") or first_line.startswith("@"):
        add("ПЕРВАЯ СТРОКА", FAIL,
            "начинается с хэштега или упоминания, а это единственное место, достойное фразы")
    elif len(first_line) > cut:
        add("ПЕРВАЯ СТРОКА", WARN,
            f"{len(first_line)} символов, обрежется на {cut} посреди мысли. "
            "Хорошо, если обрыв интригует, плохо, если это придаточное")
    else:
        add("ПЕРВАЯ СТРОКА", PASS, f"{len(first_line)} символов, видна целиком")

    add("КОНКРЕТНЫЙ ХУК", PASS if CONCRETE_RE.search(window) else WARN,
        f"чисел или имён в видимом окне: {len(CONCRETE_RE.findall(window))}"
        + ("" if CONCRETE_RE.search(window) else " - до тапа нечего проверить"))

    if len(tags) > HASHTAG_LIMIT:
        add("ХЭШТЕГИ", FAIL, f"тегов: {len(tags)}, больше лимита Instagram ({HASHTAG_LIMIT}). "
                             "Теги после пятого не учитываются, а блок выглядит устаревшим")
    elif len(tags) == HASHTAG_LIMIT and filler:
        add("ХЭШТЕГИ", WARN, f"тегов: {len(tags)}, это лимит, и "
                             f"{len(filler)} из них общие. Потратьте пять на темы")
    elif filler:
        add("ХЭШТЕГИ", WARN, f"тегов: {len(tags)}, общих из них {len(filler)} "
                             f"({', '.join(filler[:3])}). Они ничего не описывают")
    else:
        add("ХЭШТЕГИ", PASS, f"тегов: {len(tags)}" + (f" ({' '.join(tags)})" if tags else ""))

    if not tags:
        add("МЕСТО ТЕГОВ", PASS, "тегов нет")
    elif any(re.search(r"(?:^|\s)" + re.escape(t) + r"\b", window) for t in tags):
        add("МЕСТО ТЕГОВ", WARN, "хэштег попал в видимое окно и тратит место в ленте на ярлык")
    else:
        add("МЕСТО ТЕГОВ", PASS, "теги ниже обрезки")

    add("ССЫЛКИ", WARN if links else PASS,
        f"ссылок в подписи: {len(links)}, а подписи не кликабельны. "
        f"Перенесите в шапку профиля или в директ" if links else "мёртвых ссылок в тексте нет")

    if len(asks) == 1:
        add("ОДИН ПРИЗЫВ", PASS, f"один призыв к действию: {asks[0]}")
    elif not asks:
        add("ОДИН ПРИЗЫВ", WARN, "призыва нет. Решите, зачем этот пост")
    else:
        add("ОДИН ПРИЗЫВ", WARN, f"призывов: {len(asks)} ({', '.join(asks)}). "
                                 "Два призыва - то же самое, что ни одного")

    density = len(emoji) * 100 / max(chars, 1)
    add("ЭМОДЗИ", WARN if density > 4 else PASS,
        f"эмодзи: {len(emoji)}, {density:.1f} на 100 символов"
        + (" - выглядит как украшательство" if density > 4 else ""))

    if keywords:
        found = [k for k in keywords if keyword_re(k).search(stripped)]
        missing = [k for k in keywords if k not in found]
        in_window = [k for k in found if keyword_re(k).search(window)]
        status = PASS if not missing else (WARN if found else FAIL)
        add("ПОИСКОВЫЕ ФРАЗЫ", status,
            f"есть {len(found)}/{len(keywords)}"
            + (f", в видимом окне {len(in_window)}" if found else "")
            + (f". Нет: {', '.join(missing)}" if missing else ""))

    fails = sum(1 for c in checks if c["status"] == FAIL)
    warns = sum(1 for c in checks if c["status"] == WARN)
    verdict = VERDICT_FIX if fails else (VERDICT_REVIEW if warns else VERDICT_READY)

    return {
        "characters": chars, "limit": LIMIT, "truncate_at": cut,
        "visible": window, "truncated": truncated,
        "first_line_chars": len(first_line),
        "hashtags": tags, "mentions": mentions, "links": links,
        "emoji": len(emoji), "asks": asks,
        "checks": checks, "verdict": verdict,
    }


def render(a, out=sys.stdout):
    head = (f"ПРОВЕРКА ПОДПИСИ  ·  {a['characters']} / {a['limit']} символов  ·  "
            f"хэштегов {len(a['hashtags'])}  ·  призывов {len(a['asks'])}")
    print("\n" + head, file=out)
    print("=" * max(len(head), 62), file=out)
    render_box(a["visible"], a["truncated"], out=out)
    print("", file=out)
    for c in a["checks"]:
        print(f"  {c['status']:<6} {c['check']:<16} {c['detail']}", file=out)
    print("-" * max(len(head), 62), file=out)
    print(f"  ИТОГ  {a['verdict']}\n", file=out)


def main():
    ap = argparse.ArgumentParser(description="Проверить подпись к посту в Instagram.")
    ap.add_argument("input", nargs="?", default="-", help="файл с подписью или - для stdin")
    ap.add_argument("--truncate", type=int, default=TRUNCATE,
                    help=f"сколько символов видно до «... ещё» (по умолчанию {TRUNCATE})")
    ap.add_argument("--keywords", default="",
                    help="через запятую: фразы, по которым вас должны находить в поиске")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    raw = sys.stdin.read() if args.input == "-" else open(args.input, encoding="utf-8").read()
    a = analyse(raw, cut=args.truncate, keywords=args.keywords.split(","))
    if args.json:
        print(json.dumps(a, indent=2, ensure_ascii=False))
    else:
        render(a)
    sys.exit(0 if a["verdict"] == VERDICT_READY else 1)


if __name__ == "__main__":
    main()
