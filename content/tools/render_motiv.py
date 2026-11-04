"""Мотивационные Reels «Все курсы мира»: верх кадра свободен под баннер,
текст посередине, Профессор Глобус внизу. Две версии: чистая и с баннером."""
import os, sys
from PIL import Image
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import render_blue as rb
import render_avatar as ra

rb.SAY[:0] = [(r"\b20 минут\b", "двадцать минут"), (r"Просто 20\.", "Просто двадцать."),
              (r"\b100 попыток\b", "сто попыток"), (r"\b365 часов\b", "триста шестьдесят пять часов"),
              (r"\b9 полных\b", "девять полных"), (r"^9 недель", "Девять недель"),
              (r"\bв 25\b", "в двадцать пять"), (r"\bв 40\b", "в сорок")]
BANNER_ZONE = (250, 690)              # здесь встанет карточка баннера 1000x440
ra.TAG = None
ra.TEXT_TOP, ra.TEXT_BOT = 740, 1010
ra.BAR_Y = 712
SMALL = 470
ra.SP = {k: v.resize((SMALL, SMALL), Image.LANCZOS) for k, v in ra.SP.items()}
ra.CHAR_X, ra.CHAR_Y = 470 - SMALL // 2, 1440 - SMALL + 24

src, outdir, voice, piper, card = map(os.path.abspath, sys.argv[1:6])
titles = sys.argv[6].split("|")
os.makedirs(os.path.join(outdir, "чистые"), exist_ok=True)
os.makedirs(os.path.join(outdir, "с-баннером"), exist_ok=True)
banner = Image.new("RGBA", (1080, 1920), (0, 0, 0, 0))
banner.alpha_composite(Image.open(card).convert("RGBA"), (40, BANNER_ZONE[0]))
for i, title in enumerate(titles, 1):
    lines = [l.strip() for l in open(os.path.join(src, f"r{i:02d}.txt"), encoding="utf-8") if l.strip()]
    for kind, ov in (("чистые", None), ("с-баннером", banner)):
        ra.OVERLAY = ov
        total, _, durs = ra.render(lines, os.path.join(outdir, kind, f"{i:02d}-{title}.mp4"), piper, voice)
    warn = ([f"хук {durs[0]:.1f} с"] if durs[0] > 3.2 else []) + \
           [f"бит {k+1} {d:.1f} с" for k, d in enumerate(durs) if d > 4.2]
    print(f"{i:02d}-{title}  {total:.1f} с" + (f"  ! {', '.join(warn)}" if warn else ""), flush=True)
