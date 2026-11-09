"""Голос Енота Сёмы: молодой, живой, чуть мультяшный, но разборчивый.

Основа - мужской голос офлайн-модели Vosk TTS (vosk-model-tts-ru-0.9-multi,
скачивается один раз с alphacephei.com). Поверх - сдвиг тона (rubberband),
лёгкий подъём темпа и «эфирная» обработка: плотность, присутствие, громкость
под соцсети.

    python3 content/tools/semya_voice.py "Привет, я Сёма!" out.wav [вариант]
    python3 content/tools/semya_voice.py --samples content/characters/semya/voice

Вариант задаётся переменной SEMYA_VOICE (по умолчанию - DEFAULT).
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

# speaker: номер диктора в модели (3 и 4 - мужские, 118 и 139 Гц)
# pitch: во сколько раз выше тон; formant: shifted - мультяшнее, preserved - естественнее
VARIANTS = {
    "ozornoy": dict(speaker=4, pitch=1.19, formant="shifted", tempo=1.04, noise=0.85,
                    title="Озорной: молодой парень, чуть мультяшный (+3 полутона)"),
    "multyashny": dict(speaker=4, pitch=1.33, formant="shifted", tempo=1.07, noise=0.9,
                       title="Мультяшный: ярче и выше, как герой анимации (+5 полутонов)"),
    "druzhelyubny": dict(speaker=3, pitch=1.26, formant="preserved", tempo=1.03, noise=0.8,
                         title="Дружелюбный: естественный тембр, выше обычного (+4 полутона)"),
    "podrostok": dict(speaker=2, pitch=1.12, formant="shifted", tempo=1.05, noise=0.85,
                      title="Подросток: звонкий, лёгкий (+2 полутона)"),
}
DEFAULT = "ozornoy"

CHAIN = ("highpass=f=80,equalizer=f=220:t=q:w=1:g=1.5,equalizer=f=3200:t=q:w=1:g=3,"
         "equalizer=f=9000:t=q:w=0.9:g=2,deesser=i=0.3,"
         "acompressor=threshold=-24dB:ratio=2.5:attack=8:release=120:makeup=2,"
         "acompressor=threshold=-12dB:ratio=4:attack=2:release=60:makeup=1.5,"
         "loudnorm=I=-14:TP=-1.5:LRA=8,alimiter=limit=0.89:level=false,aresample=44100")

_SYNTH = None


def variant(name: str | None = None) -> dict:
    name = name or os.environ.get("SEMYA_VOICE", DEFAULT)
    if name not in VARIANTS:
        raise SystemExit(f"нет варианта голоса {name}: {', '.join(VARIANTS)}")
    return VARIANTS[name]


def fx(name: str | None = None) -> str:
    """Цепочка ffmpeg: тон, темп и обработка. Подставляется после склейки фраз."""
    v = variant(name)
    return (f"rubberband=pitch={v['pitch']}:formant={v['formant']}:transients=smooth,"
            f"atempo={v['tempo']},{CHAIN}")


def synth_raw(text: str, path: str, name: str | None = None, length: float = 1.0) -> tuple[float, int]:
    """Сырой синтез без обработки (для покадровой склейки в рендерерах). Возвращает (длина, sr).

    Длина возвращается уже с учётом будущего ускорения tempo из fx(), чтобы тайминг кадров совпал."""
    global _SYNTH
    v = variant(name)
    if _SYNTH is None:
        from vosk_tts import Model, Synth
        model = os.environ.get("VOSK_MODEL_PATH")
        _SYNTH = Synth(Model(model_path=model) if model else Model(model_name="vosk-model-tts-ru-0.9-multi"))
    text = re.sub(r"([аеёиоуыэюяАЕЁИОУЫЭЮЯ])́", r"+\1", text)
    _SYNTH.synth(text, path, speaker_id=v["speaker"], noise_level=v["noise"],
                 duration_noise_level=0.7, speech_rate=1 / length)
    with wave.open(path) as w:
        return w.getnframes() / w.getframerate() / v["tempo"], w.getframerate()


def phrase(text: str, path: str, length: float = 1.0, name: str | None = None) -> tuple[float, int]:
    """Одна фраза для рендереров видео: тон, темп и тембр уже применены, громкость - нет
    (её выравнивает общая цепочка после склейки). Пишет WAV в path, возвращает (длина, sr)."""
    v = variant(name)
    raw = path + ".raw.wav"
    synth_raw(text, raw, name, length)
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", raw, "-af",
                    f"rubberband=pitch={v['pitch']}:formant={v['formant']}:transients=smooth,"
                    f"atempo={v['tempo']},{CHAIN.split(',acompressor')[0]}", "-ac", "1", path], check=True)
    os.unlink(raw)
    with wave.open(path) as w:
        return w.getnframes() / w.getframerate(), w.getframerate()


MASTER = CHAIN[CHAIN.index("acompressor"):]   # плотность и громкость после склейки фраз


def say(text: str, out: str, name: str | None = None) -> str:
    """Готовая реплика Сёмы в WAV 44.1 кГц."""
    with tempfile.TemporaryDirectory() as tmp:
        raw = os.path.join(tmp, "raw.wav")
        synth_raw(text, raw, name)
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", raw, "-af", fx(name), "-ac", "1", out],
                       check=True)
    return out


SAMPLE = ("Привет, я Сёма! Я енот, и я нахожу бесплатное там, где другие платят. "
          "Курс за шестьдесят тысяч? Не спеши. Программа курса лежит в открытом доступе. "
          "Сохрани и учись сам!")


def samples(folder: str) -> list[Path]:
    out_dir = Path(folder)
    out_dir.mkdir(parents=True, exist_ok=True)
    made = []
    for name in VARIANTS:
        wav = out_dir / f"{name}.wav"
        say(SAMPLE, str(wav), name)
        m4a = out_dir / f"голос-{name}.m4a"
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(wav), "-c:a", "aac", "-b:a", "128k",
                        str(m4a)], check=True)
        wav.unlink()
        made.append(m4a)
    return made


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "--samples":
        for p in samples(sys.argv[2]):
            print(p)
    elif len(sys.argv) >= 3:
        print(say(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None))
    else:
        print(__doc__)
