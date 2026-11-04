"""Показывает, куда синтезатор ставит ударение: ударная гласная - ЗАГЛАВНАЯ."""
import re, sys, unicodedata
from piper.phonemize_espeak import EspeakPhonemizer
P = EspeakPhonemizer()
IPA_V = set("aɑoeiuyɪʌɛəɐæʊɵɨɯ")
CYR_V = set("аеёиоуыэюя")

def mark(word):
    ipa = "".join(P.phonemize("ru", word)[0])
    ipa = unicodedata.normalize("NFC", ipa)
    if "ˈ" not in ipa:
        return word, ipa
    k = sum(1 for c in ipa[:ipa.index("ˈ")] if c in IPA_V)
    plain = word.replace("́", "")
    out, n = [], 0
    for c in plain:
        if c.lower() in CYR_V:
            out.append(c.upper() if n == k else c)
            n += 1
        else:
            out.append(c)
    return "".join(out), ipa

if __name__ == "__main__":
    words = []
    for f in sys.argv[1:]:
        for w in re.findall(r"[А-Яа-яЁё́-]+", open(f, encoding="utf-8").read()):
            w = w.strip("-").lower()
            if sum(c in CYR_V for c in w) >= 2 and w not in words:
                words.append(w)
    print("  ".join(mark(w)[0] for w in words))
