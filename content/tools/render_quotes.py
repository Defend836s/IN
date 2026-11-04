"""Ролики на цитатах классиков для «Все курсы мира»: говорит Сова-профессор,
верх кадра свободен под баннер. Две версии: чистая и с баннером."""
import os, sys
from PIL import Image, ImageDraw, ImageFont
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import render_blue as rb
import render_avatar as ra
import owl

rb.SAY[:0] = [(r"\b137 лет\b", "сто тридцать семь лет"), (r"\b200 лет\b", "двести лет"), (r"\b200 лет\b", "двести лет"),
              (r"\b1 день\b", "один день"), (r"\b([Пп])отом\b", "\\1ото\u0301м")]
ra.TAG = None
ra.TEXT_TOP, ra.TEXT_BOT = 735, 990
ra.BAR_Y = 712
SMALL = 430
ra.SP = {k: v.resize((SMALL, SMALL), Image.LANCZOS) for k, v in owl.sprites().items()}
ra.CHAR_X, ra.CHAR_Y = 470 - SMALL // 2, 1440 - SMALL + 36


def card(w=1000, h=440):
    """Карточка баннера с совой."""
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, w - 1, h - 1], radius=44, fill=rb.BLUE + (255,), outline=rb.WHITE, width=5)
    tag = ImageFont.truetype(rb.SEMI, 34)
    d.rounded_rectangle([44, 40, 44 + d.textlength("ВСЕ КУРСЫ МИРА", font=tag) + 36, 98], radius=29, fill=rb.WHITE)
    d.text((62, 47), "ВСЕ КУРСЫ МИРА", font=tag, fill=rb.BLUE)
    f1 = ImageFont.truetype(rb.BOLD, 52)
    d.text((44, 130), "Полезная информация", font=f1, fill=rb.WHITE)
    d.text((44, 192), "по разным направлениям", font=f1, fill=rb.WHITE)
    fp = ImageFont.truetype(rb.BOLD, 96)
    price = "3 975 ₽"
    pw = d.textlength(price, font=fp)
    d.rounded_rectangle([44, 280, 44 + pw + 48, 400], radius=30, fill=rb.WHITE)
    d.text((68, 284), price, font=fp, fill=rb.BLUE)
    f2 = ImageFont.truetype(rb.SEMI, 38)
    x = 44 + pw + 90
    d.text((x, 298), "Ссылка", font=f2, fill=rb.WHITE)
    d.text((x, 344), "в шапке профиля", font=f2, fill=rb.WHITE)
    g = owl.sprite(0, False).resize((250, 250), Image.LANCZOS)
    img.alpha_composite(g, (w - 250, 6))
    return img


if __name__ == "__main__":
    src, outdir, voice, piper = map(os.path.abspath, sys.argv[1:5])
    titles = sys.argv[5].split("|")
    only = sys.argv[6:]
    os.makedirs(os.path.join(outdir, "чистые"), exist_ok=True)
    os.makedirs(os.path.join(outdir, "с-баннером"), exist_ok=True)
    os.makedirs(os.path.join(outdir, "баннер"), exist_ok=True)
    c = card()
    c.save(os.path.join(outdir, "баннер", "баннер-карточка-сова-1000x440.png"))
    banner = Image.new("RGBA", (1080, 1920), (0, 0, 0, 0))
    banner.alpha_composite(c, (40, 250))
    banner.save(os.path.join(outdir, "баннер", "баннер-накладка-сова-1080x1920.png"))
    for i, title in enumerate(titles, 1):
        if only and str(i) not in only:
            continue
        lines = [l.strip() for l in open(os.path.join(src, f"r{i:02d}.txt"), encoding="utf-8") if l.strip()]
        for kind, ov in (("чистые", None), ("с-баннером", banner)):
            ra.OVERLAY = ov
            total, _, durs = ra.render(lines, os.path.join(outdir, kind, f"{i:02d}-{title}.mp4"), piper, voice)
        warn = ([f"хук {durs[0]:.1f} с"] if durs[0] > 3.2 else []) + \
               [f"бит {k+1} {d:.1f} с" for k, d in enumerate(durs) if d > 4.2]
        print(f"{i:02d}-{title}  {total:.1f} с" + (f"  ! {', '.join(warn)}" if warn else ""), flush=True)
