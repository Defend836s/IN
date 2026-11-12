#!/usr/bin/env python3
"""Сводка рынка для инвестиционного канала: курсы ЦБ, индекс Мосбиржи, криптовалюты.

    python3 telegram/tools/markets.py          # таблица
    python3 telegram/tools/markets.py --json

Источники: ЦБ РФ (официальные курсы), Мосбиржа ISS (индекс IMOEX), CoinGecko
(BTC, ETH, TON). Цифры для поста берутся только отсюда или из новости с ссылкой.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import xml.etree.ElementTree as ET

import requests

UA = {"User-Agent": "Mozilla/5.0 (compatible; VseKursyNewsroom/1.0)"}


def get(url: str) -> requests.Response:
    for attempt in range(4):
        resp = requests.get(url, headers=UA, timeout=20)
        if resp.status_code != 429:
            resp.raise_for_status()
            return resp
        time.sleep(4 * (attempt + 1))   # общий адрес облака упирается в лимит - ждём
    resp.raise_for_status()
    return resp


def cbr() -> dict:
    root = ET.fromstring(get("https://www.cbr.ru/scripts/XML_daily.asp").content)
    out = {"date": root.get("Date")}
    for v in root.iter("Valute"):
        code = v.findtext("CharCode")
        if code in ("USD", "EUR", "CNY"):
            value = float(v.findtext("Value").replace(",", ".")) / int(v.findtext("Nominal"))
            out[code] = round(value, 4)
    return out


def moex() -> dict:
    url = ("https://iss.moex.com/iss/engines/stock/markets/index/securities/IMOEX.json"
           "?iss.meta=off&iss.only=marketdata&marketdata.columns=CURRENTVALUE,LASTCHANGEPRC,UPDATETIME")
    rows = get(url).json()["marketdata"]["data"]
    value, change, at = rows[0] if rows else (None, None, None)
    return {"IMOEX": value, "change_pct": change, "time": at}


def crypto() -> dict:
    url = ("https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum,the-open-network"
           "&vs_currencies=usd&include_24hr_change=true")
    data = get(url).json()
    names = {"bitcoin": "BTC", "ethereum": "ETH", "the-open-network": "TON"}
    return {names[k]: {"usd": v["usd"], "change_24h_pct": round(v.get("usd_24h_change", 0), 2)}
            for k, v in data.items()}


def snapshot() -> dict:
    out = {}
    for name, fn in (("cbr", cbr), ("moex", moex), ("crypto", crypto)):
        try:
            out[name] = fn()
        except (requests.RequestException, ValueError, KeyError, ET.ParseError) as exc:
            out[name] = {"error": str(exc)[:200]}
    return out


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--json", action="store_true")
    a = p.parse_args()
    s = snapshot()
    if a.json:
        print(json.dumps(s, ensure_ascii=False, indent=1))
        return 0
    c, m, k = s["cbr"], s["moex"], s["crypto"]
    if "error" not in c:
        print(f"Курсы ЦБ на {c['date']}: доллар {c['USD']:.2f} ₽, евро {c['EUR']:.2f} ₽, юань {c['CNY']:.2f} ₽")
    if "error" not in m and m["IMOEX"]:
        print(f"Индекс Мосбиржи: {m['IMOEX']:.2f} ({m['change_pct']:+.2f}% , {m['time']})")
    if "error" not in k:
        fmt = lambda x: f"{x:,.0f}".replace(",", " ") if x >= 100 else f"{x:.2f}"
        print("Крипта: " + ", ".join(f"{n} ${fmt(v['usd'])} ({v['change_24h_pct']:+.1f}% за сутки)"
                                     for n, v in k.items()))
    for name, v in s.items():
        if "error" in v:
            print(f"{name}: нет данных ({v['error']})", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
