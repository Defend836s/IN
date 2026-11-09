"""Модули площадок для autopost.py.

Каждая функция publish_<площадка>(item, cfg) публикует один ролик и
возвращает id поста на площадке или бросает PublishError. cfg - словарь
переменных окружения из PLATFORMS[площадка][1].
"""
from __future__ import annotations

import hashlib
import json
import os
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
    video: Path
    rel: str  # путь ролика относительно content/
    title: str
    caption: str


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

def public_url(item: Item, cfg: dict[str, str]) -> str:
    """Threads и Rutube забирают ролик по ссылке, а не загрузкой файла.

    PUBLIC_VIDEO_BASE_URL - адрес, по которому лежит папка content/
    (например raw-ссылка публичного репозитория или свой хостинг).
    """
    base = cfg["PUBLIC_VIDEO_BASE_URL"].rstrip("/")
    return f"{base}/{quote(item.rel)}"


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

THREADS = "https://graph.threads.net/v1.0"


def publish_threads(item: Item, cfg: dict[str, str]) -> str:
    token, user = cfg["THREADS_ACCESS_TOKEN"], cfg["THREADS_USER_ID"]
    auth = {"Authorization": f"Bearer {token}"}
    created = check(
        requests.post(
            f"{THREADS}/{user}/threads",
            headers=auth,
            data={"media_type": "VIDEO", "video_url": public_url(item, cfg), "text": item.caption[:500]},
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
        headers={"Authorization": f"Token {cfg['RUTUBE_TOKEN']}"},
        json={
            "url": public_url(item, cfg),
            "title": item.title[:100],
            "description": item.caption,
            "is_short": True,
            "category_id": int(os.environ.get("RUTUBE_CATEGORY", "13")),
        },
        timeout=TIMEOUT,
    )
    return str(check(resp, "Rutube").get("video_id"))


# ---------------------------------------------------------------- реестр

PLATFORMS = {
    "telegram": (publish_telegram, ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID")),
    "vk": (publish_vk, ("VK_TOKEN", "VK_GROUP_ID")),
    "ok": (publish_ok, ("OK_ACCESS_TOKEN", "OK_APP_KEY", "OK_APP_SECRET", "OK_GROUP_ID")),
    "instagram": (publish_instagram, ("IG_ACCESS_TOKEN", "IG_USER_ID")),
    "facebook": (publish_facebook, ("FB_PAGE_TOKEN", "FB_PAGE_ID")),
    "threads": (publish_threads, ("THREADS_ACCESS_TOKEN", "THREADS_USER_ID", "PUBLIC_VIDEO_BASE_URL")),
    "youtube": (publish_youtube, ("YT_CLIENT_ID", "YT_CLIENT_SECRET", "YT_REFRESH_TOKEN")),
    "tiktok": (publish_tiktok, ("TIKTOK_CLIENT_KEY", "TIKTOK_CLIENT_SECRET", "TIKTOK_REFRESH_TOKEN")),
    "pinterest": (publish_pinterest, ("PINTEREST_TOKEN", "PINTEREST_BOARD_ID")),
    "rutube": (publish_rutube, ("RUTUBE_TOKEN", "PUBLIC_VIDEO_BASE_URL")),
}
