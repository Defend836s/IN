"""Голос Vosk «цельной речью» (вариант D): блок фраз озвучивается одним куском,
границы фраз находятся по паузам в записи. Нужна модель vosk-model-tts-ru-0.9-multi
(путь в VOSK_MODEL_PATH или скачивание с alphacephei.com)."""
import os, re, wave
import numpy as np

SPEAKER = int(os.environ.get("VOSK_SPEAKER", "3"))          # male_0
NOISE, DNOISE, RATE = 0.8, 0.7, 1.0                           # вариант D: живой
BROADCAST = ("highpass=f=65,equalizer=f=120:t=q:w=0.9:g=2.5,equalizer=f=380:t=q:w=1.2:g=-2,"
             "equalizer=f=2800:t=q:w=1:g=2.5,equalizer=f=10000:t=q:w=0.8:g=1.5,deesser=i=0.35,"
             "acompressor=threshold=-26dB:ratio=2:attack=10:release=150:makeup=2,"
             "acompressor=threshold=-14dB:ratio=4:attack=2:release=60:makeup=2,"
             "aecho=0.92:0.9:19|31:0.06|0.04,loudnorm=I=-14:TP=-1.5:LRA=7,aresample=44100")
_S = None


def synth():
    global _S
    if _S is None:
        from vosk_tts import Model, Synth
        p = os.environ.get("VOSK_MODEL_PATH")
        _S = Synth(Model(model_path=p) if p else Model(model_name="vosk-model-tts-ru-0.9-multi"))
    return _S


def plus(text):
    return re.sub(r"([аеёиоуыэюяАЕЁИОУЫЭЮЯ])́", r"+\1", text)


def _read(path):
    with wave.open(path) as w:
        return np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768, w.getframerate()


def say(text, path):
    synth().synth(plus(text), path, speaker_id=SPEAKER, noise_level=NOISE,
                  duration_noise_level=DNOISE, speech_rate=RATE)
    return _read(path)


def chunk(lines, work, tag):
    """Озвучить фразы одним куском. Возвращает (сигнал, sr, [(начало, конец) каждой фразы])."""
    x, sr = say(" ".join(lines), os.path.join(work, f"{tag}.wav"))
    if len(lines) == 1:
        nz = np.nonzero(np.abs(x) > 0.01)[0]
        return x, sr, [(0.0, (nz[-1] + 1) / sr if len(nz) else len(x) / sr)]
    est = []
    for k, l in enumerate(lines):                     # длины по отдельности - только для оценки границ
        y, _ = say(l, os.path.join(work, f"{tag}_{k}.wav")); est.append(len(y))
    hop = int(sr * 0.01)
    env = np.array([np.sqrt(np.mean(x[i:i + hop] ** 2)) for i in range(0, len(x) - hop, hop)])
    quiet = env < max(0.004, np.percentile(env, 30) * 0.6)
    cum, total = np.cumsum(est)[:-1], sum(est)
    bounds, prev = [], 0
    for c in cum:
        guess = int(len(env) * c / total)
        lo, hi = max(prev + 5, guess - 70), min(len(env) - 5, guess + 70)
        best, best_score = guess, -1e9
        i = lo
        while i < hi:                                 # самая длинная тишина рядом с оценкой
            if quiet[i]:
                j = i
                while j < len(quiet) and quiet[j]:
                    j += 1
                score = (j - i) - abs((i + j) // 2 - guess) * 0.15
                if score > best_score:
                    best, best_score = (i + j) // 2, score
                i = j
            else:
                i += 1
        bounds.append(best); prev = best
    edges = [0] + [b * hop for b in bounds] + [len(x)]
    return x, sr, [(edges[k] / sr, edges[k + 1] / sr) for k in range(len(lines))]
