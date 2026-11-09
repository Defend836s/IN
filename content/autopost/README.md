# Автопубликация роликов

Публикует готовые ролики из `queue.yaml` в Telegram, VK, Одноклассники,
Instagram Reels, Facebook Reels, Threads, YouTube Shorts, TikTok, Pinterest и
Rutube. За один запуск на каждую подключённую площадку уходит
следующий ролик, который туда ещё не публиковался. Что и куда ушло, пишется в
`state.json`, поэтому повторный запуск не дублирует посты.

```bash
python3 content/autopost/autopost.py status          # что подключено и что дальше
python3 content/autopost/autopost.py run --dry-run   # проба, ничего не публикует
python3 content/autopost/autopost.py run             # публикация
python3 content/autopost/autopost.py run --platform telegram --count 3
python3 content/autopost/autopost.py run --kind carousel --kind image   # только карусели и картинки
python3 content/autopost/build_queue.py              # добавить новые ролики в очередь
```

## Очередь

`queue.yaml` собирается из серий `kanal`, `motivaciya`, `pravda-ili-mif`,
`citaty`: серии чередуются, подпись берётся из сценария. Подписи можно
править руками, `build_queue.py` правки не затирает. Чтобы ролик не
публиковался, добавьте ему `skip: true`.

## Карусели и картинки

Карусели (2-10 слайдов) и посты-картинки рисует `content/tools/render_carousel.py`
по `content/carousels/<слаг>/spec.yaml` (формат описан в docstring). После рендера
`build_queue.py` добавляет их в очередь как `images: [...]`.

| Площадка | Ролики | Картинка | Карусель |
|---|---|---|---|
| Telegram | да | да | да (альбом до 10) |
| VK | да | да | да (до 10 фото в посте) |
| Одноклассники | да | да | да |
| Instagram | да | да* | да* (до 10) |
| Facebook | да | да | да (пост с несколькими фото) |
| Threads | да* | да* | да* |
| Pinterest | да | да | да (до 5) |
| YouTube, TikTok, Rutube | да | нет | нет |

\* площадка забирает файл по ссылке, нужен `PUBLIC_MEDIA_BASE_URL` (см. Threads).

Ролики и картинки идут в одной очереди. Чтобы в день выходил и ролик, и карусель,
запускайте два раза: `run --kind video` и `run --kind carousel --kind image`.

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

### VK (VK Видео)

Ролики уходят в **VK Видео** сообщества официальным методом `video.save` (с постом на
стене). **VK Клипы** через API не публикуются: метода для клипов в официальной схеме
VK API нет, а неофициальный `shortVideo.create` может сломаться и стоить токена.
Вертикальный ролик в VK Видео смотрится нормально; в Клипы его можно переложить вручную.

1. Нужен **пользовательский** токен администратора сообщества с правами
   `video` и `wall` (токен сообщества метод `video.save` не принимает).
2. Переменные: `VK_TOKEN`, `VK_GROUP_ID` (число, без минуса).
3. Домены: `api.vk.com`, `pu.vk.com` (загрузка фото) и домен загрузки видео,
   который VK выдаёт в ответе `video.save` (он меняется; при блокировке скрипт
   напишет его в ошибке).

### Instagram Reels

1. Аккаунт Instagram - профессиональный (Business или Creator) и связан со
   страницей Facebook.
2. На developers.facebook.com создайте приложение, добавьте Instagram Graph API,
   выдайте права `instagram_basic`, `instagram_content_publish`,
   `pages_show_list`, получите долгоживущий токен (60 дней).
3. Переменные: `IG_ACCESS_TOKEN`, `IG_USER_ID` (id Instagram-аккаунта).
4. Домены: `graph.facebook.com`, `rupload.facebook.com`.
5. Лимит API - 50 публикаций в сутки. Токен нужно продлевать раз в 60 дней.
6. Для картинок и каруселей нужен ещё `PUBLIC_MEDIA_BASE_URL`: Instagram берёт
   фото только по публичной ссылке (ролики загружаются файлом).

### YouTube Shorts

1. В Google Cloud включите YouTube Data API v3, создайте OAuth-клиент
   (тип Desktop), получите refresh token со scope `youtube.upload`.
2. Переменные: `YT_CLIENT_ID`, `YT_CLIENT_SECRET`, `YT_REFRESH_TOKEN`,
   необязательно `YT_PRIVACY` (`public`, `unlisted`, `private`).
3. Домены: `oauth2.googleapis.com`, `www.googleapis.com`.
4. Важно: пока проект Google не прошёл аудит API, YouTube делает все
   загруженные через API ролики приватными. Аудит запрашивается в консоли
   Google Cloud.

### Одноклассники

1. На ok.ru/devaccess получите права разработчика, создайте приложение,
   запросите у поддержки ОК права `VIDEO_CONTENT`, `GROUP_CONTENT`, `LONG_ACCESS_TOKEN`.
2. Получите вечный токен администратора группы.
3. Переменные: `OK_ACCESS_TOKEN`, `OK_APP_KEY` (публичный ключ приложения),
   `OK_APP_SECRET` (секретный ключ), `OK_GROUP_ID`.
4. Домены: `api.ok.ru` и домен загрузки из ответа `video.getUploadUrl`
   (меняется, при блокировке скрипт напишет его в ошибке).

### Facebook Reels (страница)

1. То же приложение Meta, что для Instagram, права `pages_manage_posts`,
   `pages_read_engagement`, `pages_show_list`.
2. Переменные: `FB_PAGE_TOKEN` (токен страницы), `FB_PAGE_ID`.
3. Домены: `graph.facebook.com`, `rupload.facebook.com`.

### Threads

1. В приложении Meta добавьте Threads API, права `threads_basic`,
   `threads_content_publish`, получите долгоживущий токен (60 дней).
2. Переменные: `THREADS_ACCESS_TOKEN`, `THREADS_USER_ID`, `PUBLIC_MEDIA_BASE_URL`.
3. Домен: `graph.threads.net`.
4. Threads (и картинки Instagram) не принимают файл, а скачивают его по ссылке. Поэтому ролики
   должны лежать по публичному адресу: `PUBLIC_MEDIA_BASE_URL` - адрес папки
   `content/`, например `https://raw.githubusercontent.com/<владелец>/<репо>/<ветка>/content`
   для публичного репозитория или свой хостинг.

### TikTok

1. На developers.tiktok.com создайте приложение, подключите Content Posting API
   с Direct Post, scope `video.publish`, получите refresh token (действует год).
2. Переменные: `TIKTOK_CLIENT_KEY`, `TIKTOK_CLIENT_SECRET`, `TIKTOK_REFRESH_TOKEN`,
   `TIKTOK_PRIVACY` (по умолчанию `SELF_ONLY`).
3. Домены: `open.tiktokapis.com`, `open-upload.tiktokapis.com`.
4. Важно: пока приложение не прошло аудит TikTok, публиковать можно только
   с `SELF_ONLY` (видно только вам). После аудита: `PUBLIC_TO_EVERYONE`.

### Pinterest

1. На developers.pinterest.com создайте приложение, scope `pins:write`,
   `boards:read`, получите токен.
2. Переменные: `PINTEREST_TOKEN`, `PINTEREST_BOARD_ID`, необязательно
   `PINTEREST_LINK` (куда ведёт пин, например ваш Telegram-канал).
3. Домены: `api.pinterest.com`, `pinterest-media-upload.s3-accelerate.amazonaws.com`.

### Rutube

Открытой документации API загрузки у Rutube нет (старый официальный клиент закрыт,
в открытых источниках API описан как партнёрский). Проверено напрямую: адрес
`studio.rutube.ru/api/video/` работает, принимает POST и ждёт ключ `Authorization: Bearer`.

1. Ключ: запросите API-доступ для своего канала в поддержке Rutube (rutube.ru/support,
   «Студия» -> обращение) - выдают токен для загрузки по ссылке.
2. Переменные: `RUTUBE_TOKEN`, `PUBLIC_MEDIA_BASE_URL` (Rutube забирает ролик по
   публичной ссылке, как Threads), необязательно `RUTUBE_CATEGORY`,
   `RUTUBE_AUTH_SCHEME` (по умолчанию `Bearer`).
3. Домен: `studio.rutube.ru`.
4. Первая публикация - проверочная: формат ответа и поле «шортс» (`is_short`) не
   подтверждены документацией; при ошибке модуль покажет ответ сервера, поправим по нему.
5. Без API ролики в Rutube загружаются вручную через studio.rutube.ru - это
   надёжный запасной вариант.

### Дзен

API публикации нет, но работает **импорт RSS с вашего сайта**: `content/site/build.py`
собирает сайт-витрину и ленту `dzen.xml`, подробности - `content/site/README.md`.

### Чего нет и почему

- **X (Twitter)** - загрузка видео через API платная.
- **Likee, Yappy, «Нельзяграм»-клоны** - нет публичного API.

Для них остаётся ручная публикация или браузерная автоматизация, которая
нарушает правила этих площадок и ведёт к блокировке аккаунта.

## По расписанию

Запуск `run` можно поставить на расписание (запланированная задача Claude):
задача открывает новую сессию, запускает публикацию, коммитит обновлённый
`state.json` и пушит его, чтобы следующий запуск знал, что уже опубликовано.
