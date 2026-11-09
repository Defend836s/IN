# Автопубликация роликов

Публикует готовые ролики из `queue.yaml` в Telegram-канал, VK, Instagram
Reels и YouTube Shorts. За один запуск на каждую подключённую площадку уходит
следующий ролик, который туда ещё не публиковался. Что и куда ушло, пишется в
`state.json`, поэтому повторный запуск не дублирует посты.

```bash
python3 content/autopost/autopost.py status          # что подключено и что дальше
python3 content/autopost/autopost.py run --dry-run   # проба, ничего не публикует
python3 content/autopost/autopost.py run             # публикация
python3 content/autopost/autopost.py run --platform telegram --count 3
python3 content/autopost/build_queue.py              # добавить новые ролики в очередь
```

## Очередь

`queue.yaml` собирается из серий `kanal`, `motivaciya`, `pravda-ili-mif`,
`citaty`: серии чередуются, подпись берётся из сценария. Подписи можно
править руками, `build_queue.py` правки не затирает. Чтобы ролик не
публиковался, добавьте ему `skip: true`.

## Ключи

Ключи задаются переменными окружения облачной среды: меню среды в
заголовке сессии → Edit → Environment variables. **В чат ключи не
отправляйте.** Площадка без ключей просто пропускается.

Разрешите в той же среде (Network access → Allowed domains) домены своих
площадок.

### Telegram (проще всего, 5 минут)

1. В Telegram откройте @BotFather → `/newbot` → получите токен.
2. Добавьте бота в канал администратором с правом публикации.
3. Переменные: `TELEGRAM_BOT_TOKEN` = токен, `TELEGRAM_CHAT_ID` = `@имя_канала`
   (для закрытого канала - числовой id вида `-100...`).
4. Домен: `api.telegram.org`.

### VK

1. Нужен **пользовательский** токен администратора сообщества с правами
   `video` и `wall` (токен сообщества метод `video.save` не принимает).
2. Переменные: `VK_TOKEN`, `VK_GROUP_ID` (число, без минуса).
3. Домены: `api.vk.com` и домен загрузки, который VK выдаёт в ответе
   `video.save` (он меняется; при блокировке скрипт напишет его в ошибке).

### Instagram Reels

1. Аккаунт Instagram - профессиональный (Business или Creator) и связан со
   страницей Facebook.
2. На developers.facebook.com создайте приложение, добавьте Instagram Graph API,
   выдайте права `instagram_basic`, `instagram_content_publish`,
   `pages_show_list`, получите долгоживущий токен (60 дней).
3. Переменные: `IG_ACCESS_TOKEN`, `IG_USER_ID` (id Instagram-аккаунта).
4. Домены: `graph.facebook.com`, `rupload.facebook.com`.
5. Лимит API - 50 публикаций в сутки. Токен нужно продлевать раз в 60 дней.

### YouTube Shorts

1. В Google Cloud включите YouTube Data API v3, создайте OAuth-клиент
   (тип Desktop), получите refresh token со scope `youtube.upload`.
2. Переменные: `YT_CLIENT_ID`, `YT_CLIENT_SECRET`, `YT_REFRESH_TOKEN`,
   необязательно `YT_PRIVACY` (`public`, `unlisted`, `private`).
3. Домены: `oauth2.googleapis.com`, `www.googleapis.com`.
4. Важно: пока проект Google не прошёл аудит API, YouTube делает все
   загруженные через API ролики приватными. Аудит запрашивается в консоли
   Google Cloud.

## По расписанию

Запуск `run` можно поставить на расписание (запланированная задача Claude):
задача открывает новую сессию, запускает публикацию, коммитит обновлённый
`state.json` и пушит его, чтобы следующий запуск знал, что уже опубликовано.
