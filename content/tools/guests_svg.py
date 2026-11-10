"""Гости Енота Сёмы - векторные персонажи в том же стиле (SVG 600x600, бюст, прозрачный фон).

    nika(mouth, eyes, brows, size)   - Лиса Ника: проверяет факты (очки, бирюзовый свитер, значок «✓»)
    borya(mouth, eyes, brows, size)  - Бобр Боря: практик, «проверено руками» (каска, клетчатая рубашка)

Параметры те же, что у semya_svg.svg():
    mouth: 0 улыбка | 1-3 открыт сильнее | 4 «о» | 5 ухмылка
    eyes:  open | blink | happy | side | sly        brows: normal | up | frown
Персонажи оригинальные, нарисованы для «Все курсы мира».
"""
from __future__ import annotations

GOLD, GOLD_DK, NAVY = "#ffcd3c", "#d9a10f", "#0a1a4f"
RIM = "#9cc2ff"


def _defs(fur: tuple[str, str, str], cream: tuple[str, str], iris: tuple[str, str, str],
          cloth: tuple[str, str], extra: str = "") -> str:
    return f"""<defs>
  <radialGradient id="fur" cx="38%" cy="30%" r="75%">
    <stop offset="0" stop-color="{fur[0]}"/><stop offset=".55" stop-color="{fur[1]}"/><stop offset="1" stop-color="{fur[2]}"/>
  </radialGradient>
  <radialGradient id="cream" cx="45%" cy="30%" r="75%">
    <stop offset="0" stop-color="{cream[0]}"/><stop offset="1" stop-color="{cream[1]}"/>
  </radialGradient>
  <radialGradient id="iris" cx="45%" cy="40%" r="60%">
    <stop offset="0" stop-color="{iris[0]}"/><stop offset=".6" stop-color="{iris[1]}"/><stop offset="1" stop-color="{iris[2]}"/>
  </radialGradient>
  <linearGradient id="cloth" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="{cloth[0]}"/><stop offset="1" stop-color="{cloth[1]}"/>
  </linearGradient>
  <linearGradient id="gold" x1="0" y1="0" x2="1" y2="1">
    <stop offset="0" stop-color="#fff0a8"/><stop offset=".45" stop-color="{GOLD}"/><stop offset="1" stop-color="{GOLD_DK}"/>
  </linearGradient>
  <linearGradient id="rim" x1="0" y1="0" x2="1" y2="0">
    <stop offset=".72" stop-color="{RIM}" stop-opacity="0"/><stop offset="1" stop-color="{RIM}" stop-opacity=".7"/>
  </linearGradient>
  <linearGradient id="nose" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="#3a3340"/><stop offset="1" stop-color="#0e0b12"/>
  </linearGradient>
  <filter id="soft" x="-30%" y="-30%" width="160%" height="160%"><feGaussianBlur stdDeviation="9"/></filter>
  {extra}
</defs>"""


def _wrap(body: str, size: int) -> str:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 600 600" width="{size}" height="{size}">'
            f"{body}</svg>")


# ------------------------------------------------------------------ общие части лица

def _eyes(kind: str, cy: float, r: float, lid: str, line: str = "#2a1a12") -> str:
    """Глаза как у Сёмы: open | blink | happy | side | sly. r - радиус белка по x."""
    out = []
    for cx in (238, 362):
        if kind == "blink":
            out.append(f'<path d="M{cx - r * .9} {cy + 2} Q{cx} {cy + 18} {cx + r * .9} {cy + 2}" stroke="{line}" '
                       'stroke-width="6" fill="none" stroke-linecap="round"/>')
            continue
        if kind == "happy":
            out.append(f'<path d="M{cx - r * .85} {cy + 10} Q{cx} {cy - 18} {cx + r * .85} {cy + 10}" '
                       f'stroke="{line}" stroke-width="7" fill="none" stroke-linecap="round"/>')
            continue
        dx = r * .3 if kind in ("side", "sly") else 0
        k = r / 31
        out.append(
            f'<ellipse cx="{cx}" cy="{cy}" rx="{r}" ry="{35 * k}" fill="#fdfcff" stroke="{line}" '
            'stroke-opacity=".35" stroke-width="2"/>'
            f'<circle cx="{cx + dx}" cy="{cy + 4 * k}" r="{22 * k}" fill="url(#iris)"/>'
            f'<circle cx="{cx + dx}" cy="{cy + 5 * k}" r="{11 * k}" fill="#120804"/>'
            f'<circle cx="{cx + dx - 8 * k}" cy="{cy - 5 * k}" r="{7.5 * k}" fill="#fff"/>'
            f'<circle cx="{cx + dx + 8 * k}" cy="{cy + 13 * k}" r="{3.2 * k}" fill="#fff" opacity=".9"/>')
        if kind == "sly":
            top = cy - 40 * k
            out.append(f'<path d="M{cx - r - 5} {top} L{cx + r + 5} {top} L{cx + r + 5} {cy - 2} '
                       f'Q{cx} {cy - 14} {cx - r - 5} {cy - 2} Z" fill="{lid}"/>'
                       f'<path d="M{cx - r} {cy - 3} Q{cx} {cy - 15} {cx + r} {cy - 3}" stroke="{line}" '
                       'stroke-width="4" fill="none" stroke-linecap="round"/>')
    return "".join(out)


def _brows(kind: str, y: float, color: str, rx: float = 34) -> str:
    dy = {"normal": 0, "up": -16, "frown": 10}[kind]
    angle = {"normal": -10, "up": -14, "frown": 16}[kind]
    return "".join(f'<ellipse cx="{cx}" cy="{y + dy}" rx="{rx}" ry="11" fill="{color}" '
                   f'transform="rotate({angle * s} {cx} {y + dy})"/>' for cx, s in ((236, 1), (364, -1)))


def _mouth(level: int, y: float, line: str) -> str:
    """Рот как у Сёмы, сдвинутый по высоте: y - уровень улыбки."""
    smile = (f'<path d="M268 {y} Q284 {y + 14} 300 {y} Q316 {y + 14} 332 {y}" stroke="{line}" stroke-width="5" '
             'fill="none" stroke-linecap="round" stroke-linejoin="round"/>')
    if level == 0:
        return smile
    if level == 5:
        return (f'<path d="M272 {y + 4} Q290 {y + 12} 306 {y + 4} Q322 {y - 4} 336 {y - 14}" stroke="{line}" '
                'stroke-width="5" fill="none" stroke-linecap="round"/>')
    rx, ry = {1: (17, 9), 2: (22, 16), 3: (29, 22), 4: (14, 17)}[level]
    cy = y + 8 + ry * 0.55
    tongue = (f'<ellipse cx="300" cy="{cy + ry * 0.45}" rx="{rx * 0.62}" ry="{ry * 0.45}" fill="#ec7f8b"/>'
              if level in (2, 3) else "")
    return (f'<ellipse cx="300" cy="{cy}" rx="{rx}" ry="{ry}" fill="#4a1420"/>{tongue}'
            + (smile if level != 4 else ""))


def _pin(x: float, y: float, inner: str) -> str:
    return (f'<g transform="translate({x} {y}) rotate(-8)">'
            '<circle r="34" fill="#000" opacity=".25" transform="translate(3 5)"/>'
            f'<circle r="34" fill="url(#gold)" stroke="{GOLD_DK}" stroke-width="3"/>'
            '<circle r="25" fill="none" stroke="#fff" stroke-opacity=".55" stroke-width="2"/>'
            f"{inner}</g>")


SHADOW = '<ellipse cx="300" cy="402" rx="130" ry="20" fill="#000" opacity=".35" filter="url(#soft)"/>'


# ------------------------------------------------------------------ Лиса Ника

FOX = ("#ffb066", "#f07a26", "#b8501a")
FOX_HEAD = ("M300 120 C380 120 440 160 456 220 C468 262 482 296 524 330 C474 342 444 352 420 364 "
            "C390 394 350 410 300 410 C250 410 210 394 180 364 C156 352 126 342 76 330 "
            "C118 296 132 262 144 220 C160 160 220 120 300 120 Z")
FOX_WHITE = ("M76 330 C130 302 196 292 246 304 C272 296 328 296 354 304 C404 292 470 302 524 330 "
             "C474 342 444 352 420 364 C390 394 350 410 300 410 C250 410 210 394 180 364 "
             "C156 352 126 342 76 330 Z")
FOX_TAIL = ("M186 600 C160 524 96 488 64 424 C30 356 52 290 104 280 C132 276 144 300 130 326 "
            "C114 360 132 404 172 444 C214 486 236 544 236 600 Z")


def _fox_ear(flip: bool) -> str:
    g = '<g transform="translate(600 0) scale(-1 1)">' if flip else "<g>"
    return (g + f'<path d="M166 222 L146 54 Q206 84 266 150 Z" fill="url(#fur)" stroke="{FOX[2]}" '
            'stroke-width="3" stroke-linejoin="round"/>'
            '<path d="M180 202 L166 94 Q206 114 244 154 Z" fill="#fde9d6"/>'
            '<path d="M146 54 L154 118 Q182 98 200 82 Q172 64 146 54 Z" fill="#3a2418"/></g>')


def _fox_body() -> str:
    sweater = "M96 600 C100 470 176 384 300 378 C424 384 500 470 504 600 Z"
    neck = "M206 420 C214 386 386 386 394 420 C394 446 206 446 206 420 Z"
    ribs = "".join(f'<path d="M{x} 392 L{x} 440" stroke="#0f5f63" stroke-width="5" stroke-linecap="round" '
                   'opacity=".55"/>' for x in range(226, 380, 22))
    check = ('<path d="M-13 1 L-4 11 L14 -10" stroke="#0a1a4f" stroke-width="7" fill="none" '
             'stroke-linecap="round" stroke-linejoin="round"/>')
    return (f'<path d="{sweater}" fill="url(#cloth)" stroke="#0b4a4d" stroke-width="3"/>'
            f'<path d="{sweater}" fill="url(#rim)" opacity=".6"/>'
            '<path d="M170 600 C175 540 190 500 214 470" stroke="#0b4a4d" stroke-width="6" fill="none" '
            'stroke-linecap="round" opacity=".5"/>'
            f'<path d="{neck}" fill="#23a3a3" stroke="#0b4a4d" stroke-width="3"/>{ribs}'
            + _pin(404, 500, check))


def _fox_tail() -> str:
    return (f'<path d="{FOX_TAIL}" fill="url(#fur)" stroke="{FOX[2]}" stroke-width="3"/>'
            '<g clip-path="url(#tailclip)"><ellipse cx="86" cy="300" rx="74" ry="62" fill="#fff6ec"/></g>'
            f'<path d="{FOX_TAIL}" fill="none" stroke="#fff" stroke-opacity=".22" stroke-width="10" '
            'transform="translate(6 -4)"/>')


def _glasses() -> str:
    lens = "".join(f'<circle cx="{cx}" cy="252" r="46" fill="#dff4ff" fill-opacity=".10" stroke="url(#gold)" '
                   'stroke-width="7"/>' for cx in (238, 362))
    return (lens + '<path d="M284 246 Q300 234 316 246" stroke="url(#gold)" stroke-width="7" fill="none" '
            'stroke-linecap="round"/>'
            '<path d="M200 226 Q214 214 230 212" stroke="#fff" stroke-opacity=".7" stroke-width="5" '
            'fill="none" stroke-linecap="round"/>')


def nika(mouth: int = 0, eyes: str = "open", brows: str = "normal", size: int = 1200) -> str:
    defs = _defs(FOX, ("#ffffff", "#f1e3d3"), ("#7fd36b", "#2e8b3a", "#123d18"), ("#2bb0ae", "#0f6e70"),
                 f'<clipPath id="tailclip"><path d="{FOX_TAIL}"/></clipPath>')
    head = (_fox_ear(False) + _fox_ear(True)
            + f'<path d="{FOX_HEAD}" fill="url(#fur)" stroke="{FOX[2]}" stroke-width="3" stroke-linejoin="round"/>'
            + f'<path d="{FOX_WHITE}" fill="url(#cream)"/>'
            + f'<path d="{FOX_HEAD}" fill="url(#rim)" opacity=".8"/>'
            + _brows(brows, 188, "#8a3a10")
            + '<ellipse cx="300" cy="326" rx="60" ry="44" fill="url(#cream)"/>'
            + _eyes(eyes, 252, 29, FOX[1])
            + _glasses()
            + _mouth(mouth, 330, "#3a2418")
            + '<path d="M282 296 C282 284 318 284 318 296 C318 308 306 316 300 316 C294 316 282 308 282 296 Z" '
              'fill="url(#nose)"/>'
            + '<ellipse cx="294" cy="292" rx="7" ry="3.5" fill="#fff" opacity=".7"/>')
    return _wrap(defs + _fox_tail() + _fox_body() + SHADOW + head, size)


# ------------------------------------------------------------------ Бобр Боря

BEAVER = ("#c08a5c", "#8f5a33", "#5e3518")
BEAVER_HEAD = ("M300 124 C392 124 456 182 462 262 C466 316 444 350 414 372 C384 396 344 408 300 408 "
               "C256 408 216 396 186 372 C156 350 134 316 138 262 C144 182 208 124 300 124 Z")
BEAVER_TAIL = "M420 600 C430 540 470 500 520 470 C566 442 596 452 598 486 C600 526 560 566 506 600 Z"
SHIRT = "M96 600 C100 470 176 384 300 378 C424 384 500 470 504 600 Z"


def _beaver_body() -> str:
    plaid = "".join(f'<rect x="{x}" y="370" width="16" height="240" fill="#7d1f16" opacity=".45"/>'
                    for x in range(110, 500, 56))
    plaid += "".join(f'<rect x="90" y="{y}" width="420" height="14" fill="#7d1f16" opacity=".4"/>'
                     for y in range(420, 600, 56))
    plaid += "".join(f'<rect x="{x}" y="370" width="4" height="240" fill="#ffd9a0" opacity=".35"/>'
                     for x in range(134, 500, 56))
    collar = ("M214 414 L300 470 L250 392 Z", "M386 414 L300 470 L350 392 Z")
    hammer = ('<g transform="rotate(40)"><rect x="-3.5" y="-8" width="7" height="28" rx="3" fill="#0a1a4f"/>'
              '<path d="M-16 -20 L10 -20 L16 -14 L10 -8 L-16 -8 Z" fill="#0a1a4f"/></g>')
    return (f'<path d="{SHIRT}" fill="url(#cloth)" stroke="#5a140e" stroke-width="3"/>'
            f'<g clip-path="url(#shirtclip)">{plaid}</g>'
            f'<path d="{SHIRT}" fill="url(#rim)" opacity=".5"/>'
            + "".join(f'<path d="{c}" fill="#e8564a" stroke="#5a140e" stroke-width="3" stroke-linejoin="round"/>'
                      for c in collar)
            + "".join(f'<circle cx="300" cy="{y}" r="6" fill="#f3e3c8"/>' for y in (500, 548))
            + _pin(404, 500, hammer))


def _beaver_tail() -> str:
    hatch = "".join(f'<path d="M{x} 440 L{x + 120} 620" stroke="#2e1a0c" stroke-width="3" opacity=".45"/>'
                    f'<path d="M{x + 120} 440 L{x} 620" stroke="#2e1a0c" stroke-width="3" opacity=".45"/>'
                    for x in range(400, 620, 26))
    return (f'<path d="{BEAVER_TAIL}" fill="#4a3426" stroke="#2e1a0c" stroke-width="3"/>'
            f'<g clip-path="url(#tailclip)">{hatch}</g>')


def _hard_hat() -> str:
    return ('<path d="M154 182 C154 104 222 64 300 64 C378 64 446 104 446 182 Z" fill="url(#gold)" '
            f'stroke="{GOLD_DK}" stroke-width="3"/>'
            '<path d="M286 66 C290 60 310 60 314 66 L318 180 L282 180 Z" fill="#fff3b8" opacity=".7"/>'
            '<path d="M196 110 C214 88 240 76 262 72" stroke="#fff" stroke-opacity=".7" stroke-width="8" '
            'fill="none" stroke-linecap="round"/>'
            f'<rect x="120" y="170" width="360" height="28" rx="14" fill="url(#gold)" stroke="{GOLD_DK}" '
            'stroke-width="3"/>'
            '<rect x="200" y="128" width="64" height="30" rx="8" fill="#0a1a4f"/>'
            '<text x="232" y="150" text-anchor="middle" font-family="Inter" font-weight="900" font-size="20" '
            'fill="#ffcd3c">0 ₽</text>')


def borya(mouth: int = 0, eyes: str = "open", brows: str = "normal", size: int = 1200) -> str:
    defs = _defs(BEAVER, ("#f0d7b4", "#cfa77c"), ("#c47a2c", "#7a3f14", "#3b1d08"), ("#d24a3a", "#9a2a1e"),
                 f'<clipPath id="tailclip"><path d="{BEAVER_TAIL}"/></clipPath>'
                 f'<clipPath id="shirtclip"><path d="{SHIRT}"/></clipPath>')
    ears = "".join(f'<circle cx="{cx}" cy="196" r="34" fill="url(#fur)" stroke="{BEAVER[2]}" stroke-width="3"/>'
                   f'<circle cx="{cx}" cy="198" r="17" fill="#4a2a14"/>' for cx in (160, 440))
    cheeks = "".join(f'<ellipse cx="{cx}" cy="338" rx="64" ry="52" fill="url(#fur)"/>' for cx in (214, 386))
    teeth = ('<rect x="284" y="341" width="15" height="30" rx="4" fill="#fffdf6" stroke="#cdbfa6" stroke-width="2"/>'
             '<rect x="301" y="341" width="15" height="30" rx="4" fill="#fffdf6" stroke="#cdbfa6" stroke-width="2"/>')
    head = (ears
            + f'<path d="{BEAVER_HEAD}" fill="url(#fur)" stroke="{BEAVER[2]}" stroke-width="3"/>'
            + cheeks
            + f'<path d="{BEAVER_HEAD}" fill="url(#rim)" opacity=".7"/>'
            + '<ellipse cx="300" cy="336" rx="80" ry="56" fill="url(#cream)"/>'
            + _brows(brows, 214, "#3e2210", 30)
            + _eyes(eyes, 262, 26, BEAVER[1])
            + _mouth(mouth, 338, "#3a2010")
            + teeth
            + '<ellipse cx="300" cy="306" rx="30" ry="19" fill="url(#nose)"/>'
            + '<ellipse cx="290" cy="300" rx="10" ry="4.5" fill="#fff" opacity=".6"/>'
            + "".join(f'<circle cx="{x}" cy="{y}" r="3" fill="#5e3518" opacity=".7"/>'
                      for x, y in ((254, 330), (246, 344), (346, 330), (354, 344)))
            + _hard_hat())
    return _wrap(defs + _beaver_tail() + _beaver_body() + SHADOW + head, size)
