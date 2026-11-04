"""Озвученные текстовые Reels: каждая фраза озвучивается Piper отдельно,
кадр держится ровно столько, сколько звучит фраза."""
import os, re, subprocess, sys, wave
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from render_reels import frame, TITLES

SRC, OUT, VOICE = map(os.path.abspath, sys.argv[1:4])
PIPER = os.path.abspath(sys.argv[4])
LENGTH = float(os.environ.get("LENGTH_SCALE", "0.92"))   # <1 - быстрее
GAP = 0.18            # пауза между фразами, с
TAIL = 0.6            # пауза в конце
LIMIT = 25.0

# Как произносить: цифры словами, капс строчными, латиница по-русски.
SAY = [
    (r"9 990 ₽", "девять тысяч девятьсот девяносто рублей"),
    (r"По 9 990", "По девять тысяч девятьсот девяносто"),
    (r"4 990", "четыре тысячи девятьсот девяносто"),
    (r"3 000 ₽", "три тысячи рублей"),
    (r"40 000 ₽", "сорок тысяч рублей"),
    (r"40 000", "сорок тысяч"),
    (r"300 000", "триста тысяч"),
    (r"\b0:1\b", "ноль - один"),
    (r"в 9:00", "в девять утра"),
    (r"в 18:00", "в шесть вечера"),
    (r"«12 лет», «300 клиентов», «40 квартир»|\"12 лет\", \"300 клиентов\", \"40 квартир\"",
     "двенадцать лет. триста клиентов. сорок квартир."),
    (r"40 квартир", "сорок квартир"),
    (r"на 3 звёздах", "на трёх звёздах"),
    (r"на 3 звезды", "на три звезды"),
    (r"5 звёзд", "пять звёзд"),
    (r"2 часа", "два часа"),
    (r"3 тренировки", "три тренировки"),
    (r"Сделал 0", "Сделал ноль"),
    (r"120 минут", "сто двадцать минут"),
    (r"3 месяца", "три месяца"),
    (r"20 секунд", "двадцать секунд"),
    (r"5 фраз", "пять фраз"),
    (r"в 5\b", "в пять"),
    (r"в 9\b", "в девять"),
    (r"Instagram", "инстаграм"),
    (r"РАЗНОС", "разнос"),
    (r"СМЕЛЫЙ", "смелый"),
    (r"\.\.\.", ""),
]


def spoken(text):
    for a, b in SAY:
        text = re.sub(a, b, text)
    text = text.replace("«", "").replace("»", "").replace('"', "")
    assert not re.search(r"\d", text), f"цифра осталась: {text}"
    return text


def tts(text, path, length):
    subprocess.run([PIPER, "-m", VOICE, "-f", path, "--length-scale", str(length),
                    "--sentence-silence", "0.12"],
                   input=text.encode("utf-8"), check=True, capture_output=True)
    with wave.open(path) as w:
        return w.getnframes() / w.getframerate(), w.getframerate()


def beats_of(raw):
    return [l.strip() for l in raw.splitlines() if l.strip()]


os.makedirs(OUT, exist_ok=True)
only = sys.argv[5:]
report = []
for i in range(1, 11):
    if only and str(i) not in only:
        continue
    lines = beats_of(open(os.path.join(SRC, f"r{i:02d}.txt"), encoding="utf-8").read())
    work = os.path.join(OUT, f".work{i:02d}")
    os.makedirs(work, exist_ok=True)
    length = LENGTH
    while True:                       # если не влезли в 25 с - чуть ускоряем
        durs = []
        for k, line in enumerate(lines):
            d, sr = tts(spoken(line), os.path.join(work, f"{k:02d}.wav"), length)
            durs.append(d)
        total = sum(durs) + GAP * (len(lines) - 1) + TAIL
        if total <= LIMIT or length <= 0.75:
            break
        length = round(length - 0.04, 2)
    # кадры
    concat, t = [], 0.0
    for k, line in enumerate(lines):
        dur = durs[k] + (GAP if k < len(lines) - 1 else TAIL)
        t += dur
        p = os.path.join(work, f"{k:02d}.png")
        frame(line, "", min(1.0, t / total), p, k == 0)
        concat.append(f"file '{p}'\nduration {dur:.3f}")
    concat.append(f"file '{os.path.join(work, f'{len(lines)-1:02d}.png')}'")
    open(os.path.join(work, "v.txt"), "w").write("\n".join(concat) + "\n")
    # звук: фразы + паузы
    alist = []
    for k in range(len(lines)):
        alist.append(f"file '{os.path.join(work, f'{k:02d}.wav')}'")
        pad = GAP if k < len(lines) - 1 else TAIL
        sil = os.path.join(work, f"sil{k:02d}.wav")
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                        f"anullsrc=r={sr}:cl=mono", "-t", f"{pad:.3f}", sil], check=True)
        alist.append(f"file '{sil}'")
    open(os.path.join(work, "a.txt"), "w").write("\n".join(alist) + "\n")
    name = f"{i:02d}-" + re.sub(r"[«»\"]", "", TITLES[i-1]).replace(" ", "-").lower() + ".mp4"
    out = os.path.join(OUT, name)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error",
                    "-f", "concat", "-safe", "0", "-i", os.path.join(work, "v.txt"),
                    "-f", "concat", "-safe", "0", "-i", os.path.join(work, "a.txt"),
                    "-vf", "fps=30,format=yuv420p", "-c:v", "libx264", "-preset", "medium", "-crf", "20",
                    "-af", "loudnorm=I=-14:TP=-1.5:LRA=11,aresample=44100", "-ac", "2",
                    "-c:a", "aac", "-b:a", "160k", "-t", f"{total:.2f}", "-movflags", "+faststart",
                    out], check=True)
    subprocess.run(["rm", "-rf", work])
    report.append((name, total, length))
    print(f"{name}  {total:.1f} с  (скорость {length})", flush=True)
