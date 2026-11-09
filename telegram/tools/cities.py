#!/usr/bin/env python3
"""Собирает telegram/cities.yaml - новостной канал на каждый город России.

    git clone --depth 1 https://github.com/hflabs/city /tmp/city
    python3 -I telegram/tools/cities.py /tmp/city/city.csv [--min-pop 100000]

Источник списка: справочник городов России HFLabs (github.com/hflabs/city, CC BY-SA 4.0):
1117 городов с населением, регионом, федеральным округом и часовым поясом.

Для каждого города строится шаблон названия с учётом падежей («Казань» -> «Казани»,
«Нижний Новгород» -> «Нижнем Новгороде»). Областным центрам добавляется название
региона. Чтобы «Мирный житель» не попал в город Мирный, а «перевозки» - в Перевоз:
- от 300 тыс. жителей - название где угодно;
- меньше - только в «городском» контексте: «в Ярцеве», «из Сокола», «житель Сокола», «мэр...»;
- меньше 50 тыс. и тёзки поменьше (два Кирова) - ещё и с упоминанием региона.
Заполненные chat не теряются.
"""
from __future__ import annotations

import csv
import re
import sys
from collections import Counter
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "cities.yaml"

REGION_TYPE = {"обл": "область", "край": "край", "Респ": "Республика", "АО": "автономный округ",
               "Аобл": "автономная область", "г": "город федерального значения", "Чувашия": "Республика"}
TRANSLIT = dict(zip("абвгдеёжзийклмнопрстуфхцчшщъыьэюя",
                    ["a", "b", "v", "g", "d", "e", "e", "zh", "z", "i", "y", "k", "l", "m", "n", "o", "p", "r", "s",
                     "t", "u", "f", "h", "ts", "ch", "sh", "sch", "", "y", "", "e", "yu", "ya"]))


def slug(text: str) -> str:
    s = "".join(TRANSLIT.get(c, c) for c in text.lower())
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def stem_word(word: str) -> str:
    """Основа слова для падежей: Казань->Казан\\w{0,3}, Нижний->Нижн\\w{0,3}, Мирный->Мирн\\w{0,3}."""
    w = word.replace("ё", "е").replace("Ё", "Е")
    base = re.sub(r"(ий|ый|ой|ая|ое|ые|ь|й|а|я|о|е|ы|и)$", "", w)
    if len(base) < 3:                    # «Ухта», «Сочи», «Ая» - короткие: слово целиком
        base = w
    fleeting = re.search(r"[её](л|к|ц|н)ь?$", w) and base == w   # Орёл-Орла, Елец-Ельца: гласная выпадает
    base = re.escape(base).replace("е", "[её]").replace("Е", "[ЕЁ]")
    if fleeting:
        base = re.sub(r"\[её\](\w)$", r"[её]?ь?\1", base)
    return base + r"\w{0,3}"


def name_pattern(name: str) -> str:
    parts = []
    for word in name.split():
        sub = [stem_word(p) if len(p) > 3 or p[:1].isupper() else re.escape(p) for p in word.split("-")]
        parts.append("-".join(sub))
    return r"\b" + r"\s+".join(parts) + r"\b"


ALIASES = {"Северная Осетия": "Северн\\w* Осети|Осети|Алани", "Марий Эл": "Марий Эл|Марийск", "Коми": "Коми\\b",
           "Тыва": "Тыв[аеуы]\\b|Тувы|Туве", "Адыгея": "Адыге", "Алтай": "Республик\\w* Алтай|Горн\\w* Алта",
           "Московская": "Подмосков", "Ленинградская": "Ленобласт", "Краснодарский": "Кубан",
           "Саха /Якутия/": "Якути", "Башкортостан": "Башкири", "Ханты-Мансийский Автономный округ - Югра": "Югр",
           "Ямало-Ненецкий": "ЯНАО|Ямал", "Кемеровская область - Кузбасс": "Кузбасс", "Чувашская Республика -": "Чуваш"}
CONTEXT = (r"(?:\b(?:[Вв]о?|[Ии]з|[Пп]од|[Уу]|[Жж]ител\w*|[Мм]эр\w*|[Гг]лав\w+|[Аа]дминистраци\w+|"
           r"[Гг]ород\w*|[Гг]\.)\s+)")
CONTEXT_FROM, REGION_FROM = 300_000, 50_000   # меньше - нужен «городской» контекст; ещё меньше - и регион


# Города, чьё название - имя или фамилия: без «городского» контекста ловили бы «Путин Владимир».
PERSON_NAMES = {"Владимир", "Королев", "Пушкин", "Пушкино", "Чехов", "Жуковский", "Александров", "Гагарин",
                "Ломоносов", "Лермонтов", "Киров", "Шахты", "Кстово", "Белый", "Мирный", "Остров", "Сокол", "Бор",
                "Луга", "Поронайск", "Советск", "Советский", "Королёв", "Орёл", "Орел", "Иваново", "Петровск",
                "Калинин", "Фрязино", "Гусев", "Суворов", "Жуков", "Кириллов", "Тутаев", "Ленинск", "Энгельс",
                "Электросталь", "Киселевск", "Чапаевск", "Мичуринск", "Дзержинск", "Дзержинский", "Свердловский"}


# Тёзки известных мест вне справочника (Донецк Ростовской обл. и Донецк ДНР): всегда нужен регион.
OUTSIDE_NAMESAKES = {"Донецк", "Кировск", "Красный Луч", "Первомайск", "Северодонецк"}


def region_pattern(region: str, rtype: str) -> str:
    alias = next((v for k, v in ALIASES.items() if region.startswith(k)), None)
    if alias and rtype == "Респ":          # у республик с короткими/общими словами в названии - только точные формы
        return r"\b(?:" + alias + ")"
    first = re.split(r"[\s-]", region.strip())[0]
    pat = stem_word(first) if len(first) >= 6 else r"\b" + re.escape(first) + r"\b"
    if rtype in ("обл", "край", "АО", "Аобл"):
        pat += r"\s+(обл|кра|автономн)"
    return r"\b(?:" + pat + (f"|{alias}" if alias else "") + ")"


def city_name(row: dict) -> str:
    if row["city"]:
        return row["city"]
    m = re.search(r"г ([^,]+)$", row["address"])
    return m.group(1) if m else row["region"]


def build(csv_path: str) -> list[dict]:
    rows = list(csv.DictReader(open(csv_path, encoding="utf-8")))
    names = Counter(city_name(r) for r in rows)
    biggest: dict[str, int] = {}
    for r in rows:
        n = city_name(r)
        biggest[n] = max(biggest.get(n, 0), int(r["population"] or 0))
    old = {}
    if OUT.exists():
        old = {c["id"]: c for c in (yaml.safe_load(OUT.read_text(encoding="utf-8")) or {}).get("cities", [])}
    used, out = set(), []
    for r in sorted(rows, key=lambda r: -int(r["population"] or 0)):
        name = city_name(r)
        pop = int(r["population"] or 0)
        cid = slug(name)
        if cid in used:
            cid = f"{cid}-{slug(r['region'])}"
        used.add(cid)
        rtype = r["region_type"]
        region = name if rtype == "г" else f"{r['region']} {REGION_TYPE.get(rtype, rtype)}".strip()
        anywhere = pop >= CONTEXT_FROM and name not in PERSON_NAMES
        include = [name_pattern(name) if anywhere else CONTEXT + name_pattern(name)[2:]]
        if r["capital_marker"] == "2" and rtype != "г":
            include.append(region_pattern(r["region"], rtype))
        entry = {"id": cid, "type": "news", "title": f"{name}: новости", "city": name, "region": region,
                 "district": r["federal_district"], "population": pop, "tz": r["timezone"],
                 "chat": old.get(cid, {}).get("chat", ""), "include": include}
        if rtype != "г" and ((names[name] > 1 and pop < biggest[name]) or pop < REGION_FROM
                             or name in OUTSIDE_NAMESAKES):
            entry["require"] = [region_pattern(r["region"], rtype)]     # маленький город или тёзка: нужен и регион
        entry["posts_per_run"] = 3 if pop >= 500_000 else 2 if pop >= 100_000 else 1
        out.append(entry)
    return out


LIST = ROOT / "ГОРОДА.md"
SOURCE = ("справочник городов России HFLabs (github.com/hflabs/city, лицензия CC BY-SA 4.0); "
          "население - как в Википедии на момент выгрузки справочника, у части городов устарело")


def write_list(cities: list[dict], min_pop: int) -> None:
    lines = [f"# Города России от {min_pop:,} жителей - {len(cities)} новостных каналов".replace(",", " "), "",
             f"Источник: {SOURCE}. Порядок - по населению. id - имя канала в `cities.yaml`;",
             "chat - подключённый Telegram-канал (пусто - пока черновики).", "",
             "| # | Город | Регион | Округ | Население | id | chat |", "|---|---|---|---|---|---|---|"]
    for i, c in enumerate(cities, 1):
        lines.append(f"| {i} | {c['city']} | {c['region']} | {c['district']} | "
                     f"{c['population']:,} | `{c['id']}` | {c['chat'] or ''} |".replace(",", " "))
    LIST.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    import argparse
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("csv", help="city.csv из github.com/hflabs/city")
    p.add_argument("--min-pop", type=int, default=50_000, help="минимум жителей (по умолчанию 50 000)")
    a = p.parse_args()
    cities = [c for c in build(a.csv) if c["population"] >= a.min_pop]
    header = ("# Новостные каналы городов России - сгенерировано telegram/tools/cities.py\n"
              f"# Источник: {SOURCE}.\n"
              f"# Города от {a.min_pop} жителей. Меняйте только chat (@канал или -100...) -\n"
              "# остальное пересоздаётся генератором; chat сохраняется. Список: telegram/ГОРОДА.md\n")
    OUT.write_text(header + yaml.safe_dump({"cities": cities}, allow_unicode=True, sort_keys=False, width=200),
                   encoding="utf-8")
    write_list(cities, a.min_pop)
    print(f"{OUT}: {len(cities)} городов от {a.min_pop} жителей; список - {LIST}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
