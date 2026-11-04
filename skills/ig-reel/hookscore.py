#!/usr/bin/env python3
"""
hookscore.py - оценивает первую фразу Reels по пяти свойствам, общим для
сильных хуков, и ранжирует пачку хуков друг против друга.

Что это:  пять локальных эвристик, которые считаются на вашей машине только по
тексту. Они измеряют то, что обычно есть у хуков, удерживающих внимание:
длина, которую можно произнести меньше чем за три секунды, конкретика, ставка
(что-то на кону), полезная нагрузка в начале фразы, а не в конце, и зритель,
к которому обращаются.

Чего это НЕ делает:  не предсказывает просмотры. Оригинальная (английская)
версия проверялась на 74 реальных хуках из коротких видео: отличать настоящий
хук от нарочно плохого она умеет хорошо (AUC 0.83), а отличать удачные ролики
автора от его же неудачных почти не умеет (AUC 0.56, где 0.50 - подброшенная
монетка). Русские словари в этой версии на корпусе не проверялись, так что
считайте их ещё более грубым фильтром.

Используйте его для того, что он умеет: ловить приветствия, вступления, хуки
без единой конкретной детали и хуки, которые произносятся пять секунд. Какой из
двух нормальных хуков «залетит», он не скажет - и никакой анализ текста не
скажет, потому что это решают ваше лицо, монтаж, звук и то, кому Instagram
покажет ролик. Графику удержания верьте больше, чем этому скрипту.

Каждая проверка возвращает от 0 до 100. Чем выше, тем лучше.
Скрипт понимает русский и английский текст.

Запуск
  python3 hookscore.py hooks.txt              # один хук на строку, рейтинг
  python3 hookscore.py --hook "Я потерял 180 000 ₽ из-за одного пункта в договоре."
  pbpaste | python3 hookscore.py -
  python3 hookscore.py hooks.txt --json
"""

import argparse
import json
import re
import statistics
import sys

WORD_RE = re.compile(r"[A-Za-zА-Яа-яЁё0-9$₽€%'’-]+")
NUMBER_RE = re.compile(
    r"[$€]\s?\d[\d,]*(?:\.\d+)?"                          # деньги: $18,000
    r"|\b\d[\d,.]*\s?(?:₽|руб\w*|р\.|тыс\w*|млн|млрд|к\b|k\b|%|x\b|х\b|раз\w*"
    r"|ч\b|час\w*|мин\w*|сек\w*|дн\w*|день|недел\w*|месяц\w*|год\w*|лет\b"
    r"|hrs?\b|hours?\b|mins?\b|minutes?\b|days?\b|weeks?\b|months?\b|years?\b)?",
    re.IGNORECASE)
PROPER_RE = re.compile(r"(?<!^)(?<![.!?]\s)\b[A-ZА-ЯЁ][a-zа-яё]{2,}\b")
HASHTAG_RE = re.compile(r"(?:^|\s)#\w+")
EMOJI_RE = re.compile(r"[\U0001F300-\U0001FAFF☀-➿]")


def norm(word):
    """Нижний регистр, ё -> е, без апострофов по краям."""
    return word.lower().replace("ё", "е").strip("'’")


def stem_hit(token, exact, stems):
    """Русский склоняется, поэтому кроме точных форм проверяем основы слов."""
    return token in exact or any(token.startswith(s) for s in stems)


# Числа в устной речи произносят словами. «Двести тысяч» так же конкретно, как
# «200 000», и если считать только цифры, такие хуки выглядят пустыми.
# «Один» и «первый» сознательно не включены: это чаще слово-паразит, чем
# количество.
SPOKEN_NUMBERS = {
    # en
    "zero", "two", "three", "four", "five", "six", "seven", "eight", "nine",
    "ten", "eleven", "twelve", "fifteen", "twenty", "thirty", "forty", "fifty",
    "sixty", "seventy", "eighty", "ninety", "hundred", "thousand", "million",
    "billion", "dozen", "half", "twice", "triple",
    # ru
    "ноль", "нуля", "два", "две", "двух", "три", "трех", "четыре", "четырех",
    "пять", "пяти", "шесть", "шести", "семь", "семи", "восемь", "восьми",
    "девять", "девяти", "десять", "десяти", "двадцать", "тридцать", "сорок",
    "пятьдесят", "сто", "двести", "триста", "пятьсот", "дюжина", "половина",
    "полтора", "полторы", "вдвое", "втрое", "дважды", "трижды",
}
SPOKEN_NUMBER_STEMS = ("тысяч", "миллион", "миллиард", "сотн", "десятк",
                       "одиннадцат", "двенадцат", "пятнадцат")
MONEY_WORDS = {
    "dollars", "dollar", "bucks", "grand", "percent", "cents",
    "millionaire", "billionaire", "revenue", "profit", "salary", "rent",
}
MONEY_STEMS = ("рубл", "долл", "бакс", "евро", "процент", "косар", "лям",
               "выручк", "прибыл", "зарплат", "аренд", "оборот", "миллионер",
               "доход")

# Слова, которые ставят что-то на кон. Хук без них - утверждение; хук с одним
# из них - причина досмотреть.
STAKES = {
    "stop", "never", "wrong", "mistake", "mistakes", "lost", "lose", "losing",
    "cost", "costs", "broke", "broken", "failed", "failure", "fail", "nobody",
    "no", "not", "don't", "dont", "doesn't", "didn't", "can't", "won't",
    "quit", "quitting", "fired", "deleted", "delete", "killed", "kills", "kill",
    "replaced", "replaces", "cut", "beat", "free", "paid", "charged", "hired",
    "saved", "first",
    "banned", "illegal", "worst", "hate", "hated", "wasted", "waste", "scam",
    "lie", "lied", "lying", "truth", "secret", "hidden", "stole", "stolen",
    "before", "until", "instead", "but", "except", "unless", "problem",
    "risk", "danger", "warning", "regret", "wish", "should", "shouldn't",
    "still", "already", "only", "without", "versus", "vs", "actually",
    # ru, точные формы
    "стоп", "хватит", "никогда", "никто", "ничего", "не", "нет", "нельзя",
    "бесплатно", "даром", "правда", "секрет", "до", "пока", "вместо", "но",
    "кроме", "раньше", "против", "только", "без", "уже", "еще", "жаль", "зря",
    "впустую", "первый", "первые", "хуже", "худший", "худшая", "ложь",
}
STAKE_STEMS = (
    "ошибк", "ошиб", "потерял", "потеря", "теря", "слил", "стоил", "стоит",
    "провал", "провалил", "бросил", "брос", "уволил", "уволи", "удалил", "удали",
    "убил", "убива", "замени", "заменя", "заплатил", "переплат", "сэконом",
    "спас", "запрещ", "запрет", "незакон", "ненави", "обман", "развод", "врут",
    "соврал", "скрыв", "скрыт", "украл", "укради", "проблем", "риск", "опасн",
    "предупрежд", "пожалел", "жалею", "должен", "должна", "должны", "неправильн",
    "на самом", "сгорел", "выгор", "банкрот", "долг", "штраф", "блокир", "бан",
)

# Начала, которые тратят первую секунду впустую.
WEAK_OPENERS = [
    "so", "ok", "okay", "hey", "hi", "hello", "guys", "yo", "alright",
    "welcome", "today", "basically", "honestly", "look", "listen", "um",
    "just", "let", "lets", "let's", "i wanted", "i want", "one of",
    "have you", "did you", "do you", "are you", "in this", "in today",
    "the thing", "a lot", "there is", "there are", "this is", "it is",
    "as a", "when it", "if you've", "you know",
    # ru
    "итак", "так вот", "ну", "короче", "в общем", "вообщем", "привет",
    "всем привет", "здравствуйте", "добрый", "доброе", "ребята", "ребят",
    "друзья", "народ", "сегодня", "честно", "слушайте", "слушай", "давайте",
    "давай", "я хочу", "я хотел", "я хотела", "хочу рассказать", "один из",
    "одна из", "вы когда-нибудь", "ты когда-нибудь", "а вы", "а ты",
    "в этом", "в сегодняшнем", "есть такая", "есть такой", "это", "когда речь",
    "знаете", "знаешь", "вот", "эм", "э", "как бы", "типа",
]

# Повелительные формы, которые заслуживают первого места.
IMPERATIVES = {
    "stop", "steal", "copy", "delete", "try", "watch", "read", "save",
    "use", "build", "make", "write", "send", "take", "start", "quit",
    "never", "always", "don't", "dont", "do", "put", "run", "check",
    "стоп", "хватит", "никогда", "всегда", "не",
}
IMPERATIVE_STEMS = (
    "перестан", "прекрат", "укради", "украдит", "забира", "копиру", "удали",
    "попробу", "смотри", "посмотри", "глянь", "читай", "прочитай", "сохран",
    "используй", "сделай", "напиши", "пиши", "отправь", "возьми", "начни",
    "брось", "проверь", "запомни", "повтори", "ставь", "убери", "добавь",
)

DEALBREAKERS = [
    (re.compile(r"(?i)^\s*(?:stop scrolling|don'?t scroll)"),
     "Начинается со «stop scrolling». Просить внимания - значит признать, что вы его не заработали."),
    (re.compile(r"(?i)^\s*(?:стоп[,!.]?\s*)?(?:не листай\w*|не пролистыва\w*|не скролль\w*|остановись)"),
     "Начинается с «не листай». Просить внимания - значит признать, что вы его не заработали."),
    (re.compile(r"(?i)\b(?:in (?:this|today'?s) (?:video|reel)|i'?m going to show you|i'?ll show you how)\b"),
     "Вступление в духе «in this video». Удалите и начните сразу с сути."),
    (re.compile(r"(?i)\b(?:в (?:этом|сегодняшнем) (?:видео|ролике|рилсе|рилс)|(?:сегодня|сейчас) я (?:вам |тебе )?(?:покажу|расскажу)|я (?:вам |тебе )?покажу,? как)\b"),
     "Вступление «в этом видео я покажу». Удалите и начните сразу с сути."),
    (re.compile(r"(?i)^\s*(?:hey |hi |what'?s up |welcome )"),
     "Приветствие. В ленту никто не приходит, чтобы с ним поздоровались."),
    (re.compile(r"(?i)^\s*(?:привет|всем привет|здравствуйте|хай|салют|добрый (?:день|вечер)|доброе утро)\b"),
     "Приветствие. В ленту никто не приходит, чтобы с ним поздоровались."),
    (HASHTAG_RE,
     "Хэштег в хуке. Хэштегам место внизу подписи, если вообще где-то."),
    (EMOJI_RE,
     "Эмодзи в хуке. В тексте на экране крупным шрифтом есть место либо для слов, либо для эмодзи."),
]


def clamp(n):
    return max(0.0, min(100.0, n))


def words(text):
    # «180 000» и «$18,000» произносятся как одно число, значит и тут это одно слово.
    text = re.sub(r"(?<=\d)[,\s  ](?=\d{3}\b)", "", text)
    return [w for w in WORD_RE.findall(text) if any(c.isalnum() for c in w)]


def is_payload(token, raw, i):
    return (token in STAKES or stem_hit(token, SPOKEN_NUMBERS, SPOKEN_NUMBER_STEMS)
            or stem_hit(token, MONEY_WORDS, MONEY_STEMS)
            or any(token.startswith(s) for s in STAKE_STEMS)
            or NUMBER_RE.match(raw) or (i and PROPER_RE.match(raw)))


def check_length(text):
    """Хук должен сработать раньше, чем дрогнет палец. Примерно две секунды."""
    w = words(text)
    n = len(w)
    secs = n / 2.2                       # ~130 слов в минуту в русской речи
    chars = len(text.strip())
    if 4 <= n <= 10:
        score = 100.0
    elif n < 4:
        score = clamp(100 - (4 - n) * 22)
    else:
        score = clamp(100 - (n - 10) * 12)
    if chars > 70:                       # две строки крупного текста на экране
        score -= 12
    return clamp(score), (f"{n} слов, {chars} знаков, ~{secs:.1f} с вслух "
                          "(нужно 4-10 слов)")


def check_specificity(text):
    """Одна конкретная деталь лучше трёх абстрактных."""
    nums = [n.strip() for n in NUMBER_RE.findall(text) if n.strip()]
    propers = set(PROPER_RE.findall(text))
    low = [norm(w) for w in words(text)]
    spoken = [w for w in low if stem_hit(w, SPOKEN_NUMBERS, SPOKEN_NUMBER_STEMS)
              or stem_hit(w, MONEY_WORDS, MONEY_STEMS)]
    hits = len(nums) + len(propers) + len(spoken)
    score = 15.0 if hits == 0 else clamp(45 + hits * 30)
    found = ", ".join(nums[:2] + sorted(propers)[:2] + spoken[:2])
    return score, (f"конкретных деталей: {hits}" + (f" ({found})" if found else
                   " - ни числа, ни имени, нечего проверить"))


def check_stakes(text):
    """Напряжение, цена, отрицание. То, что зритель может потерять."""
    w = [norm(x) for x in words(text)]
    hits = [x for x in w if stem_hit(x, STAKES, STAKE_STEMS)]
    markers = sorted(set(hits))
    if re.search(r"[$€]\s?\d|\d\s?(?:₽|руб)", text):
        markers.append("цена")
    n = len(markers)
    score = {0: 20.0, 1: 70.0}.get(n, 100.0)
    detail = f"маркеров напряжения: {n}" + (f" ({', '.join(markers[:4])})" if markers else
                                            " - в этой фразе ничего не стоит на кону")
    return clamp(score), detail


def check_frontload(text):
    """Самое интересное слово не может стоять девятым."""
    w = words(text)
    if not w:
        return 0.0, "пусто"
    low = [norm(x) for x in w]
    opener = " ".join(low[:2])
    penalty = 0
    hit_opener = None
    for weak in WEAK_OPENERS:
        weak_n = norm(weak)
        if opener == weak_n or opener.startswith(weak_n + " ") or low[0] == weak_n:
            penalty, hit_opener = 30, weak
            break
    payload = None
    for i, token in enumerate(low):
        if is_payload(token, w[i], i):
            payload = i
            break
    if payload is None:
        base = 30.0
        where = "во фразе нет ни одного цепляющего слова"
    elif payload <= 2:
        base = 100.0
        where = f"суть на {payload + 1}-м слове"
    elif payload <= 5:
        base = 70.0
        where = f"суть на {payload + 1}-м слове, можно ближе к началу"
    else:
        base = 40.0
        where = f"суть на {payload + 1}-м слове, слишком поздно"
    detail = where + (f"; слабое начало «{hit_opener}»" if hit_opener else "")
    return clamp(base - penalty), detail


YOU_RE = re.compile(r"(?i)\b(?:you|your|you're|youre|yourself|ты|тебя|тебе|тобой|твой|твоя|твое|твоё|"
                    r"твои|твоих|твоим|твоей|твоего|вы|вас|вам|вами|ваш|ваша|ваше|ваши|ваших|"
                    r"вашим|вашей|вашего)\b")
ME_RE = re.compile(r"(?i)\b(?:i|my|me|we|our|я|мне|меня|мной|мой|моя|мое|моё|мои|моих|моим|моей|"
                   r"моего|мы|нас|нам|нами|наш|наша|наше|наши|наших)\b")


def check_address(text):
    """Обращено к одному зрителю или висит в воздухе."""
    w = [norm(x) for x in words(text)]
    if YOU_RE.search(text):
        return 100.0, "обращается к зрителю"
    if w and stem_hit(w[0], IMPERATIVES, IMPERATIVE_STEMS):
        return 90.0, f"начинается с повелительной формы («{w[0]}»)"
    if ME_RE.search(text):
        return 70.0, "от первого лица, зритель не назван"
    return 35.0, "в третьем лице, в комнате никого нет"


CHECKS = ["ДЛИНА", "КОНКРЕТИКА", "СТАВКА", "СУТЬ В НАЧАЛЕ", "ОБРАЩЕНИЕ"]
VERDICT_STRONG, VERDICT_OK, VERDICT_WEAK = "СИЛЬНЫЙ", "НОРМ", "СЛАБЫЙ"


def run(text):
    results = {
        "ДЛИНА": check_length(text),
        "КОНКРЕТИКА": check_specificity(text),
        "СТАВКА": check_stakes(text),
        "СУТЬ В НАЧАЛЕ": check_frontload(text),
        "ОБРАЩЕНИЕ": check_address(text),
    }
    flags = []
    for pattern, msg in DEALBREAKERS:
        if pattern.search(text) and msg not in flags:
            flags.append(msg)
    scores = [results[c][0] for c in CHECKS]
    # Самое слабое свойство ограничивает весь хук, как в detect.py: одного
    # провала достаточно, чтобы палец продолжил листать.
    overall = statistics.mean(scores) * 0.6 + min(scores) * 0.4 - len(flags) * 15
    overall = clamp(overall)
    verdict = VERDICT_STRONG if overall >= 70 and min(scores) >= 55 and not flags else (
        VERDICT_OK if overall >= 50 else VERDICT_WEAK)
    return results, overall, verdict, flags


def bar(score, width=24):
    filled = round(score / 100 * width)
    return "#" * filled + "." * (width - filled)


def render_one(text, results, overall, verdict, flags, out=sys.stdout):
    print("\nОЦЕНКА ХУКА", file=out)
    print("=" * 62, file=out)
    print(f"  «{text.strip()}»\n", file=out)
    for name in CHECKS:
        score, detail = results[name]
        print(f"  {name:<14} {bar(score)} {score:5.1f}", file=out)
        print(f"  {'':<14} {detail}", file=out)
    print("-" * 62, file=out)
    print(f"  {'ИТОГ':<14} {bar(overall)} {overall:5.1f}   {verdict}", file=out)
    for f in flags:
        print(f"\n  СТОП-ФАКТОР  {f}", file=out)
    if verdict != VERDICT_STRONG:
        weakest = min(CHECKS, key=lambda c: results[c][0])
        print(f"\n  Самое слабое место: {weakest}. Исправьте его и запустите снова.", file=out)
    print("", file=out)


def render_table(rows, out=sys.stdout):
    print("\nРЕЙТИНГ ХУКОВ\n" + "=" * 78, file=out)
    for i, r in enumerate(rows, 1):
        mark = "->" if i == 1 else "  "
        hook = r["hook"] if len(r["hook"]) <= 62 else r["hook"][:59] + "..."
        print(f"{mark} {r['score']:5.1f} {r['verdict']:<8} {hook}", file=out)
        print(f"        слабое место: {r['weakest']} ({r['checks'][r['weakest']]['score']:.0f})",
              file=out)
        for f in r["flags"]:
            print(f"        стоп-фактор: {f}", file=out)
    print("\nСнимайте первый. Если у первого меньше 50, хука среди этих вариантов нет.\n",
          file=out)


def main():
    ap = argparse.ArgumentParser(description="Оценить хук Reels по пяти свойствам.")
    ap.add_argument("input", nargs="?", default="-", help="файл, один хук на строку, или -")
    ap.add_argument("--hook", help="оценить один хук из командной строки")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if args.hook:
        lines = [args.hook]
    else:
        raw = sys.stdin.read() if args.input == "-" else open(args.input, encoding="utf-8").read()
        lines = [l.strip() for l in raw.splitlines() if l.strip()]
    if not lines:
        print("нечего оценивать", file=sys.stderr)
        sys.exit(2)

    payload = []
    for line in lines:
        results, overall, verdict, flags = run(line)
        payload.append({
            "hook": line,
            "checks": {k: {"score": round(v[0], 1), "detail": v[1]} for k, v in results.items()},
            "weakest": min(CHECKS, key=lambda c: results[c][0]),
            "flags": flags,
            "score": round(overall, 1),
            "verdict": verdict,
        })

    if args.json:
        print(json.dumps(payload if len(payload) > 1 else payload[0], indent=2, ensure_ascii=False))
        return

    if len(payload) == 1:
        results, overall, verdict, flags = run(lines[0])
        render_one(lines[0], results, overall, verdict, flags)
    else:
        render_table(sorted(payload, key=lambda r: -r["score"]))

    sys.exit(0 if max(p["score"] for p in payload) >= 70 else 1)


if __name__ == "__main__":
    main()
