import os, subprocess, sys, wave
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import render_blue as rb
from music import bed

PIPER = os.path.abspath("tts-venv/bin/piper")
V = lambda n: os.path.abspath(f"voices/vits-piper-ru_RU-{n}-medium/ru_RU-{n}-medium.onnx")
LINES = ["Правда или миф?", "После тридцати тебе уже поздно учиться.", "Как думаешь?", "Миф.",
         "Мозг учится всю жизнь.", "Взрослым не хватает времени, а не способностей."]
PRO_FX = ("highpass=f=75,asetrate={sr}*0.98,aresample={sr},atempo=1.0204,"
          "equalizer=f=150:t=q:w=1:g=2,equalizer=f=3000:t=q:w=1.2:g=3,equalizer=f=7500:t=q:w=1:g=-1.5,"
          "deesser=i=0.4,acompressor=threshold=-22dB:ratio=3:attack=4:release=90:makeup=4,"
          "aecho=0.9:0.85:23|37:0.10|0.06,loudnorm=I=-14:TP=-1.5:LRA=8,aresample=44100")
OUT = "voice-samples2"; os.makedirs(OUT, exist_ok=True)


def synth(voice, noise, noise_w, length, path):
    parts = []
    for k, l in enumerate(LINES):
        p = f"{OUT}/_{k}.wav"
        subprocess.run([PIPER, "-m", voice, "-f", p, "--length-scale", str(length), "--noise-scale", str(noise),
                        "--noise-w-scale", str(noise_w), "--sentence-silence", "0.1"],
                       input=rb.spoken(l).encode(), check=True, capture_output=True)
        with wave.open(p) as w:
            sr = w.getframerate(); parts.append(np.frombuffer(w.readframes(w.getnframes()), np.int16))
        parts.append(np.zeros(int(0.24 * sr), np.int16))
    with wave.open(path, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr); w.writeframes(np.concatenate(parts).tobytes())
    return sr


def fx(src, dst, chain, sr):
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", src, "-af", chain.format(sr=sr), "-ar", "44100", dst],
                   check=True)


def with_music(voice_wav, dst):
    with wave.open(voice_wav) as w:
        dur = w.getnframes() / w.getframerate()
    m = bed(dur + 0.5)
    mp = voice_wav + ".music.wav"
    with wave.open(mp, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(44100); w.writeframes((m * 32767).astype(np.int16).tobytes())
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", voice_wav, "-i", mp, "-filter_complex",
                    "[1:a]volume=0.32[m];[m][0:a]sidechaincompress=threshold=0.05:ratio=6:attack=20:release=300[d];"
                    "[0:a][d]amix=inputs=2:duration=first:normalize=0,loudnorm=I=-14:TP=-1.5",
                    "-ar", "44100", dst], check=True)


variants = {
    "1-сейчас-denis": ("denis", 0.55, 0.6, 0.95, rb.VOICE_FX),
    "2-denis-живой-студия": ("denis", 0.667, 0.8, 1.0, PRO_FX),
    "3-ruslan-живой-студия": ("ruslan", 0.667, 0.8, 1.0, PRO_FX),
}
for name, (v, ns, nw, ln, chain) in variants.items():
    raw = f"{OUT}/{name}.raw.wav"; sr = synth(V(v), ns, nw, ln, raw)
    fx(raw, f"{OUT}/{name}.wav", chain, sr)
for name in ["2-denis-живой-студия", "3-ruslan-живой-студия"]:
    with_music(f"{OUT}/{name}.wav", f"{OUT}/{name}-с-музыкой.wav")
for f in sorted(os.listdir(OUT)):
    if f.endswith(".wav") and ".raw" not in f and not f.startswith("_") and ".music" not in f:
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", f"{OUT}/{f}", "-c:a", "aac", "-b:a", "160k",
                        f"{OUT}/проба-{f[:-4]}.m4a"], check=True)
print("\n".join(sorted(x for x in os.listdir(OUT) if x.endswith(".m4a"))))
