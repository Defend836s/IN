"""Медведь-наставник v3 («максимум»): голова поворачивается (вид 3/4) и смотрит,
плавные жесты, наклон при ходьбе, сжатие-растяжение на шаге, качание галстука,
подрагивание ушей, контровой свет. Голова: head(...) с кэшем, тело - body(...) в 2x."""
import math
from functools import lru_cache
from PIL import Image, ImageDraw, ImageFilter, ImageChops
from bear2 import (NAVY, NAVY_LT, NAVY_HI, FUR, FUR_DK, FUR_LT, MUZZLE, MUZZLE_DK, EAR_IN, SHIRT, GOLD, GOLD_DK,
                   MOUTH_IN, TONGUE, NOSE, BLUSH, _soft_ellipse)

S = 2
HEAD_PX = 300                      # итоговый размер слоя головы (1x)
PANTS = (18, 34, 92)
SHOE, SHOE_HI = (40, 26, 20), (90, 66, 56)
RIM = (150, 200, 255)


@lru_cache(maxsize=400)
def head(mouth=0, shape="wide", blink=False, brow=0, turn=0.0, ear=0):
    """turn: -1 (влево) .. 1 (вправо); brow: 0 или 1; ear: подрагивание ушей -1/0/1."""
    W = 420 * S
    img = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    cx, cy, r = W / 2, W * 0.55, W * 0.36
    fx = turn * r * 0.16                                    # смещение черт лица при повороте
    lw = int(7 * S)
    for sx in (-1, 1):                                      # уши: дальнее чуть меньше и смещено
        far = (sx == -1 and turn > 0) or (sx == 1 and turn < 0)
        k = 1 - 0.12 * abs(turn) if far else 1
        ex = cx + sx * r * 0.8 + turn * r * 0.08
        ey = cy - r * 0.78 + ear * sx * 4 * S
        rr = r * 0.32 * k
        d.ellipse([ex - rr, ey - rr, ex + rr, ey + rr], fill=FUR, outline=NAVY, width=lw)
        d.ellipse([ex - rr * 0.56, ey - rr * 0.5, ex + rr * 0.56, ey + rr * 0.62], fill=EAR_IN)
    pts = []
    for k in range(72):
        a = 2 * math.pi * k / 72
        tuft = 0.045 if (k % 3 == 0 and 0.6 < math.sin(a) + 0.9 < 1.9 and abs(math.cos(a)) > 0.55) else 0
        pts.append((cx + r * (1 + tuft) * 1.06 * math.cos(a), cy + r * (1 + tuft) * math.sin(a)))
    d.polygon(pts, fill=FUR)
    d.line(pts + [pts[0]], fill=NAVY, width=lw, joint="curve")
    mask = Image.new("L", (W, W), 0); ImageDraw.Draw(mask).polygon(pts, fill=255)
    shade = _soft_ellipse((W, W), [cx - r * 1.1 - fx, cy + r * 0.2, cx + r * 1.1 - fx, cy + r * 1.3], FUR_DK + (150,), 40 * S)
    hi = _soft_ellipse((W, W), [cx - r * 0.85 + fx * 0.5, cy - r * 0.95, cx + r * 0.1 + fx * 0.5, cy - r * 0.25],
                       FUR_LT + (170,), 30 * S)
    for lay in (shade, hi):
        lay.putalpha(ImageChops.multiply(lay.getchannel("A"), mask)); img.alpha_composite(lay)
    d = ImageDraw.Draw(img)
    mx = cx + fx * 1.15
    my = cy + r * 0.38
    d.ellipse([mx - r * 0.55, my - r * 0.37, mx + r * 0.55, my + r * 0.45], fill=MUZZLE)
    img.alpha_composite(_soft_ellipse((W, W), [mx - r * 0.5, my + r * 0.1, mx + r * 0.5, my + r * 0.5],
                                      MUZZLE_DK + (120,), 12 * S))
    for sx in (-1, 1):
        img.alpha_composite(_soft_ellipse((W, W), [mx + sx * r * 0.62 - r * 0.15, my - r * 0.12,
                                                   mx + sx * r * 0.62 + r * 0.15, my + r * 0.1], BLUSH, 10 * S))
    d = ImageDraw.Draw(img)
    ey, er = cy - r * 0.12, r * 0.2
    for sx in (-1, 1):
        far = (sx == -1 and turn > 0) or (sx == 1 and turn < 0)
        x = cx + fx + sx * r * 0.43 * (1 - (0.14 * abs(turn) if far else 0))
        ew = er * (1 - (0.15 * abs(turn) if far else 0))
        if blink:
            d.arc([x - ew, ey - er * 0.6, x + ew, ey + er * 0.7], 15, 165, fill=NAVY, width=int(7 * S))
        else:
            d.ellipse([x - ew, ey - er, x + ew, ey + er], fill=(255, 255, 255), outline=NAVY, width=int(5 * S))
            pr = er * 0.58; gx = turn * ew * 0.32           # взгляд по направлению поворота
            d.ellipse([x + gx - pr, ey - pr * 0.6, x + gx + pr, ey + pr * 1.4], fill=(70, 40, 20))
            d.ellipse([x + gx - pr * 0.55, ey - pr * 0.15, x + gx + pr * 0.55, ey + pr * 0.95], fill=NAVY)
            d.ellipse([x + gx - pr * 0.05, ey - pr * 0.35, x + gx + pr * 0.45, ey + pr * 0.1], fill=(255, 255, 255))
            d.ellipse([x + gx - pr * 0.5, ey + pr * 0.6, x + gx - pr * 0.25, ey + pr * 0.85], fill=(255, 255, 255))
            lid = ey + er * (0.15 - 0.35 * brow)
            d.chord([x - ew * 1.06, ey - er * 1.12, x + ew * 1.06, lid + er * 0.1], 180, 360, fill=FUR)
            d.arc([x - ew, ey - er * 0.95, x + ew, lid + er * 0.12], 200, 340, fill=NAVY, width=int(5 * S))
        by = ey - er * (1.35 + 0.45 * brow)
        tilt = er * (0.17 - 0.25 * brow)
        d.line([x - sx * ew * 1.15, by, x + sx * ew * 1.05, by - tilt], fill=FUR_DK, width=int(13 * S))
    ny = my - r * 0.12
    d.ellipse([mx - r * 0.17, ny - r * 0.11, mx + r * 0.17, ny + r * 0.11], fill=NOSE)
    d.ellipse([mx - r * 0.08, ny - r * 0.08, mx + r * 0.01, ny - r * 0.03], fill=(140, 120, 110))
    mty = ny + r * 0.2
    d.line([mx, ny + r * 0.1, mx, mty], fill=NOSE, width=int(5 * S))
    if mouth == 0:
        d.arc([mx - r * 0.28, mty - r * 0.16, mx + r * 0.02, mty + r * 0.12], 20, 120, fill=NOSE, width=int(6 * S))
        d.arc([mx - r * 0.02, mty - r * 0.2, mx + r * 0.32, mty + r * 0.1], 40, 150, fill=NOSE, width=int(6 * S))
    else:
        if shape == "round":
            h, w = r * (0.09 + 0.07 * mouth), r * (0.13 + 0.015 * mouth)
        else:
            h, w = r * (0.06 + 0.06 * mouth), r * (0.26 - 0.01 * mouth)
        d.rounded_rectangle([mx - w, mty - h * 0.15, mx + w, mty + h], radius=int(min(w, h) * 0.95),
                            fill=MOUTH_IN, outline=NOSE, width=int(5 * S))
        if shape != "round":
            d.rounded_rectangle([mx - w * 0.75, mty - h * 0.1, mx + w * 0.75, mty + h * 0.2],
                                radius=int(4 * S), fill=(255, 255, 255))
        if mouth >= 2:
            d.ellipse([mx - w * 0.55, mty + h * 0.45, mx + w * 0.55, mty + h * 0.95], fill=TONGUE)
    return img.resize((HEAD_PX, HEAD_PX), Image.LANCZOS)


FW, FH = 460, 640                   # итоговый слой персонажа (1x)


def _arm(d, sx, sy, side, ang, palm, point):
    L, w = 150 * S, 50 * S
    a = math.radians(ang)
    ex, ey = sx + side * math.sin(a) * L, sy + math.cos(a) * L
    d.line([sx, sy, ex, ey], fill=NAVY, width=w + 10 * S)
    d.line([sx, sy, ex, ey], fill=NAVY_LT, width=w)
    r = 27 * S
    d.ellipse([ex - r, ey - r, ex + r, ey + r], fill=FUR, outline=NAVY, width=int(6 * S))
    if palm > 0.5:
        for k in (-1, 0, 1):
            d.ellipse([ex + k * r * 0.45 - r * 0.16, ey - r * 0.75, ex + k * r * 0.45 + r * 0.16, ey - r * 0.45],
                      fill=MUZZLE)
    if point > 0.01:
        fl = 58 * S * point
        fx, fy = ex + side * math.sin(a) * fl, ey + math.cos(a) * fl
        d.line([ex, ey, fx, fy], fill=NAVY, width=int(26 * S)); d.line([ex, ey, fx, fy], fill=FUR, width=int(16 * S))
        d.ellipse([fx - 10 * S, fy - 10 * S, fx + 10 * S, fy + 10 * S], fill=FUR, outline=NAVY, width=int(5 * S))


def _leg(d, hx, hy, lift, fwd):
    foot = hy + 150 * S - lift
    fxo = fwd * 8 * S
    d.rounded_rectangle([hx - 31 * S + fxo * 0.5, hy, hx + 31 * S + fxo * 0.5, foot], radius=int(22 * S), fill=PANTS,
                        outline=NAVY, width=int(6 * S))
    d.ellipse([hx - 44 * S + fxo, foot - 20 * S, hx + 44 * S + fxo, foot + 22 * S], fill=SHOE, outline=NAVY,
              width=int(5 * S))
    d.ellipse([hx - 26 * S + fxo, foot - 14 * S, hx - 6 * S + fxo, foot - 4 * S], fill=SHOE_HI)


def figure(state):
    """state: mouth, shape, blink, brow, turn, ear, armL, armR (углы от вертикали наружу),
    palmR, pointL (0..1), phase, walk (0..1 - насколько идёт), lean (град), tilt, nod, breath."""
    W, H = FW * S, FH * S
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    cx = W / 2
    walk, ph = state["walk"], state["phase"]
    step = abs(math.sin(ph))
    bob = -step * 12 * S * walk + math.sin(state["breath"] * math.pi) * 2 * S
    squash = 1 + (0.025 * (1 - step) - 0.012) * walk     # на касании ноги корпус чуть приседает
    d.ellipse([cx - 125 * S, H - 40 * S, cx + 125 * S, H - 8 * S], fill=(0, 20, 90, 100))
    hy = H - 205 * S + bob
    dirv = state["turn"]
    _leg(d, cx - 44 * S, hy, max(0.0, math.sin(ph)) * 34 * S * walk, dirv * max(0.0, math.sin(ph)) * walk)
    _leg(d, cx + 44 * S, hy, max(0.0, -math.sin(ph)) * 34 * S * walk, dirv * max(0.0, -math.sin(ph)) * walk)
    top = H - 400 * S + bob - (squash - 1) * 200 * S
    sh_y = top + 30 * S
    if state["pointL"] < 0.5:
        _arm(d, cx - 92 * S, sh_y, -1, state["armL"], 0, state["pointL"])
    if state["palmR"] < 0.5:
        _arm(d, cx + 92 * S, sh_y, 1, state["armR"], state["palmR"], 0)
    d.rounded_rectangle([cx - 108 * S, top, cx + 108 * S, hy + 30 * S], radius=int(60 * S), fill=NAVY_LT,
                        outline=NAVY, width=int(7 * S))
    img.alpha_composite(_soft_ellipse((W, H), [cx - 100 * S, top + 10 * S, cx - 20 * S, top + 120 * S],
                                      NAVY_HI + (90,), 22 * S))
    d = ImageDraw.Draw(img)
    d.polygon([(cx - 36 * S, top + 4 * S), (cx + 36 * S, top + 4 * S), (cx, top + 92 * S)], fill=SHIRT)
    for side in (-1, 1):
        d.polygon([(cx + side * 36 * S, top + 4 * S), (cx + side * 62 * S, top + 12 * S),
                   (cx + side * 8 * S, top + 104 * S)], fill=NAVY)
    sw = math.sin(ph) * 7 * S * walk                         # галстук качается на шаге
    d.polygon([(cx - 9 * S, top + 8 * S), (cx + 9 * S, top + 8 * S), (cx + 6 * S, top + 20 * S),
               (cx - 6 * S, top + 20 * S)], fill=GOLD_DK)
    d.polygon([(cx - 6 * S, top + 20 * S), (cx + 6 * S, top + 20 * S), (cx + 12 * S + sw, top + 72 * S),
               (cx + sw, top + 86 * S), (cx - 12 * S + sw, top + 72 * S)], fill=GOLD, outline=GOLD_DK)
    for k in range(2):
        y = top + (122 + 34 * k) * S
        d.ellipse([cx - 8 * S, y - 8 * S, cx + 8 * S, y + 8 * S], fill=NAVY_HI, outline=NAVY)
    px, py = cx + 62 * S, top + 46 * S
    d.line([px - 22 * S, py + 10 * S, px + 22 * S, py + 10 * S], fill=NAVY, width=int(4 * S))
    d.polygon([(px - 16 * S, py + 10 * S), (px - 7 * S, py - 6 * S), (px + 2 * S, py + 10 * S)], fill=GOLD)
    d.polygon([(px, py + 10 * S), (px + 9 * S, py - 7 * S), (px + 18 * S, py + 10 * S)], fill=GOLD_DK)
    d.line([cx - 104 * S, hy + 4 * S, cx + 104 * S, hy + 4 * S], fill=NAVY, width=int(5 * S))
    if state["pointL"] >= 0.5:
        _arm(d, cx - 92 * S, sh_y, -1, state["armL"], 0, state["pointL"])
    if state["palmR"] >= 0.5:
        _arm(d, cx + 92 * S, sh_y, 1, state["armR"], state["palmR"], 0)
    body = img.resize((FW, FH), Image.LANCZOS)
    if state["lean"]:
        body = body.rotate(-state["lean"], resample=Image.BICUBIC, center=(FW / 2, FH - 20))
    # голова (1x): поворот, кивок, наклон
    tq = round(max(-1, min(1, state["turn"])) * 2) / 2
    h = head(state["mouth"], state["shape"], state["blink"], 1 if state["brow"] > 0.5 else 0, tq, state["ear"])
    ang = state["tilt"] - state["lean"] * 0.6
    if ang:
        h = h.rotate(ang, resample=Image.BICUBIC, center=(HEAD_PX / 2, HEAD_PX * 0.85))
    hx = int(FW / 2 - HEAD_PX / 2 + state["lean"] * 2.2 + state["turn"] * 6)
    hy0 = int(top / S - HEAD_PX * 0.8 + state["nod"])
    body.alpha_composite(h, (hx, hy0))
    # контровой свет справа-сверху: светлая кайма по краю силуэта
    a = body.getchannel("A")
    inner = ImageChops.offset(a, -5, 4)
    rim = ImageChops.subtract(a, inner).filter(ImageFilter.GaussianBlur(1.5))
    rim = rim.point(lambda v: int(v * 0.55))
    rl = Image.new("RGBA", body.size, RIM + (0,)); rl.putalpha(rim)
    body.alpha_composite(rl)
    return body


if __name__ == "__main__":
    import sys
    base = dict(mouth=0, shape="wide", blink=False, brow=0, turn=0.0, ear=0, armL=12, armR=12, palmR=0, pointL=0,
                phase=0.0, walk=0.0, lean=0.0, tilt=0, nod=0, breath=0)
    poses = [dict(base),
             dict(base, mouth=3, turn=1.0, walk=1, phase=math.pi / 2, lean=4, armL=-6, armR=30),
             dict(base, mouth=2, shape="round", turn=-1.0, walk=1, phase=-math.pi / 2, lean=-4, armL=30, armR=-6),
             dict(base, mouth=3, shape="round", brow=1, armR=145, palmR=1, tilt=-4),
             dict(base, mouth=2, turn=-0.5, armL=138, pointL=1, nod=4)]
    sheet = Image.new("RGBA", (FW * len(poses), FH), (0, 71, 255, 255))
    for k, p in enumerate(poses):
        sheet.alpha_composite(figure(p), (k * FW, 0))
    sheet.convert("RGB").resize((FW * len(poses) // 2, FH // 2)).save(sys.argv[1])
