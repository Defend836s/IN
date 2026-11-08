"""Медведь-наставник в полный рост: ходит и жестикулирует.
Голова - из bear2 (объём, брови, формы рта); тело, руки и ноги рисуются каждый кадр
в 2x и уменьшаются (гладкие края). frame(...) -> RGBA FW x FH."""
import math
from PIL import Image, ImageDraw
import bear2
from bear2 import NAVY, NAVY_LT, NAVY_HI, FUR, MUZZLE, SHIRT, GOLD, GOLD_DK

FW, FH = 420, 600        # итоговый размер кадра персонажа
S = 2
SHOE, SHOE_HI = (40, 26, 20), (90, 66, 56)
PANTS = (18, 34, 92)


class FullRig:
    def __init__(self):
        hs = int(250 * S)
        self.heads = {k: v.resize((hs, hs), Image.LANCZOS) for k, v in bear2.Rig().heads.items()}
        self.hs = hs

    def _arm(self, d, sx, sy, side, ang, pose):
        L, w = 150 * S, 50 * S
        a = math.radians(ang)
        ex, ey = sx + side * math.sin(a) * L, sy + math.cos(a) * L
        d.line([sx, sy, ex, ey], fill=NAVY, width=w + 10 * S)
        d.line([sx, sy, ex, ey], fill=NAVY_LT, width=w)
        r = 27 * S
        d.ellipse([ex - r, ey - r, ex + r, ey + r], fill=FUR, outline=NAVY, width=int(6 * S))
        if pose == "point":                       # палец поверх лапы, вдоль руки
            fx, fy = ex + side * math.sin(a) * 58 * S, ey + math.cos(a) * 58 * S
            d.line([ex, ey, fx, fy], fill=NAVY, width=int(26 * S))
            d.line([ex, ey, fx, fy], fill=FUR, width=int(16 * S))
            d.ellipse([fx - 10 * S, fy - 10 * S, fx + 10 * S, fy + 10 * S], fill=FUR, outline=NAVY, width=int(5 * S))
        if pose == "palm":
            for k in (-1, 0, 1):
                d.ellipse([ex + k * r * 0.45 - r * 0.16, ey - r * 0.75, ex + k * r * 0.45 + r * 0.16, ey - r * 0.45],
                          fill=MUZZLE)

    def _leg(self, d, hx, hy, lift):
        foot = hy + 150 * S - lift
        d.rounded_rectangle([hx - 31 * S, hy, hx + 31 * S, foot], radius=int(22 * S), fill=PANTS,
                            outline=NAVY, width=int(6 * S))
        d.ellipse([hx - 44 * S, foot - 20 * S, hx + 44 * S, foot + 22 * S], fill=SHOE, outline=NAVY, width=int(5 * S))
        d.ellipse([hx - 26 * S, foot - 14 * S, hx - 6 * S, foot - 4 * S], fill=SHOE_HI)

    def frame(self, mouth, shape, blink, brow, pose="idle", phase=0.0, walking=False,
              tilt=0.0, nod=0, breath=0.0):
        W, H = FW * S, FH * S
        img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        cx = W / 2
        bob = -abs(math.sin(phase)) * 10 * S if walking else math.sin(breath * math.pi) * 2 * S
        sway = math.sin(phase) * 3 if walking else 0
        # тень под ногами
        d.ellipse([cx - 120 * S, H - 40 * S, cx + 120 * S, H - 8 * S], fill=(0, 20, 90, 100))
        # ноги (шаг: поочерёдно поднимаются)
        hy = H - 205 * S + bob
        lift_l = max(0.0, math.sin(phase)) * 34 * S if walking else 0
        lift_r = max(0.0, -math.sin(phase)) * 34 * S if walking else 0
        self._leg(d, cx - 44 * S, hy, lift_l)
        self._leg(d, cx + 44 * S, hy, lift_r)
        # руки за туловищем, если просто идёт
        swing = math.sin(phase) * 18 if walking else 0
        top = H - 400 * S + bob
        sh_y = top + 30 * S
        poses = {"left": ("rest", 12 + swing), "right": ("rest", 12 - swing)}
        if pose == "palm":
            poses["right"] = ("palm", 145)
        elif pose == "point":
            poses["left"] = ("point", 138)
        for side, key in ((-1, "left"), (1, "right")):
            p, ang = poses[key]
            if p == "rest":
                self._arm(d, cx + side * 92 * S, sh_y, side, ang, p)
        # туловище: пиджак, рубашка, галстук, пуговицы, платок
        d.rounded_rectangle([cx - 108 * S, top, cx + 108 * S, hy + 30 * S], radius=int(60 * S),
                            fill=NAVY_LT, outline=NAVY, width=int(7 * S))
        d.polygon([(cx - 36 * S, top + 4 * S), (cx + 36 * S, top + 4 * S), (cx, top + 92 * S)], fill=SHIRT)
        for side in (-1, 1):
            d.polygon([(cx + side * 36 * S, top + 4 * S), (cx + side * 62 * S, top + 12 * S),
                       (cx + side * 8 * S, top + 104 * S)], fill=NAVY)
        d.polygon([(cx - 9 * S, top + 8 * S), (cx + 9 * S, top + 8 * S), (cx + 6 * S, top + 20 * S),
                   (cx - 6 * S, top + 20 * S)], fill=GOLD_DK)
        d.polygon([(cx - 6 * S, top + 20 * S), (cx + 6 * S, top + 20 * S), (cx + 12 * S, top + 72 * S),
                   (cx, top + 86 * S), (cx - 12 * S, top + 72 * S)], fill=GOLD, outline=GOLD_DK)
        for k in range(2):
            y = top + (122 + 34 * k) * S
            d.ellipse([cx - 8 * S, y - 8 * S, cx + 8 * S, y + 8 * S], fill=NAVY_HI, outline=NAVY)
        px, py = cx + 62 * S, top + 46 * S
        d.line([px - 22 * S, py + 10 * S, px + 22 * S, py + 10 * S], fill=NAVY, width=int(4 * S))
        d.polygon([(px - 16 * S, py + 10 * S), (px - 7 * S, py - 6 * S), (px + 2 * S, py + 10 * S)], fill=GOLD)
        d.polygon([(px, py + 10 * S), (px + 9 * S, py - 7 * S), (px + 18 * S, py + 10 * S)], fill=GOLD_DK)
        d.line([cx - 104 * S, hy + 4 * S, cx + 104 * S, hy + 4 * S], fill=NAVY, width=int(5 * S))   # пояс
        # руки в жесте - поверх туловища
        for side, key in ((-1, "left"), (1, "right")):
            p, ang = poses[key]
            if p != "rest":
                self._arm(d, cx + side * 92 * S, sh_y, side, ang, p)
        # голова
        h = self.heads[(mouth, shape, blink, 1.0 if brow > 0.5 else 0.0)]
        if tilt + sway:
            h = h.rotate(tilt + sway, resample=Image.BICUBIC, center=(self.hs / 2, self.hs * 0.85))
        img.alpha_composite(h, (int(cx - self.hs / 2), int(top - self.hs * 0.8 + nod * S)))
        return img.resize((FW, FH), Image.LANCZOS)


if __name__ == "__main__":
    import sys
    rig = FullRig()
    poses = [dict(mouth=0, shape="wide", blink=False, brow=0, pose="idle"),
             dict(mouth=3, shape="wide", blink=False, brow=0, walking=True, phase=math.pi / 2),
             dict(mouth=2, shape="round", blink=False, brow=0, walking=True, phase=-math.pi / 2),
             dict(mouth=3, shape="round", blink=False, brow=1, pose="palm", tilt=-4),
             dict(mouth=2, shape="wide", blink=False, brow=0, pose="point", nod=5)]
    sheet = Image.new("RGBA", (FW * len(poses), FH), (0, 71, 255, 255))
    for k, p in enumerate(poses):
        sheet.alpha_composite(rig.frame(**p), (k * FW, 0))
    sheet.convert("RGB").resize((FW * len(poses) // 2, FH // 2)).save(sys.argv[1])
