#!/usr/bin/env python3
"""
humanize.py - убирает из черновика машинный отпечаток.

Три прохода, в таком порядке:

  1. НЕВИДИМОЕ    удаляет или нормализует символы, которые не набирает
                  человеческая клавиатура: символы нулевой ширины, соединители
                  слов, мягкие переносы, BOM, Unicode-теги, неразрывные и узкие
                  пробелы. Они переживают копирование и являются самой
                  механической приметой сгенерированного текста.
  2. ТИПОГРАФИКА  длинное тире -> дефис с пробелами (« - », так печатают с
                  телефона, и грамматика русского тире сохраняется), среднее
                  тире -> дефис, «ёлочки» и фигурные кавычки -> прямые,
                  многоточие одним знаком -> три точки, маркер списка -> дефис.
  3. ЛЕКСИКА      заменяет штампы из slop.json на простые слова, сохраняя
                  регистр и не трогая ссылки.

Структурные приметы («это не просто X, это Y», правило трёх, стены хэштегов)
только ПОКАЗЫВАЮТСЯ и никогда не переписываются автоматически: чтобы изменить
форму предложения, нужно суждение, а это работа модели, а не регулярки.

Понимает русский и английский текст.

Запуск
  python3 humanize.py draft.txt
  python3 humanize.py draft.txt --report
  pbpaste | python3 humanize.py - --report
  python3 humanize.py draft.txt --json
  python3 humanize.py draft.txt -o clean.txt
"""

import argparse
import json
import os
import re
import sys
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
LEX = os.path.join(HERE, "slop.json")

URL_RE = re.compile(r"https?://\S+|www\.\S+|\S+@\S+\.\S+")
SENT_RE = re.compile(r"[^.!?\n]+[.!?]*")


def load_lexicon(path=LEX):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _cp(spec):
    """'U+200B' -> '\\u200b';  'U+E0000-U+E007F' -> (start, end)."""
    if "-" in spec:
        a, b = spec.split("-")
        return (int(a[2:], 16), int(b[2:], 16))
    return int(spec[2:], 16)


def protect_urls(text):
    """Прячем ссылки за заглушками, чтобы ни один проход не правил внутри ссылки."""
    found = []

    def stash(m):
        found.append(m.group(0))
        return f"\x00URL{len(found) - 1}\x00"

    return URL_RE.sub(stash, text), found


def restore_urls(text, found):
    for i, url in enumerate(found):
        text = text.replace(f"\x00URL{i}\x00", url)
    return text


def pass_invisible(text, lex):
    """Удаляет невидимые символы или заменяет их пробелом. Возвращает (текст, находки)."""
    hits = []
    for entry in lex["invisible"]:
        cp = _cp(entry["cp"])
        if isinstance(cp, tuple):
            pattern = "[" + re.escape(chr(cp[0])) + "-" + re.escape(chr(cp[1])) + "]"
        else:
            pattern = re.escape(chr(cp))
        n = len(re.findall(pattern, text))
        if n:
            hits.append({"name": entry["cp"] + " " + entry["name"], "count": n,
                         "action": entry["action"]})
            text = re.sub(pattern, "" if entry["action"] == "delete" else " ", text)
    # Любой оставшийся символ категории Cf (format) невидим по определению.
    stray = [c for c in text if unicodedata.category(c) == "Cf"]
    if stray:
        hits.append({"name": "прочие невидимые служебные символы", "count": len(stray),
                     "action": "delete"})
        text = "".join(c for c in text if unicodedata.category(c) != "Cf")
    return text, hits


def is_russian(text):
    """Кириллицы больше, чем латиницы."""
    cyr = len(re.findall(r"[А-Яа-яЁё]", text))
    lat = len(re.findall(r"[A-Za-z]", text))
    return cyr >= lat


def pass_typographic(text, lex):
    hits = []
    for entry in lex["typographic"]:
        ch = entry["from"]
        n = text.count(ch)
        if not n:
            continue
        hits.append({"name": f"{ch} {entry['name']}", "count": n, "to": entry["to"].strip() or "(пробел)"})
        if ch == "—" and is_russian(text):
            # Тире в начале строки (диалог) -> дефис; внутри фразы -> « - ».
            # В русском тире грамматическое («Москва - столица»), и запятая,
            # как в английской версии, ломает смысл.
            text = re.sub(r"(?m)^([ \t]*)—[ \t]*", r"\1- ", text)
            text = re.sub(r"[ \t]*—[ \t]*", " - ", text)
        elif ch == "—":
            # Английский текст: " word — word " и "word—word" -> запятая.
            text = re.sub(r"\s*—\s*", ", ", text)
        elif ch == "–":
            text = re.sub(r"\s*–\s*(?=\d)", "-", text)      # 5–10  -> 5-10
            text = re.sub(r"\s+–\s+", ", ", text)            # used as em dash
            text = text.replace("–", "-")
        else:
            text = text.replace(ch, entry["to"])
    # Запятая перед другим знаком препинания читается плохо.
    text = re.sub(r",\s*([,.;:!?])", r"\1", text)
    text = re.sub(r",\s*\n", "\n", text)
    return text, hits


def _match_case(src, repl):
    if not repl:
        return repl
    if src.isupper() and len(src) > 1:
        return repl.upper()
    if src[0].isupper():
        return repl[0].upper() + repl[1:]
    return repl


def entry_pattern(entry):
    """Регулярка для записи словаря.

    Обычная запись - фраза целиком, пробелы гибкие, е и ё равны. Запись с полем
    pattern - готовая регулярка по основе слова (для падежей), \\1 в replace
    подставляет окончание.
    """
    if entry.get("pattern"):
        body = entry["pattern"]
    else:
        body = re.escape(entry["find"]).replace(r"\ ", r"\s+")
    body = body.replace("ё", "[её]").replace("е", "[её]").replace("[[её]ё]", "[её]")
    # \b не работает рядом с «?» или «,» на краю фразы, поэтому границы мягкие.
    return re.compile(r"(?<!\w)" + body + r"(?!\w)", re.IGNORECASE)


def pass_lexical(text, lex):
    """Заменяет штампы. Сначала длинные, чтобы фразы выигрывали у слов."""
    hits = []
    entries = sorted(lex["phrases"] + lex["words"],
                     key=lambda e: len(e["find"]), reverse=True)
    for entry in entries:
        find = entry["find"]
        pattern = entry_pattern(entry)
        found = pattern.findall(text)
        if not found:
            continue
        shown = re.sub(r"\\\d", "…", entry["replace"])
        hits.append({"find": find, "replace": shown or "(удалено)",
                     "count": len(found), "family": entry["family"]})
        if entry.get("pattern"):
            text = pattern.sub(lambda m: _match_case(m.group(0), m.expand(entry["replace"])), text)
        else:
            text = pattern.sub(lambda m: _match_case(m.group(0), entry["replace"]), text)
    # Уборка после удалений. Удалённый оборот оставляет осиротевшую пунктуацию
    # («система. .» или строку, которая теперь начинается с запятой), и это
    # читается хуже, чем сам штамп.
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"(?m)^[ \t]*(?:[,.;:!?]+[ \t]*)+", "", text)
    text = re.sub(r"(?m)^[ \t](?=\S)", "", text)       # один пробел остался от удаления.
                                                      # Более глубокий отступ - намеренный.
    text = re.sub(r"[ \t]+([,.;:!?])", r"\1", text)   # только пробелы: знак не должен
                                                      # перепрыгивать через перенос строки
    text = re.sub(r",\s*([,.;:!?])", r"\1", text)      # тире стало запятой,
                                                      # а оборот после него удалили
    text = text.replace("...", "\x00ELL\x00")          # защищаем настоящие многоточия
    text = re.sub(r"\.\s*\.+", ".", text)
    text = re.sub(r"([!?])\s*\.", r"\1", text)
    text = text.replace("\x00ELL\x00", "...")
    text = re.sub(r"(?m)^[ \t]+$", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    # Тире, ставшее запятой, перед связкой даёт склейку («is important, also,
    # it's proof»). Превращаем её в точку.
    text = re.sub(r",\s*(also|so|still|basically|in the end|ещё|и ещё|но|так что|значит|в итоге)\s*,\s*",
                  lambda m: ". " + m.group(1)[0].upper() + m.group(1)[1:] + ", ", text)
    return text, hits


def scan_structures(text, lex):
    flags = []
    for s in lex["structures"]:
        try:
            pattern = re.compile(s["regex"], re.MULTILINE)
        except re.error:
            continue
        found = pattern.findall(text)
        if found:
            flags.append({"name": s["name"], "count": len(found), "fix": s["fix"]})
    # Sentence-length uniformity is structural too.
    lens = [len(s.split()) for s in SENT_RE.findall(text) if len(s.split()) > 2]
    if len(lens) >= 4:
        mean = sum(lens) / len(lens)
        var = sum((n - mean) ** 2 for n in lens) / len(lens)
        cv = (var ** 0.5) / mean if mean else 0
        if cv < 0.35:
            flags.append({
                "name": f"Одинаковая длина предложений (вариация {cv:.2f})",
                "count": len(lens),
                "fix": "Разрежьте одно предложение пополам. Другому дайте разрастись. Машины пишут ровно.",
            })
    return flags


def restore_capitals(original, text):
    """После удаления зачина следующее слово остаётся со строчной буквы.

    Исправляем это только у тех, кто вообще пишет предложения с заглавной:
    нарочно строчный голос - это стиль, а не артефакт, и перекрикивать его -
    ровно то, с чем этот скрипт борется.
    """
    starts = re.findall(r"(?:^|[.!?]\s+|\n)\s*([A-Za-zА-Яа-яЁё])", original)
    if not starts or sum(1 for c in starts if c.isupper()) * 2 < len(starts):
        return text
    return re.sub(r"(?:^|(?<=[.!?] )|(?<=[.!?]\n)|(?<=\n))\s*([a-zа-яё])",
                  lambda m: m.group(0)[:-1] + m.group(1).upper(), text)


def humanize(text, lex):
    raw_for_case = text
    text, urls = protect_urls(text)
    text, inv = pass_invisible(text, lex)
    text, typo = pass_typographic(text, lex)
    text, lexi = pass_lexical(text, lex)
    text = restore_capitals(raw_for_case, text)
    text = restore_urls(text, urls)
    return text.strip() + "\n", {
        "invisible": inv,
        "typographic": typo,
        "lexical": lexi,
        "structures": scan_structures(text, lex),
    }


def render_report(report, out=sys.stderr):
    def head(title):
        print(f"\n{title}\n" + "-" * len(title), file=out)

    total = sum(h["count"] for h in report["invisible"]) \
        + sum(h["count"] for h in report["typographic"]) \
        + sum(h["count"] for h in report["lexical"])

    head("ОТЧЁТ ОЧИСТКИ")
    print(f"убрано машинных артефактов: {total}, "
          f"структурных примет на переписывание: {len(report['structures'])}", file=out)

    actions = {"delete": "удалить", "space": "пробел"}
    if report["invisible"]:
        head("1. НЕВИДИМЫЕ СИМВОЛЫ")
        for h in report["invisible"]:
            print(f"  {h['count']:>3}x  {h['name']}  -> {actions.get(h['action'], h['action'])}",
                  file=out)
    if report["typographic"]:
        head("2. ТИПОГРАФИКА")
        for h in report["typographic"]:
            print(f"  {h['count']:>3}x  {h['name']}  -> {h['to']}", file=out)
    if report["lexical"]:
        head("3. ШТАМПЫ")
        for h in report["lexical"]:
            print(f"  {h['count']:>3}x  {h['find']}  -> {h['replace']}   [{h['family']}]", file=out)
    if report["structures"]:
        head("4. СТРУКТУРНЫЕ ПРИМЕТЫ  (не исправляются сами - перепишите вручную)")
        for h in report["structures"]:
            print(f"  {h['count']:>3}x  {h['name']}\n        {h['fix']}", file=out)
    if not any(report.values()):
        head("ЧИСТО")
        print("  Убирать нечего.", file=out)
    print("", file=out)


def main():
    ap = argparse.ArgumentParser(description="Убрать из черновика машинный отпечаток.")
    ap.add_argument("input", nargs="?", default="-", help="файл или - для stdin")
    ap.add_argument("-o", "--out", help="записать очищенный текст в файл, а не в stdout")
    ap.add_argument("--report", action="store_true", help="показать, что изменилось (в stderr)")
    ap.add_argument("--json", action="store_true", help="вывести {text, report} в JSON")
    ap.add_argument("--lexicon", default=LEX, help="путь к slop.json")
    args = ap.parse_args()

    raw = sys.stdin.read() if args.input == "-" else open(args.input, encoding="utf-8").read()
    lex = load_lexicon(args.lexicon)
    clean, report = humanize(raw, lex)

    if args.json:
        print(json.dumps({"text": clean, "report": report}, indent=2, ensure_ascii=False))
        return
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(clean)
        print(f"записано: {args.out}", file=sys.stderr)
    else:
        sys.stdout.write(clean)
    if args.report:
        render_report(report)


if __name__ == "__main__":
    main()
