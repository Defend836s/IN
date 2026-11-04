"""Профессор Глобус: оригинальный персонаж канала «Все курсы мира».
Спрайты рисуются один раз: 5 положений рта x 2 положения глаз."""
import math
from PIL import Image, ImageDraw

S = 2                     # суперсэмплинг для гладких краёв
SIZE = 600                # итоговый размер спрайта
NAVY = (10, 26, 79)
WHITE = (255, 255, 255)
SEA = (226, 236, 255)
LAND = (120, 170, 255)
LINE = (170, 200, 255)
GOLD = (255, 210, 63)
MOUTH_IN = (120, 20, 40)
TONGUE = (240, 110, 120)


def sprite(mouth=0, blink=False):
    W = SIZE * S
    img = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    cx, cy, r = W // 2, int(W * 0.58), int(W * 0.36)
    lw = int(9 * S)
    # тень
    d.ellipse([cx - r * 0.8, cy + r * 0.92, cx + r * 0.8, cy + r * 1.08], fill=(0, 20, 90, 90))
    # голова-глобус
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=SEA, outline=NAVY, width=lw)
    # материки (абстрактные пятна, без реальной карты)
    for (dx, dy, rx, ry) in [(-0.55, -0.35, 0.28, 0.2), (-0.62, 0.25, 0.2, 0.3), (0.5, -0.5, 0.25, 0.16),
                             (0.62, 0.3, 0.22, 0.26), (0.05, 0.72, 0.35, 0.14)]:
        x, y = cx + dx * r, cy + dy * r
        d.ellipse([x - rx * r, y - ry * r, x + rx * r, y + ry * r], fill=LAND)
    # меридианы и параллели
    for k in (0.45, 0.8):
        d.ellipse([cx - r * k, cy - r, cx + r * k, cy + r], outline=LINE, width=int(4 * S))
    for k in (-0.5, 0.5):
        y = cy + k * r; hw = r * math.sqrt(1 - k * k)
        d.line([cx - hw, y, cx + hw, y], fill=LINE, width=int(4 * S))
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=NAVY, width=lw)
    # очки и глаза
    ey, er, ex = cy - r * 0.12, r * 0.24, r * 0.36
    for sx in (-1, 1):
        x = cx + sx * ex
        d.ellipse([x - er, ey - er, x + er, ey + er], fill=WHITE, outline=NAVY, width=int(8 * S))
        if blink:
            d.line([x - er * 0.6, ey + er * 0.1, x + er * 0.6, ey + er * 0.1], fill=NAVY, width=int(8 * S))
        else:
            pr = er * 0.42
            d.ellipse([x - pr + er * 0.08, ey - pr, x + pr + er * 0.08, ey + pr], fill=NAVY)
            d.ellipse([x - pr * 0.2, ey - pr * 0.75, x + pr * 0.35, ey - pr * 0.2], fill=WHITE)
        # уверенные брови: чуть сведены к центру
        by = ey - er * 1.45
        d.line([x - sx * er * 0.75, by + er * 0.07, x + sx * er * 0.75, by - er * 0.07],
               fill=NAVY, width=int(11 * S))
    d.line([cx - ex + er, ey, cx + ex - er, ey], fill=NAVY, width=int(8 * S))   # перемычка очков
    # рот
    my, mw = cy + r * 0.42, r * 0.34
    if mouth == 0:
        d.arc([cx - mw, my - mw * 0.55, cx + mw, my + mw * 0.45], 20, 160, fill=NAVY, width=int(10 * S))
    else:
        h = mw * (0.18 + 0.2 * mouth)
        w = mw * (0.95 - 0.06 * mouth)
        d.rounded_rectangle([cx - w, my - h * 0.5, cx + w, my + h], radius=int(min(w, h)),
                            fill=MOUTH_IN, outline=NAVY, width=int(8 * S))
        if mouth >= 2:
            d.ellipse([cx - w * 0.5, my + h * 0.35, cx + w * 0.5, my + h * 0.95], fill=TONGUE)
        d.rounded_rectangle([cx - w * 0.7, my - h * 0.5 + 4 * S, cx + w * 0.7, my - h * 0.5 + h * 0.28],
                            radius=int(6 * S), fill=WHITE)                       # зубы
    # академическая шапочка
    top = cy - r * 0.93
    d.polygon([(cx - r * 0.62, top), (cx, top - r * 0.28), (cx + r * 0.62, top), (cx, top + r * 0.22)],
              fill=NAVY)
    d.rectangle([cx - r * 0.32, top + r * 0.02, cx + r * 0.32, top + r * 0.2], fill=NAVY)
    d.ellipse([cx - r * 0.06, top - r * 0.08, cx + r * 0.06, top + r * 0.04], fill=GOLD)
    d.line([cx, top - r * 0.02, cx + r * 0.52, top + r * 0.12], fill=GOLD, width=int(7 * S))
    d.line([cx + r * 0.52, top + r * 0.12, cx + r * 0.52, top + r * 0.42], fill=GOLD, width=int(7 * S))
    d.ellipse([cx + r * 0.44, top + r * 0.38, cx + r * 0.6, top + r * 0.54], fill=GOLD)
    return img.resize((SIZE, SIZE), Image.LANCZOS)


def sprites():
    return {(m, b): sprite(m, b) for m in range(5) for b in (False, True)}


if __name__ == "__main__":
    import sys
    sp = sprites()
    sheet = Image.new("RGBA", (SIZE * 6, SIZE), (0, 71, 255, 255))
    for k, key in enumerate([(0, False), (1, False), (2, False), (3, False), (4, False), (0, True)]):
        sheet.alpha_composite(sp[key], (k * SIZE, 0))
    sheet.convert("RGB").resize((SIZE * 3, SIZE // 2)).save(sys.argv[1])
