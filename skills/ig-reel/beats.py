#!/usr/bin/env python3
"""
beats.py - превращает сценарий Reels в раскадровку с таймингом ещё до записи.

Оценивает, сколько времени занимает каждая строка, складывает их в таймкоды и
отмечает четыре вещи, которые убивают Reels на монтаже: хук, который выходит за
три секунды, бит настолько длинный, что зритель успевает уйти, серию строк без
единой конкретной детали и общую длину, не совпадающую с задуманной.

Тайминги - это оценка по количеству слов и темпу речи (слов в минуту). Их
хватает, чтобы спланировать монтаж, но это не замена записи. Задайте свой темп
через --wpm, когда засечёте, как читаете сценарий вслух: в русском большинство
говорит 110-160 слов в минуту (слова длиннее английских), по умолчанию 130.
Для английского сценария ставьте --wpm 165.

Запуск
  python3 beats.py script.txt
  python3 beats.py script.txt --target 30
  python3 beats.py script.txt --wpm 150 --target 45
  pbpaste | python3 beats.py -
  python3 beats.py script.txt --json
"""

import argparse
import json
import re
import sys

WORD_RE = re.compile(r"[A-Za-zА-Яа-яЁё0-9$₽€%'’-]+")
SENT_RE = re.compile(r"[^.!?]+[.!?]*")
CONCRETE_RE = re.compile(r"[$€]\s?\d|\b\d[\d,.]*|(?<!^)(?<![.!?]\s)\b[A-ZА-ЯЁ][a-zа-яё]{2,}\b",
                         re.MULTILINE)
STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "if", "of", "to", "in", "on", "for",
    "with", "that", "this", "it", "is", "are", "was", "were", "be", "been",
    "you", "your", "i", "my", "me", "we", "our", "they", "them", "he", "she",
    "so", "just", "not", "no", "do", "did", "does", "have", "has", "had",
    "will", "can", "at", "as", "by", "from", "out", "up", "off", "one", "all",
    "и", "а", "но", "или", "в", "во", "на", "с", "со", "к", "ко", "по", "за",
    "из", "у", "о", "об", "от", "до", "для", "при", "про", "что", "чтобы",
    "это", "этот", "эта", "эти", "как", "так", "не", "ни", "я", "ты", "вы",
    "мы", "он", "она", "оно", "они", "мне", "меня", "тебе", "тебя", "вам",
    "вас", "нам", "нас", "мой", "моя", "мои", "твой", "твоя", "ваш", "наш",
    "же", "ли", "бы", "то", "все", "всё", "был", "была", "было", "были",
    "есть", "уже", "вот", "ну", "да", "нет", "один", "одна", "его", "ее",
    "её", "их", "там", "тут", "здесь", "если", "когда", "потом", "теперь",
}

HOOK_WINDOW = 3.0        # секунды. После этого палец уже всё решил.
MAX_BEAT = 4.0           # секунды на одной мысли без смены картинки.
ABSTRACT_RUN = 3         # битов подряд без единой проверяемой детали.


def words(text):
    # «180 000» и «$18,000» произносятся как одно число, значит и тут это одно слово.
    found = WORD_RE.findall(re.sub(r"(?<=\d)[,\s\u00a0\u202f](?=\d{3}\b)", "", text))
    return [w for w in found if any(c.isalnum() for c in w)]   # одиночный « - » не слово


def pretty(token):
    """Вернуть разделитель тысяч для вывода."""
    return re.sub(r"(\d)(?=(\d{3})+$)", r"\1 ", token)


def stem(word):
    """Грубая основа слова: русский склоняется, «договор» и «договоре» - одно слово.

    Режем окончание у слов длиннее пяти букв. Это не морфология, но для поиска
    повтора между хуком и последней строкой этого хватает.
    """
    w = word.lower().replace("ё", "е")
    if w.isdigit() or len(w) <= 5:
        return w
    return w[:max(5, len(w) - 3)]


def tc(seconds):
    m, s = divmod(seconds, 60)
    return f"{int(m)}:{s:04.1f}"


def split_beats(raw, wps):
    """Одна строка - один бит, если строка не слишком длинная для одного бита."""
    beats = []
    for line in [l.strip() for l in raw.splitlines()]:
        if not line:
            continue
        if len(words(line)) / wps <= MAX_BEAT * 1.5:
            beats.append(line)
            continue
        # Длинный абзац: режем по концам предложений, чтобы тайминги что-то
        # значили.
        parts = [p.strip() for p in SENT_RE.findall(line) if p.strip()]
        buf = ""
        for part in parts:
            candidate = (buf + " " + part).strip()
            if buf and len(words(candidate)) / wps > MAX_BEAT:
                beats.append(buf)
                buf = part
            else:
                buf = candidate
        if buf:
            beats.append(buf)
    return beats


def analyse(raw, wpm=130, target=None):
    wps = wpm / 60.0
    beats = split_beats(raw, wps)
    if not beats:
        return None

    rows, clock = [], 0.0
    for i, text in enumerate(beats):
        n = len(words(text))
        dur = n / wps
        rows.append({
            "n": i + 1,
            "start": round(clock, 2),
            "dur": round(dur, 2),
            "words": n,
            "text": text,
            "concrete": len(CONCRETE_RE.findall(text)),
            "label": "",
            "flags": [],
        })
        clock += dur
    total = clock

    # Помечаем позиции, вокруг которых на самом деле строится Reels.
    for r in rows:
        if r["n"] == 1 or r["start"] + r["dur"] <= HOOK_WINDOW:
            r["label"] = "ХУК"
    rows[-1]["label"] = "ПРИЗЫВ" if rows[-1]["label"] != "ХУК" else "ХУК/ПРИЗЫВ"
    half = total / 2
    for r in rows:
        if not r["label"] and r["start"] <= half < r["start"] + r["dur"]:
            r["label"] = "СЕРЕДИНА"

    notes = []
    if rows[0]["dur"] > HOOK_WINDOW:
        rows[0]["flags"].append(f"хук идёт {rows[0]['dur']:.1f} с, дольше {HOOK_WINDOW:.0f} с")
        notes.append(f"Бит 1 произносится {rows[0]['dur']:.1f} с. Сократите до "
                     f"{int(HOOK_WINDOW * wps)} слов или меньше, иначе хук прозвучит, когда "
                     "решение уже принято.")
    if rows[0]["concrete"] == 0:
        notes.append("В бите 1 нет ни числа, ни имени. Хуки, в которых нечего проверить, "
                     "пролистывают.")

    for r in rows:
        if r["dur"] > MAX_BEAT:
            r["flags"].append(f"{r['dur']:.1f} с на одном бите")
    long_beats = [r["n"] for r in rows if r["dur"] > MAX_BEAT]
    if long_beats:
        notes.append(f"Бит(ы) {', '.join(map(str, long_beats))} дольше {MAX_BEAT:.0f} с. "
                     "Разбейте строку или смените картинку внутри неё. "
                     "На статичном кадре зрители и уходят.")

    run, start = 0, None
    for r in rows:
        if r["concrete"] == 0:
            run += 1
            start = start if start is not None else r["n"]
            if run == ABSTRACT_RUN:
                notes.append(f"В битах {start}-{r['n']} нет ничего конкретного. "
                             "Добавьте в один из них число, имя или цену.")
        else:
            run, start = 0, None

    # Возвращает ли последняя строка к первой?
    first = {stem(w): w for w in words(rows[0]["text"]) if w.lower() not in STOPWORDS}
    last = {stem(w) for w in words(rows[-1]["text"]) if w.lower() not in STOPWORDS}
    loop = sorted(pretty(first[k]) for k in first.keys() & last)
    if loop:
        notes.append(f"Есть петля: последний бит повторяет «{', '.join(loop[:3])}» из хука. "
                     "Повторные просмотры - бесплатный охват.")
    else:
        notes.append("Петли нет. В последнем бите нет ни одного слова из хука, и видео "
                     "заканчивается плоско. Повторить одно слово из бита 1 - самый дешёвый "
                     "повторный просмотр.")

    if target:
        delta = total - target
        if abs(delta) <= target * 0.1:
            notes.append(f"Длина в цель ({total:.1f} с при цели {target:g} с).")
        elif delta > 0:
            notes.append(f"На {delta:.1f} с длиннее цели. Вырежьте примерно {int(delta * wps)} слов.")
        else:
            notes.append(f"На {-delta:.1f} с короче цели. Добавьте {int(-delta * wps)} слов "
                         "или снимайте короче. Обычно короче - правильно.")

    return {
        "wpm": wpm, "target": target,
        "total_seconds": round(total, 2),
        "total_words": sum(r["words"] for r in rows),
        "beats": rows,
        "notes": notes,
    }


def render(a, out=sys.stdout):
    head = (f"РАСКАДРОВКА  ·  {a['total_words']} слов  ·  ~{a['total_seconds']:.1f} с "
            f"при {a['wpm']:g} сл/мин" + (f"  ·  цель {a['target']:g} с" if a["target"] else ""))
    print("\n" + head, file=out)
    print("=" * max(len(head), 72), file=out)
    for r in a["beats"]:
        label = f"{r['label']:<11}" if r["label"] else " " * 11
        print(f"  {tc(r['start'])}  {r['dur']:4.1f}с  {label}{r['text']}", file=out)
        for f in r["flags"]:
            print(f"  {'':>6}  {'':>5}  {'':<11}^ {f}", file=out)
    print("-" * max(len(head), 72), file=out)
    for n in a["notes"]:
        print(f"  - {n}", file=out)
    print("", file=out)


def main():
    ap = argparse.ArgumentParser(description="Разложить сценарий Reels в раскадровку с таймингом.")
    ap.add_argument("input", nargs="?", default="-", help="файл сценария или - для stdin")
    ap.add_argument("--wpm", type=float, default=130,
                    help="темп речи, слов в минуту (по умолчанию 130; для английского ~165)")
    ap.add_argument("--target", type=float, help="целевая длина в секундах")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    raw = sys.stdin.read() if args.input == "-" else open(args.input, encoding="utf-8").read()
    a = analyse(raw, wpm=args.wpm, target=args.target)
    if not a:
        print("сценарий пуст", file=sys.stderr)
        sys.exit(2)
    if args.json:
        print(json.dumps(a, indent=2, ensure_ascii=False))
    else:
        render(a)
    sys.exit(0)


if __name__ == "__main__":
    main()
