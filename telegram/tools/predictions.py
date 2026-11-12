#!/usr/bin/env python3
"""Журнал прогнозов с честной статистикой для канала аналитики матчей.

    python3 telegram/tools/predictions.py add --match "Зенит - Спартак" --date 2026-11-12 \\
        --pick "П1" --odds 2.10 --prob 0.52 --why "форма дома 8-1-1, у гостей нет двух защитников"
    python3 telegram/tools/predictions.py settle <id> win|loss|void
    python3 telegram/tools/predictions.py stats            # статистика для поста
    python3 telegram/tools/predictions.py open             # нерассчитанные

Каждый прогноз записывается ДО матча (время записи фиксируется) и не удаляется:
и попадания, и промахи остаются в статистике. Прогноз без перевеса не принимается:
наша вероятность должна быть выше вероятности по коэффициенту (1/odds) на min_edge
из channels.yaml. Это не делает прогноз «верным» - только отсекает ставки,
которые заведомо проигрывают марже букмекера на длинной дистанции.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
LOG = ROOT / "state" / "predictions.json"
CONFIG = yaml.safe_load((ROOT / "channels.yaml").read_text(encoding="utf-8"))
MIN_EDGE = next((c.get("min_edge", 0.03) for c in CONFIG["channels"] if c["type"] == "predictions"), 0.03)


def load() -> list[dict]:
    return json.loads(LOG.read_text(encoding="utf-8")) if LOG.exists() else []


def save(rows: list[dict]) -> None:
    LOG.parent.mkdir(exist_ok=True)
    LOG.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")


def add(a: argparse.Namespace) -> int:
    if not 1.01 <= a.odds <= 50:
        raise SystemExit("коэффициент вне разумных пределов")
    if not 0.01 <= a.prob <= 0.95:
        raise SystemExit("вероятность выше 95% в спорте не бывает - проверьте расчёт")
    implied = 1 / a.odds
    edge = a.prob - implied
    if edge < MIN_EDGE:
        raise SystemExit(f"перевеса нет: наша {a.prob:.0%}, по коэффициенту {implied:.0%} (нужно +{MIN_EDGE:.0%}). "
                         "Такой прогноз не публикуем.")
    rows = load()
    row = {"id": len(rows) + 1, "match": a.match, "date": a.date, "pick": a.pick, "odds": a.odds,
           "prob": a.prob, "implied": round(implied, 4), "edge": round(edge, 4), "why": a.why,
           "created": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "result": None}
    rows.append(row)
    save(rows)
    print(json.dumps(row, ensure_ascii=False))
    return 0


def settle(a: argparse.Namespace) -> int:
    rows = load()
    for r in rows:
        if r["id"] == a.id:
            if r["result"] is not None:
                raise SystemExit(f"прогноз {a.id} уже рассчитан: {r['result']} (результаты не переписываем)")
            r["result"] = a.result
            r["settled"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            save(rows)
            print(json.dumps(r, ensure_ascii=False))
            return 0
    raise SystemExit(f"нет прогноза {a.id}")


def stats(_: argparse.Namespace | None = None) -> dict:
    rows = [r for r in load() if r["result"] in ("win", "loss")]
    n = len(rows)
    wins = sum(r["result"] == "win" for r in rows)
    profit = sum((r["odds"] - 1) if r["result"] == "win" else -1 for r in rows)
    brier = sum((r["prob"] - (r["result"] == "win")) ** 2 for r in rows) / n if n else None
    expected = sum(r["prob"] for r in rows)
    out = {"рассчитано": n, "угадано": wins, "процент": round(wins / n * 100, 1) if n else None,
           "ожидали_угадать": round(expected, 1), "прибыль_в_ставках": round(profit, 2),
           "ROI_%": round(profit / n * 100, 1) if n else None, "Brier": round(brier, 3) if brier is not None else None,
           "открыто": sum(r["result"] is None for r in load())}
    if _ is not None:
        print(json.dumps(out, ensure_ascii=False, indent=1))
        if n < 100:
            print(f"\nВыборка {n} прогнозов - меньше 100: о результативности говорить рано.", file=sys.stderr)
    return out


def open_(_: argparse.Namespace) -> int:
    for r in load():
        if r["result"] is None:
            print(f"{r['id']:4} {r['date']} {r['match']} - {r['pick']} @ {r['odds']} (наша {r['prob']:.0%})")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add")
    a.add_argument("--match", required=True); a.add_argument("--date", required=True)
    a.add_argument("--pick", required=True); a.add_argument("--odds", type=float, required=True)
    a.add_argument("--prob", type=float, required=True); a.add_argument("--why", required=True)
    a.set_defaults(func=add)
    s = sub.add_parser("settle")
    s.add_argument("id", type=int); s.add_argument("result", choices=["win", "loss", "void"])
    s.set_defaults(func=settle)
    sub.add_parser("stats").set_defaults(func=lambda x: (stats(x), 0)[1])
    sub.add_parser("open").set_defaults(func=open_)
    args = p.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
