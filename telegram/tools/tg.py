#!/usr/bin/env python3
"""Публикация в Telegram-каналы из channels.yaml с проверкой правил по типу канала.

    python3 telegram/tools/tg.py check kzn post.html            # только проверка
    python3 telegram/tools/tg.py post kzn post.html [--photo img.jpg] [--keys k1,k2]
    python3 telegram/tools/tg.py poll free "Какой курс выложить следующим?" "Python|Дизайн|Excel"

Текст - HTML Telegram (<b>, <i>, <a href="...">). Ключ бота - TELEGRAM_BOT_TOKEN,
канал - chat из channels.yaml. Нет ключа или chat - пост сохраняется черновиком
в telegram/drafts/<канал>/ (ничего не теряется, опубликовать можно позже).
--keys - ключи новостей из feeds.py: после публикации они больше не предлагаются.

Проверки (ОШИБКА - пост не уйдёт), подробно - telegram/RULES.md:
  все:          длина (4096 / 1024 с фото), обещания гарантий;
  news:         ссылка на источник обязательна;
  invest:       пометка «не является индивидуальной инвестиционной рекомендацией»,
                без призывов «купите/продавайте» и обещаний доходности;
  predictions:  «18+» и «прогноз не гарантирует выигрыш», без «верняк/100%/договорняк»
                и без рекламы букмекеров.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
import feeds  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
API = "https://api.telegram.org/bot{token}/{method}"

INVEST_DISCLAIMER = re.compile(r"не\s+является\s+индивидуальной\s+инвестиционной\s+рекомендаци", re.I)
BET_18 = re.compile(r"18\s?\+")
BET_DISCLAIMER = re.compile(r"не\s+гарантиру\w+\s+выигрыш", re.I)
RULES = {
    "all": [
        (r"гарантирован\w*\s+(доход|прибыл|выигрыш|рост)|без\s+риска|100\s?%\s*(доход|прибыл|проход|выигрыш)",
         "обещание гарантированного результата"),
        (r"\bслив\w*\s+курс|скача\w*\s+платн", "пиратский контент"),
    ],
    "invest": [
        (r"\b(купите|покупайте|продавайте|продайте|заходите\s+в|срочно\s+бери)\b",
         "прямой призыв купить/продать - это индивидуальная рекомендация, нужна лицензия инвестсоветника"),
        (r"удво\w+\s+(капитал|деньг|вложен)|\bx\s?\d{1,3}\b|иксы|точно\s+вырастет",
         "обещание доходности"),
        (r"оплат\w+\s+(в\s+)?(криптовалют|биткоин)|принима\w+\s+(криптовалют|биткоин)",
         "предложение криптовалюты как средства платежа запрещено в РФ (259-ФЗ)"),
    ],
    "predictions": [
        (r"верняк|железобетон|договорн\w+|инсайд\w*\s+(на\s+)?матч|\b100\s?%", "ложная уверенность / договорные матчи"),
        (r"fonbet|фонбет|winline|винлайн|лига\s+ставок|1xbet|1хбет|мелбет|melbet|pari|пари\s?матч|bet\s?boom|"
         r"бетбум|марафонбет|olimp\s?bet|олимпбет|leon|леон\s?бетс|zenit\s?bet|зенит\s?бет",
         "название букмекера - реклама ставок в Telegram без соблюдения закона о рекламе (ст. 27) запрещена"),
        (r"закрыт\w+\s+(канал|прогноз)|vip|платн\w+\s+прогноз|продаю\s+прогноз",
         "продажа прогнозов - типичная схема мошенничества, не делаем"),
    ],
}


def check(cid: str, text: str, photo: bool = False) -> list[str]:
    ch = feeds.channel(cid)
    kind = ch["type"]
    plain = re.sub(r"<[^>]+>", "", text)
    errs = []
    limit = 1024 if photo else 4096
    if len(plain) > limit:
        errs.append(f"длина {len(plain)} > {limit}")
    for pattern, why in RULES["all"] + RULES.get(kind, []):
        m = re.search(pattern, plain, re.I)
        if m:
            errs.append(f"«{m.group(0)}»: {why}")
    if kind == "news" and not re.search(r"https?://", text):
        errs.append("нет ссылки на источник новости")
    if kind == "invest" and not INVEST_DISCLAIMER.search(plain):
        errs.append("нет пометки «Не является индивидуальной инвестиционной рекомендацией»")
    if kind == "predictions" and not (BET_18.search(plain) and BET_DISCLAIMER.search(plain)):
        errs.append("нет «18+» и «прогноз не гарантирует выигрыш»")
    return errs


def draft(cid: str, text: str, photo: str | None, reason: str) -> Path:
    folder = ROOT / "drafts" / cid
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / (datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S") + ".html")
    path.write_text((f"<!-- photo: {photo} -->\n" if photo else "") + text, encoding="utf-8")
    print(f"черновик: {path} ({reason})")
    return path


def log(cid: str, entry: dict) -> None:
    path = ROOT / "state" / f"posts-{cid}.jsonl"
    path.parent.mkdir(exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), **entry},
                            ensure_ascii=False) + "\n")


def call(method: str, data: dict, files: dict | None = None) -> dict:
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    resp = requests.post(API.format(token=token, method=method), data=data, files=files, timeout=60)
    body = resp.json()
    if not body.get("ok"):
        raise SystemExit(f"Telegram {method}: {body.get('description')}")
    return body["result"]


def target(cid: str) -> str | None:
    chat = feeds.channel(cid).get("chat")
    return chat if chat and os.environ.get("TELEGRAM_BOT_TOKEN") else None


def post(a: argparse.Namespace) -> int:
    text = Path(a.file).read_text(encoding="utf-8").strip()
    errs = check(a.channel, text, bool(a.photo))
    if errs:
        print("НЕ ОПУБЛИКОВАНО:\n- " + "\n- ".join(errs))
        return 1
    keys = [k for k in (a.keys or "").split(",") if k]
    chat = target(a.channel)
    if not chat or a.dry_run:
        draft(a.channel, text, a.photo, "проба" if a.dry_run else "нет TELEGRAM_BOT_TOKEN или chat в channels.yaml")
        if keys and not a.dry_run:
            feeds.mark_seen(a.channel, keys)
        return 0
    if a.photo:
        with open(a.photo, "rb") as fh:
            res = call("sendPhoto", {"chat_id": chat, "caption": text, "parse_mode": "HTML"}, {"photo": fh})
    else:
        res = call("sendMessage", {"chat_id": chat, "text": text, "parse_mode": "HTML",
                                   "link_preview_options": json.dumps({"is_disabled": False})})
    feeds.mark_seen(a.channel, keys)
    log(a.channel, {"message_id": res["message_id"], "keys": keys, "chars": len(text)})
    print(f"опубликовано: {a.channel} message_id={res['message_id']}")
    return 0


def poll(a: argparse.Namespace) -> int:
    options = [o.strip() for o in a.options.split("|") if o.strip()]
    if not 2 <= len(options) <= 10:
        raise SystemExit("в опросе 2-10 вариантов")
    chat = target(a.channel)
    if not chat:
        draft(a.channel, f"ОПРОС: {a.question}\n" + "\n".join(f"- {o}" for o in options), None,
              "нет TELEGRAM_BOT_TOKEN или chat")
        return 0
    res = call("sendPoll", {"chat_id": chat, "question": a.question[:300],
                            "options": json.dumps([{"text": o[:100]} for o in options], ensure_ascii=False),
                            "is_anonymous": "true"})
    log(a.channel, {"message_id": res["message_id"], "poll": a.question})
    print(f"опрос опубликован: message_id={res['message_id']}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check"); c.add_argument("channel"); c.add_argument("file"); c.add_argument("--photo")
    c.set_defaults(func=lambda a: (print("\n".join(check(a.channel, Path(a.file).read_text(encoding="utf-8"),
                                                          bool(a.photo))) or "ок"), 0)[1])
    s = sub.add_parser("post"); s.add_argument("channel"); s.add_argument("file")
    s.add_argument("--photo"); s.add_argument("--keys"); s.add_argument("--dry-run", action="store_true")
    s.set_defaults(func=post)
    q = sub.add_parser("poll"); q.add_argument("channel"); q.add_argument("question"); q.add_argument("options")
    q.set_defaults(func=poll)
    a = p.parse_args()
    return a.func(a)


if __name__ == "__main__":
    sys.exit(main())
