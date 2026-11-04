#!/usr/bin/env bash
# Переозвучка роликов «Все курсы мира» голосом Vosk TTS (бесплатно, офлайн).
# Нужен доступ к alphacephei.com (оттуда один раз качается модель).
# Диктор: VOSK_SPEAKER (номер голоса в модели), по умолчанию 2.
set -euo pipefail
cd "$(dirname "$0")/../.."
python3 -m venv /tmp/vk-venv >/dev/null 2>&1 || true
/tmp/vk-venv/bin/pip install -q pillow numpy vosk-tts
export TTS_BACKEND=vosk
PY=/tmp/vk-venv/bin/python
$PY content/tools/render_myth.py content/pravda-ili-mif/scripts content/pravda-ili-mif - - \
  "после-30-поздно|без-диплома|20-минут-мало|забудешь-половину"
$PY content/tools/render_quotes.py content/citaty/scripts content/citaty - - \
  "чехов-по-каплям|пушкин-чтение|прутков-необъятное|достоевский-свобода"
