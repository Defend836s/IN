#!/usr/bin/env bash
# Переозвучка 10 роликов «Все курсы мира» и баннера голосом Yandex SpeechKit.
# Нужно: переменная YANDEX_API_KEY и доступ к tts.api.cloud.yandex.net.
# Голос: YANDEX_VOICE (по умолчанию filipp; ещё мужские: ermil, zahar).
set -euo pipefail
cd "$(dirname "$0")/../.."
: "${YANDEX_API_KEY:?Нет переменной YANDEX_API_KEY}"
python3 -m venv /tmp/vk-venv >/dev/null 2>&1 || true
/tmp/vk-venv/bin/pip install -q pillow numpy
export TTS_BACKEND=yandex
T="ты-не-обязан-платить|профессия-не-за-3-года|бросишь-курс|сколько-потерял|навык-за-вечер|курс-против-40-минут|план-на-30-дней|вода-в-курсах|потратил-впустую|через-12-месяцев"
/tmp/vk-venv/bin/python content/tools/render_avatar.py content/kanal/scripts content/kanal/videos - - "$T"
/tmp/vk-venv/bin/python content/tools/render_banner.py content/kanal/banner - -
