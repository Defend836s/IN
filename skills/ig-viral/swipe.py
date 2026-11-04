#!/usr/bin/env python3
"""
swipe.py - ранжирует собранные Reels по тому, насколько каждый обогнал свой
собственный аккаунт, называет формулу хука и пишет свайп-файл.

Весь смысл скрипта в одной поправке: голые просмотры - не доказательство.
Аккаунт на 2 000 000 подписчиков с 400 000 просмотров просто провёл тихий день.
Аккаунт на 4 000 подписчиков с 400 000 просмотров что-то нашёл. Скрипт
ранжирует по кратности над обычным уровнем аккаунта - это единственная версия
«залетело», из которой можно что-то перенять.

На вход - файл с табуляцией, который вы заполняете по ходу просмотра, один
Reels на строку, первая строка - названия колонок (русские или английские):

    аккаунт   подписчики   медиана   просмотры   хук
    @someone  48000        11000     412000      никто не говорит, что первые 30 рилсов провалятся

`медиана` (median) - типичные просмотры аккаунта за последнее время, это
лучшая база. Если есть только `подписчики` (followers), колонку медианы можно
не заполнять, скрипт так и скажет. `хук` (hook) - первая фраза ролика, сказанная
или на экране, словами автора.

Запуск
  python3 swipe.py captured.tsv
  python3 swipe.py captured.tsv --out ~/.claude/instagram/swipe.md
  python3 swipe.py captured.tsv --json
"""

import argparse
import json
import os
import re
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
HOOKS = os.path.join(HERE, "..", "ig-reel", "hooks.json")
WORD_RE = re.compile(r"[A-Za-zА-Яа-яЁё0-9$₽€%'’-]+")

# Русские названия колонок -> внутренние английские ключи.
COLUMN_ALIASES = {
    "аккаунт": "account", "автор": "account", "ник": "account",
    "подписчики": "followers", "подписчиков": "followers",
    "медиана": "median", "просмотры": "views", "просмотров": "views",
    "хук": "hook", "на экране": "on-screen", "длина": "length", "призыв": "cta",
}

try:                                              # по желанию: оценить и хуки
    sys.path.insert(0, os.path.join(HERE, "..", "ig-reel"))
    from hookscore import run as score_hook       # noqa: E402
except Exception:                                 # ig-viral скопирован отдельно
    score_hook = None


def load_formulas(path):
    try:
        d = json.load(open(path, encoding="utf-8"))
    except Exception:
        return None
    by_id = {h["id"]: h for h in d["hooks"]}
    order = d.get("classify_order") or sorted(by_id)
    return [(by_id[i]["id"], by_id[i]["name"],
             re.compile(by_id[i]["match"], re.IGNORECASE)) for i in order if i in by_id]


UNCLASSIFIED = "без формулы"


def classify(hook, formulas):
    if not formulas:
        return None, UNCLASSIFIED
    for fid, name, pattern in formulas:
        if pattern.search(hook):
            return fid, name
    return None, UNCLASSIFIED


def read_rows(path):
    raw = sys.stdin.read() if path == "-" else open(path, encoding="utf-8").read()
    lines = [l for l in raw.splitlines() if l.strip() and not l.lstrip().startswith("#")]
    if not lines:
        return []
    head = [COLUMN_ALIASES.get(c.strip().lower(), c.strip().lower())
            for c in lines[0].split("\t")]
    if "views" in head and "hook" in head:
        cols, body = head, lines[1:]
    else:
        cols, body = ["account", "followers", "views", "hook"], lines
    rows = []
    for line in body:
        cells = line.split("\t")
        if len(cells) < len(cols):
            cells += [""] * (len(cols) - len(cells))
        r = dict(zip(cols, [c.strip() for c in cells]))
        try:
            r["views"] = int(re.sub(r"[^\d]", "", r.get("views", "")) or 0)
        except ValueError:
            continue
        for k in ("followers", "median"):
            digits = re.sub(r"[^\d]", "", r.get(k, "") or "")
            r[k] = int(digits) if digits else None
        if r["views"] and r.get("hook"):
            rows.append(r)
    return rows


def analyse(rows, formulas):
    used_median = any(r.get("median") for r in rows)
    for r in rows:
        base = r.get("median") or r.get("followers") or 0
        r["baseline"] = base
        r["outlier"] = round(r["views"] / base, 2) if base else None
        r["formula_id"], r["formula"] = classify(r["hook"], formulas)
        r["words"] = len(WORD_RE.findall(r["hook"]))
        if score_hook:
            _, overall, verdict, _ = score_hook(r["hook"])
            r["hook_score"], r["hook_verdict"] = round(overall, 1), verdict
        else:
            r["hook_score"], r["hook_verdict"] = None, None
    ranked = sorted(rows, key=lambda r: -(r["outlier"] or 0))
    third = max(1, len(ranked) // 3)
    top, bottom = ranked[:third], ranked[-third:]

    def med(items, key):
        vals = [i[key] for i in items if i.get(key) is not None]
        return round(statistics.median(vals), 1) if vals else None

    counts = {}
    for r in top:
        counts[r["formula"]] = counts.get(r["formula"], 0) + 1
    return {
        "baseline": "медиана аккаунта" if used_median else "число подписчиков",
        "n": len(ranked),
        "accounts": len({r.get("account", "") for r in ranked}),
        "reels": ranked,
        "top_formulas": sorted(counts.items(), key=lambda kv: -kv[1]),
        "top_hook_score": med(top, "hook_score"),
        "bottom_hook_score": med(bottom, "hook_score"),
        "top_words": med(top, "words"),
        "bottom_words": med(bottom, "words"),
        "unclassified": sum(1 for r in ranked if r["formula"] == UNCLASSIFIED),
    }


def render(a, out=sys.stdout):
    head = (f"СВАЙП-ФАЙЛ  ·  роликов {a['n']}  ·  аккаунтов {a['accounts']}  ·  "
            f"база: {a['baseline']}")
    print("\n" + head, file=out)
    print("=" * max(len(head), 78), file=out)
    for r in a["reels"]:
        mult = f"{r['outlier']:.1f}x" if r["outlier"] else "   ?"
        score = f"{r['hook_score']:.0f}" if r["hook_score"] is not None else " -"
        fid = f"#{r['formula_id']:<2}" if r["formula_id"] else "-  "
        print(f"  {mult:>7}  хук {score:>3}  {fid} {r['formula'][:22]:<22} "
              f"{r.get('account', '')[:16]:<16} {r['views']:>9,}".replace(",", " "), file=out)
        print(f"           «{r['hook'][:96]}»", file=out)
    print("-" * max(len(head), 78), file=out)
    print("ЧТО РАБОТАЕТ В ЭТОЙ ВЫБОРКЕ", file=out)
    if a["top_formulas"]:
        print("  верхняя треть по кратности:  "
              + ", ".join(f"{n} x{c}" for n, c in a["top_formulas"][:4]), file=out)
    if a["top_hook_score"] is not None:
        print(f"  медианная оценка хука:       верх {a['top_hook_score']:.0f}  "
              f"против низа {a['bottom_hook_score']:.0f}", file=out)
    print(f"  медианная длина хука:        верх {a['top_words']} слов  "
          f"против низа {a['bottom_words']} слов", file=out)
    print(f"  без формулы:                 {a['unclassified']} из {a['n']}. Прочитайте их "
          "вручную: там прячется формула, которой у вас ещё нет.", file=out)
    print("\n  Выборка, собранная руками, - это свидетельство, а не доказательство. Двенадцать "
          "роликов не\n  показывают ничего; сорок из шести аккаунтов уже что-то показывают. "
          "Соберите больше, прежде чем верить.\n", file=out)


def to_markdown(a):
    lines = ["# Свайп-файл", "",
             f"Роликов: {a['n']}, аккаунтов: {a['accounts']}. "
             f"Ранжировано по кратности над базой ({a['baseline']}).", ""]
    for r in a["reels"]:
        mult = f"{r['outlier']:.1f}x" if r["outlier"] else "?"
        lines += [f"## {mult}  {r['formula']}  ({r.get('account', '')})",
                  f"- просмотры: {r['views']:,}  база: {r['baseline']:,}".replace(",", " "),
                  f"- оценка хука: {r['hook_score']}  слов: {r['words']}",
                  f"- хук: «{r['hook']}»", ""]
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser(description="Ранжировать собранные Reels по кратности.")
    ap.add_argument("input", nargs="?", default="-", help="TSV-файл или - для stdin")
    ap.add_argument("--hooks", default=HOOKS, help="путь к ig-reel/hooks.json")
    ap.add_argument("--out", help="дополнительно записать свайп-файл в markdown сюда")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    rows = read_rows(args.input)
    if not rows:
        print("нет пригодных строк. Нужен файл с табуляцией, где есть хотя бы просмотры и хук.",
              file=sys.stderr)
        sys.exit(2)
    formulas = load_formulas(args.hooks)
    a = analyse(rows, formulas)
    if not formulas:
        print("заметка: hooks.json не найден, формулы не названы. Укажите --hooks.", file=sys.stderr)
    if score_hook is None:
        print("заметка: hookscore.py не импортируется, оценки хуков пропущены.", file=sys.stderr)

    if args.json:
        print(json.dumps(a, indent=2, ensure_ascii=False))
    else:
        render(a)
    if args.out:
        path = os.path.expanduser(args.out)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        open(path, "w", encoding="utf-8").write(to_markdown(a))
        print(f"записано: {path}", file=sys.stderr)


if __name__ == "__main__":
    main()
