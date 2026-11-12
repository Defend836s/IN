"""Енот Сёма - векторный маскот «Все курсы мира» (SVG).

Сёма находит бесплатное там, где другие платят: чёрная маска на глазах,
полосатый хвост, карандаш за ухом, худи цвета бренда со значком «0 ₽».

svg(mouth, eyes, brows, view) возвращает SVG 600x600 (бюст, прозрачный фон):
    mouth: 0 закрыт (улыбка) | 1 чуть открыт | 2 открыт | 3 широко | 4 «о» | 5 ухмылка
    eyes:  open | blink | happy (^^) | side (смотрит в сторону) | sly (полуприкрыты)
    brows: normal | up (удивление, акцент) | frown (хитрый прищур)
"""
from __future__ import annotations

NAVY = "#0a1a4f"
NAVY_LT = "#1d3a8f"
GOLD = "#ffcd3c"
GOLD_DK = "#d9a10f"
FUR_LT, FUR, FUR_DK = "#c9ccd6", "#9a9eab", "#6c7080"
MASK, MASK_LT = "#1b1d26", "#3a3d4a"
CREAM = "#f6f3ee"
RIM = "#9cc2ff"

DEFS = f"""
<defs>
  <radialGradient id="fur" cx="38%" cy="30%" r="75%">
    <stop offset="0" stop-color="{FUR_LT}"/><stop offset=".55" stop-color="{FUR}"/><stop offset="1" stop-color="{FUR_DK}"/>
  </radialGradient>
  <radialGradient id="mask" cx="50%" cy="35%" r="70%">
    <stop offset="0" stop-color="{MASK_LT}"/><stop offset="1" stop-color="{MASK}"/>
  </radialGradient>
  <radialGradient id="cream" cx="45%" cy="30%" r="75%">
    <stop offset="0" stop-color="#ffffff"/><stop offset="1" stop-color="#e3ddd3"/>
  </radialGradient>
  <radialGradient id="iris" cx="45%" cy="40%" r="60%">
    <stop offset="0" stop-color="#c47a2c"/><stop offset=".6" stop-color="#7a3f14"/><stop offset="1" stop-color="#3b1d08"/>
  </radialGradient>
  <linearGradient id="hoodie" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="{NAVY_LT}"/><stop offset="1" stop-color="{NAVY}"/>
  </linearGradient>
  <linearGradient id="gold" x1="0" y1="0" x2="1" y2="1">
    <stop offset="0" stop-color="#fff0a8"/><stop offset=".45" stop-color="{GOLD}"/><stop offset="1" stop-color="{GOLD_DK}"/>
  </linearGradient>
  <linearGradient id="rim" x1="0" y1="0" x2="1" y2="0">
    <stop offset=".72" stop-color="{RIM}" stop-opacity="0"/><stop offset="1" stop-color="{RIM}" stop-opacity=".75"/>
  </linearGradient>
  <linearGradient id="nose" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="#3a3340"/><stop offset="1" stop-color="#0e0b12"/>
  </linearGradient>
  <filter id="soft" x="-30%" y="-30%" width="160%" height="160%"><feGaussianBlur stdDeviation="9"/></filter>
  <filter id="soft2" x="-30%" y="-30%" width="160%" height="160%"><feGaussianBlur stdDeviation="4"/></filter>
  <clipPath id="tailclip"><path d="{{TAIL}}"/></clipPath>
  <clipPath id="headclip"><path d="{{HEAD}}"/></clipPath>
</defs>"""

HEAD = ("M300 108 C385 108 448 150 466 214 L522 262 L470 276 L512 318 L454 326 "
        "C428 378 368 404 300 404 C232 404 172 378 146 326 L88 318 L130 276 L78 262 "
        "L134 214 C152 150 215 108 300 108 Z")
TAIL = ("M432 600 C440 525 478 478 524 448 C572 416 594 368 578 318 C566 282 534 266 502 276 "
        "C480 284 474 306 488 320 C508 338 500 366 470 388 C420 426 386 500 380 600 Z")


def _ear(cx: float, flip: int) -> str:
    s = flip
    outer = (f"M{cx - 62 * s} 196 C{cx - 72 * s} 140 {cx - 40 * s} 92 {cx + 6 * s} 82 "
             f"C{cx + 30 * s} 112 {cx + 44 * s} 152 {cx + 40 * s} 190 Z")
    inner = (f"M{cx - 42 * s} 186 C{cx - 48 * s} 146 {cx - 26 * s} 114 {cx + 2 * s} 106 "
             f"C{cx + 18 * s} 128 {cx + 26 * s} 156 {cx + 22 * s} 184 Z")
    return (f'<path d="{outer}" fill="url(#fur)" stroke="{FUR_DK}" stroke-width="3"/>'
            f'<path d="{inner}" fill="{MASK}"/>'
            f'<path d="{inner}" fill="#e7a7a0" transform="translate({cx} 150) scale(.62) translate({-cx} -150)"/>')


def _pencil() -> str:
    return ('<g transform="translate(150 150) rotate(-28) scale(.85)">'
            '<rect x="-12" y="-120" width="24" height="200" rx="4" fill="#ffc531"/>'
            '<rect x="-12" y="-120" width="8" height="200" fill="#ffdb6e"/>'
            '<rect x="4" y="-120" width="8" height="200" fill="#e9a812"/>'
            '<rect x="-12" y="-148" width="24" height="30" rx="5" fill="#f08a9a"/>'
            '<rect x="-13" y="-124" width="26" height="12" fill="#c9ccd6"/>'
            '<path d="M-12 80 L0 118 L12 80 Z" fill="#f2d3a8"/>'
            '<path d="M-4 105 L0 118 L4 105 Z" fill="#2b2b33"/></g>')


def _tail() -> str:
    bands = "".join(f'<rect x="380" y="{y}" width="260" height="34" fill="{MASK}" '
                    f'transform="rotate(-42 500 460)"/>' for y in range(300, 660, 62))
    return (f'<path d="{TAIL}" fill="url(#fur)" stroke="{FUR_DK}" stroke-width="3"/>'
            f'<g clip-path="url(#tailclip)">{bands}'
            f'<path d="{TAIL}" fill="none" stroke="#fff" stroke-opacity=".25" stroke-width="10" '
            f'transform="translate(-6 -4)"/></g>')


def _body() -> str:
    hoodie = "M96 600 C100 470 176 384 300 378 C424 384 500 470 504 600 Z"
    hood = ("M150 452 C140 398 200 352 300 350 C400 352 460 398 450 452 "
            "C420 420 360 404 300 404 C240 404 180 420 150 452 Z")
    strings = "".join(
        f'<path d="M{x} 418 C{x + d} 462 {x - d} 492 {x} 528" stroke="{CREAM}" stroke-width="7" '
        f'fill="none" stroke-linecap="round"/><rect x="{x - 6}" y="524" width="12" height="20" rx="4" fill="{GOLD}"/>'
        for x, d in ((262, -8), (338, 8)))
    pin = ('<g transform="translate(404 500) rotate(-8)">'
           '<circle r="34" fill="#000" opacity=".25" transform="translate(3 5)"/>'
           f'<circle r="34" fill="url(#gold)" stroke="{GOLD_DK}" stroke-width="3"/>'
           '<circle r="25" fill="none" stroke="#fff" stroke-opacity=".55" stroke-width="2"/>'
           f'<text x="0" y="11" text-anchor="middle" font-family="Inter" font-weight="900" '
           f'font-size="25" fill="{NAVY}">0 ₽</text></g>')
    folds = ('<path d="M170 600 C175 540 190 500 214 470" stroke="#07123a" stroke-width="6" fill="none" '
             'stroke-linecap="round" opacity=".55"/>'
             '<path d="M430 600 C425 540 410 500 386 470" stroke="#07123a" stroke-width="6" fill="none" '
             'stroke-linecap="round" opacity=".4"/>')
    return (f'<path d="{hoodie}" fill="url(#hoodie)" stroke="#06103a" stroke-width="3"/>'
            f'<path d="{hoodie}" fill="url(#rim)" opacity=".7"/>{folds}'
            f'<path d="{hood}" fill="{NAVY_LT}" stroke="#06103a" stroke-width="3"/>'
            f'<path d="M190 430 C230 404 370 404 410 430 C380 452 220 452 190 430 Z" fill="#06103a"/>'
            f'{strings}{pin}')


def _brows(kind: str) -> str:
    dy = {"normal": 0, "up": -16, "frown": 10}[kind]
    angle = {"normal": -10, "up": -14, "frown": 16}[kind]   # для frown внутренние концы опущены
    out = []
    for cx, s in ((236, 1), (364, -1)):
        out.append(f'<ellipse cx="{cx}" cy="{194 + dy}" rx="40" ry="17" fill="url(#cream)" '
                   f'transform="rotate({angle * s} {cx} {194 + dy})"/>')
    return "".join(out)


def _eyes(kind: str) -> str:
    out = []
    for cx in (238, 362):
        if kind == "blink":
            out.append(f'<path d="M{cx - 28} 252 Q{cx} 268 {cx + 28} 252" stroke="#e9e6f0" stroke-width="6" '
                       'fill="none" stroke-linecap="round"/>')
            continue
        if kind == "happy":
            out.append(f'<path d="M{cx - 26} 260 Q{cx} 232 {cx + 26} 260" stroke="#e9e6f0" stroke-width="7" '
                       'fill="none" stroke-linecap="round"/>')
            continue
        dx = 9 if kind in ("side", "sly") else 0
        out.append(
            f'<ellipse cx="{cx}" cy="250" rx="31" ry="35" fill="#fdfcff"/>'
            f'<ellipse cx="{cx}" cy="242" rx="31" ry="26" fill="#000" opacity=".07"/>'
            f'<circle cx="{cx + dx}" cy="254" r="22" fill="url(#iris)"/>'
            f'<circle cx="{cx + dx}" cy="255" r="11" fill="#120804"/>'
            f'<circle cx="{cx + dx - 8}" cy="245" r="7.5" fill="#fff"/>'
            f'<circle cx="{cx + dx + 8}" cy="263" r="3.2" fill="#fff" opacity=".9"/>')
        if kind == "sly":  # полуприкрытые веки
            out.append(f'<path d="M{cx - 36} 210 L{cx + 36} 210 L{cx + 36} 248 Q{cx} 236 {cx - 36} 248 Z" '
                       f'fill="{MASK}"/><path d="M{cx - 32} 247 Q{cx} 235 {cx + 32} 247" stroke="#e9e6f0" '
                       'stroke-width="4" fill="none" stroke-linecap="round" opacity=".8"/>')
    return "".join(out)


def _mouth(level: int) -> str:
    smile = (f'<path d="M268 322 Q284 336 300 322 Q316 336 332 322" stroke="{MASK}" stroke-width="5" '
             'fill="none" stroke-linecap="round" stroke-linejoin="round"/>')
    if level == 0:
        return smile
    if level == 5:  # ухмылка
        return (f'<path d="M272 326 Q290 334 306 326 Q322 318 336 308" stroke="{MASK}" stroke-width="5" '
                'fill="none" stroke-linecap="round"/>')
    rx, ry = {1: (17, 9), 2: (22, 16), 3: (29, 22), 4: (14, 17)}[level]
    cy = 330 + ry * 0.55
    tongue = (f'<ellipse cx="300" cy="{cy + ry * 0.45}" rx="{rx * 0.62}" ry="{ry * 0.45}" fill="#ec7f8b"/>'
              if level in (2, 3) else "")
    teeth = (f'<rect x="{300 - rx * 0.5}" y="{cy - ry + 1}" width="{rx}" height="7" rx="3" fill="#fff"/>'
             if level == 3 else "")
    return (f'<ellipse cx="300" cy="{cy}" rx="{rx}" ry="{ry}" fill="#4a1420"/>{tongue}{teeth}'
            + (smile if level != 4 else ""))


def svg(mouth: int = 0, eyes: str = "open", brows: str = "normal", size: int = 1200) -> str:
    defs = DEFS.replace("{TAIL}", TAIL).replace("{HEAD}", HEAD)
    head = (
        _ear(176, 1) + _ear(424, -1)
        + f'<path d="{HEAD}" fill="url(#fur)" stroke="{FUR_DK}" stroke-width="3" stroke-linejoin="round"/>'
        + (f'<path d="M262 122 C262 92 284 74 300 64 C296 86 304 96 318 84 C320 100 314 114 336 120 '
           f'C318 130 282 132 262 122 Z" fill="url(#fur)" stroke="{FUR_DK}" stroke-width="3" stroke-linejoin="round"/>')
        + '<g clip-path="url(#headclip)">'
        # тёмная полоса по лбу
        + f'<path d="M300 104 C318 150 316 190 300 236 C284 190 282 150 300 104 Z" fill="{FUR_DK}" opacity=".85"/>'
        # светлые щёки
        + '<path d="M150 300 C190 280 240 300 262 340 C230 392 170 380 146 330 Z" fill="url(#cream)"/>'
        + '<path d="M450 300 C410 280 360 300 338 340 C370 392 430 380 454 330 Z" fill="url(#cream)"/>'
        # маска
        + ('<path d="M136 252 C160 200 250 198 300 238 C350 198 440 200 464 252 C470 294 430 314 386 308 '
           'C350 304 322 290 300 272 C278 290 250 304 214 308 C170 314 130 294 136 252 Z" fill="url(#mask)"/>')
        + f'<path d="{HEAD}" fill="url(#rim)"/>'
        + "</g>"
        + _brows(brows)
        # морда
        + '<ellipse cx="300" cy="318" rx="70" ry="52" fill="url(#cream)"/>'
        + '<ellipse cx="300" cy="300" rx="40" ry="18" fill="#fff" opacity=".6" filter="url(#soft2)"/>'
        + _eyes(eyes)
        + _mouth(mouth)
        + '<path d="M276 286 C276 272 324 272 324 286 C324 300 308 310 300 310 C292 310 276 300 276 286 Z" fill="url(#nose)"/>'
        + '<ellipse cx="292" cy="282" rx="9" ry="4.5" fill="#fff" opacity=".7"/>'
    )
    shadow = '<ellipse cx="300" cy="400" rx="130" ry="20" fill="#000" opacity=".35" filter="url(#soft)"/>'
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 600 600" width="{size}" height="{size}">'
            f"{defs}{_tail()}{_body()}{shadow}{_pencil()}{head}</svg>")
