"""Баннер закрытого канала: карточка PNG, прозрачная накладка 1080x1920 и
озвученная концовка MP4."""
import os, subprocess, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PIL import Image, ImageDraw, ImageFont
from render_blue import BLUE, BLUE_DK, WHITE, BOLD, SEMI
import render_avatar
from globus import sprite

OUT = os.path.abspath(sys.argv[1]); VOICE, PIPER = map(os.path.abspath, sys.argv[2:4])
PRICE = "3 975 ₽"
os.makedirs(OUT, exist_ok=True)


def card(w=1000, h=440):
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, w - 1, h - 1], radius=44, fill=BLUE + (255,), outline=WHITE, width=5)
    tag = ImageFont.truetype(SEMI, 34)
    d.rounded_rectangle([44, 40, 44 + d.textlength("ВСЕ КУРСЫ МИРА", font=tag) + 36, 98], radius=29,
                        fill=WHITE)
    d.text((62, 47), "ВСЕ КУРСЫ МИРА", font=tag, fill=BLUE)
    f1 = ImageFont.truetype(BOLD, 52)
    d.text((44, 130), "Полезная информация", font=f1, fill=WHITE)
    d.text((44, 192), "по разным направлениям", font=f1, fill=WHITE)
    fp = ImageFont.truetype(BOLD, 96)
    pw = d.textlength(PRICE, font=fp)
    d.rounded_rectangle([44, 280, 44 + pw + 48, 400], radius=30, fill=WHITE)
    d.text((68, 284), PRICE, font=fp, fill=BLUE)
    f2 = ImageFont.truetype(SEMI, 38)
    x = 44 + pw + 90
    d.text((x, 298), "Ссылка", font=f2, fill=WHITE)
    d.text((x, 344), "в шапке профиля", font=f2, fill=WHITE)
    g = sprite(0, False).resize((250, 250))
    img.alpha_composite(g, (w - 250, 8))
    return img


c = card()
c.save(os.path.join(OUT, "баннер-карточка-1000x440.png"))
over = Image.new("RGBA", (1080, 1920), (0, 0, 0, 0))
over.alpha_composite(c, (40, 250))          # верх безопасной зоны: не закрывает подпись и кнопки
over.save(os.path.join(OUT, "баннер-накладка-1080x1920.png"))

# Концовка: полноэкранная, со своим голосом.
lines = ["Канал «Все курсы мира».", "Полезная информация по разным направлениям.",
         f"Всего {PRICE}.", "Ссылка в шапке профиля."]
import render_blue
render_blue.SAY.insert(0, (r"3 975 ₽", "три тысячи девятьсот семьдесят пять рублей"))
total, _, _ = render_avatar.render(lines, os.path.join(OUT, "баннер-концовка.mp4"), PIPER, VOICE)
print(f"концовка {total:.1f} с")
