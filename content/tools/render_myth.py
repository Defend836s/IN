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
import bear, bear2, semya
CHARACTER = os.environ.get("CHARACTER", "owl")
CHAR = {"owl": owl, "bear": bear, "bear2": bear, "bearfull": bear, "bear3": bear, "semya": semya}[CHARACTER]
RIG = bear2.Rig() if CHARACTER == "bear2" else None
FULL = None
B3 = None
if CHARACTER == "bear3":
    import bear3
    B3 = bear3; RIG = True
if CHARACTER == "bearfull":
    import bear_full
    FULL = bear_full.FullRig(); RIG = FULL
FULL_W, FULL_H = 350, 500                 # медведь в полный рост: ноги у нижнего края безопасной зоны
FULL_Y = 1470 - FULL_H
WALK_MIN, WALK_MAX, WALK_SPEED = 200, 630, 150   # центр по x, px; скорость px/с
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
    """Плашка «ПРАВДА ИЛИ МИФ?»; возвращает x её правого края (там встаёт отсчёт)."""
    f = ImageFont.truetype(rb.BOLD, HEADER_PX)
    txt = "ПРАВДА ИЛИ МИФ?"
    w = d.textlength(txt, font=f)
    hgt = int(HEADER_PX * 1.45)
    d.rounded_rectangle([rb.X0 - 6, TEXT_TOP - 4, rb.X0 + w + 34, TEXT_TOP + hgt], radius=22, fill=rb.WHITE)
    d.text((rb.X0 + 14, TEXT_TOP + 4), txt, font=f, fill=rb.BLUE)
    return rb.X0 + w + 34


HEADER_PX, Q_OFFSET = 54, 95


LAYOUTS = {   # TEXT_TOP, TEXT_BOT, BAR_Y, масштаб персонажа, низ ног, размер плашки, отступ вопроса
    "banner": (728, 950, 708, 0.82, 1478, 40, 66),
    "clean": (330, 700, 300, 1.15, 1482, 54, 95),
}


def render(segs, out, piper, voice, overlay=None):
    global TEXT_TOP, TEXT_BOT, BAR_Y, HEADER_PX, Q_OFFSET
    if B3:
        TEXT_TOP, TEXT_BOT, BAR_Y, b3_scale, b3_floor, HEADER_PX, Q_OFFSET = \
            LAYOUTS["banner" if overlay is not None else "clean"]
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
    ra.TEXT_TOP, ra.TEXT_BOT = TEXT_TOP + Q_OFFSET, TEXT_BOT
    q_layer = ra.text_layer(q["text"], True)
    ra.TEXT_TOP = TEXT_TOP
    layers = {}
    for k, s in enumerate(segs):
        if s["kind"] == "ТЕКСТ":
            layers[k] = ra.text_layer(s["text"], False)
    stamps = {k: stamp(s["text"]) for k, s in enumerate(segs) if s["kind"] == "ОТВЕТ"}
    num_font = ImageFont.truetype(rb.BOLD, int(HEADER_PX * 1.5))
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
    walk = {"x": float(WALK_MIN), "dir": 1, "phase": 0.0}
    if B3:
        bw, bh = int(bear3.FW * b3_scale), int(bear3.FH * b3_scale)
        x_min, x_max = 20 + bw // 2, 845 - bw // 2
        st3 = dict(mouth=0, shape="wide", blink=False, brow=0.0, turn=0.0, ear=0, armL=12.0, armR=12.0,
                   palmR=0.0, pointL=0.0, phase=0.0, walk=0.0, lean=0.0, tilt=0.0, nod=0, breath=0.0)
        pos = {"x": float(x_min), "dir": 1}

    def ease(cur, target, tau):
        return cur + (target - cur) * min(1.0, (1 / FPS) / tau)
    for fr in range(n):
        tt = fr / FPS
        k = max(i for i, s in enumerate(segs) if s["start"] <= tt + 1e-6)
        img = bg.copy(); d = ImageDraw.Draw(img)
        d.rounded_rectangle([rb.X0, BAR_Y, rb.X1, BAR_Y + 8], radius=4, fill=rb.BLUE_DK)
        d.rounded_rectangle([rb.X0, BAR_Y, rb.X0 + max(8, int((rb.X1 - rb.X0) * tt / total)), BAR_Y + 8],
                            radius=4, fill=rb.WHITE)
        s = segs[k]
        if k <= ans_k:                      # вопрос, отсчёт и штамп - на экране вопроса
            hx_end = header(d)
            img.paste(q_layer, (0, 0), q_layer)
            if s["kind"] == "ПАУЗА" and tt >= s.get("count_start", 1e9):
                c = 3 - int((tt - s["count_start"]) / (COUNT / 3))
                if c >= 1:
                    rr = int(HEADER_PX * 0.95)
                    cx, cy = hx_end + rr + 24, TEXT_TOP + int(HEADER_PX * 0.7)
                    d.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], fill=rb.WHITE)
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
        if B3:
            kind = s["kind"]
            walking = kind in ("ВОПРОС", "ТЕКСТ")
            pointing = kind == "ОТВЕТ" or (k == ans_k + 1 and tt - s["start"] < 0.9)
            if pointing:
                walking = False
            palm = kind == "ПАУЗА"
            st3["walk"] = ease(st3["walk"], 1.0 if walking else 0.0, 0.18)
            pos["x"] += pos["dir"] * 150 * st3["walk"] / FPS
            if pos["x"] > x_max or pos["x"] < x_min:
                pos["dir"] *= -1; pos["x"] = min(max(pos["x"], x_min), x_max)
            st3["phase"] += 2 * math.pi * 1.7 * st3["walk"] / FPS
            turn_t = -0.5 if pointing else (pos["dir"] * st3["walk"] if walking else 0.0)
            st3["turn"] = ease(st3["turn"], turn_t, 0.14)
            st3["lean"] = 4 * pos["dir"] * st3["walk"]
            st3["palmR"] = ease(st3["palmR"], 1.0 if palm else 0.0, 0.1)
            st3["pointL"] = ease(st3["pointL"], 1.0 if pointing else 0.0, 0.1)
            swing = math.sin(st3["phase"]) * 18 * st3["walk"]
            st3["armL"] = 12 + (138 - 12) * st3["pointL"] + swing * (1 - st3["pointL"])
            st3["armR"] = 12 + (145 - 12) * st3["palmR"] - swing * (1 - st3["palmR"])
            emph = 1.0 if (fr > 2 and loud[fr] - loud[fr - 3] > 1.6) else 0.0     # брови на ударных
            st3["brow"] = max(1.0 if kind in ("ВОПРОС", "ПАУЗА") else 0.0, ease(st3["brow"], emph, 0.12))
            st3.update(mouth=mouths[fr], shape=shapes[fr], blink=fr in blink,
                       ear=1 if (tt % 4.3) < 0.12 else 0,
                       tilt=math.sin(tt * 2 * math.pi * 0.35) * 2 + (3 if kind in ("ВОПРОС", "ПАУЗА") else 0),
                       nod=int(loud[fr] * 3), breath=math.sin(tt * 2 * math.pi * 0.25))
            fig = bear3.figure(st3).resize((bw, bh), Image.LANCZOS)
            img.paste(fig, (int(pos["x"] - bw / 2) + shake, b3_floor - bh + dy), fig)
        elif FULL:
            kind = s["kind"]
            pose, walking = "idle", kind in ("ВОПРОС", "ТЕКСТ")
            if kind == "ПАУЗА":
                pose = "palm"
            elif kind == "ОТВЕТ" or (k == ans_k + 1 and tt - s["start"] < 0.8):
                pose, walking = "point", False
            dt = 1 / FPS
            if walking:
                walk["x"] += walk["dir"] * WALK_SPEED * dt; walk["phase"] += 2 * math.pi * 1.7 * dt
                if walk["x"] > WALK_MAX or walk["x"] < WALK_MIN:
                    walk["dir"] *= -1; walk["x"] = min(max(walk["x"], WALK_MIN), WALK_MAX)
            brow = 1.0 if kind in ("ВОПРОС", "ПАУЗА") else 0.0
            fig = FULL.frame(mouths[fr], shapes[fr], fr in blink, brow, pose, phase=walk["phase"],
                             walking=walking, tilt=math.sin(tt * 2 * math.pi * 0.35) * 2 + (3 if brow else 0),
                             nod=int(loud[fr] * 3), breath=math.sin(tt * 2 * math.pi * 0.25))
            fig = fig.resize((FULL_W, FULL_H), Image.LANCZOS)
            img.paste(fig, (int(walk["x"] - FULL_W / 2) + shake, FULL_Y + dy), fig)
        elif RIG:
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
        if B3:
            f = bear3.figure(dict(mouth=0, shape="wide", blink=False, brow=0, turn=0.0, ear=0, armL=12, armR=12,
                                  palmR=0, pointL=0, phase=0.0, walk=0.0, lean=0.0, tilt=0, nod=0, breath=0))
            sq = Image.new("RGBA", (600, 600), (0, 0, 0, 0)); sq.alpha_composite(f.resize((430, 600)), (85, 0))
            return sq
        if FULL:
            f = FULL.frame(0, "wide", False, 0, "idle")
            sq = Image.new("RGBA", (600, 600), (0, 0, 0, 0)); sq.alpha_composite(f.resize((420, 600)), (90, 0))
            return sq
        return bear2.Rig().frame(0, "wide", False, 0, "rest", size=600)


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
