"""Формат «Правда или миф» для «Все курсы мира».
Строки сценария:  ВОПРОС: ...  /  ПАУЗА: ... (затем отсчёт 3-2-1)  /  ОТВЕТ: МИФ|ПРАВДА  /  обычные строки.
Ведущая - Сова-профессор. Верх кадра свободен под баннер; версия с баннером тоже пишется."""
import math, os, re, subprocess, sys, wave
import numpy as np
from PIL import Image, ImageDraw, ImageFont
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import render_blue as rb
import render_avatar as ra
import owl
from render_quotes import card

rb.SAY[:0] = [(r"\b30\b", "тридцати"), (r"\b5 лет\b", "пяти лет"), (r"\b3 проекта\b", "три проекта"),
              (r"\b20 минут\b", "двадцать минут"), (r"\b121 час\b", "сто двадцать один час"),
              (r"\b3 полные\b", "три полные"), (r"\bпо 5 часов\b", "по пять часов"),
              (r"\b1 день\b", "один день"), (r"в 1885 году", "в тысяча восемьсот восемьдесят пятом году"),
              (r"\b([Уу])чится\b", "\\1чи\u0301тся"), (r"\b([Уу])чишься\b", "\\1чи\u0301шься")]
FPS, W, H, SR = 30, 1080, 1920, 44100
TEXT_TOP, TEXT_BOT, BAR_Y = 735, 990, 712
SMALL = 430
import bear, bear2
CHARACTER = os.environ.get("CHARACTER", "owl")
CHAR = {"owl": owl, "bear": bear, "bear2": bear}[CHARACTER]
RIG = bear2.Rig() if CHARACTER == "bear2" else None
SP = {} if RIG else {k: v.resize((SMALL, SMALL), Image.LANCZOS) for k, v in CHAR.sprites().items()}


def mouth_shapes(wav_path, n):
    """Форма рта по тембру: низкий спектральный центр - «о/у» (round), иначе wide."""
    with wave.open(wav_path) as w:
        sr = w.getframerate(); x = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32)
    hop = sr / FPS; out = []
    for i in range(n):
        seg = x[int(i * hop):int((i + 1) * hop)]
        if len(seg) < 64:
            out.append("wide"); continue
        sp = np.abs(np.fft.rfft(seg * np.hanning(len(seg)))); f = np.fft.rfftfreq(len(seg), 1 / sr)
        band = (f > 150) & (f < 4000)
        c = (sp[band] * f[band]).sum() / (sp[band].sum() + 1e-9)
        out.append("round" if c < 950 else "wide")
    return out
CHAR_X, CHAR_Y = 470 - SMALL // 2, 1440 - SMALL + 36
if RIG:                                   # медведь с туловищем: крупнее и ниже, плечи уходят за край зоны
    SMALL = 510
    CHAR_X, CHAR_Y = 470 - SMALL // 2, 1460 - SMALL + 80
COUNT = 1.8          # секунды отсчёта после «Как думаешь?»
GAP, TAIL = 0.2, 0.35


def parse(path):
    segs = []
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        m = re.match(r"^(ВОПРОС|ПАУЗА|ОТВЕТ):\s*(.*)$", line)
        kind, text = (m.group(1), m.group(2)) if m else ("ТЕКСТ", line)
        say = {"ВОПРОС": "Правда или миф? " + text, "ОТВЕТ": text.capitalize() + "."}.get(kind, text)
        segs.append({"kind": kind, "text": text, "say": say})
    return segs


def sfx_thump():
    t = np.arange(int(SR * 0.32)) / SR
    body = np.sin(2 * np.pi * (110 - 60 * t / 0.32) * t) * np.exp(-t * 14)
    click = np.random.default_rng(1).normal(0, 1, len(t)) * np.exp(-t * 90) * 0.35
    return (body + click) * 0.9


def sfx_tick():
    t = np.arange(int(SR * 0.05)) / SR
    return np.sin(2 * np.pi * 1300 * t) * np.exp(-t * 70) * 0.35


def build_vosk(segs, work):
    """Цельная речь Vosk: [вопрос + «Как думаешь?»] -> отсчёт -> [ответ] -> пауза -> [объяснение]."""
    import vosk_voice as vv
    groups, cur = [], []
    for k, s in enumerate(segs):
        if s["kind"] == "ОТВЕТ" or (s["kind"] == "ТЕКСТ" and cur and segs[cur[-1]]["kind"] == "ОТВЕТ"):
            if cur: groups.append(cur)
            cur = []
        cur.append(k)
    groups.append(cur)
    t, sr, pieces = 0.0, None, []
    for g, idx in enumerate(groups):
        x, sr, spans = vv.chunk([rb.spoken(segs[k]["say"]) for k in idx], work, f"g{g}")
        pieces.append((t, x))
        for k, (a, b) in zip(idx, spans):
            segs[k].update(start=t + a, dur=b - a)
        t += len(x) / sr
        last = segs[idx[-1]]
        if last["kind"] == "ПАУЗА":
            last["count_start"] = t + 0.1; t += COUNT
        elif last["kind"] == "ОТВЕТ":
            t += 0.7
        t += GAP
    total = t - GAP + TAIL
    raw = np.zeros(int(total * sr) + sr)
    for st, x in pieces:
        i = int(st * sr); raw[i:i + len(x)] += x
    return raw, sr, total, vv.BROADCAST


def build(segs, work, piper, voice, length=0.95):
    """TTS по фразам -> единая дорожка голоса (с обработкой) + звуки -> таймлайн."""
    if rb.BACKEND == "vosk":
        raw, sr, total, chain = build_vosk(segs, work)
        return _finish(segs, work, raw, sr, total, chain)
    t, timeline, voice_parts = 0.0, [], []
    for k, s in enumerate(segs):
        p = os.path.join(work, f"{k:02d}.wav")
        d, sr = rb.tts(piper, voice, rb.spoken(s["say"]), p, length)
        with wave.open(p) as w:
            x = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768
        s.update(start=t, dur=d)
        voice_parts.append((t, x, sr))
        t += d
        if s["kind"] == "ПАУЗА":
            s["count_start"] = t + 0.1
            t += COUNT
        if s["kind"] == "ОТВЕТ":
            t += 0.7                      # штамп держится, чтобы его успели прочитать
        t += GAP
    total = t - GAP + TAIL
    sr = voice_parts[0][2]
    raw = np.zeros(int(total * sr) + sr)
    for st, x, _ in voice_parts:
        i = int(st * sr); raw[i:i + len(x)] += x
    return _finish(segs, work, raw, sr, total, rb.VOICE_FX.format(sr=sr))


def _finish(segs, work, raw, sr, total, chain):
    rawp = os.path.join(work, "raw.wav")
    with wave.open(rawp, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes((np.clip(raw, -1, 1) * 32767).astype(np.int16).tobytes())
    vfx = os.path.join(work, "voice.wav")
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", rawp, "-af", chain,
                    "-ac", "1", "-ar", str(SR), vfx], check=True)
    with wave.open(vfx) as w:
        v = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768
    mix = np.zeros(int(total * SR) + SR); v = v[:len(mix)]; mix[:len(v)] += v
    for s in segs:
        if s["kind"] == "ПАУЗА":
            for j in range(3):
                i = int((s["count_start"] + j * COUNT / 3) * SR); tk = sfx_tick(); mix[i:i + len(tk)] += tk
        if s["kind"] == "ОТВЕТ":
            i = int(s["start"] * SR); th = sfx_thump(); mix[i:i + len(th)] += th
    final = os.path.join(work, "final.wav")
    with wave.open(final, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes((np.clip(mix[:int(total * SR)], -1, 1) * 32767).astype(np.int16).tobytes())
    return vfx, final, total


def stamp(word):
    f = ImageFont.truetype(rb.BOLD, 150)
    tmp = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    tw = int(tmp.textlength(word, font=f))
    img = Image.new("RGBA", (tw + 120, 250), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([6, 6, tw + 114, 244], radius=36, fill=rb.WHITE, outline=rb.BLUE_DK, width=10)
    d.text((60, 30), word, font=f, fill=rb.BLUE)
    return img.rotate(-7, expand=True, resample=Image.BICUBIC)


def header(d):
    f = ImageFont.truetype(rb.BOLD, 54)
    txt = "ПРАВДА ИЛИ МИФ?"
    w = d.textlength(txt, font=f)
    d.rounded_rectangle([rb.X0 - 6, TEXT_TOP - 4, rb.X0 + w + 34, TEXT_TOP + 74], radius=22, fill=rb.WHITE)
    d.text((rb.X0 + 14, TEXT_TOP + 4), txt, font=f, fill=rb.BLUE)


def render(segs, out, piper, voice, overlay=None):
    work = out + ".work"; os.makedirs(work, exist_ok=True)
    vfx, final, total = build(segs, work, piper, voice)
    n = int(math.ceil(total * FPS))
    mouths, loud = ra.mouth_levels(vfx, n)
    shapes = mouth_shapes(vfx, n) if RIG else None
    ra.TAG = None
    bg = ra.background()
    if overlay is not None:
        bg.paste(overlay, (0, 0), overlay)
    q = next(s for s in segs if s["kind"] == "ВОПРОС")
    ra.TEXT_TOP, ra.TEXT_BOT = TEXT_TOP + 95, TEXT_BOT
    q_layer = ra.text_layer(q["text"], True)
    ra.TEXT_TOP = TEXT_TOP
    layers = {}
    for k, s in enumerate(segs):
        if s["kind"] == "ТЕКСТ":
            layers[k] = ra.text_layer(s["text"], False)
    stamps = {k: stamp(s["text"]) for k, s in enumerate(segs) if s["kind"] == "ОТВЕТ"}
    num_font = ImageFont.truetype(rb.BOLD, 120)
    blink = set()
    t = 1.3
    while t < total:
        f = int(t * FPS); blink |= {f, f + 1, f + 2}; t += 2.8
    enc = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
                            "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-i", final,
                            "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p",
                            "-c:a", "aac", "-b:a", "160k", "-ac", "2", "-shortest", "-movflags", "+faststart", out],
                           stdin=subprocess.PIPE)
    ans_k = next(k for k, s in enumerate(segs) if s["kind"] == "ОТВЕТ")
    for fr in range(n):
        tt = fr / FPS
        k = max(i for i, s in enumerate(segs) if s["start"] <= tt + 1e-6)
        img = bg.copy(); d = ImageDraw.Draw(img)
        d.rounded_rectangle([rb.X0, BAR_Y, rb.X1, BAR_Y + 8], radius=4, fill=rb.BLUE_DK)
        d.rounded_rectangle([rb.X0, BAR_Y, rb.X0 + max(8, int((rb.X1 - rb.X0) * tt / total)), BAR_Y + 8],
                            radius=4, fill=rb.WHITE)
        s = segs[k]
        if k <= ans_k:                      # вопрос, отсчёт и штамп - на экране вопроса
            header(d)
            img.paste(q_layer, (0, 0), q_layer)
            if s["kind"] == "ПАУЗА" and tt >= s.get("count_start", 1e9):
                c = 3 - int((tt - s["count_start"]) / (COUNT / 3))
                if c >= 1:
                    cx, cy = 900, TEXT_TOP + 150
                    d.ellipse([cx - 80, cy - 80, cx + 80, cy + 80], fill=rb.WHITE)
                    d.text((cx, cy - 4), str(c), font=num_font, fill=rb.BLUE, anchor="mm")
            if s["kind"] == "ОТВЕТ":
                st = stamps[k]
                p = min(1.0, (tt - s["start"]) / 0.18)
                sc = 1.8 - 0.8 * p + (0.06 * math.sin(p * math.pi) if p < 1 else 0)
                sw, sh = int(st.width * sc), int(st.height * sc)
                ss = st.resize((max(1, sw), max(1, sh)), Image.BICUBIC)
                if p < 1:
                    a = ss.getchannel("A").point(lambda v: int(v * p)); ss.putalpha(a)
                img.paste(ss, (540 - sw // 2 - 40, TEXT_TOP + 140 - sh // 2), ss)
        else:
            img.paste(layers[k], (0, 0), layers[k])
        # сова
        enter = min(1.0, tt / 0.35)
        dy = int((1 - enter) ** 2 * 520 - math.sin(enter * math.pi) * 25)
        shake = 0
        if s["kind"] == "ОТВЕТ" and tt - s["start"] < 0.25:
            shake = int(math.sin((tt - s["start"]) * 90) * 6)
        bob = int(math.sin(tt * 2 * math.pi * 0.8) * 8 - loud[fr] * 3)
        if RIG:
            kind = s["kind"]
            arm = "rest"
            if kind == "ПАУЗА":
                arm = "palm"
            elif kind == "ОТВЕТ" or (k == ans_k + 1 and tt - s["start"] < 0.8):
                arm = "point"
            brow = 1.0 if kind in ("ВОПРОС", "ПАУЗА") else 0.0
            nod = int(loud[fr] * 4 + math.sin(tt * 2 * math.pi * 1.6) * 2)
            spr = RIG.frame(mouths[fr], shapes[fr], fr in blink, brow, arm,
                            tilt=math.sin(tt * 2 * math.pi * 0.35) * 3 + (2 if brow else 0),
                            nod=nod, breath=math.sin(tt * 2 * math.pi * 0.25), size=SMALL)
            img.paste(spr, (CHAR_X + shake, CHAR_Y + dy + int(bob * 0.4)), spr)
        else:
            spr = SP[(mouths[fr], fr in blink)].rotate(math.sin(tt * math.pi) * 2.5, resample=Image.BICUBIC)
            img.paste(spr, (CHAR_X + shake, CHAR_Y + dy + bob), spr)
        enc.stdin.write(img.tobytes())
    enc.stdin.close(); enc.wait()
    subprocess.run(["rm", "-rf", work])
    return total


class _RigCard:
    """Чтобы карточка баннера брала нового медведя."""
    @staticmethod
    def sprite(m, b):
        return RIG.frame(0, "wide", False, 0, "rest", size=600)


if __name__ == "__main__":
    src, outdir, voice, piper = map(os.path.abspath, sys.argv[1:5])
    titles = sys.argv[5].split("|"); only = sys.argv[6:]
    banner = Image.new("RGBA", (W, H), (0, 0, 0, 0)); banner.alpha_composite(card(char=CHAR if not RIG else _RigCard()), (40, 250))
    for kind in ("чистые", "с-баннером"):
        os.makedirs(os.path.join(outdir, kind), exist_ok=True)
    for i, title in enumerate(titles, 1):
        if only and str(i) not in only:
            continue
        segs = parse(os.path.join(src, f"r{i:02d}.txt"))
        for kind, ov in (("чистые", None), ("с-баннером", banner)):
            total = render([dict(s) for s in segs], os.path.join(outdir, kind, f"{i:02d}-{title}.mp4"),
                           piper, voice, ov)
        print(f"{i:02d}-{title}  {total:.1f} с", flush=True)
