"""Модули площадок для autopost.py.

Каждая функция publish_<площадка>(item, cfg) публикует один ролик и
возвращает id поста на площадке или бросает PublishError. cfg - словарь
переменных окружения из PLATFORMS[площадка][1].
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

import requests

TIMEOUT = 120


class PublishError(RuntimeError):
    pass


@dataclass(frozen=True)
class Item:
    id: str
    kind: str                # video | image | carousel
    files: tuple[Path, ...]  # абсолютные пути
    rels: tuple[str, ...]    # пути относительно content/ (для публичных ссылок)
    title: str
    caption: str

    @property
    def video(self) -> Path:
        return self.files[0]


def env(*names: str) -> dict[str, str] | None:
    values = {n: os.environ.get(n, "").strip() for n in names}
    return values if all(values.values()) else None


def check(resp: requests.Response, what: str) -> dict:
    try:
        data = resp.json()
    except ValueError:
        data = {}
    if resp.status_code >= 400 or (isinstance(data, dict) and data.get("error")):
        detail = data.get("error") if isinstance(data, dict) else None
        raise PublishError(f"{what}: HTTP {resp.status_code} {detail or resp.text[:300]}")
    return data


# ---------------------------------------------------------------- Telegram

def publish_telegram(item: Item, cfg: dict[str, str]) -> str:
    url = f"https://api.telegram.org/bot{cfg['TELEGRAM_BOT_TOKEN']}/sendVideo"
    with item.video.open("rb") as fh:
        resp = requests.post(
            url,
            data={
                "chat_id": cfg["TELEGRAM_CHAT_ID"],
                "caption": item.caption[:1024],
                "supports_streaming": "true",
            },
            files={"video": (item.video.name, fh, "video/mp4")},
            timeout=TIMEOUT,
        )
    data = check(resp, "Telegram sendVideo")
    if not data.get("ok"):
        raise PublishError(f"Telegram: {data.get('description')}")
    return str(data["result"]["message_id"])


# ---------------------------------------------------------------- VK

VK_API = "https://api.vk.com/method"
VK_VERSION = "5.199"


def publish_vk(item: Item, cfg: dict[str, str]) -> str:
    resp = requests.post(
        f"{VK_API}/video.save",
        data={
            "access_token": cfg["VK_TOKEN"],
            "v": VK_VERSION,
            "group_id": cfg["VK_GROUP_ID"].lstrip("-"),
            "name": item.title[:128],
            "description": item.caption,
            "wallpost": 1,
        },
        timeout=TIMEOUT,
    )
    data = check(resp, "VK video.save")
    if "error" in data or "response" not in data:
        raise PublishError(f"VK video.save: {data.get('error')}")
    upload_url = data["response"]["upload_url"]
    with item.video.open("rb") as fh:
        up = requests.post(upload_url, files={"video_file": (item.video.name, fh, "video/mp4")}, timeout=TIMEOUT)
    result = check(up, "VK upload")
    return str(result.get("video_id") or data["response"].get("video_id"))


# ---------------------------------------------------------------- Instagram

GRAPH = "https://graph.facebook.com/v21.0"


def publish_instagram(item: Item, cfg: dict[str, str]) -> str:
    token, user = cfg["IG_ACCESS_TOKEN"], cfg["IG_USER_ID"]
    auth = {"Authorization": f"OAuth {token}"}
    created = check(
        requests.post(
            f"{GRAPH}/{user}/media",
            headers=auth,
            data={"media_type": "REELS", "upload_type": "resumable", "caption": item.caption[:2200]},
            timeout=TIMEOUT,
        ),
        "Instagram media",
    )
    container = created["id"]
    upload_uri = created.get("uri") or f"https://rupload.facebook.com/ig-api-upload/v21.0/{container}"
    body = item.video.read_bytes()
    check(
        requests.post(
            upload_uri,
            headers={**auth, "offset": "0", "file_size": str(len(body))},
            data=body,
            timeout=TIMEOUT,
        ),
        "Instagram upload",
    )
    for _ in range(60):
        status = check(
            requests.get(f"{GRAPH}/{container}", headers=auth, params={"fields": "status_code,status"}, timeout=TIMEOUT),
            "Instagram status",
        )
        code = status.get("status_code")
        if code == "FINISHED":
            break
        if code in ("ERROR", "EXPIRED"):
            raise PublishError(f"Instagram обработка: {status.get('status')}")
        time.sleep(10)
    else:
        raise PublishError("Instagram: ролик не обработался за 10 минут")
    done = check(
        requests.post(f"{GRAPH}/{user}/media_publish", headers=auth, data={"creation_id": container}, timeout=TIMEOUT),
        "Instagram media_publish",
    )
    return str(done["id"])


# ---------------------------------------------------------------- YouTube

def publish_youtube(item: Item, cfg: dict[str, str]) -> str:
    tok = check(
        requests.post(
            "https://oauth2.googleapis.com/token",
            data={
                "client_id": cfg["YT_CLIENT_ID"],
                "client_secret": cfg["YT_CLIENT_SECRET"],
                "refresh_token": cfg["YT_REFRESH_TOKEN"],
                "grant_type": "refresh_token",
            },
            timeout=TIMEOUT,
        ),
        "YouTube token",
    )
    auth = {"Authorization": f"Bearer {tok['access_token']}"}
    title = item.title[:90].rstrip() + " #Shorts"
    meta = {
        "snippet": {"title": title, "description": item.caption, "categoryId": "27"},
        "status": {"privacyStatus": os.environ.get("YT_PRIVACY", "public"), "selfDeclaredMadeForKids": False},
    }
    init = requests.post(
        "https://www.googleapis.com/upload/youtube/v3/videos",
        params={"uploadType": "resumable", "part": "snippet,status"},
        headers={**auth, "Content-Type": "application/json; charset=UTF-8", "X-Upload-Content-Type": "video/mp4"},
        data=json.dumps(meta),
        timeout=TIMEOUT,
    )
    check(init, "YouTube init")
    location = init.headers.get("Location")
    if not location:
        raise PublishError("YouTube: нет адреса для загрузки")
    with item.video.open("rb") as fh:
        up = requests.put(location, headers={**auth, "Content-Type": "video/mp4"}, data=fh, timeout=TIMEOUT * 5)
    return str(check(up, "YouTube upload")["id"])


# ---------------------------------------------------------------- общий публичный адрес ролика

def public_url(rel: str, cfg: dict[str, str]) -> str:
    """Threads, Rutube и картинки Instagram забираются по ссылке, а не загрузкой файла.

    PUBLIC_MEDIA_BASE_URL - адрес, по которому лежит папка content/
    (например raw-ссылка публичного репозитория или свой хостинг).
    """
    base = cfg["PUBLIC_MEDIA_BASE_URL"].rstrip("/")
    return f"{base}/{quote(rel)}"


def wait_status(url: str, params: dict, headers: dict, field: str, ok: str, bad: tuple[str, ...], what: str) -> None:
    for _ in range(60):
        status = check(requests.get(url, params=params, headers=headers, timeout=TIMEOUT), what)
        code = status.get(field)
        if code == ok:
            return
        if code in bad:
            raise PublishError(f"{what}: {status}")
        time.sleep(10)
    raise PublishError(f"{what}: ролик не обработался за 10 минут")


# ---------------------------------------------------------------- Threads

def threads_text(caption: str) -> str:
    """Threads принимает одну тему (хэштег) на пост: оставляем первую, остальные убираем."""
    tags = re.findall(r"(?<!\w)#[\wё]+", caption, flags=re.I)
    for extra in tags[1:]:
        caption = re.sub(r"\s*" + re.escape(extra) + r"(?!\w)", "", caption)
    return caption.strip()

THREADS = "https://graph.threads.net/v1.0"


def publish_threads(item: Item, cfg: dict[str, str]) -> str:
    token, user = cfg["THREADS_ACCESS_TOKEN"], cfg["THREADS_USER_ID"]
    auth = {"Authorization": f"Bearer {token}"}
    created = check(
        requests.post(
            f"{THREADS}/{user}/threads",
            headers=auth,
            data={"media_type": "VIDEO", "video_url": public_url(item.rels[0], cfg), "text": threads_text(item.caption)[:500]},
            timeout=TIMEOUT,
        ),
        "Threads create",
    )
    container = created["id"]
    wait_status(f"{THREADS}/{container}", {"fields": "status,error_message"}, auth,
                "status", "FINISHED", ("ERROR", "EXPIRED"), "Threads status")
    done = check(
        requests.post(f"{THREADS}/{user}/threads_publish", headers=auth, data={"creation_id": container}, timeout=TIMEOUT),
        "Threads publish",
    )
    return str(done["id"])


# ---------------------------------------------------------------- Facebook Reels (страница)

def publish_facebook(item: Item, cfg: dict[str, str]) -> str:
    token, page = cfg["FB_PAGE_TOKEN"], cfg["FB_PAGE_ID"]
    auth = {"Authorization": f"OAuth {token}"}
    start = check(
        requests.post(f"{GRAPH}/{page}/video_reels", headers=auth, data={"upload_phase": "start"}, timeout=TIMEOUT),
        "Facebook start",
    )
    video_id = start["video_id"]
    upload_url = start.get("upload_url") or f"https://rupload.facebook.com/video-upload/v21.0/{video_id}"
    body = item.video.read_bytes()
    check(
        requests.post(upload_url, headers={**auth, "offset": "0", "file_size": str(len(body))}, data=body, timeout=TIMEOUT),
        "Facebook upload",
    )
    check(
        requests.post(
            f"{GRAPH}/{page}/video_reels",
            headers=auth,
            data={"upload_phase": "finish", "video_id": video_id, "video_state": "PUBLISHED", "description": item.caption},
            timeout=TIMEOUT,
        ),
        "Facebook finish",
    )
    return str(video_id)


# ---------------------------------------------------------------- Одноклассники

OK_API = "https://api.ok.ru/fb.do"


def ok_call(method: str, cfg: dict[str, str], **params: str) -> dict:
    """Вызов API ОК с подписью: sig = md5(параметры по алфавиту + md5(token + secret))."""
    token = cfg["OK_ACCESS_TOKEN"]
    params = {"application_key": cfg["OK_APP_KEY"], "method": method, "format": "json", **params}
    secret = hashlib.md5((token + cfg["OK_APP_SECRET"]).encode()).hexdigest()
    raw = "".join(f"{k}={params[k]}" for k in sorted(params)) + secret
    params["sig"] = hashlib.md5(raw.encode()).hexdigest()
    params["access_token"] = token
    data = check(requests.post(OK_API, data=params, timeout=TIMEOUT), f"OK {method}")
    if isinstance(data, dict) and data.get("error_code"):
        raise PublishError(f"OK {method}: {data.get('error_code')} {data.get('error_msg')}")
    return data


def publish_ok(item: Item, cfg: dict[str, str]) -> str:
    gid = cfg["OK_GROUP_ID"]
    size = item.video.stat().st_size
    up = ok_call("video.getUploadUrl", cfg, gid=gid, file_name=item.video.name, file_size=str(size))
    with item.video.open("rb") as fh:
        check(requests.post(up["upload_url"], files={"data": (item.video.name, fh, "video/mp4")}, timeout=TIMEOUT),
              "OK upload")
    vid = str(up["video_id"])
    ok_call("video.update", cfg, vid=vid, title=item.title[:200], description=item.caption)
    attachment = {"media": [{"type": "text", "text": item.caption}, {"type": "movie", "list": [{"id": vid}]}]}
    post = ok_call("mediatopic.post", cfg, gid=gid, type="GROUP_THEME",
                   attachment=json.dumps(attachment, ensure_ascii=False))
    return str(post if not isinstance(post, dict) else post.get("id", vid))


# ---------------------------------------------------------------- TikTok

TIKTOK = "https://open.tiktokapis.com/v2"


def publish_tiktok(item: Item, cfg: dict[str, str]) -> str:
    tok = check(
        requests.post(
            f"{TIKTOK}/oauth/token/",
            data={
                "client_key": cfg["TIKTOK_CLIENT_KEY"],
                "client_secret": cfg["TIKTOK_CLIENT_SECRET"],
                "grant_type": "refresh_token",
                "refresh_token": cfg["TIKTOK_REFRESH_TOKEN"],
            },
            timeout=TIMEOUT,
        ),
        "TikTok token",
    )
    auth = {"Authorization": f"Bearer {tok['access_token']}", "Content-Type": "application/json; charset=UTF-8"}
    size = item.video.stat().st_size
    init = check(
        requests.post(
            f"{TIKTOK}/post/publish/video/init/",
            headers=auth,
            data=json.dumps({
                "post_info": {
                    "title": item.caption[:2200],
                    "privacy_level": os.environ.get("TIKTOK_PRIVACY", "SELF_ONLY"),
                },
                "source_info": {"source": "FILE_UPLOAD", "video_size": size, "chunk_size": size, "total_chunk_count": 1},
            }),
            timeout=TIMEOUT,
        ),
        "TikTok init",
    )
    data = init["data"]
    with item.video.open("rb") as fh:
        up = requests.put(
            data["upload_url"],
            headers={"Content-Type": "video/mp4", "Content-Length": str(size), "Content-Range": f"bytes 0-{size - 1}/{size}"},
            data=fh,
            timeout=TIMEOUT * 5,
        )
    if up.status_code >= 400:
        raise PublishError(f"TikTok upload: HTTP {up.status_code} {up.text[:300]}")
    return str(data["publish_id"])


# ---------------------------------------------------------------- Pinterest

PINTEREST = "https://api.pinterest.com/v5"


def publish_pinterest(item: Item, cfg: dict[str, str]) -> str:
    auth = {"Authorization": f"Bearer {cfg['PINTEREST_TOKEN']}"}
    media = check(requests.post(f"{PINTEREST}/media", headers=auth, json={"media_type": "video"}, timeout=TIMEOUT),
                  "Pinterest media")
    with item.video.open("rb") as fh:
        up = requests.post(media["upload_url"], data=media["upload_parameters"],
                           files={"file": (item.video.name, fh, "video/mp4")}, timeout=TIMEOUT * 5)
    if up.status_code >= 400:
        raise PublishError(f"Pinterest upload: HTTP {up.status_code} {up.text[:300]}")
    wait_status(f"{PINTEREST}/media/{media['media_id']}", {}, auth, "status", "succeeded", ("failed",), "Pinterest status")
    pin = {
        "board_id": cfg["PINTEREST_BOARD_ID"],
        "title": item.title[:100],
        "description": item.caption[:800],
        "media_source": {"source_type": "video_id", "media_id": media["media_id"], "cover_image_key_frame_time": 1},
    }
    if os.environ.get("PINTEREST_LINK"):
        pin["link"] = os.environ["PINTEREST_LINK"]
    return str(check(requests.post(f"{PINTEREST}/pins", headers=auth, json=pin, timeout=TIMEOUT), "Pinterest pin")["id"])


# ---------------------------------------------------------------- Rutube

def publish_rutube(item: Item, cfg: dict[str, str]) -> str:
    resp = requests.post(
        "https://studio.rutube.ru/api/video/",
        # сервер отвечает WWW-Authenticate: Bearer (проверено 10.11.2026); схему можно сменить RUTUBE_AUTH_SCHEME
        headers={"Authorization": f"{os.environ.get('RUTUBE_AUTH_SCHEME', 'Bearer')} {cfg['RUTUBE_TOKEN']}"},
        json={
            "url": public_url(item.rels[0], cfg),
            "title": item.title[:100],
            "description": item.caption,
            "is_short": True,
            "category_id": int(os.environ.get("RUTUBE_CATEGORY", "13")),
        },
        timeout=TIMEOUT,
    )
    return str(check(resp, "Rutube").get("video_id"))


# ================================================================ картинки и карусели
#
# image-функции принимают Item с kind image (1 файл) или carousel (2-10 файлов).


def _images(item: Item) -> list[tuple[Path, str]]:
    return list(zip(item.files, item.rels))


# ---------------------------------------------------------------- Telegram

def publish_telegram_images(item: Item, cfg: dict[str, str]) -> str:
    base = f"https://api.telegram.org/bot{cfg['TELEGRAM_BOT_TOKEN']}"
    chat = cfg["TELEGRAM_CHAT_ID"]
    if len(item.files) == 1:
        with item.files[0].open("rb") as fh:
            resp = requests.post(f"{base}/sendPhoto", data={"chat_id": chat, "caption": item.caption[:1024]},
                                 files={"photo": (item.files[0].name, fh, "image/png")}, timeout=TIMEOUT)
        data = check(resp, "Telegram sendPhoto")
        return str(data["result"]["message_id"])
    media, files = [], {}
    for i, path in enumerate(item.files):
        entry = {"type": "photo", "media": f"attach://f{i}"}
        if i == 0:
            entry["caption"] = item.caption[:1024]
        media.append(entry)
        files[f"f{i}"] = (path.name, path.read_bytes(), "image/png")
    resp = requests.post(f"{base}/sendMediaGroup", data={"chat_id": chat, "media": json.dumps(media, ensure_ascii=False)},
                         files=files, timeout=TIMEOUT)
    data = check(resp, "Telegram sendMediaGroup")
    if not data.get("ok"):
        raise PublishError(f"Telegram: {data.get('description')}")
    return str(data["result"][0]["message_id"])


# ---------------------------------------------------------------- Instagram и Threads (по ссылке)

def _meta_carousel(api: str, user: str, auth: dict, item: Item, cfg: dict[str, str],
                   text_field: str, text_limit: int, publish_path: str, what: str) -> str:
    def container(**fields) -> str:
        return check(requests.post(f"{api}/{user}/{'threads' if 'threads' in api else 'media'}",
                                   headers=auth, data=fields, timeout=TIMEOUT), what)["id"]

    status_field = "status" if "threads" in api else "status_code"
    pics = _images(item)
    if len(pics) == 1:
        extra = {"media_type": "IMAGE"} if "threads" in api else {}
        cid = container(image_url=public_url(pics[0][1], cfg), **{text_field: item.caption[:text_limit]}, **extra)
    else:
        kids = []
        for _, rel in pics:
            extra = {"media_type": "IMAGE"} if "threads" in api else {}
            kids.append(container(image_url=public_url(rel, cfg), is_carousel_item="true", **extra))
        for kid in kids:
            wait_status(f"{api}/{kid}", {"fields": status_field}, auth, status_field, "FINISHED",
                        ("ERROR", "EXPIRED"), f"{what} слайд")
        cid = container(media_type="CAROUSEL", children=",".join(kids), **{text_field: item.caption[:text_limit]})
    wait_status(f"{api}/{cid}", {"fields": status_field}, auth, status_field, "FINISHED", ("ERROR", "EXPIRED"), what)
    done = check(requests.post(f"{api}/{user}/{publish_path}", headers=auth, data={"creation_id": cid},
                               timeout=TIMEOUT), f"{what} publish")
    return str(done["id"])


def publish_instagram_images(item: Item, cfg: dict[str, str]) -> str:
    auth = {"Authorization": f"OAuth {cfg['IG_ACCESS_TOKEN']}"}
    return _meta_carousel(GRAPH, cfg["IG_USER_ID"], auth, item, cfg, "caption", 2200, "media_publish", "Instagram")


def publish_threads_images(item: Item, cfg: dict[str, str]) -> str:
    auth = {"Authorization": f"Bearer {cfg['THREADS_ACCESS_TOKEN']}"}
    item = Item(item.id, item.kind, item.files, item.rels, item.title, threads_text(item.caption))
    return _meta_carousel(THREADS, cfg["THREADS_USER_ID"], auth, item, cfg, "text", 500, "threads_publish", "Threads")


# ---------------------------------------------------------------- VK

def _vk(method: str, cfg: dict[str, str], **params) -> dict:
    data = check(requests.post(f"{VK_API}/{method}", data={"access_token": cfg["VK_TOKEN"], "v": VK_VERSION, **params},
                               timeout=TIMEOUT), f"VK {method}")
    if "response" not in data:
        raise PublishError(f"VK {method}: {data.get('error')}")
    return data["response"]


def publish_vk_images(item: Item, cfg: dict[str, str]) -> str:
    gid = cfg["VK_GROUP_ID"].lstrip("-")
    attachments = []
    for path in item.files:
        server = _vk("photos.getWallUploadServer", cfg, group_id=gid)
        with path.open("rb") as fh:
            up = check(requests.post(server["upload_url"], files={"photo": (path.name, fh, "image/png")},
                                     timeout=TIMEOUT), "VK upload photo")
        saved = _vk("photos.saveWallPhoto", cfg, group_id=gid, server=up["server"], photo=up["photo"], hash=up["hash"])
        attachments.append(f"photo{saved[0]['owner_id']}_{saved[0]['id']}")
    post = _vk("wall.post", cfg, owner_id=f"-{gid}", from_group=1, message=item.caption,
               attachments=",".join(attachments))
    return str(post["post_id"])


# ---------------------------------------------------------------- Одноклассники

def publish_ok_images(item: Item, cfg: dict[str, str]) -> str:
    gid = cfg["OK_GROUP_ID"]
    up = ok_call("photosV2.getUploadUrl", cfg, gid=gid, count=str(len(item.files)))
    files = {f"pic{i + 1}": (p.name, p.read_bytes(), "image/png") for i, p in enumerate(item.files)}
    result = check(requests.post(up["upload_url"], files=files, timeout=TIMEOUT), "OK upload photo")
    tokens = [result["photos"][pid]["token"] for pid in up["photo_ids"]]
    attachment = {"media": [{"type": "text", "text": item.caption},
                            {"type": "photo", "list": [{"id": t} for t in tokens]}]}
    post = ok_call("mediatopic.post", cfg, gid=gid, type="GROUP_THEME",
                   attachment=json.dumps(attachment, ensure_ascii=False))
    return str(post if not isinstance(post, dict) else post.get("id", ""))


# ---------------------------------------------------------------- Facebook (страница)

def publish_facebook_images(item: Item, cfg: dict[str, str]) -> str:
    auth = {"Authorization": f"OAuth {cfg['FB_PAGE_TOKEN']}"}
    page = cfg["FB_PAGE_ID"]
    ids = []
    for path in item.files:
        with path.open("rb") as fh:
            photo = check(requests.post(f"{GRAPH}/{page}/photos", headers=auth, data={"published": "false"},
                                        files={"source": (path.name, fh, "image/png")}, timeout=TIMEOUT),
                          "Facebook photo")
        ids.append(photo["id"])
    data = {"message": item.caption}
    for i, pid in enumerate(ids):
        data[f"attached_media[{i}]"] = json.dumps({"media_fbid": pid})
    return str(check(requests.post(f"{GRAPH}/{page}/feed", headers=auth, data=data, timeout=TIMEOUT),
                     "Facebook feed")["id"])


# ---------------------------------------------------------------- Pinterest

def publish_pinterest_images(item: Item, cfg: dict[str, str]) -> str:
    import base64
    auth = {"Authorization": f"Bearer {cfg['PINTEREST_TOKEN']}"}
    blobs = [base64.b64encode(p.read_bytes()).decode() for p in item.files[:5]]  # Pinterest: до 5 в карусели
    if len(blobs) == 1:
        source = {"source_type": "image_base64", "content_type": "image/png", "data": blobs[0]}
    else:
        source = {"source_type": "multiple_image_base64",
                  "items": [{"content_type": "image/png", "data": b} for b in blobs]}
    pin = {"board_id": cfg["PINTEREST_BOARD_ID"], "title": item.title[:100],
           "description": item.caption[:800], "media_source": source}
    if os.environ.get("PINTEREST_LINK"):
        pin["link"] = os.environ["PINTEREST_LINK"]
    return str(check(requests.post(f"{PINTEREST}/pins", headers=auth, json=pin, timeout=TIMEOUT), "Pinterest pin")["id"])


# ================================================================ реестр

@dataclass(frozen=True)
class Platform:
    video: object                 # publish(item, cfg) для роликов
    video_keys: tuple[str, ...]
    images: object = None         # publish(item, cfg) для картинок и каруселей; None - не умеет
    image_keys: tuple[str, ...] = ()

    def handler(self, kind: str):
        """(функция, нужные переменные) для типа контента или (None, ()) если площадка его не берёт."""
        if kind == "video":
            return self.video, self.video_keys
        return (self.images, self.image_keys) if self.images else (None, ())


TG = ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID")
VK = ("VK_TOKEN", "VK_GROUP_ID")
OK = ("OK_ACCESS_TOKEN", "OK_APP_KEY", "OK_APP_SECRET", "OK_GROUP_ID")
IG = ("IG_ACCESS_TOKEN", "IG_USER_ID")
FB = ("FB_PAGE_TOKEN", "FB_PAGE_ID")
TH = ("THREADS_ACCESS_TOKEN", "THREADS_USER_ID", "PUBLIC_MEDIA_BASE_URL")
PIN = ("PINTEREST_TOKEN", "PINTEREST_BOARD_ID")

PLATFORMS = {
    "telegram": Platform(publish_telegram, TG, publish_telegram_images, TG),
    "vk": Platform(publish_vk, VK, publish_vk_images, VK),
    "ok": Platform(publish_ok, OK, publish_ok_images, OK),
    "instagram": Platform(publish_instagram, IG, publish_instagram_images, IG + ("PUBLIC_MEDIA_BASE_URL",)),
    "facebook": Platform(publish_facebook, FB, publish_facebook_images, FB),
    "threads": Platform(publish_threads, TH, publish_threads_images, TH),
    "youtube": Platform(publish_youtube, ("YT_CLIENT_ID", "YT_CLIENT_SECRET", "YT_REFRESH_TOKEN")),
    "tiktok": Platform(publish_tiktok, ("TIKTOK_CLIENT_KEY", "TIKTOK_CLIENT_SECRET", "TIKTOK_REFRESH_TOKEN")),
    "pinterest": Platform(publish_pinterest, PIN, publish_pinterest_images, PIN),
    "rutube": Platform(publish_rutube, ("RUTUBE_TOKEN", "PUBLIC_MEDIA_BASE_URL")),
}
