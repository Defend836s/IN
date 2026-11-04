import os, re, subprocess, sys
sys.path.insert(0, "/home/user/IN/skills/ig-reel")
from beats import analyse
from PIL import Image, ImageDraw, ImageFont

W, H = 1080, 1920
BG, FG, ACC, MUTED = (14, 14, 16), (245, 245, 240), (255, 59, 48), (120, 120, 126)
BOLD = "/usr/share/fonts/opentype/inter/Inter-ExtraBold.otf"
SEMI = "/usr/share/fonts/opentype/inter/Inter-SemiBold.otf"
X0, X1, Y0, Y1 = 90, 850, 230, 1440          # безопасная зона: справа 230 px свободно
ACCENT_RE = re.compile(r"\d|₽|^[«\"]?[A-ZА-ЯЁ]{3,}[»\".,!?:]*$")
TITLES = ["Подъём в 5 утра", "Марафоны", "«Эксперт» в шапке", "Отзывы", "Нет времени на спорт",
          "Курсы про курсы", "Мотивация vs дедлайн", "«Деньги любят смелых»", "Предназначение",
          "Перевод вакансий"]

def layout(text, size):
    font = ImageFont.truetype(BOLD, size)
    d = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    lines, cur = [], []
    for w in [t for t in text.split(" ") if t]:
        trial = " ".join(cur + [w])
        if cur and d.textlength(trial, font=font) > X1 - X0:
            lines.append(cur); cur = [w]
        else:
            cur.append(w)
    if cur: lines.append(cur)
    return font, lines

def glue(text):
    """Не разрывать «9 990 ₽», «300 000» и «- беги» между строками."""
    text = re.sub(r"(?<=\d) (?=\d{3}\b)", "\u00a0", text)
    text = re.sub(r"(?<=\d) (?=₽)", "\u00a0", text)
    return re.sub(r" (?=- )", "\u00a0", text).replace(" - ", " -\u00a0")


def frame(text, label, progress, path, is_hook):
    text = glue(text)
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    size = 104 if is_hook else 92
    while True:
        font, lines = layout(text, size)
        lh = int(size * 1.18)
        if len(lines) * lh <= (Y1 - Y0 - 260) and all(
                d.textlength(" ".join(l), font=font) <= X1 - X0 for l in lines) or size <= 56:
            break
        size -= 6
    block = len(lines) * lh
    y = Y0 + 130 + ((Y1 - Y0 - 260) - block) // 2
    space = d.textlength(" ", font=font)
    for line in lines:
        x = X0
        for w in line:
            col = ACC if ACCENT_RE.search(w) else FG
            d.text((x, y), w, font=font, fill=col)
            x += d.textlength(w, font=font) + space
        y += lh
    small = ImageFont.truetype(SEMI, 34)
    d.text((X0, Y0 + 20), "ЗЛОЙ ЖУРНАЛИСТ", font=small, fill=MUTED)
    d.rectangle([X0, Y0 + 70, X0 + 60, Y0 + 76], fill=ACC)
    # полоса прогресса: зритель видит, сколько осталось
    d.rectangle([X0, Y1 - 12, X1, Y1 - 6], fill=(40, 40, 44))
    d.rectangle([X0, Y1 - 12, X0 + int((X1 - X0) * progress), Y1 - 6], fill=ACC)
    img.save(path)

def main():
    SRC, OUT = os.path.abspath(sys.argv[1]), os.path.abspath(sys.argv[2])
    only = sys.argv[3:]
    os.makedirs(OUT, exist_ok=True)
    for i in range(1, 11):
        if only and str(i) not in only: continue
        raw = open(os.path.join(SRC, f"r{i:02d}.txt"), encoding="utf-8").read()
        a = analyse(raw, wpm=130, target=25)
        work = os.path.join(OUT, f".work{i:02d}"); os.makedirs(work, exist_ok=True)
        beats = a["beats"]
        total = a["total_seconds"] + 0.5
        concat = []
        for k, b in enumerate(beats):
            dur = b["dur"] + (0.5 if k == len(beats) - 1 else 0)   # пауза на последней фразе
            p = os.path.join(work, f"{k:02d}.png")
            frame(b["text"], b["label"], (b["start"] + b["dur"]) / a["total_seconds"], p, k == 0)
            concat.append(f"file '{p}'\nduration {dur:.3f}")
        concat.append(f"file '{os.path.join(work, f'{len(beats)-1:02d}.png')}'")
        lst = os.path.join(work, "list.txt"); open(lst, "w").write("\n".join(concat) + "\n")
        name = f"{i:02d}-" + re.sub(r"[«»\"]", "", TITLES[i-1]).replace(" ", "-").lower() + ".mp4"
        out = os.path.join(OUT, name)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lst,
                        "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
                        "-vf", "fps=30,format=yuv420p", "-c:v", "libx264", "-preset", "medium", "-crf", "20",
                        "-c:a", "aac", "-b:a", "128k", "-t", f"{total:.2f}", "-movflags", "+faststart",
                        out], check=True)
        subprocess.run(["rm", "-rf", work])
        print(f"{name}  {total:.1f} s")


if __name__ == "__main__":
    main()
