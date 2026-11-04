"""Озвученные Reels в ярко-синем стиле с петлёй. Каждая фраза озвучивается
отдельно, кадр держится ровно столько, сколько она звучит."""
import os, re, subprocess, sys, wave
from PIL import Image, ImageDraw, ImageFont

W, H = 1080, 1920
BLUE, BLUE_DK, WHITE = (0, 71, 255), (0, 40, 170), (255, 255, 255)
BOLD = "/usr/share/fonts/opentype/inter/Inter-ExtraBold.otf"
SEMI = "/usr/share/fonts/opentype/inter/Inter-SemiBold.otf"
X0, X1, Y0, Y1 = 90, 850, 230, 1440
TAG = os.environ.get("TAG", "ЗАКРЫТЫЙ КАНАЛ")
ACCENT_RE = re.compile(r"\d|^[«\"]?[A-ZА-ЯЁ]{3,}[»\".,!?:]*$")
KEY = {"сэкономить", "сэкономишь", "бесплатно", "любого", "любые", "закрытом", "закрытый",
       "навык", "навыков", "профессию", "впустую", "воды", "систему"}
GAP, TAIL, LIMIT = 0.22, 0.35, 25.0

SAY = [
    (r"\b3 года\b", "три года"), (r"\b40 минут\b", "сорок минут"), (r"\b3-й неделе\b", "третьей неделе"),
    (r"\b12 месяцев\b", "двенадцать месяцев"), (r"\b1 вечер\b", "один вечер"), (r"\b30 дней\b", "тридцать дней"),
    (r"Неделя 1:", "Неделя первая:"), (r"Неделя 2:", "Неделя вторая:"), (r"Неделя 3:", "Неделя третья:"),
    (r"Неделя 4:", "Неделя четвёртая:"), (r"\b40 часов\b", "сорок часов"), (r"\b2 раза\b", "два раза"),
    (r"\bSMM\b", "эс-эм-эм"),
    # ударения, которые синтезатор ставит неправильно (проверено stress_audit.py)
    (r"\b[Уу]же\b", lambda m: m.group(0) + "\u0301"),
    (r"\b[Нн]ейросети\b", "нейросе\u0301ти"),
    (r"\b[Ии]ли\b", lambda m: m.group(0) + "\u0301"),
    (r"([Сс]колько) воды\b", "\\1 воды\u0301"),
    (r"\b([Сс])орок\b", "\\1о\u0301рок"),
    (r"\.\.\.", ""),
]


def spoken(text):
    for a, b in SAY:
        text = re.sub(a, b, text)
    text = re.sub(r"[«»\"]", "", text)
    assert not re.search(r"\d|[A-Za-z]", text), f"цифра или латиница: {text}"
    return text


def glue(text):
    text = re.sub(r"(?<=\d) (?=\d{3}\b)", "\u00a0", text)
    text = re.sub(r"(?<=\d) (?=₽)", "\u00a0", text)
    text = text.replace("«Все курсы мира»", "«Все\u00a0курсы\u00a0мира»")
    return text.replace(" - ", "\u00a0- ")


def is_key(w):
    bare = re.sub(r"[^\wё-]", "", w.lower())
    return bool(ACCENT_RE.search(w)) or bare in KEY


def layout(text, size, d, x1=None):
    x1 = x1 or X1
    font = ImageFont.truetype(BOLD, size)
    lines, cur = [], []
    for w in [t for t in text.split(" ") if t]:
        trial = " ".join(cur + [w])
        extra = sum(int(size * 0.3) for t in cur + [w] if is_key(t))
        if cur and d.textlength(trial, font=font) + extra > x1 - X0:
            lines.append(cur); cur = [w]
        else:
            cur.append(w)
    if cur:
        lines.append(cur)
    return font, lines


def frame(text, progress, path, is_hook):
    text = glue(text)
    img = Image.new("RGB", (W, H), BLUE)
    d = ImageDraw.Draw(img)
    # мягкая виньетка сверху и снизу, чтобы синий не был плоским
    for y in range(0, 260):
        a = 1 - y / 260
        c = tuple(int(BLUE[i] * (1 - 0.35 * a) + BLUE_DK[i] * 0.35 * a) for i in range(3))
        d.line([(0, y), (W, y)], fill=c); d.line([(0, H - 1 - y), (W, H - 1 - y)], fill=c)
    size = 108 if is_hook else 96
    while True:
        font, lines = layout(text, size, d)
        lh = int(size * 1.24)
        if (len(lines) * lh <= Y1 - Y0 - 300 and
                all(d.textlength(" ".join(l), font=font) + sum(int(size * 0.3) for t in l if is_key(t))
                    <= X1 - X0 for l in lines)) or size <= 56:
            break
        size -= 6
    y = Y0 + 140 + ((Y1 - Y0 - 300) - len(lines) * lh) // 2
    space = d.textlength(" ", font=font)
    for line in lines:
        x = X0
        for w in line:
            tw = d.textlength(w, font=font)
            if is_key(w):
                pad = int(size * 0.14)
                core, punct = re.match(r"^(.*?)([.,!?:;»\"]*)$", w).groups()
                cw = d.textlength(core, font=font)
                x += pad
                d.rounded_rectangle([x - pad, y + int(size * 0.08), x + cw + pad, y + int(size * 1.12)],
                                    radius=int(size * 0.18), fill=WHITE)
                d.text((x, y), core, font=font, fill=BLUE)
                if punct:
                    d.text((x + cw + pad, y), punct, font=font, fill=WHITE)
                x += tw + pad + (pad if punct else 0)
            else:
                d.text((x, y), w, font=font, fill=WHITE)
                x += tw
            x += space
        y += lh
    small = ImageFont.truetype(SEMI, 36)
    d.rounded_rectangle([X0 - 4, Y0 + 8, X0 + d.textlength(TAG, font=small) + 28, Y0 + 64],
                        radius=28, outline=WHITE, width=3)
    d.text((X0 + 12, Y0 + 15), TAG, font=small, fill=WHITE)
    d.rounded_rectangle([X0, Y1 - 16, X1, Y1 - 8], radius=4, fill=BLUE_DK)
    d.rounded_rectangle([X0, Y1 - 16, X0 + max(8, int((X1 - X0) * progress)), Y1 - 8], radius=4, fill=WHITE)
    img.save(path)


BACKEND = os.environ.get("TTS_BACKEND", "piper")      # piper | yandex


def tts_yandex(text, path, length):
    """Yandex SpeechKit v1. Ключ - из переменной YANDEX_API_KEY (ключ сервисного
    аккаунта с ролью ai.speechkit-tts.user). Ударение: «+» перед гласной."""
    import json, urllib.parse, urllib.request
    text = re.sub(r"([аеёиоуыэюяАЕЁИОУЫЭЮЯ])\u0301", r"+\1", text)
    params = {"text": text, "lang": "ru-RU", "voice": os.environ.get("YANDEX_VOICE", "filipp"),
              "speed": f"{1 / length:.2f}", "format": "lpcm", "sampleRateHertz": "48000"}
    if os.environ.get("YANDEX_FOLDER_ID"):
        params["folderId"] = os.environ["YANDEX_FOLDER_ID"]
    req = urllib.request.Request("https://tts.api.cloud.yandex.net/speech/v1/tts:synthesize",
                                 data=urllib.parse.urlencode(params).encode(),
                                 headers={"Authorization": "Api-Key " + os.environ["YANDEX_API_KEY"]})
    try:
        pcm = urllib.request.urlopen(req, timeout=60).read()
    except urllib.error.HTTPError as e:
        raise SystemExit(f"Yandex SpeechKit: {e.code} {e.read()[:300]!r}")
    with wave.open(path, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(48000); w.writeframes(pcm)
    return len(pcm) / 2 / 48000, 48000


_VOSK = None


def tts_vosk(text, path, length):
    """Vosk TTS (alphacephei), офлайн после скачивания модели с alphacephei.com.
    Голос: VOSK_SPEAKER (номер диктора в многоголосой модели). Ударение: «+» перед гласной."""
    global _VOSK
    from vosk_tts import Model, Synth
    if _VOSK is None:
        name = os.environ.get("VOSK_MODEL")
        _VOSK = Synth(Model(model_name=name) if name else Model(lang="ru"))
    text = re.sub(r"([аеёиоуыэюяАЕЁИОУЫЭЮЯ])\u0301", r"+\1", text)
    _VOSK.synth(text, path, speaker_id=int(os.environ.get("VOSK_SPEAKER", "2")),
                speech_rate=1 / length)
    with wave.open(path) as w:
        return w.getnframes() / w.getframerate(), w.getframerate()


def tts(piper, voice, text, path, length):
    if BACKEND == "yandex":
        return tts_yandex(text, path, length)
    if BACKEND == "vosk":
        return tts_vosk(text, path, length)
    subprocess.run([piper, "-m", voice, "-f", path, "--length-scale", str(length),
                    "--noise-scale", "0.55", "--noise-w-scale", "0.6", "--sentence-silence", "0.1"],
                   input=text.encode("utf-8"), check=True, capture_output=True)
    with wave.open(path) as w:
        return w.getnframes() / w.getframerate(), w.getframerate()


# Голос увереннее: на полтона ниже, плотнее (компрессор), громкость под соцсети.
VOICE_FX = ("asetrate={sr}*0.971,aresample={sr},atempo=1.0299,"
            "acompressor=threshold=-20dB:ratio=3:attack=5:release=80:makeup=4,"
            "equalizer=f=140:t=q:w=1:g=2.5,loudnorm=I=-14:TP=-1.5:LRA=9,aresample=44100")
if BACKEND in ("yandex", "vosk"):   # живому голосу сдвиг тона не нужен, только плотность и громкость
    VOICE_FX = ("acompressor=threshold=-20dB:ratio=2.5:attack=5:release=80:makeup=3,"
                "loudnorm=I=-14:TP=-1.5:LRA=9,aresample=44100")


def render(lines, out, piper, voice, length=0.95):
    work = out + ".work"; os.makedirs(work, exist_ok=True)
    while True:
        durs = []
        for k, line in enumerate(lines):
            d, sr = tts(piper, voice, spoken(line), os.path.join(work, f"{k:02d}.wav"), length)
            durs.append(d)   # сдвиг тона + atempo не меняют длину
        total = sum(durs) + GAP * (len(lines) - 1) + TAIL
        if total <= LIMIT or length <= 0.8:
            break
        length = round(length - 0.03, 2)
    concat, alist, t = [], [], 0.0
    for k, line in enumerate(lines):
        dur = durs[k] + (GAP if k < len(lines) - 1 else TAIL)
        t += dur
        p = os.path.join(work, f"{k:02d}.png")
        frame(line, min(1.0, t / total), p, k == 0)
        concat.append(f"file '{p}'\nduration {dur:.3f}")
        sil = os.path.join(work, f"s{k:02d}.wav")
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                        f"anullsrc=r={sr}:cl=mono", "-t", f"{dur - durs[k]:.3f}", sil], check=True)
        alist += [f"file '{os.path.join(work, f'{k:02d}.wav')}'", f"file '{sil}'"]
    concat.append(f"file '{os.path.join(work, f'{len(lines)-1:02d}.png')}'")
    open(os.path.join(work, "v.txt"), "w").write("\n".join(concat) + "\n")
    open(os.path.join(work, "a.txt"), "w").write("\n".join(alist) + "\n")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error",
                    "-f", "concat", "-safe", "0", "-i", os.path.join(work, "v.txt"),
                    "-f", "concat", "-safe", "0", "-i", os.path.join(work, "a.txt"),
                    "-vf", "fps=30,format=yuv420p", "-c:v", "libx264", "-preset", "medium", "-crf", "19",
                    "-af", VOICE_FX.format(sr=sr), "-ac", "2", "-c:a", "aac", "-b:a", "160k",
                    "-t", f"{total:.2f}", "-movflags", "+faststart", out], check=True)
    subprocess.run(["rm", "-rf", work])
    return total, length, durs


if __name__ == "__main__":
    src, outdir, voice, piper = map(os.path.abspath, sys.argv[1:5])
    titles = sys.argv[5].split("|")
    only = sys.argv[6:]
    os.makedirs(outdir, exist_ok=True)
    for i, title in enumerate(titles, 1):
        if only and str(i) not in only:
            continue
        lines = [l.strip() for l in open(os.path.join(src, f"r{i:02d}.txt"), encoding="utf-8") if l.strip()]
        name = f"{i:02d}-{title}.mp4"
        total, length, durs = render(lines, os.path.join(outdir, name), piper, voice)
        warn = []
        if durs[0] > 3.2: warn.append(f"хук {durs[0]:.1f} с")
        warn += [f"бит {k+1} {d:.1f} с" for k, d in enumerate(durs) if d > 4.2]
        print(f"{name}  {total:.1f} с  скорость {length}" + (f"  ! {', '.join(warn)}" if warn else ""), flush=True)
