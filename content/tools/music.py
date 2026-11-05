"""Фоновая музыка-подложка, сгенерированная с нуля (без чужих треков и прав).
Мягкий пэд + бас + пиано-арпеджио, ля минор, Am-F-C-G, 92 BPM."""
import numpy as np

NOTES = {"A2": 110.0, "F2": 87.31, "C3": 130.81, "G2": 98.0}
CHORDS = [("A2", [220.0, 261.63, 329.63]), ("F2", [174.61, 220.0, 261.63]),
          ("C3", [196.0, 261.63, 329.63]), ("G2", [196.0, 246.94, 293.66])]


def _env(n, sr, a, r):
    e = np.ones(n)
    na, nr = int(a * sr), int(r * sr)
    e[:na] = np.linspace(0, 1, na)
    e[-nr:] *= np.linspace(1, 0, nr)
    return e


def _lp(x, cutoff, sr):
    a = np.exp(-2 * np.pi * cutoff / sr)
    y = np.empty_like(x); acc = 0.0
    for i in range(len(x)):            # однополюсный НЧ-фильтр
        acc = (1 - a) * x[i] + a * acc; y[i] = acc
    return y


def bed(seconds, sr=44100, bpm=92):
    beat = 60 / bpm
    bar = beat * 4
    n = int(seconds * sr)
    out = np.zeros(n + int(bar * sr) * 3)
    t_all = 0.0; k = 0
    while t_all < seconds + bar:
        root, tones = CHORDS[k % 4]
        L = int(bar * sr); t = np.arange(L) / sr; i0 = int(t_all * sr)
        pad = sum(np.sin(2 * np.pi * f * t) + 0.35 * np.sin(2 * np.pi * f * 2.003 * t)
                  + 0.2 * np.sin(2 * np.pi * f * 0.997 * t) for f in tones)
        pad *= _env(L, sr, 0.6, 0.6) * 0.10
        bass = np.sin(2 * np.pi * NOTES[root] * t) * _env(L, sr, 0.05, 0.3) * 0.22
        seg = pad + bass
        for j in range(8):              # арпеджио восьмыми
            f = tones[[0, 1, 2, 1, 0, 2, 1, 2][j]] * 2
            m = int(beat / 2 * sr); tt = np.arange(m) / sr
            pl = (np.sin(2 * np.pi * f * tt) + 0.3 * np.sin(2 * np.pi * 2 * f * tt)) * np.exp(-tt * 6) * 0.07
            s = j * m; seg[s:s + m] += pl[:max(0, min(m, L - s))]
        out[i0:i0 + L] += seg
        t_all += bar; k += 1
    out = _lp(out[:n], 3500, sr)
    fade = int(0.8 * sr)
    out[:fade] *= np.linspace(0, 1, fade); out[-fade:] *= np.linspace(1, 0, fade)
    return out / (np.max(np.abs(out)) + 1e-9) * 0.5
