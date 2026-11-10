#!/usr/bin/env python3
"""Персонажи роликов: реестр, единый доступ к позам и «замок» внешности и голоса.

Реестр - content/characters/registry.yaml (ведущий + гости). Замок -
content/characters/locks.json: отпечатки файлов рисунка и параметров голоса.
Рендереры вызывают verify() и не собирают ролик, если персонаж изменился
без подтверждения - так Сёма в каждом ролике выглядит и звучит одинаково.

    python3 content/tools/characters.py                # список и проверка замков
    python3 content/tools/characters.py --lock globus  # запереть персонажа (только
                                                       # новый или перерисованный с согласия владельца)
"""
from __future__ import annotations

import hashlib
import importlib
import json
import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml
from PIL import Image

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
REGISTRY = HERE.parent / "characters" / "registry.yaml"
LOCKS = HERE.parent / "characters" / "locks.json"
sys.path.insert(0, str(HERE))

# Эмоции ведущего (глаза, брови). Гостям без своих эмоций достаётся ближайшее: открытые глаза.
EYES_FALLBACK = {"open": False, "blink": True, "happy": False, "side": False, "sly": False}


@dataclass(frozen=True)
class Character:
    id: str
    name: str
    aliases: tuple[str, ...]
    module: str
    voice: str
    look: tuple[str, ...]

    def pose(self, mouth: int = 0, eyes: str = "open", brows: str = "normal") -> Image.Image:
        """RGBA 600x600. Ведущий - полный набор эмоций, гости - рот и моргание."""
        mod = _module(self.module)
        if hasattr(mod, "pose"):
            return mod.pose(mouth, eyes, brows)
        return mod.sprite(min(mouth, 4), EYES_FALLBACK.get(eyes, False)).convert("RGBA")


@lru_cache(maxsize=None)
def _module(name: str):
    return importlib.import_module(name)


@lru_cache(maxsize=1)
def registry() -> dict:
    return yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))


def get(cid: str) -> Character:
    data = registry()["characters"].get(cid)
    if data is None:
        raise SystemExit(f"нет персонажа {cid!r} в {REGISTRY.name}: {', '.join(registry()['characters'])}")
    return Character(cid, data["name"], tuple(data.get("aliases", [])), data["module"], data["voice"],
                     tuple(data.get("look", [])))


def main_id() -> str:
    return registry()["main"]


def by_alias(word: str) -> str | None:
    """«Глобус» -> globus. Регистр и ё не важны."""
    key = word.strip().lower().replace("ё", "е")
    for cid, data in registry()["characters"].items():
        names = [cid, data["name"], *data.get("aliases", [])]
        if any(key == n.lower().replace("ё", "е") for n in names):
            return cid
    return None


# ------------------------------------------------------------------ замок

def _files(paths: tuple[str, ...]) -> list[Path]:
    out = []
    for p in paths:
        path = ROOT / p
        out += sorted(f for f in path.iterdir() if f.is_file()) if path.is_dir() else [path]
    return out


def fingerprint(cid: str, only: list[str] | None = None) -> dict:
    """Отпечатки файлов рисунка и параметров голоса. only - проверять только эти файлы
    (у Сёмы новые сочетания эмоций дорисовываются в кэш, это не изменение внешности)."""
    import semya_voice
    ch = get(cid)
    files = {}
    for f in _files(ch.look):
        rel = str(f.relative_to(ROOT))
        if only is None or rel in only:
            files[rel] = hashlib.sha256(f.read_bytes()).hexdigest()
    voice = semya_voice.VARIANTS.get(ch.voice)
    if voice is None:
        raise SystemExit(f"у {ch.name} голос {ch.voice!r}, такого нет в semya_voice.VARIANTS")
    return {"voice": ch.voice, "voice_params": {k: v for k, v in voice.items() if k != "title"},
            "files": files}


def _locks() -> dict:
    return json.loads(LOCKS.read_text(encoding="utf-8")) if LOCKS.exists() else {}


def check(cid: str) -> list[str]:
    """Что изменилось у персонажа с момента запирания. Пусто - всё как было."""
    lock = _locks().get(cid)
    if lock is None:
        return [f"{get(cid).name}: не заперт (python3 content/tools/characters.py --lock {cid})"]
    now = fingerprint(cid, list(lock["files"]))
    problems = []
    if now["voice"] != lock["voice"] or now["voice_params"] != lock["voice_params"]:
        problems.append(f"{get(cid).name}: изменился голос ({lock['voice']} -> {now['voice']})")
    for rel, digest in lock["files"].items():
        if rel not in now["files"]:
            problems.append(f"{get(cid).name}: пропал файл рисунка {rel}")
        elif now["files"][rel] != digest:
            problems.append(f"{get(cid).name}: изменился рисунок {rel}")
    return problems


def verify(ids: list[str]) -> None:
    """Остановить рендер, если хоть один персонаж изменился."""
    problems = [p for cid in dict.fromkeys(ids) for p in check(cid)]
    if problems:
        raise SystemExit("Персонаж изменился, ролик не собран:\n  " + "\n  ".join(problems) +
                         "\nВерните прежний рисунок/голос или, если владелец одобрил новый вид,"
                         " запритесь заново: python3 content/tools/characters.py --lock <id>")


def lock(cid: str) -> None:
    locks = _locks()
    locks[cid] = fingerprint(cid)
    LOCKS.write_text(json.dumps(locks, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"{get(cid).name}: заперт, файлов {len(locks[cid]['files'])}, голос {locks[cid]['voice']}")


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--lock":
        lock(sys.argv[2])
        sys.exit(0)
    bad = False
    for cid in registry()["characters"]:
        ch, problems = get(cid), check(cid)
        role = "ведущий" if cid == main_id() else "гость"
        print(f"{'OK ' if not problems else 'ИЗМ'} {ch.name} ({cid}, {role}, голос {ch.voice})")
        for p in problems:
            print("     " + p)
        bad = bad or bool(problems)
    sys.exit(1 if bad else 0)
