#!/usr/bin/env python3
"""
detect.py - панель из пяти проверок, которая оценивает, насколько машинным
выглядит черновик.

Что это:  пять локальных эвристик по мотивам сигналов, которые на самом деле
измеряют публичные ИИ-детекторы: разброс длины предложений, конкретика,
штампы, типографский отпечаток и живой голос. Всё считается на вашей машине
только по тексту. Ничего никуда не отправляется.

Чего это НЕ делает:  это не GPTZero, Originality, Copyleaks, Winston, Turnitin
и не русские сервисы вроде text.ru. Их API не вызываются, их вердикт не
обещается. Скрипт ловит то, на что все они смотрят, поэтому исправления обычно
двигают и их цифры, но честное утверждение - только то, что в этой строке.

Каждая проверка возвращает «человечность» от 0 до 100. Чем выше, тем лучше.
Понимает русский и английский текст.

Запуск
  python3 detect.py draft.txt
  pbpaste | python3 detect.py -
  python3 detect.py draft.txt --json
  python3 detect.py before.txt after.txt      # сравнить два черновика
"""

import argparse
import json
import os
import re
import statistics
import sys
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from humanize import entry_pattern, is_russian  # noqa: E402  одна и та же логика поиска штампов
LEX = os.path.join(HERE, "slop.json")

SENT_RE = re.compile(r"[^.!?\n]+[.!?]*")
WORD_RE = re.compile(r"[A-Za-zА-Яа-яЁё']+")
# В английском живой голос слышен по сокращениям (it's, don't). В русском их
# нет, зато есть разговорные частицы и словечки, которых нейросеть избегает.
CONTRACTIONS = re.compile(
    r"\b\w+'(?:s|t|re|ve|ll|d|m)\b"
    r"|(?<![\w-])(?:же|ну|вот|ведь|короче|типа|блин|кстати|прям|реально|щас|чё|чо|норм|"
    r"ок|окей|ага|ладно|вообще|тупо|капец|жесть|кринж|имхо|походу|вроде|небось|"
    r"пофиг|фиг|ваще|чуть-чуть|чутка)(?![\w-])"
    r"|\w+-(?:то|таки|ка)\b",
    re.IGNORECASE)
PRONOUNS = re.compile(
    r"\b(?:i|me|my|mine|we|us|our|you|your|я|мне|меня|мной|мой|моя|моё|мое|мои|моих|"
    r"мы|нас|нам|нами|наш|наша|наше|наши|ты|тебя|тебе|тобой|твой|твоя|твоё|твое|твои|"
    r"вы|вас|вам|вами|ваш|ваша|ваше|ваши)\b",
    re.IGNORECASE)
NUMBERS = re.compile(r"\b\d[\d,.]*%?|[$€]\d|\d\s?₽")
PROPER = re.compile(r"(?<![.!?]\s)(?<!^)\b[A-ZА-ЯЁ][a-zа-яё]{2,}\b", re.MULTILINE)


def clamp(n):
    return max(0.0, min(100.0, n))


def scale(value, human, machine):
    """Отображает value на 0-100, где `human` -> 100, а `machine` -> 0."""
    if human == machine:
        return 50.0
    return clamp((value - machine) / (human - machine) * 100)


def sentences(text):
    return [s.strip() for s in SENT_RE.findall(text) if len(s.split()) > 2]


def words(text):
    return WORD_RE.findall(text)


def check_burstiness(text):
    """Люди сильно меняют длину предложений. Модели пишут ровно."""
    lens = [len(s.split()) for s in sentences(text)]
    if len(lens) < 4:
        return 50.0, "слишком коротко, чтобы судить"
    mean = statistics.mean(lens)
    cv = statistics.pstdev(lens) / mean if mean else 0
    score = scale(cv, human=0.70, machine=0.22)
    return score, f"вариация {cv:.2f} по {len(lens)} предложениям (нужно 0.55+)"


def check_specificity(text):
    """Числа, имена, конкретные вещи. Штампы абстрактны."""
    w = words(text)
    if len(w) < 25:
        return 50.0, "слишком коротко, чтобы судить"
    per100 = 100 / len(w)
    hits = len(NUMBERS.findall(text)) + len(set(PROPER.findall(text)))
    density = hits * per100
    score = scale(density, human=6.0, machine=0.5)
    return score, f"конкретных деталей {hits}, {density:.1f} на 100 слов (нужно 4+)"


def check_slop(text, lex):
    """Плотность штампов по словарю."""
    w = words(text)
    if not w:
        return 50.0, "пусто"
    hits, found = 0, []
    for entry in lex["words"] + lex["phrases"]:
        n = len(entry_pattern(entry).findall(text))
        if n:
            hits += n
            found.append(entry["find"])
    density = hits * 100 / len(w)
    score = scale(density, human=0.0, machine=4.0)
    detail = f"штампов {hits}, {density:.1f} на 100 слов"
    if found:
        detail += " (" + ", ".join(sorted(found)[:4]) + (", ..." if len(found) > 4 else "") + ")"
    return score, detail


def check_fingerprint(text):
    """Символы, которые не набирает клавиатура телефона."""
    invisible = sum(1 for c in text if unicodedata.category(c) == "Cf")
    em = text.count("—")
    curly = sum(text.count(c) for c in "‘’“”«»„")
    ellip = text.count("…")
    nbsp = sum(text.count(c) for c in "   ")
    total = invisible * 4 + em * 2 + curly + ellip + nbsp
    per1k = total * 1000 / max(len(text), 1)
    score = scale(per1k, human=0.0, machine=12.0)
    detail = (f"невидимых {invisible}, длинных тире {em}, типографских кавычек {curly}, "
              f"многоточий-символов {ellip}, неразрывных пробелов {nbsp}")
    return score, detail


def check_voice(text, lex):
    """Разговорность, лицо и формы, к которым модели тянутся по умолчанию."""
    w = words(text)
    if len(w) < 25:
        return 50.0, "слишком коротко, чтобы судить"
    per100 = 100 / len(w)
    contractions = len(CONTRACTIONS.findall(text)) * per100
    person = len(PRONOUNS.findall(text)) * per100
    tells = 0
    names = []
    for s in lex["structures"]:
        try:
            n = len(re.compile(s["regex"], re.MULTILINE).findall(text))
        except re.error:
            continue
        if n:
            tells += n
            names.append(s["id"])
    bullets = [len(b.split()) for b in re.findall(r"(?m)^\s*[-*•]\s+(.+)$", text)]
    uniform = (len(bullets) >= 3 and statistics.pstdev(bullets) < 1.6)
    score = (scale(contractions, human=3.0, machine=0.0) * 0.35
             + scale(person, human=5.0 if is_russian(text) else 8.0, machine=1.0) * 0.35
             + clamp(100 - tells * 22) * 0.30)
    if uniform:
        score -= 12
        names.append("uniform-bullets")
    # В русском лицо видно по глаголу («напиши», «потерял»), местоимений меньше,
    # поэтому порог для них ниже.
    detail = (f"разговорных маркеров {contractions:.1f}, личных местоимений {person:.1f} "
              f"на 100 слов, структурных примет {tells}")
    if names:
        detail += " [" + ", ".join(names[:4]) + "]"
    return clamp(score), detail


CHECKS = ["РИТМ", "КОНКРЕТИКА", "ШТАМПЫ", "ОТПЕЧАТОК", "ГОЛОС"]
VERDICT_PASS, VERDICT_REVIEW, VERDICT_FLAGGED = "ПРОЙДЕНО", "ПРОВЕРИТЬ", "ПОХОЖЕ НА ИИ"


def run(text, lex):
    results = {}
    results["РИТМ"] = check_burstiness(text)
    results["КОНКРЕТИКА"] = check_specificity(text)
    results["ШТАМПЫ"] = check_slop(text, lex)
    results["ОТПЕЧАТОК"] = check_fingerprint(text)
    results["ГОЛОС"] = check_voice(text, lex)
    scores = [results[c][0] for c in CHECKS]
    # Самая слабая проверка тянет вердикт вниз: детектору хватает одного сигнала.
    overall = statistics.mean(scores) * 0.6 + min(scores) * 0.4
    verdict = VERDICT_PASS if overall >= 70 and min(scores) >= 55 else (
        VERDICT_REVIEW if overall >= 50 else VERDICT_FLAGGED)
    return results, overall, verdict


def bar(score, width=24):
    filled = round(score / 100 * width)
    return "#" * filled + "." * (width - filled)


def render(results, overall, verdict, label=None, out=sys.stdout):
    title = "ПАНЕЛЬ ПРОВЕРКИ НА ИИ" + (f"  -  {label}" if label else "")
    print("\n" + title, file=out)
    print("=" * max(len(title), 62), file=out)
    for name in CHECKS:
        score, detail = results[name]
        print(f"  {name:<13} {bar(score)} {score:5.1f}", file=out)
        print(f"  {'':<13} {detail}", file=out)
    print("-" * 62, file=out)
    print(f"  {'ЧЕЛОВЕЧНОСТЬ':<13} {bar(overall)} {overall:5.1f}   {verdict}", file=out)
    if verdict != VERDICT_PASS:
        weakest = min(CHECKS, key=lambda c: results[c][0])
        print(f"\n  Самый слабый сигнал: {weakest}. Начните с него.", file=out)
    print("", file=out)


def main():
    ap = argparse.ArgumentParser(description="Оценить, насколько машинным выглядит черновик.")
    ap.add_argument("input", nargs="?", default="-", help="файл или - для stdin")
    ap.add_argument("compare", nargs="?", help="второй файл, чтобы показать «до» и «после»")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--lexicon", default=LEX)
    args = ap.parse_args()

    lex = json.load(open(args.lexicon, encoding="utf-8"))
    read = lambda p: sys.stdin.read() if p == "-" else open(p, encoding="utf-8").read()

    targets = [(args.input, read(args.input))]
    if args.compare:
        targets.append((args.compare, read(args.compare)))

    payload = []
    for name, text in targets:
        results, overall, verdict = run(text, lex)
        payload.append({
            "source": name,
            "checks": {k: {"score": round(v[0], 1), "detail": v[1]} for k, v in results.items()},
            "human_score": round(overall, 1),
            "verdict": verdict,
        })

    if args.json:
        print(json.dumps(payload if args.compare else payload[0], indent=2, ensure_ascii=False))
        return

    for (name, text), p in zip(targets, payload):
        results, overall, verdict = run(text, lex)
        render(results, overall, verdict, label=os.path.basename(name) if args.compare else None)
    if args.compare:
        a, b = payload
        delta = b["human_score"] - a["human_score"]
        print(f"  {a['human_score']:.1f} {a['verdict']}  ->  "
              f"{b['human_score']:.1f} {b['verdict']}   ({delta:+.1f})\n")

    sys.exit(0 if payload[-1]["verdict"] == VERDICT_PASS else 1)


if __name__ == "__main__":
    main()
