"""Сова-профессор: оригинальный персонаж канала «Все курсы мира».
Тот же интерфейс, что у globus.py: sprites() -> {(рот 0..4, моргание): RGBA}."""
from PIL import Image, ImageDraw

S, SIZE = 2, 600
NAVY = (10, 26, 79)
BROWN, BROWN_DK = (156, 98, 58), (110, 64, 34)
BELLY, BELLY_LINE = (246, 226, 196), (214, 182, 140)
DISC = (250, 238, 220)
IRIS = (255, 170, 30)
BEAK, BEAK_DK = (255, 186, 40), (196, 120, 10)
MOUTH_IN = (120, 30, 30)
GOLD = (255, 210, 63)


def sprite(mouth=0, blink=False):
    W = SIZE * S
    img = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    cx = W // 2
    lw = int(8 * S)
    # тень
    d.ellipse([cx - 230 * S / 2 * 1.6, W * 0.93, cx + 230 * S / 2 * 1.6, W * 0.99], fill=(0, 20, 90, 90))
    # тело
    bw, top, bot = W * 0.33, W * 0.36, W * 0.96
    d.ellipse([cx - bw, top, cx + bw, bot], fill=BROWN, outline=NAVY, width=lw)
    # крылья
    for sx in (-1, 1):
        x0 = cx + sx * bw * 0.78
        d.ellipse([x0 - bw * 0.32, W * 0.55, x0 + bw * 0.32, W * 0.9], fill=BROWN_DK, outline=NAVY, width=lw)
    # животик с пёрышками
    d.ellipse([cx - bw * 0.62, W * 0.55, cx + bw * 0.62, W * 0.94], fill=BELLY)
    for row in range(3):
        y = W * (0.64 + row * 0.08)
        for k in range(-2 + (row % 2), 3, 2):
            x = cx + k * bw * 0.17
            d.arc([x - 16 * S, y - 10 * S, x + 16 * S, y + 12 * S], 20, 160, fill=BELLY_LINE, width=int(4 * S))
    # голова
    hw, htop, hbot = W * 0.36, W * 0.12, W * 0.6
    d.ellipse([cx - hw, htop, cx + hw, hbot], fill=BROWN, outline=NAVY, width=lw)
    # ушки-пучки
    for sx in (-1, 1):
        x = cx + sx * hw * 0.72
        d.polygon([(x - sx * 40 * S, htop + 40 * S), (x + sx * 22 * S, htop - 40 * S),
                   (x + sx * 46 * S, htop + 70 * S)], fill=BROWN_DK, outline=NAVY)
    d.ellipse([cx - hw, htop, cx + hw, hbot], outline=NAVY, width=lw)
    # лицевые диски и глаза
    ey, er = W * 0.35, W * 0.115
    for sx in (-1, 1):
        x = cx + sx * hw * 0.46
        d.ellipse([x - er * 1.3, ey - er * 1.3, x + er * 1.3, ey + er * 1.3], fill=DISC)
        if blink:
            d.arc([x - er * 0.8, ey - er * 0.4, x + er * 0.8, ey + er * 0.6], 15, 165, fill=NAVY, width=int(9 * S))
        else:
            d.ellipse([x - er, ey - er, x + er, ey + er], fill=IRIS, outline=NAVY, width=int(6 * S))
            pr = er * 0.5
            d.ellipse([x - pr, ey - pr, x + pr, ey + pr], fill=NAVY)
            d.ellipse([x - pr * 0.1, ey - pr * 0.8, x + pr * 0.5, ey - pr * 0.2], fill=(255, 255, 255))
        # очки
        d.ellipse([x - er * 1.12, ey - er * 1.12, x + er * 1.12, ey + er * 1.12], outline=NAVY, width=int(7 * S))
        # уверенные брови
        d.line([x - sx * er * 1.0, ey - er * 1.18, x + sx * er * 0.9, ey - er * 1.36],
               fill=NAVY, width=int(10 * S))
    d.line([cx - hw * 0.46 + er * 1.12, ey, cx + hw * 0.46 - er * 1.12, ey], fill=NAVY, width=int(7 * S))
    # клюв: верхняя часть неподвижна, нижняя опускается при речи
    by = ey + er * 0.55
    open_ = mouth * 17 * S
    if mouth:
        d.ellipse([cx - 30 * S, by + 18 * S, cx + 30 * S, by + 40 * S + open_], fill=MOUTH_IN, outline=NAVY,
                  width=int(4 * S))
    d.polygon([(cx - 30 * S, by + 26 * S + open_ * 0.35), (cx + 30 * S, by + 26 * S + open_ * 0.35),
               (cx, by + 56 * S + open_)], fill=BEAK_DK, outline=NAVY)
    d.polygon([(cx - 34 * S, by), (cx + 34 * S, by), (cx, by + 50 * S)], fill=BEAK, outline=NAVY)
    # академическая шапочка
    ct = htop - 14 * S
    d.polygon([(cx - hw * 0.62, ct), (cx, ct - hw * 0.26), (cx + hw * 0.62, ct), (cx, ct + hw * 0.2)], fill=NAVY)
    d.rectangle([cx - hw * 0.3, ct + hw * 0.02, cx + hw * 0.3, ct + hw * 0.17], fill=NAVY)
    d.ellipse([cx - 10 * S, ct - 14 * S, cx + 10 * S, ct + 6 * S], fill=GOLD)
    d.line([cx, ct - 4 * S, cx + hw * 0.5, ct + hw * 0.1], fill=GOLD, width=int(7 * S))
    d.line([cx + hw * 0.5, ct + hw * 0.1, cx + hw * 0.5, ct + hw * 0.24], fill=GOLD, width=int(7 * S))
    d.ellipse([cx + hw * 0.43, ct + hw * 0.21, cx + hw * 0.57, ct + hw * 0.35], fill=GOLD)
    return img.resize((SIZE, SIZE), Image.LANCZOS)


def sprites():
    return {(m, b): sprite(m, b) for m in range(5) for b in (False, True)}


if __name__ == "__main__":
    import sys
    sheet = Image.new("RGBA", (SIZE * 5, SIZE), (0, 71, 255, 255))
    for k, key in enumerate([(0, False), (1, False), (2, False), (3, False), (0, True)]):
        sheet.alpha_composite(sprite(*key), (k * SIZE, 0))
    sheet.convert("RGB").resize((SIZE * 5 // 2, SIZE // 2)).save(sys.argv[1])
