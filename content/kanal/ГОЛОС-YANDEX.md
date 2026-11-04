# Голос Yandex SpeechKit для «Все курсы мира»

## 1. Ключ в Yandex Cloud (5 минут)

1. https://console.yandex.cloud → создать платёжный аккаунт и каталог.
2. Сервисные аккаунты → Создать → роль `ai.speechkit-tts.user`.
3. Открыть аккаунт → Создать новый ключ → **API-ключ**. Скопировать.

## 2. Настройки облачной среды Claude

Меню облачной среды в заголовке сессии → Edit:

- **Network access** → Allowed domains: `tts.api.cloud.yandex.net`
  (галочку Allow package managers оставить).
- **Network secrets** (или переменная окружения): `YANDEX_API_KEY` = ваш ключ.
  Ключ в чат не отправлять.

## 3. Новая сессия

Открыть новую сессию на этом репозитории и написать:
«Переозвучь ролики голосом Yandex: content/tools/pereozvuchka-yandex.sh».
