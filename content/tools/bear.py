"""Медведь-наставник: оригинальный персонаж «Все курсы мира» под голос Vosk male_0 (вариант D).
Интерфейс как у owl.py / globus.py: sprites() -> {(рот 0..4, моргание): RGBA}, SIZE."""
from PIL import Image, ImageDraw

S, SIZE = 2, 600
NAVY, NAVY_LT = (10, 26, 79), (24, 44, 112)
FUR, FUR_DK, MUZZLE, EAR_IN = (150, 92, 52), (112, 64, 32), (226, 186, 140), (214, 150, 110)
SHIRT, GOLD, GOLD_DK = (250, 250, 252), (255, 205, 60), (214, 160, 20)
MOUTH_IN, TONGUE, NOSE = (90, 20, 30), (232, 104, 112), (40, 24, 20)


def sprite(mouth=0, blink=False):
    W = SIZE * S
    img = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    cx, lw = W // 2, int(8 * S)
    # тень
    d.ellipse([cx - W * 0.36, W * 0.94, cx + W * 0.36, W * 1.0], fill=(0, 20, 90, 90))
    # плечи: пиджак, рубашка, галстук
    d.rounded_rectangle([cx - W * 0.4, W * 0.66, cx + W * 0.4, W * 1.05], radius=int(W * 0.16),
                        fill=NAVY_LT, outline=NAVY, width=lw)
    d.polygon([(cx - W * 0.12, W * 0.67), (cx + W * 0.12, W * 0.67), (cx, W * 0.86)], fill=SHIRT)
    for sx in (-1, 1):                                     # лацканы
        d.polygon([(cx + sx * W * 0.12, W * 0.67), (cx + sx * W * 0.2, W * 0.69), (cx + sx * W * 0.03, W * 0.9)],
                  fill=NAVY, outline=NAVY)
    d.polygon([(cx - W * 0.03, W * 0.69), (cx + W * 0.03, W * 0.69), (cx + W * 0.022, W * 0.72),
               (cx - W * 0.022, W * 0.72)], fill=GOLD_DK)
    d.polygon([(cx - W * 0.022, W * 0.72), (cx + W * 0.022, W * 0.72), (cx + W * 0.04, W * 0.84),
               (cx, W * 0.88), (cx - W * 0.04, W * 0.84)], fill=GOLD, outline=GOLD_DK)
    # уши
    hx, hy, hr = cx, W * 0.42, W * 0.27
    for sx in (-1, 1):
        ex, ey = hx + sx * hr * 0.78, hy - hr * 0.78
        d.ellipse([ex - hr * 0.33, ey - hr * 0.33, ex + hr * 0.33, ey + hr * 0.33], fill=FUR, outline=NAVY, width=lw)
        d.ellipse([ex - hr * 0.18, ey - hr * 0.18, ex + hr * 0.18, ey + hr * 0.18], fill=EAR_IN)
    # голова
    d.ellipse([hx - hr * 1.05, hy - hr, hx + hr * 1.05, hy + hr * 0.98], fill=FUR, outline=NAVY, width=lw)
    # морда
    my = hy + hr * 0.38
    d.ellipse([hx - hr * 0.52, my - hr * 0.36, hx + hr * 0.52, my + hr * 0.42], fill=MUZZLE)
    # глаза с уверенным прищуром (верхнее веко прикрывает треть глаза)
    ey, er = hy - hr * 0.12, hr * 0.205
    for sx in (-1, 1):
        x = hx + sx * hr * 0.42
        if blink:
            d.arc([x - er, ey - er * 0.6, x + er, ey + er * 0.7], 15, 165, fill=NAVY, width=int(8 * S))
        else:
            d.ellipse([x - er, ey - er, x + er, ey + er], fill=(255, 255, 255), outline=NAVY, width=int(5 * S))
            pr = er * 0.55
            d.ellipse([x - pr + sx * er * 0.05, ey - pr * 0.7, x + pr + sx * er * 0.05, ey + pr * 1.3], fill=NAVY)
            d.ellipse([x - pr * 0.1, ey - pr * 0.4, x + pr * 0.4, ey + pr * 0.1], fill=(255, 255, 255))
            d.chord([x - er * 1.05, ey - er * 1.1, x + er * 1.05, ey + er * 0.25], 180, 360, fill=FUR)
            d.arc([x - er * 1.0, ey - er * 0.95, x + er * 1.0, ey + er * 0.25], 200, 340, fill=NAVY, width=int(6 * S))
        # густые брови, внутренний край ниже: собранный уверенный взгляд
        d.line([x - sx * er * 1.15, ey - er * 1.3, x + sx * er * 1.05, ey - er * 1.48], fill=FUR_DK, width=int(14 * S))
    # нос
    ny = my - hr * 0.12
    d.ellipse([hx - hr * 0.17, ny - hr * 0.11, hx + hr * 0.17, ny + hr * 0.11], fill=NOSE)
    d.ellipse([hx - hr * 0.07, ny - hr * 0.08, hx + hr * 0.02, ny - hr * 0.03], fill=(120, 100, 90))
    # рот: закрытый - полуулыбка, открытый - по громкости
    mty = ny + hr * 0.2
    d.line([hx, ny + hr * 0.1, hx, mty], fill=NOSE, width=int(5 * S))
    if mouth == 0:
        d.arc([hx - hr * 0.28, mty - hr * 0.16, hx + hr * 0.02, mty + hr * 0.12], 20, 120, fill=NOSE, width=int(6 * S))
        d.arc([hx - hr * 0.02, mty - hr * 0.2, hx + hr * 0.32, mty + hr * 0.1], 40, 150, fill=NOSE, width=int(6 * S))
    else:
        h = hr * (0.07 + 0.065 * mouth); w = hr * (0.27 - 0.012 * mouth)
        d.rounded_rectangle([hx - w, mty - h * 0.15, hx + w, mty + h], radius=int(min(w, h) * 0.9),
                            fill=MOUTH_IN, outline=NOSE, width=int(5 * S))
        d.rounded_rectangle([hx - w * 0.75, mty - h * 0.1, hx + w * 0.75, mty + h * 0.22], radius=int(4 * S),
                            fill=(255, 255, 255))
        if mouth >= 2:
            d.ellipse([hx - w * 0.5, mty + h * 0.45, hx + w * 0.5, mty + h * 0.95], fill=TONGUE)
    return img.resize((SIZE, SIZE), Image.LANCZOS)


def sprites():
    return {(m, b): sprite(m, b) for m in range(5) for b in (False, True)}


if __name__ == "__main__":
    import sys
    sheet = Image.new("RGBA", (SIZE * 5, SIZE), (0, 71, 255, 255))
    for k, key in enumerate([(0, False), (1, False), (2, False), (4, False), (0, True)]):
        sheet.alpha_composite(sprite(*key), (k * SIZE, 0))
    sheet.convert("RGB").resize((SIZE * 5 // 2, SIZE // 2)).save(sys.argv[1])
