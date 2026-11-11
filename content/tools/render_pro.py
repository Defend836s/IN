#!/usr/bin/env python3
"""Reels «уровня студии» с Енотом Сёмой: субтитры по слову, камера, эмоции, стикеры, звук.

    CHARACTER=semya python content/tools/render_pro.py <сценарий.txt> <выход.mp4>

Сценарий - по фразе в строке. Необязательная разметка:
    [удивлён] [хитрит] [радуется] [объясняет] [спокоен]  - эмоция фразы (в начале строки);
    *слово*                                              - акцент: золото, тряска, щелчок.
    [фото 2]                                             - архивный снимок media/02.jpg (держится,
                                                           пока не сменят); формат «Расследование истории»
    {1903|тысяча девятьсот третьего}                     - на экране 1903, голос читает слова
    Ника: текст                                          - реплика гостя (имя из
                                                           content/characters/registry.yaml).
Ведущий (Енот Сёма) есть в каждом ролике и говорит строки без имени. Гость выходит
справа на своей первой реплике, Сёма сдвигается влево; говорящий крупнее, у каждого
свой голос. Со снимками ([фото N]) ролик идёт в формате «Расследование истории»: снимок из
архива в центре с медленным наездом и подписью источника (media/sources.yaml, см. archive.py),
персонажи меньше и ниже. Папка снимков - MEDIA_DIR или <серия>/media/NN для сценария
<серия>/scripts/rNN.txt. Перед рендером проверяется замок персонажей (characters.py): если рисунок
или голос изменились без подтверждения, ролик не собирается.
Без разметки эмоции и акценты расставляются сами: хук и вопросы - удивление,
лайфхаки - хитрость, последняя фраза - радость; числа, ₽ и «бесплатно» - акценты.

Что делает:
- голос Сёмы (semya_voice через render_blue/render_avatar), время каждого слова -
  распознаванием Vosk по самой озвучке (если модели нет - по слогам);
- субтитры по 1-3 слова, текущее слово подсвечено и «выпрыгивает»;
- камера: наезд на хуке, рывок на каждой фразе, тряска на акцентах; петля в конце;
- Сёма на пол-экрана, эмоция по фразе, рот по громкости, моргание, покачивание;
- стикеры с суммами и числами (перечёркиваются, если перед ними «не»);
- музыка с приглушением под голос, «вжух» на переходах, щелчки и «дзынь»;
- плашка временной акции закрытого канала (после хука) и карточка на последней фразе
  («Новые курсы каждую неделю» + бесплатный канал с опросами) - тексты и цены из
  content/brand.yaml; PROMO=0 / ENDCARD=0 - выключить, PROMO_* - переопределить.
"""
from __future__ import annotations

import json
import math
import os
import re
import subprocess
import sys
import wave
from functools import lru_cache

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

os.environ.setdefault("CHARACTER", "semya")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import render_avatar as ra  # noqa: E402  (голос, громкость рта)
import render_blue as rb  # noqa: E402
import characters  # noqa: E402  (реестр, позы, замок внешности и голоса)

W, H, FPS = 1080, 1920, 30
SR = 44100
NAVY, NAVY2, BLUE = (8, 20, 64), (18, 44, 140), (0, 71, 255)
GOLD, WHITE, RED = (255, 205, 60), (255, 255, 255), (255, 72, 72)
FONT_DIR = "/usr/share/fonts/opentype/inter"
CAP_SIZE, CAP_Y, CAP_W = 118, 560, 900
CHAR_SIZE = 1000
CHAR_X, CHAR_Y = (W - CHAR_SIZE) // 2, H - CHAR_SIZE + 150   # низ худи уходит за кадр
DUO_SIZE = 700                                            # размер каждого в диалоге
DUO_X = (290, 790)                                        # центры: ведущий слева, гость справа
EMPH_WORDS = {"бесплатно", "бесплатное", "бесплатный", "даром", "серьёзно", "никогда", "всегда", "ноль"}
EMOTIONS = {"удивлён": ("open", "up"), "хитрит": ("sly", "frown"), "радуется": ("happy", "normal"),
            "объясняет": ("open", "normal"), "спокоен": ("open", "normal")}
# Факты о бренде - из content/brand.yaml; переменные окружения переопределяют.
import yaml  # noqa: E402
BRAND = yaml.safe_load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "brand.yaml"),
                            encoding="utf-8"))
_P = BRAND.get("promo", {})
PROMO = os.environ.get("PROMO", "1" if _P.get("enabled") else "0") != "0"
PROMO_TITLE = os.environ.get("PROMO_TITLE", BRAND["closed_channel"]["name"].capitalize())
PROMO_PRICE = os.environ.get("PROMO_PRICE", _P.get("price", ""))
PROMO_OLD = os.environ.get("PROMO_OLD", _P.get("old_price", ""))
PROMO_UNTIL = os.environ.get("PROMO_UNTIL", _P.get("until", ""))   # «до 30 ноября»; пусто - «временно»
ENDCARD = os.environ.get("ENDCARD", "1") != "0"                     # карточка на последней фразе
PROMO_FROM = 2.0                                          # появляется после хука, секунд
TRICK = re.compile(r"\b(смотри|секрет|лайфхак|бери|хитрость|вот как|программ)", re.I)


# ------------------------------------------------------------------ сценарий

SAY_MARK = re.compile(r"\{([^|{}]+)\|([^{}]+)\}")     # {1903|тысяча девятьсот третьего}


def parse(path: str) -> list[dict]:
    raw = [l.strip() for l in open(path, encoding="utf-8") if l.strip()]
    lines, photo = [], None
    for k, l in enumerate(raw):
        speaker, emo, text = None, None, l
        while True:                       # префиксы в любом порядке: Имя:, [эмоция], [фото N]
            m = re.match(r"^\[(\w+)\]\s*", text)
            pm = re.match(r"^\[фото\s+(\w+)\]\s*", text, re.I)
            if pm:
                photo, text = pm.group(1).zfill(2), text[pm.end():]
            elif m and m.group(1) in EMOTIONS:
                emo, text = m.group(1), text[m.end():]
            elif speaker is None and split_speaker(text)[0]:
                speaker, text = split_speaker(text)
            else:
                break
        speaker = speaker or characters.main_id()
        say = [(a.strip(), b.strip()) for a, b in SAY_MARK.findall(text)]
        text = SAY_MARK.sub(lambda mm: mm.group(1).strip(), text)
        marked = set(re.findall(r"\*([^*]+)\*", text))
        text = text.replace("*", "")
        if emo is None:
            if k == 0 or text.endswith("?"):
                emo = "удивлён"
            elif k == len(raw) - 1:
                emo = "радуется"
            elif TRICK.search(text):
                emo = "хитрит"
            else:
                emo = "объясняет" if k % 2 else "спокоен"
        lines.append({"text": text, "emotion": emo, "marked": marked, "speaker": speaker,
                      "say": say, "photo": photo})
    return lines


def say_text(text: str, say: list[tuple[str, str]]) -> str:
    """Текст для голоса: числа из разметки {1903|...} заменяются словами."""
    for shown, spoken in say:
        text = text.replace(shown, spoken, 1)
    return text


def split_speaker(line: str) -> tuple[str | None, str]:
    """«Ника: текст» -> ("nika", "текст"). «Смотри: ...» - обычный текст ведущего."""
    m = re.match(r"^([А-ЯЁA-Z][\w ]{1,24}):\s+", line)
    if not m:
        return None, line
    cid = characters.by_alias(m.group(1))
    if cid is None:
        print(f"внимание: «{m.group(1)}:» - не имя персонажа, читаю как текст. Если это гость -"
              f" добавьте его в content/characters/registry.yaml", file=sys.stderr)
        return None, line
    return cid, line[m.end():]


def tokens(text: str) -> list[str]:
    """Слова для субтитров; «60 000 ₽» - один токен."""
    text = re.sub(r"(\d) (\d{3})", "\\1\u00a0\\2", text)
    text = re.sub(r"(\d) ₽", "\\1\u00a0₽", text)
    return [t for t in text.split(" ") if t]   # split() без аргумента режет и по неразрывному пробелу


def is_emph(tok: str, marked: set[str]) -> bool:
    bare = re.sub(r"[^\wё\u00a0₽]", "", tok.lower())
    return bool(re.search(r"\d|₽", tok)) or bare in EMPH_WORDS or any(bare == m.lower() for m in marked)


# ------------------------------------------------------------------ время слов

def norm(w: str) -> str:
    return re.sub(r"[^а-я]", "", w.lower().replace("ё", "е"))


def asr_words(wav: str) -> list[tuple[str, float, float]] | None:
    try:
        from vosk import KaldiRecognizer, Model, SetLogLevel
    except ImportError:
        return None
    SetLogLevel(-1)
    global _ASR
    if "_ASR" not in globals():
        _ASR = Model(model_name="vosk-model-small-ru-0.22")
    pcm = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", wav, "-ar", "16000", "-ac", "1", "-f", "s16le", "-"],
                         capture_output=True, check=True).stdout
    rec = KaldiRecognizer(_ASR, 16000)
    rec.SetWords(True)
    out = []
    for i in range(0, len(pcm), 8000):
        if rec.AcceptWaveform(pcm[i:i + 8000]):
            out += json.loads(rec.Result()).get("result", [])
    out += json.loads(rec.FinalResult()).get("result", [])
    return [(r["word"], r["start"], r["end"]) for r in out]


def syllables(w: str) -> int:
    return max(1, len(re.findall(r"[аеёиоуыэюя]", w.lower())))


def spoken_groups(toks: list[str], say: list[tuple[str, str]] = ()) -> list[list[str]]:
    """Слова озвучки на каждый токен субтитров (числа раскрываются в несколько слов)."""
    groups, done = [], 0
    for i in range(len(toks)):
        part = " ".join(toks[: i + 1]).replace("\u00a0", " ")
        try:
            words = rb.spoken(say_text(part, [x for x in say if x[0] in part])).split()
        except AssertionError:
            words = None
        if words is None:
            groups.append([])
            continue
        groups.append(words[done:])
        done = len(words)
    return groups


def word_times(toks: list[str], wav: str, offset: float, dur: float,
               say: list[tuple[str, str]] = ()) -> list[tuple[float, float]]:
    groups = spoken_groups(toks, say)
    flat = [(gi, w) for gi, g in enumerate(groups) for w in g]
    times: list[tuple[float, float] | None] = [None] * len(flat)
    rec = asr_words(wav)
    if rec:
        import difflib
        sm = difflib.SequenceMatcher(None, [norm(w) for _, w in flat], [norm(r[0]) for r in rec], autojunk=False)
        for a, b, size in sm.get_matching_blocks():
            for j in range(size):
                times[a + j] = (rec[b + j][1], rec[b + j][2])
    # пропуски: по слогам между известными соседями
    weights = [syllables(w) for _, w in flat]
    known = [(i, t) for i, t in enumerate(times) if t]
    anchors = [(-1, (0.0, 0.0))] + known + [(len(flat), (dur, dur))]
    for (ia, ta), (ib, tb) in zip(anchors, anchors[1:]):
        if ib - ia <= 1:
            continue
        span_start, span_end = ta[1], tb[0]
        total = sum(weights[ia + 1:ib]) or 1
        t = span_start
        for i in range(ia + 1, ib):
            d = (span_end - span_start) * weights[i] / total
            times[i] = (t, t + d)
            t += d
    out = []
    for gi in range(len(toks)):
        ts = [times[i] for i, (g, _) in enumerate(flat) if g == gi]
        if ts:
            out.append((offset + ts[0][0], offset + ts[-1][1]))
        else:  # токен без слов (знак): прилипает к предыдущему
            out.append(out[-1] if out else (offset, offset))
    return out


# ------------------------------------------------------------------ графика

@lru_cache(maxsize=64)
def font(size: int, weight: str = "Black") -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(f"{FONT_DIR}/Inter-{weight}.otf", size)


def ease_out(x: float) -> float:
    x = min(max(x, 0.0), 1.0)
    return 1 - (1 - x) ** 3


def back_out(x: float) -> float:
    x = min(max(x, 0.0), 1.0)
    c = 1.9
    return 1 + (c + 1) * (x - 1) ** 3 + c * (x - 1) ** 2


# ------------------------------------------------------------------ архивный снимок

PHOTO_BOX = (80, 760, 1000, 1340)                         # x0, y0, x1, y1 - снимок в центре кадра
PHOTO_Y_CHAR = 1340                                        # ниже - персонажи (формат истории)


def media_dir(script: str) -> str:
    """MEDIA_DIR или <серия>/media/NN для сценария <серия>/scripts/rNN.txt."""
    if os.environ.get("MEDIA_DIR"):
        return os.environ["MEDIA_DIR"]
    path = os.path.abspath(script)
    num = re.sub(r"\D", "", os.path.splitext(os.path.basename(path))[0])
    return os.path.join(os.path.dirname(os.path.dirname(path)), "media", num)


def photo_label(folder: str, key: str) -> str:
    src_file = os.path.join(folder, "sources.yaml")
    meta = (yaml.safe_load(open(src_file, encoding="utf-8")) or {}).get(key, {}) if os.path.exists(src_file) else {}
    if not meta:
        raise SystemExit(f"у снимка {key} нет записи в {src_file}: источник обязателен")
    year = re.search(r"\b(1[0-9]{3}|20[0-9]{2})\b", str(meta.get("date", "")))
    return "  ·  ".join(x for x in (meta.get("source", ""), year.group(1) if year else "") if x)


@lru_cache(maxsize=None)
def photo_source(folder: str, key: str) -> Image.Image:
    """Снимок в архивном тоне (сепия), с запасом под наезд камеры."""
    from PIL import ImageOps
    path = os.path.join(folder, f"{key}.jpg")
    if not os.path.exists(path):
        raise SystemExit(f"нет снимка {path} (archive.py photos ...)")
    img = Image.open(path).convert("L")
    img = ImageOps.autocontrast(img, cutoff=1)
    img = ImageOps.colorize(img, black=(26, 18, 6), white=(246, 236, 214))
    bw, bh = PHOTO_BOX[2] - PHOTO_BOX[0], PHOTO_BOX[3] - PHOTO_BOX[1]
    return ImageOps.fit(img, (int(bw * 1.12), int(bh * 1.12)), Image.LANCZOS)


@lru_cache(maxsize=None)
def photo_frame(label: str) -> tuple[Image.Image, Image.Image]:
    """Рамка-фотокарточка с тенью и плашка «АРХИВ · источник · год» (без самого снимка)."""
    bw, bh = PHOTO_BOX[2] - PHOTO_BOX[0], PHOTO_BOX[3] - PHOTO_BOX[1]
    pad = 14
    card = Image.new("RGBA", (bw + 2 * pad + 40, bh + 2 * pad + 40), (0, 0, 0, 0))
    sh = Image.new("RGBA", card.size, (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle([20, 28, 20 + bw + 2 * pad, 28 + bh + 2 * pad], radius=10,
                                         fill=(0, 0, 0, 150))
    card.alpha_composite(sh.filter(ImageFilter.GaussianBlur(14)))
    ImageDraw.Draw(card).rounded_rectangle([20, 20, 20 + bw + 2 * pad, 20 + bh + 2 * pad], radius=10,
                                           fill=(250, 244, 230, 255))
    font = ImageFont.truetype(f"{FONT_DIR}/Inter-SemiBold.otf", 30)
    bold = ImageFont.truetype(f"{FONT_DIR}/Inter-Black.otf", 30)
    tw = int(ImageDraw.Draw(card).textlength(label, font=font) + ImageDraw.Draw(card).textlength("АРХИВ  ", font=bold))
    tag = Image.new("RGBA", (tw + 48, 58), (0, 0, 0, 0))
    d = ImageDraw.Draw(tag)
    d.rounded_rectangle([0, 0, tag.width - 1, 57], radius=29, fill=NAVY + (235,), outline=GOLD + (200,), width=2)
    d.text((24, 11), "АРХИВ", font=bold, fill=GOLD)
    d.text((24 + d.textlength("АРХИВ  ", font=bold), 11), label, font=font, fill=WHITE)
    return card, tag


def draw_photo(world: Image.Image, folder: str, key: str, progress: float, appear: float, drift: int) -> None:
    """Снимок с медленным наездом (Ken Burns) и плашкой источника; appear 0..1 - появление."""
    src = photo_source(folder, key)
    card, tag = photo_frame(photo_label(folder, key))
    bw, bh = PHOTO_BOX[2] - PHOTO_BOX[0], PHOTO_BOX[3] - PHOTO_BOX[1]
    z = 1.0 - 0.09 * min(1.0, max(0.0, progress))            # окно кадрирования сужается - наезд
    cw, ch = src.width / 1.12 * (1.12 * z), src.height / 1.12 * (1.12 * z)
    cx = src.width / 2 + drift * (src.width - cw) / 2 * (progress - 0.5)
    cy = src.height / 2
    crop = src.crop((int(cx - cw / 2), int(cy - ch / 2), int(cx + cw / 2), int(cy + ch / 2))).resize((bw, bh), Image.BILINEAR)
    frame = card.copy()
    frame.paste(crop, (34, 34))
    if appear < 1:
        frame.putalpha(frame.getchannel("A").point(lambda v: int(v * appear)))
        tag = tag.copy()
        tag.putalpha(tag.getchannel("A").point(lambda v: int(v * appear)))
    dy = int((1 - appear) * 30)
    world.alpha_composite(frame, (PHOTO_BOX[0] - 34, PHOTO_BOX[1] - 34 + dy))
    world.alpha_composite(tag, (PHOTO_BOX[0] + 10, PHOTO_BOX[3] - 38 + dy))


def make_background() -> tuple[Image.Image, list[Image.Image]]:
    base = Image.new("RGB", (W, H), NAVY)
    d = ImageDraw.Draw(base)
    for y in range(H):
        t = y / H
        d.line([(0, y), (W, y)], fill=tuple(int(a + (b - a) * t) for a, b in zip(NAVY, NAVY2)))
    blobs = []
    for color, r, a in ((BLUE, 520, 150), (GOLD, 300, 60), ((120, 170, 255), 380, 90)):
        im = Image.new("RGBA", (r * 2, r * 2), (0, 0, 0, 0))
        ImageDraw.Draw(im).ellipse([r * 0.2, r * 0.2, r * 1.8, r * 1.8], fill=color + (a,))
        blobs.append(im.filter(ImageFilter.GaussianBlur(r * 0.28)))
    return base, blobs


def background(t: float, base: Image.Image, blobs: list[Image.Image]) -> Image.Image:
    frame = base.copy().convert("RGBA")
    paths = ((0.13, 0.0, 120, 1200, 260, 180), (0.19, 2.0, 820, 520, 160, 220), (0.11, 4.0, 300, 300, 220, 140))
    for blob, (sp, ph, cx, cy, ax, ay) in zip(blobs, paths):
        x = cx + math.sin(t * sp * 2 * math.pi + ph) * ax - blob.width // 2
        y = cy + math.cos(t * sp * 1.7 * math.pi + ph) * ay - blob.height // 2
        frame.alpha_composite(blob, (int(x), int(y)))
    return frame


def sticker(text: str, strike: float) -> Image.Image:
    f = font(110)
    tw = int(ImageDraw.Draw(Image.new("RGB", (1, 1))).textlength(text, font=f))
    w, h = tw + 110, 190
    im = Image.new("RGBA", (w + 40, h + 40), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([26, 30, w + 26, h + 30], radius=34, fill=(0, 0, 0, 90))
    d.rounded_rectangle([20, 20, w + 20, h + 20], radius=34, fill=GOLD + (255,), outline=WHITE, width=6)
    d.text((20 + 55, 20 + 30), text, font=f, fill=NAVY)
    if strike > 0:
        x1 = 40 + (w - 40) * strike
        d.line([(40, h * 0.62 + 20), (x1, h * 0.38 + 20)], fill=RED, width=16)
    return im.rotate(-7, resample=Image.BICUBIC, expand=True)


POP = 0.12   # насколько «выпрыгивает» активное слово


def caption(chunk: list[dict], t: float) -> Image.Image:
    """Слова чанка: активное - золото и «прыжок», акценты - золото после произнесения.
    Кегль уменьшается, пока строка (с запасом под прыжок и обводку) не влезет в CAP_W."""
    layer = Image.new("RGBA", (W, 700), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    size = CAP_SIZE
    while True:
        f = font(size)
        space = d.textlength(" ", font=f) + size * 0.22
        rows, row, width = [], [], 0.0
        for w in chunk:
            ww = d.textlength(w["text"], font=f)
            if row and width + space + ww > CAP_W:
                rows.append((row, width)); row, width = [], 0.0
            row.append((w, ww)); width += (space if len(row) > 1 else 0) + ww
        rows.append((row, width))
        widest = max(max(ww for _, ww in r) * (1 + POP) for r, _ in rows)
        if (max(wd for _, wd in rows) <= CAP_W and widest <= CAP_W and len(rows) <= 2) or size <= 70:
            break
        size -= 6
    y = 350 - len(rows) * size * 0.58
    for row, width in rows:
        x = (W - width) / 2
        for w, ww in row:
            active = w["start"] <= t < w["end"] + 0.05
            said = t >= w["start"]
            color = GOLD if (active or (w["emph"] and said)) else WHITE
            grow = min(POP, 44 / max(ww, 1))   # прыжок не больше 22 px на сторону: не наезжает на соседа
            scale = 1.0 + grow * min(1.0, back_out((t - w["start"]) / 0.16)) if active else 1.0
            fs = font(int(size * scale))
            cx, cy = x + ww / 2, y + size / 2
            tw = d.textlength(w["text"], font=fs)
            stroke = max(8, size // 10)
            d.text((cx - tw / 2 + 6, cy - fs.size / 2 + 10), w["text"], font=fs, fill=(0, 0, 0, 110),
                   stroke_width=stroke, stroke_fill=(0, 0, 0, 110))
            d.text((cx - tw / 2, cy - fs.size / 2), w["text"], font=fs, fill=color,
                   stroke_width=stroke, stroke_fill=NAVY)
            x += ww + space
        y += size * 1.12
    return layer


def promo_banner() -> Image.Image:
    """Компактная плашка: [часы АКЦИЯ] Закрытый канал / 3 975 ₽ (зачёркнуто) 1 511 ₽ / до ..."""
    tag_f, small, old_f, new_f = font(30), font(28, "SemiBold"), font(34, "Bold"), font(50)
    meas = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    until = PROMO_UNTIL or "временно"
    tag_w = 64 + meas.textlength("АКЦИЯ", font=tag_f) + 26
    old_w = meas.textlength(PROMO_OLD, font=old_f)
    new_w = meas.textlength(PROMO_PRICE, font=new_f)
    body_w = max(meas.textlength(PROMO_TITLE, font=small), old_w + 18 + new_w)
    until_w = meas.textlength(until, font=small)
    w, h = int(16 + tag_w + 24 + body_w + 28 + until_w + 26), 112
    im = Image.new("RGBA", (w + 12, h + 14), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([6, 10, w + 6, h + 10], radius=30, fill=(0, 0, 0, 70))
    d.rounded_rectangle([0, 0, w, h], radius=30, fill=(10, 22, 70, 225), outline=(255, 205, 60, 150), width=3)
    # метка АКЦИЯ с часами
    x0, y0 = 14, 18
    d.rounded_rectangle([x0, y0, x0 + tag_w, h - 18], radius=22, fill=RED + (255,))
    cx, cy, r = x0 + 34, h / 2, 15
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=WHITE, width=4)
    d.line([(cx, cy), (cx, cy - 9)], fill=WHITE, width=4)
    d.line([(cx, cy), (cx + 7, cy + 3)], fill=WHITE, width=4)
    d.text((x0 + 60, cy - 18), "АКЦИЯ", font=tag_f, fill=WHITE)
    # название и цены
    bx = x0 + tag_w + 24
    d.text((bx, 12), PROMO_TITLE, font=small, fill=(178, 192, 230))
    oy = 50
    d.text((bx, oy + 10), PROMO_OLD, font=old_f, fill=(150, 160, 200))
    d.line([(bx - 2, oy + 32), (bx + old_w + 2, oy + 26)], fill=RED, width=4)
    d.text((bx + old_w + 18, oy - 2), PROMO_PRICE, font=new_f, fill=GOLD)
    # срок
    d.text((w - 26 - until_w, h / 2 - 16), until, font=small, fill=WHITE)
    return im


def end_card() -> Image.Image:
    """Карточка на последней фразе: обновления каждую неделю + бесплатный канал с опросами."""
    l1, l2 = BRAND["updates"], BRAND["free_channel"]["short"]
    f1, f2 = font(46, "ExtraBold"), font(38, "Bold")
    meas = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    lines2, cur = [], ""
    l2 = re.sub(r"(?<![\w-])(\w{1,2}) ", "\\1\u00a0", l2)   # предлоги не висят в конце строки
    for word in l2.split(" "):
        trial = f"{cur} {word}".strip()
        if cur and meas.textlength(trial, font=f2) > 720:
            lines2.append(cur); cur = word
        else:
            cur = trial
    lines2.append(cur)
    w = int(max(meas.textlength(l1, font=f1), *(meas.textlength(x, font=f2) for x in lines2))) + 150
    h = 40 + 56 + 18 + 48 * len(lines2) + 34
    im = Image.new("RGBA", (w + 14, h + 16), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([7, 12, w + 7, h + 12], radius=34, fill=(0, 0, 0, 80))
    d.rounded_rectangle([0, 0, w, h], radius=34, fill=(10, 22, 70, 235), outline=GOLD + (220,), width=4)
    # календарь
    x, y = 40, 46
    d.rounded_rectangle([x, y, x + 50, y + 46], radius=8, outline=WHITE, width=4)
    d.line([(x, y + 14), (x + 50, y + 14)], fill=WHITE, width=4)
    for i in range(3):
        d.ellipse([x + 9 + i * 13, y + 25, x + 16 + i * 13, y + 32], fill=GOLD)
    d.text((110, 40), l1, font=f1, fill=WHITE)
    # опрос: три полоски
    y2 = 40 + 56 + 18
    for i, bw in enumerate((44, 30, 20)):
        d.rounded_rectangle([x, y2 + 6 + i * 14, x + bw, y2 + 14 + i * 14], radius=4, fill=GOLD if i == 0 else WHITE)
    for i, line in enumerate(lines2):
        d.text((110, y2 + i * 48), line, font=f2, fill=GOLD)
    return im


# ------------------------------------------------------------------ звук

def sfx_whoosh(sr: int = SR) -> np.ndarray:
    n = int(0.42 * sr)
    t = np.arange(n) / sr
    noise = np.random.default_rng(1).standard_normal(n)
    cutoff = 300 + 5200 * np.sin(np.pi * t / t[-1]) ** 2
    out, acc = np.empty(n), 0.0
    for i in range(n):
        a = math.exp(-2 * math.pi * cutoff[i] / sr)
        acc = (1 - a) * noise[i] + a * acc
        out[i] = acc
    return out * np.sin(np.pi * t / t[-1]) ** 1.5 * 0.55


def sfx_pop(sr: int = SR) -> np.ndarray:
    t = np.arange(int(0.07 * sr)) / sr
    f = 950 - 4000 * t
    return np.sin(2 * np.pi * np.cumsum(f) / sr) * np.exp(-t * 55) * 0.35


def sfx_ding(sr: int = SR) -> np.ndarray:
    t = np.arange(int(0.6 * sr)) / sr
    return (np.sin(2 * np.pi * 1318 * t) + 0.5 * np.sin(2 * np.pi * 1976 * t)) * np.exp(-t * 7) * 0.22


def read_wav(path: str) -> np.ndarray:
    with wave.open(path) as w:
        x = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768
        if w.getframerate() != SR:
            raise SystemExit(f"ожидался {SR} Гц: {path}")
    return x


def mix(voice_wav: str, total: float, events: list[tuple[float, str]], out: str) -> None:
    import music
    n = int(total * SR) + SR
    voice = np.zeros(n)
    v = read_wav(voice_wav)
    voice[: len(v)] = v[:n]
    env = np.convolve(np.abs(voice), np.ones(int(0.08 * SR)) / int(0.08 * SR), mode="same")
    env = np.clip(env / (np.percentile(env[env > 1e-4], 90) + 1e-9), 0, 1)
    bed = music.bed(total + 1)[:n]
    bed = np.pad(bed, (0, n - len(bed)))
    music_gain = 0.32 * (1 - 0.65 * env)
    fx = {"whoosh": sfx_whoosh(), "pop": sfx_pop(), "ding": sfx_ding()}
    sfx = np.zeros(n)
    for t, kind in events:
        s = fx[kind]
        i = int(t * SR)
        if 0 <= i < n:
            sfx[i:i + len(s)] += s[: n - i]
    mixdown = voice + bed * music_gain + sfx
    mixdown /= max(1.0, np.abs(mixdown).max() / 0.95)
    raw = out + ".mix.wav"
    with wave.open(raw, "w") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes((mixdown * 32767).astype(np.int16).tobytes())
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", raw, "-af",
                    "loudnorm=I=-14:TP=-1.2:LRA=9,aresample=44100", "-ac", "2", out], check=True)
    os.unlink(raw)


# ------------------------------------------------------------------ сборка

def poses() -> dict:
    cache = {}

    def get(cid: str, mouth: int, eyes: str, brows: str, size: int = CHAR_SIZE) -> Image.Image:
        key = (cid, mouth, eyes, brows, size)
        if key not in cache:
            cache[key] = characters.get(cid).pose(mouth, eyes, brows).resize((size, size), Image.LANCZOS)
        return cache[key]
    return get


def place(world: Image.Image, spr: Image.Image, cx: float, size: int, squash: float, tilt: float,
          bob: float) -> None:
    """Персонаж низом за кадр: центр по x, сжатие на новой фразе, наклон, покачивание."""
    if squash < 0.999:
        spr = spr.resize((int(size * (2 - squash)), int(size * squash)), Image.BICUBIC)
    spr = spr.rotate(tilt, resample=Image.BICUBIC, center=(spr.width / 2, spr.height * 0.8))
    bottom = H + 150 * size / CHAR_SIZE
    world.alpha_composite(spr, (int(cx - spr.width / 2), int(bottom - spr.height + bob)))


def char_pose(emotion: str, level: int, speaking: bool, blink: bool) -> tuple[int, str, str]:
    eyes, brows = EMOTIONS[emotion]
    if eyes == "sly":
        return (min(level, 2) if speaking and level else 5), eyes, brows
    if eyes == "happy":
        return ({0: 2, 1: 2, 4: 3}.get(level, level) if speaking else 2), eyes, brows
    if blink:
        return level, "blink", "normal"
    return level, eyes, brows


def render(script: str, out: str) -> None:
    out = os.path.abspath(out)          # ffmpeg concat читает пути относительно списка - нужны абсолютные
    lines = parse(script)
    work = out + ".work"
    os.makedirs(work, exist_ok=True)
    host = characters.main_id()
    characters.verify([host] + [l["speaker"] for l in lines])
    voices = [characters.get(l["speaker"]).voice for l in lines]
    wav, starts, durs, total, _ = ra.build_audio([say_text(l["text"], l["say"]) for l in lines], work,
                                                 None, None, speakers=voices)
    total = round(total + 0.4, 2)
    n_frames = int(math.ceil(total * FPS))
    mouths, loud = ra.mouth_levels(wav, n_frames)

    words, events, stickers = [], [], []
    for k, line in enumerate(lines):
        toks = tokens(line["text"])
        times = word_times(toks, os.path.join(work, f"{k:02d}.wav"), starts[k], durs[k], line["say"])
        line_words = [{"text": tk.replace("\u00a0", " "), "start": s, "end": e, "line": k,
                       "emph": is_emph(tk, line["marked"])} for tk, (s, e) in zip(toks, times)]
        for i, w in enumerate(line_words):  # конец слова = начало следующего, чтобы не мигало
            if i + 1 < len(line_words):
                w["end"] = max(w["end"], line_words[i + 1]["start"])
        words += line_words
        events.append((max(0.0, starts[k] - 0.12), "whoosh"))
        for i, w in enumerate(line_words):
            if re.search(r"\d|₽", w["text"]):
                negated = any(x["text"].lower() in ("не", "без") for x in line_words[:i])
                stickers.append({"text": w["text"], "start": w["start"], "end": starts[k] + durs[k] + 0.15,
                                 "strike": negated})
                events.append((w["start"], "ding"))
            elif w["emph"]:
                events.append((w["start"], "pop"))
    line_of = lambda t: max(i for i in range(len(lines)) if starts[i] <= t + 0.12) if t >= 0 else 0

    # чанки субтитров: до 3 слов и до 16 букв, новая фраза или конец предложения - новый чанк
    chunks, cur = [], []
    for w in words:
        too_long = len(" ".join(x["text"] for x in cur + [w])) > 16
        if cur and (len(cur) == 3 or too_long or w["line"] != cur[-1]["line"]
                    or re.search(r"[.!?:]$", cur[-1]["text"])):
            chunks.append(cur); cur = []
        cur.append(w)
    chunks.append(cur)

    base, blobs = make_background()
    banner = promo_banner() if PROMO else None
    outro = end_card() if ENDCARD else None
    get = poses()
    folder = media_dir(script)
    history = any(l["photo"] for l in lines)
    for l in lines:
        if l["photo"]:
            photo_label(folder, l["photo"]), photo_source(folder, l["photo"])   # проверить до долгого рендера
    guests = [(starts[i], l["speaker"]) for i, l in enumerate(lines) if l["speaker"] != host]
    guest_from = guests[0][0] if guests else 0.0
    blink_frames = {f + d for f in range(int(1.8 * FPS), n_frames, int(3.1 * FPS)) for d in range(3)}
    rng = np.random.default_rng(7)
    proc = subprocess.Popen(["ffmpeg", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
                             "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "medium",
                             "-crf", "18", "-pix_fmt", "yuv420p", work + "/video.mp4"], stdin=subprocess.PIPE)
    for f in range(n_frames):
        t = f / FPS
        k = line_of(t)
        since_line = t - starts[k]
        speaking = any(w["start"] - 0.05 <= t <= w["end"] + 0.05 for w in words if w["line"] == k)
        # камера: наезд на хуке, рывок на фразе, тряска на акцентах, петля в конце
        zoom = 1.0 + 0.16 * (1 - ease_out(t / 0.6)) if k == 0 else 1.0 + 0.07 * (1 - ease_out(since_line / 0.35))
        zoom += 0.12 * ease_out((t - (total - 0.45)) / 0.45)
        shake = any(w["emph"] and 0 <= t - w["start"] < 0.18 for w in words)
        sx, sy = (rng.integers(-9, 10), rng.integers(-9, 10)) if shake else (0, 0)

        world = background(t, base, blobs)
        if history and lines[k]["photo"]:
            key = lines[k]["photo"]
            first, last = k, k                                   # подряд идущие фразы с этим снимком
            while first > 0 and lines[first - 1]["photo"] == key:
                first -= 1
            while last + 1 < len(lines) and lines[last + 1]["photo"] == key:
                last += 1
            span_t0, span_t1 = starts[first], starts[last] + durs[last]
            draw_photo(world, folder, key, (t - span_t0) / max(0.1, span_t1 - span_t0),
                       ease_out((t - span_t0 + 0.12) / 0.3), 1 if first % 2 else -1)
        talker = lines[k]["speaker"]
        guest = next((g for t0, g in reversed(guests) if t0 <= t + 0.3), None)
        duo = ease_out((t - guest_from + 0.3) / 0.45) if guest else 0.0     # выход гостя
        if history:
            duo = 1.0 if guest else duo                          # в истории персонажи сразу внизу, меньше
        cast = [(host, (W / 2) * (1 - duo) + DUO_X[0] * duo, CHAR_SIZE + (DUO_SIZE - CHAR_SIZE) * duo)]
        if history and not guest:
            cast = [(host, DUO_X[0], DUO_SIZE)]
        if guest:
            cast.append((guest, DUO_X[1] + (1 - duo) * 600, DUO_SIZE))
        for cid, cx, size in sorted(cast, key=lambda c: c[0] == talker):   # говорящий - поверх
            talking = cid == talker
            level = mouths[f] if speaking and talking else 0
            emo = lines[k]["emotion"] if talking else "спокоен"
            mouth, eyes, brows = char_pose(emo, level, speaking and talking, f in blink_frames)
            size = int(size * (1.0 if talking or len(cast) == 1 else 0.9))
            spr = get(cid, mouth, eyes, brows, size)
            squash = 1 - 0.05 * (1 - ease_out(since_line / 0.22)) if talking else 1.0
            bob = math.sin(t * 5.2 + (0 if cid == host else 1.7)) * (10 if speaking and talking else 4)
            bob += float(loud[f]) * 6 if talking else 0
            tilt = math.sin(t * 1.9 + (0 if cid == host else 2.3)) * 2.4 + (4 if eyes == "sly" else 0)
            place(world, spr, cx, size, squash, tilt, bob)
        for st in ([] if history else stickers):    # в истории даты уже в субтитрах, снимок не закрываем
            if st["start"] <= t <= st["end"]:
                p = back_out((t - st["start"]) / 0.3)
                im = sticker(st["text"], ease_out((t - st["start"] - 0.45) / 0.3) if st["strike"] else 0)
                im = im.resize((max(1, int(im.width * p)), max(1, int(im.height * p))), Image.BICUBIC)
                world.alpha_composite(im, (int(W - 60 - im.width - (1 - p) * 40),
                                          int((PHOTO_BOX[1] + 10 if history else 930) - im.height / 2)))
        if zoom != 1.0 or sx or sy:
            zw, zh = int(W * zoom), int(H * zoom)
            big = world.resize((zw, zh), Image.BILINEAR)
            left, top = (zw - W) // 2 + sx, int((zh - H) * 0.42) + sy
            world = big.crop((left, top, left + W, top + H))
        if outro is not None and k == len(lines) - 1:
            p = back_out(since_line / 0.35)
            oc = outro.resize((max(1, int(outro.width * p)), max(1, int(outro.height * p))), Image.BICUBIC)
            world.alpha_composite(oc, ((W - oc.width) // 2, int(930 - oc.height / 2)))
        chunk = next((c for c in reversed(chunks) if c[0]["start"] - 0.06 <= t), chunks[0])
        cap = caption(chunk, t)
        appear = ease_out((t - chunk[0]["start"] + 0.06) / 0.12)
        world.alpha_composite(cap, (0, int(CAP_Y - 350 + (1 - appear) * 30)))
        d = ImageDraw.Draw(world)
        d.rounded_rectangle([60, 70, W - 60, 82], radius=6, fill=(255, 255, 255, 60))
        d.rounded_rectangle([60, 70, 60 + int((W - 120) * t / total), 82], radius=6, fill=GOLD)
        if banner is not None and t >= PROMO_FROM:
            a = ease_out((t - PROMO_FROM) / 0.4)
            pulse = 0.5 + 0.5 * math.sin(t * 2 * math.pi / 1.6)   # метка «АКЦИЯ» мягко пульсирует
            b = banner.copy()
            if a < 1:
                b.putalpha(b.getchannel("A").point(lambda v: int(v * a)))
            world.alpha_composite(b, ((W - b.width) // 2, int(108 - (1 - a) * 20)))
            glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            gx = (W - b.width) // 2 + 14
            ImageDraw.Draw(glow).rounded_rectangle([gx - 4, 108 + 14, gx + 150, 108 + 98], radius=26,
                                                   outline=RED + (int(110 * pulse * a),), width=4)
            world.alpha_composite(glow)
        proc.stdin.write(world.convert("RGB").tobytes())
    proc.stdin.close()
    proc.wait()

    mix(wav, total, sorted(events), work + "/audio.wav")
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", work + "/video.mp4", "-i", work + "/audio.wav",
                    "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", out],
                   check=True)
    subprocess.run(["rm", "-rf", work])
    print(f"{out}  {total:.1f} с, слов {len(words)}, стикеров {len(stickers)}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(2)
    render(sys.argv[1], sys.argv[2])
