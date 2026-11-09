#!/usr/bin/env python3
"""Reels «уровня студии» с Енотом Сёмой: субтитры по слову, камера, эмоции, стикеры, звук.

    CHARACTER=semya python content/tools/render_pro.py <сценарий.txt> <выход.mp4>

Сценарий - по фразе в строке. Необязательная разметка:
    [удивлён] [хитрит] [радуется] [объясняет] [спокоен]  - эмоция фразы (в начале строки);
    *слово*                                              - акцент: золото, тряска, щелчок.
Без разметки эмоции и акценты расставляются сами: хук и вопросы - удивление,
лайфхаки - хитрость, последняя фраза - радость; числа, ₽ и «бесплатно» - акценты.

Что делает:
- голос Сёмы (semya_voice через render_blue/render_avatar), время каждого слова -
  распознаванием Vosk по самой озвучке (если модели нет - по слогам);
- субтитры по 1-3 слова, текущее слово подсвечено и «выпрыгивает»;
- камера: наезд на хуке, рывок на каждой фразе, тряска на акцентах; петля в конце;
- Сёма на пол-экрана, эмоция по фразе, рот по громкости, моргание, покачивание;
- стикеры с суммами и числами (перечёркиваются, если перед ними «не»);
- музыка с приглушением под голос, «вжух» на переходах, щелчки и «дзынь».
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
import semya  # noqa: E402

W, H, FPS = 1080, 1920, 30
SR = 44100
NAVY, NAVY2, BLUE = (8, 20, 64), (18, 44, 140), (0, 71, 255)
GOLD, WHITE, RED = (255, 205, 60), (255, 255, 255), (255, 72, 72)
FONT_DIR = "/usr/share/fonts/opentype/inter"
CAP_SIZE, CAP_Y, CAP_W = 118, 560, 900
CHAR_SIZE = 1000
CHAR_X, CHAR_Y = (W - CHAR_SIZE) // 2, H - CHAR_SIZE + 150   # низ худи уходит за кадр
EMPH_WORDS = {"бесплатно", "бесплатное", "бесплатный", "даром", "серьёзно", "никогда", "всегда", "ноль"}
EMOTIONS = {"удивлён": ("open", "up"), "хитрит": ("sly", "frown"), "радуется": ("happy", "normal"),
            "объясняет": ("open", "normal"), "спокоен": ("open", "normal")}
TRICK = re.compile(r"\b(смотри|секрет|лайфхак|бери|хитрость|вот как|программ)", re.I)


# ------------------------------------------------------------------ сценарий

def parse(path: str) -> list[dict]:
    raw = [l.strip() for l in open(path, encoding="utf-8") if l.strip()]
    lines = []
    for k, l in enumerate(raw):
        m = re.match(r"^\[(\w+)\]\s*", l)
        emo = m.group(1) if m and m.group(1) in EMOTIONS else None
        text = l[m.end():] if m else l
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
        lines.append({"text": text, "emotion": emo, "marked": marked})
    return lines


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


def spoken_groups(toks: list[str]) -> list[list[str]]:
    """Слова озвучки на каждый токен субтитров (числа раскрываются в несколько слов)."""
    groups, done = [], 0
    for i in range(len(toks)):
        try:
            words = rb.spoken(" ".join(toks[: i + 1]).replace("\u00a0", " ")).split()
        except AssertionError:
            words = None
        if words is None:
            groups.append([])
            continue
        groups.append(words[done:])
        done = len(words)
    return groups


def word_times(toks: list[str], wav: str, offset: float, dur: float) -> list[tuple[float, float]]:
    groups = spoken_groups(toks)
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

    def get(mouth: int, eyes: str, brows: str) -> Image.Image:
        key = (mouth, eyes, brows)
        if key not in cache:
            cache[key] = semya.pose(*key).resize((CHAR_SIZE, CHAR_SIZE), Image.LANCZOS)
        return cache[key]
    return get


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
    lines = parse(script)
    work = out + ".work"
    os.makedirs(work, exist_ok=True)
    wav, starts, durs, total, _ = ra.build_audio([l["text"] for l in lines], work, None, None)
    total = round(total + 0.4, 2)
    n_frames = int(math.ceil(total * FPS))
    mouths, loud = ra.mouth_levels(wav, n_frames)

    words, events, stickers = [], [], []
    for k, line in enumerate(lines):
        toks = tokens(line["text"])
        times = word_times(toks, os.path.join(work, f"{k:02d}.wav"), starts[k], durs[k])
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
    get = poses()
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
        level = mouths[f] if speaking else 0
        mouth, eyes, brows = char_pose(lines[k]["emotion"], level, speaking, f in blink_frames)
        spr = get(mouth, eyes, brows)
        squash = 1 - 0.05 * (1 - ease_out(since_line / 0.22))
        bob = math.sin(t * 5.2) * (10 if speaking else 4) + float(loud[f]) * 6
        tilt = math.sin(t * 1.9) * 2.4 + (4 if eyes == "sly" else 0)
        if squash < 0.999:
            spr = spr.resize((int(CHAR_SIZE * (2 - squash)), int(CHAR_SIZE * squash)), Image.BICUBIC)
        spr = spr.rotate(tilt, resample=Image.BICUBIC, center=(spr.width / 2, spr.height * 0.8))
        world.alpha_composite(spr, (int(CHAR_X + (CHAR_SIZE - spr.width) / 2),
                                    int(CHAR_Y + (CHAR_SIZE - spr.height) + bob)))
        for st in stickers:
            if st["start"] <= t <= st["end"]:
                p = back_out((t - st["start"]) / 0.3)
                im = sticker(st["text"], ease_out((t - st["start"] - 0.45) / 0.3) if st["strike"] else 0)
                im = im.resize((max(1, int(im.width * p)), max(1, int(im.height * p))), Image.BICUBIC)
                world.alpha_composite(im, (int(W - 60 - im.width - (1 - p) * 40), int(930 - im.height / 2)))
        if zoom != 1.0 or sx or sy:
            zw, zh = int(W * zoom), int(H * zoom)
            big = world.resize((zw, zh), Image.BILINEAR)
            left, top = (zw - W) // 2 + sx, int((zh - H) * 0.42) + sy
            world = big.crop((left, top, left + W, top + H))
        chunk = next((c for c in reversed(chunks) if c[0]["start"] - 0.06 <= t), chunks[0])
        cap = caption(chunk, t)
        appear = ease_out((t - chunk[0]["start"] + 0.06) / 0.12)
        world.alpha_composite(cap, (0, int(CAP_Y - 350 + (1 - appear) * 30)))
        d = ImageDraw.Draw(world)
        d.rounded_rectangle([60, 70, W - 60, 82], radius=6, fill=(255, 255, 255, 60))
        d.rounded_rectangle([60, 70, 60 + int((W - 120) * t / total), 82], radius=6, fill=GOLD)
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
