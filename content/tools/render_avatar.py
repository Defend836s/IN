"""Reels «Все курсы мира» с говорящим Профессором Глобусом.
Голос: Piper, рот - по громкости звука в каждом кадре, моргание, покачивание,
выход персонажа в начале. Кадры идут в ffmpeg напрямую (rawvideo)."""
import math, os, re, subprocess, sys, wave
import numpy as np
from PIL import Image, ImageDraw, ImageFont
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import render_blue as rb
from globus import sprites, SIZE

FPS, W, H = 30, 1080, 1920
TAG = "ВСЕ КУРСЫ МИРА"
TEXT_TOP, TEXT_BOT = 360, 880
TEXT_X1 = 990                         # кнопки Instagram справа ниже, текст сверху их не задевает          # текст сверху
CHAR_X, CHAR_Y = 470 - SIZE // 2, 1440 - SIZE + 30   # персонаж снизу, в безопасной зоне
SP = sprites()
BAR_Y = None                          # по умолчанию под плашкой с названием
OVERLAY = None                        # RGBA-картинка поверх фона (например, баннер)


def background():
    img = Image.new("RGB", (W, H), rb.BLUE)
    d = ImageDraw.Draw(img)
    for y in range(0, 260):
        a = 1 - y / 260
        c = tuple(int(rb.BLUE[i] * (1 - 0.35 * a) + rb.BLUE_DK[i] * 0.35 * a) for i in range(3))
        d.line([(0, y), (W, y)], fill=c); d.line([(0, H - 1 - y), (W, H - 1 - y)], fill=c)
    if TAG:
        small = ImageFont.truetype(rb.SEMI, 36)
        X0, Y0 = rb.X0, rb.Y0
        d.rounded_rectangle([X0 - 4, Y0 + 8, X0 + d.textlength(TAG, font=small) + 28, Y0 + 64],
                            radius=28, fill=rb.WHITE)
        d.text((X0 + 12, Y0 + 15), TAG, font=small, fill=rb.BLUE)
    if OVERLAY is not None:
        img.paste(OVERLAY, (0, 0), OVERLAY)
    return img


def text_layer(text, is_hook):
    """Текст строки на прозрачном слое, в верхней зоне."""
    text = rb.glue(text)
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    size = 96 if is_hook else 86
    while True:
        font, lines = rb.layout(text, size, d, TEXT_X1)
        lh = int(size * 1.22)
        fits = all(d.textlength(" ".join(l), font=font) + sum(int(size * 0.3) for t in l if rb.is_key(t))
                   <= TEXT_X1 - rb.X0 for l in lines)
        if (len(lines) * lh <= TEXT_BOT - TEXT_TOP and fits) or size <= 54:
            break
        size -= 6
    y = TEXT_TOP + ((TEXT_BOT - TEXT_TOP) - len(lines) * lh) // 2
    space = d.textlength(" ", font=font)
    for line in lines:
        x = rb.X0
        for w in line:
            tw = d.textlength(w, font=font)
            if rb.is_key(w):
                pad = int(size * 0.14)
                core, punct = re.match(r"^(.*?)([.,!?:;»\"]*)$", w).groups()
                cw = d.textlength(core, font=font)
                x += pad
                d.rounded_rectangle([x - pad, y + int(size * 0.08), x + cw + pad, y + int(size * 1.12)],
                                    radius=int(size * 0.18), fill=rb.WHITE)
                d.text((x, y), core, font=font, fill=rb.BLUE)
                if punct:
                    d.text((x + cw + pad, y), punct, font=font, fill=rb.WHITE)
                x += tw + pad + (pad if punct else 0)
            else:
                d.text((x, y), w, font=font, fill=rb.WHITE)
                x += tw
            x += space
        y += lh
    return img


def build_audio(lines, work, piper, voice, length=0.95):
    while True:
        durs = []
        for k, line in enumerate(lines):
            d, sr = rb.tts(piper, voice, rb.spoken(line), os.path.join(work, f"{k:02d}.wav"), length)
            durs.append(d)
        total = sum(durs) + rb.GAP * (len(lines) - 1) + rb.TAIL
        if total <= rb.LIMIT or length <= 0.8:
            break
        length = round(length - 0.03, 2)
    alist, starts, t = [], [], 0.0
    for k in range(len(lines)):
        pad = rb.GAP if k < len(lines) - 1 else rb.TAIL
        starts.append(t); t += durs[k] + pad
        sil = os.path.join(work, f"s{k:02d}.wav")
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                        f"anullsrc=r={sr}:cl=mono", "-t", f"{pad:.3f}", sil], check=True)
        alist += [f"file '{os.path.join(work, f'{k:02d}.wav')}'", f"file '{sil}'"]
    open(os.path.join(work, "a.txt"), "w").write("\n".join(alist) + "\n")
    final = os.path.join(work, "voice.wav")
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0",
                    "-i", os.path.join(work, "a.txt"), "-af", rb.VOICE_FX.format(sr=sr),
                    "-ac", "1", "-ar", "44100", final], check=True)
    return final, starts, durs, total, length


def mouth_levels(wav_path, n_frames):
    with wave.open(wav_path) as w:
        sr = w.getframerate()
        x = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768
    hop = sr / FPS
    x = np.concatenate([x, np.zeros(int(hop * 2))])        # хвост: кадры после конца звука - тишина
    rms = np.array([np.sqrt(np.mean(x[int(i * hop):int((i + 1) * hop)] ** 2) + 1e-12)
                    if int(i * hop) < len(x) else 1e-6 for i in range(n_frames)])
    db = 20 * np.log10(rms)
    ref = np.percentile(db[db > -50], 90) if np.any(db > -50) else -20
    lv = np.clip((db - (ref - 22)) / 22 * 3.0, 0, 3)
    out, prev = [], 0.0
    for v in lv:                        # быстрое открытие, чуть плавнее закрытие
        prev = v if v > prev else prev * 0.55 + v * 0.45
        out.append(int(round(prev)) if prev > 0.6 else 0)
    return out, lv


def render(lines, out, piper, voice):
    work = out + ".work"; os.makedirs(work, exist_ok=True)
    wav, starts, durs, total, length = build_audio(lines, work, piper, voice)
    n = int(math.ceil(total * FPS))
    mouths, loud = mouth_levels(wav, n)
    bg = background()
    layers = [text_layer(l, k == 0) for k, l in enumerate(lines)]
    blink_at = set()
    t = 1.1
    while t < total:                    # моргание каждые ~2.5-3.7 с
        f = int(t * FPS); blink_at |= {f, f + 1, f + 2}
        t += 2.5 + (hash((round(t, 2), out)) % 120) / 100
    enc = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
                            "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-i", wav,
                            "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p",
                            "-c:a", "aac", "-b:a", "160k", "-ac", "2", "-shortest",
                            "-movflags", "+faststart", out], stdin=subprocess.PIPE)
    for f in range(n):
        tt = f / FPS
        k = max(i for i, s in enumerate(starts) if s <= tt + 1e-6)
        img = bg.copy()
        img.paste(layers[k], (0, 0), layers[k])
        d = ImageDraw.Draw(img)
        py = BAR_Y if BAR_Y else rb.Y0 + 90
        d.rounded_rectangle([rb.X0, py, rb.X1, py + 8], radius=4, fill=rb.BLUE_DK)
        d.rounded_rectangle([rb.X0, py, rb.X0 + max(8, int((rb.X1 - rb.X0) * tt / total)), py + 8],
                            radius=4, fill=rb.WHITE)
        # выход персонажа: снизу за 0.35 с, с лёгким перелётом
        enter = min(1.0, tt / 0.35)
        dy = int((1 - enter) ** 2 * 520 - math.sin(enter * math.pi) * 25)
        bob = int(math.sin(tt * 2 * math.pi * 0.8) * 8 - loud[f] * 3)
        tilt = math.sin(tt * 2 * math.pi * 0.5) * 2.5
        spr = SP[(mouths[f], f in blink_at)].rotate(tilt, resample=Image.BICUBIC)
        img.paste(spr, (CHAR_X, CHAR_Y + dy + bob), spr)
        enc.stdin.write(img.tobytes())
    enc.stdin.close(); enc.wait()
    subprocess.run(["rm", "-rf", work])
    return total, length, durs


if __name__ == "__main__":
    src, outdir, voice, piper = map(os.path.abspath, sys.argv[1:5])
    titles = sys.argv[5].split("|"); only = sys.argv[6:]
    os.makedirs(outdir, exist_ok=True)
    for i, title in enumerate(titles, 1):
        if only and str(i) not in only:
            continue
        lines = [l.strip() for l in open(os.path.join(src, f"r{i:02d}.txt"), encoding="utf-8") if l.strip()]
        name = f"{i:02d}-{title}.mp4"
        total, length, durs = render(lines, os.path.join(outdir, name), piper, voice)
        warn = ([f"хук {durs[0]:.1f} с"] if durs[0] > 3.2 else []) + \
               [f"бит {k+1} {d:.1f} с" for k, d in enumerate(durs) if d > 4.2]
        print(f"{name}  {total:.1f} с" + (f"  ! {', '.join(warn)}" if warn else ""), flush=True)
