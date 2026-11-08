"""Медведь-наставник v2: объём, детали и «риг» из отдельных частей.
Голова (рот 0..4 x форма wide/round x моргание x брови) и тело (лапа: rest/palm/point)
рисуются заранее, кадр собирается из них с наклоном и кивком головы."""
import math
from PIL import Image, ImageDraw, ImageFilter

S = 2
HEAD, BODY = 420, 600          # размеры слоёв в итоговых пикселях
NAVY, NAVY_LT, NAVY_HI = (10, 26, 79), (26, 46, 116), (52, 76, 160)
FUR, FUR_DK, FUR_LT = (150, 92, 52), (104, 58, 28), (186, 124, 76)
MUZZLE, MUZZLE_DK, EAR_IN = (232, 194, 148), (206, 160, 112), (220, 150, 112)
SHIRT, GOLD, GOLD_DK = (250, 250, 252), (255, 205, 60), (214, 160, 20)
MOUTH_IN, TONGUE, NOSE = (84, 18, 28), (232, 104, 112), (36, 22, 18)
BLUSH = (236, 120, 110, 70)


def _soft_ellipse(size, box, color, blur):
    """Полупрозрачное размытое пятно: тень или блик."""
    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    ImageDraw.Draw(layer).ellipse(box, fill=color)
    return layer.filter(ImageFilter.GaussianBlur(blur))


def head(mouth=0, shape="wide", blink=False, brow_up=0.0):
    W = HEAD * S
    img = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    cx, cy, r = W / 2, W * 0.55, W * 0.36
    lw = int(7 * S)
    # уши с объёмом
    for sx in (-1, 1):
        ex, ey = cx + sx * r * 0.8, cy - r * 0.78
        d.ellipse([ex - r * 0.32, ey - r * 0.32, ex + r * 0.32, ey + r * 0.32], fill=FUR, outline=NAVY, width=lw)
        d.ellipse([ex - r * 0.18, ey - r * 0.16, ex + r * 0.18, ey + r * 0.2], fill=EAR_IN)
    # голова: пушистые щёки по краю
    pts = []
    for k in range(72):
        a = 2 * math.pi * k / 72
        rr = r * (1.0 + (0.045 if (k % 3 == 0 and 0.6 < math.sin(a) + 0.9 < 1.9 and abs(math.cos(a)) > 0.55) else 0))
        pts.append((cx + rr * 1.06 * math.cos(a), cy + rr * math.sin(a)))
    d.polygon(pts, fill=FUR, outline=NAVY)
    d.line(pts + [pts[0]], fill=NAVY, width=lw, joint="curve")
    # объём: тень снизу, блик сверху-слева
    shade = _soft_ellipse((W, W), [cx - r * 1.1, cy + r * 0.2, cx + r * 1.1, cy + r * 1.3], FUR_DK + (150,), 40 * S)
    hi = _soft_ellipse((W, W), [cx - r * 0.85, cy - r * 0.95, cx + r * 0.1, cy - r * 0.25], FUR_LT + (170,), 30 * S)
    mask = Image.new("L", (W, W), 0); ImageDraw.Draw(mask).polygon(pts, fill=255)
    for lay in (shade, hi):
        a = lay.getchannel("A"); a = Image.composite(a, Image.new("L", (W, W), 0), mask); lay.putalpha(a)
        img.alpha_composite(lay)
    d = ImageDraw.Draw(img)
    # морда
    my = cy + r * 0.38
    d.ellipse([cx - r * 0.55, my - r * 0.37, cx + r * 0.55, my + r * 0.45], fill=MUZZLE)
    img.alpha_composite(_soft_ellipse((W, W), [cx - r * 0.5, my + r * 0.1, cx + r * 0.5, my + r * 0.5],
                                      MUZZLE_DK + (120,), 12 * S))
    d = ImageDraw.Draw(img)
    # румянец
    for sx in (-1, 1):
        img.alpha_composite(_soft_ellipse((W, W), [cx + sx * r * 0.62 - r * 0.15, my - r * 0.12,
                                                   cx + sx * r * 0.62 + r * 0.15, my + r * 0.1], BLUSH, 10 * S))
    d = ImageDraw.Draw(img)
    # глаза
    ey, er = cy - r * 0.12, r * 0.2
    for sx in (-1, 1):
        x = cx + sx * r * 0.43
        if blink:
            d.arc([x - er, ey - er * 0.6, x + er, ey + er * 0.7], 15, 165, fill=NAVY, width=int(7 * S))
        else:
            d.ellipse([x - er, ey - er, x + er, ey + er], fill=(255, 255, 255), outline=NAVY, width=int(5 * S))
            pr = er * 0.58
            d.ellipse([x - pr, ey - pr * 0.6, x + pr, ey + pr * 1.4], fill=(70, 40, 20))     # радужка
            d.ellipse([x - pr * 0.55, ey - pr * 0.15, x + pr * 0.55, ey + pr * 0.95], fill=NAVY)
            d.ellipse([x - pr * 0.05, ey - pr * 0.35, x + pr * 0.45, ey + pr * 0.1], fill=(255, 255, 255))
            d.ellipse([x - pr * 0.5, ey + pr * 0.6, x - pr * 0.25, ey + pr * 0.85], fill=(255, 255, 255))
            lid = ey + er * (0.15 - 0.35 * brow_up)                     # при поднятых бровях глаза шире
            d.chord([x - er * 1.06, ey - er * 1.12, x + er * 1.06, lid + (lid - ey) * 0.0 + er * 0.1],
                    180, 360, fill=FUR)
            d.arc([x - er, ey - er * 0.95, x + er, lid + er * 0.12], 200, 340, fill=NAVY, width=int(5 * S))
        # брови
        by = ey - er * (1.35 + 0.45 * brow_up)
        tilt = er * (0.17 - 0.25 * brow_up)
        d.line([x - sx * er * 1.15, by, x + sx * er * 1.05, by - tilt], fill=FUR_DK, width=int(13 * S))
    # нос с бликом
    ny = my - r * 0.12
    d.ellipse([cx - r * 0.17, ny - r * 0.11, cx + r * 0.17, ny + r * 0.11], fill=NOSE)
    d.ellipse([cx - r * 0.08, ny - r * 0.08, cx + r * 0.01, ny - r * 0.03], fill=(140, 120, 110))
    # рот
    mty = ny + r * 0.2
    d.line([cx, ny + r * 0.1, cx, mty], fill=NOSE, width=int(5 * S))
    if mouth == 0:
        d.arc([cx - r * 0.28, mty - r * 0.16, cx + r * 0.02, mty + r * 0.12], 20, 120, fill=NOSE, width=int(6 * S))
        d.arc([cx - r * 0.02, mty - r * 0.2, cx + r * 0.32, mty + r * 0.1], 40, 150, fill=NOSE, width=int(6 * S))
    else:
        if shape == "round":      # «о», «у»
            h, w = r * (0.09 + 0.07 * mouth), r * (0.13 + 0.015 * mouth)
        else:                     # «а», «и», «е»
            h, w = r * (0.06 + 0.06 * mouth), r * (0.26 - 0.01 * mouth)
        d.rounded_rectangle([cx - w, mty - h * 0.15, cx + w, mty + h], radius=int(min(w, h) * 0.95),
                            fill=MOUTH_IN, outline=NOSE, width=int(5 * S))
        if shape != "round":
            d.rounded_rectangle([cx - w * 0.75, mty - h * 0.1, cx + w * 0.75, mty + h * 0.2],
                                radius=int(4 * S), fill=(255, 255, 255))
        if mouth >= 2:
            d.ellipse([cx - w * 0.55, mty + h * 0.45, cx + w * 0.55, mty + h * 0.95], fill=TONGUE)
    return img.resize((HEAD, HEAD), Image.LANCZOS)


def _paw(d, x, y, r):
    d.ellipse([x - r, y - r, x + r, y + r], fill=FUR, outline=NAVY, width=int(6 * S))
    for k in (-1, 0, 1):
        d.ellipse([x + k * r * 0.45 - r * 0.16, y - r * 0.75, x + k * r * 0.45 + r * 0.16, y - r * 0.45], fill=MUZZLE)


def body(arm="rest"):
    W = BODY * S
    img = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    cx, lw = W / 2, int(8 * S)
    d.ellipse([cx - W * 0.38, W * 0.94, cx + W * 0.38, W * 1.0], fill=(0, 20, 90, 90))
    top = W * 0.5
    d.rounded_rectangle([cx - W * 0.42, top, cx + W * 0.42, W * 1.08], radius=int(W * 0.18), fill=NAVY_LT,
                        outline=NAVY, width=lw)
    img.alpha_composite(_soft_ellipse((W, W), [cx - W * 0.36, top + W * 0.02, cx - W * 0.05, top + W * 0.25],
                                      NAVY_HI + (110,), 25 * S))
    d = ImageDraw.Draw(img)
    d.polygon([(cx - W * 0.13, top + 4), (cx + W * 0.13, top + 4), (cx, top + W * 0.22)], fill=SHIRT)
    for sx in (-1, 1):
        d.polygon([(cx + sx * W * 0.13, top + 4), (cx + sx * W * 0.22, top + W * 0.03), (cx + sx * W * 0.03, top + W * 0.26)],
                  fill=NAVY)
    d.polygon([(cx - W * 0.03, top + W * 0.02), (cx + W * 0.03, top + W * 0.02), (cx + W * 0.022, top + W * 0.05),
               (cx - W * 0.022, top + W * 0.05)], fill=GOLD_DK)
    d.polygon([(cx - W * 0.022, top + W * 0.05), (cx + W * 0.022, top + W * 0.05), (cx + W * 0.04, top + W * 0.18),
               (cx, top + W * 0.22), (cx - W * 0.04, top + W * 0.18)], fill=GOLD, outline=GOLD_DK)
    for k in range(2):                                            # пуговицы
        y = top + W * (0.3 + 0.08 * k)
        d.ellipse([cx - 9 * S, y - 9 * S, cx + 9 * S, y + 9 * S], fill=NAVY_HI, outline=NAVY)
    px, py = cx + W * 0.25, top + W * 0.12                        # платок в нагрудном кармане
    d.line([px - W * 0.06, py + W * 0.03, px + W * 0.06, py + W * 0.03], fill=NAVY, width=int(4 * S))
    d.polygon([(px - W * 0.045, py + W * 0.03), (px - W * 0.02, py - W * 0.015), (px + W * 0.005, py + W * 0.03)], fill=GOLD)
    d.polygon([(px - W * 0.005, py + W * 0.03), (px + W * 0.025, py - W * 0.02), (px + W * 0.05, py + W * 0.03)], fill=GOLD_DK)
    # лапа
    if arm == "palm":            # раскрытая лапа сбоку: «как думаешь?»
        d.line([cx + W * 0.33, top + W * 0.18, cx + W * 0.43, top - W * 0.02], fill=NAVY_LT, width=int(70 * S))
        _paw(d, cx + W * 0.44, top - W * 0.06, W * 0.075)
    elif arm == "point":         # указывает по диагонали вверх, на текст и штамп
        sx0, sy0 = cx - W * 0.33, top + W * 0.18
        x, y = cx - W * 0.4, top - W * 0.04
        d.line([sx0, sy0, x, y], fill=NAVY_LT, width=int(70 * S))
        d.ellipse([x - W * 0.065, y - W * 0.06, x + W * 0.065, y + W * 0.065], fill=FUR, outline=NAVY, width=int(6 * S))
        ang = math.radians(-135)                   # вверх-влево, вдоль руки
        fx, fy = x + math.cos(ang) * W * 0.05, y + math.sin(ang) * W * 0.05
        tx, ty = x + math.cos(ang) * W * 0.15, y + math.sin(ang) * W * 0.15
        d.line([fx, fy, tx, ty], fill=NAVY, width=int(34 * S))
        d.line([fx, fy, tx, ty], fill=FUR, width=int(22 * S))
        d.ellipse([tx - 11 * S, ty - 11 * S, tx + 11 * S, ty + 11 * S], fill=FUR, outline=NAVY, width=int(6 * S))
        bx, by = x + W * 0.045, y - W * 0.035      # большой палец сбоку
        d.ellipse([bx - W * 0.03, by - W * 0.025, bx + W * 0.03, by + W * 0.025], fill=FUR, outline=NAVY, width=int(5 * S))
    return img.resize((BODY, BODY), Image.LANCZOS)


class Rig:
    def __init__(self):
        self.heads = {(m, sh, b, bu): head(m, sh, b, bu) for m in range(5) for sh in ("wide", "round")
                      for b in (False, True) for bu in (0.0, 1.0)}
        self.bodies = {a: body(a) for a in ("rest", "palm", "point")}

    def frame(self, mouth, shape, blink, brow_up, arm, tilt=0.0, nod=0, breath=0.0, size=430):
        """Собрать персонажа: тело + голова с наклоном и кивком. Возвращает RGBA size x size."""
        canvas = Image.new("RGBA", (BODY, BODY), (0, 0, 0, 0))
        b = self.bodies[arm]
        if breath:
            bh = int(BODY * (1 + breath * 0.012))
            b = b.resize((BODY, bh), Image.BICUBIC).crop((0, bh - BODY, BODY, bh))
        canvas.alpha_composite(b)
        h = self.heads[(mouth, shape, blink, 1.0 if brow_up > 0.5 else 0.0)]
        if tilt:
            h = h.rotate(tilt, resample=Image.BICUBIC, center=(HEAD / 2, HEAD * 0.85))
        canvas.alpha_composite(h, ((BODY - HEAD) // 2, int(BODY * 0.5 - HEAD * 0.78) + nod))
        return canvas.resize((size, size), Image.LANCZOS) if size != BODY else canvas


if __name__ == "__main__":
    import sys
    rig = Rig()
    poses = [dict(mouth=0, shape="wide", blink=False, brow_up=0, arm="rest"),
             dict(mouth=3, shape="wide", blink=False, brow_up=0, arm="rest", tilt=3),
             dict(mouth=3, shape="round", blink=False, brow_up=1, arm="palm", tilt=-4),
             dict(mouth=2, shape="wide", blink=False, brow_up=0, arm="point", nod=6),
             dict(mouth=0, shape="wide", blink=True, brow_up=0, arm="rest")]
    sheet = Image.new("RGBA", (BODY * len(poses), BODY), (0, 71, 255, 255))
    for k, p in enumerate(poses):
        sheet.alpha_composite(rig.frame(size=BODY, **p), (k * BODY, 0))
    sheet.convert("RGB").resize((BODY * len(poses) // 2, BODY // 2)).save(sys.argv[1])
