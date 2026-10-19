"""Media extraction and stream-copy downloads. No HTTP listener or cookie files."""

from __future__ import annotations

import http.cookiejar
import os
from pathlib import Path
import re
import shutil
import threading
import time
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

from yt_dlp import YoutubeDL

PLATFORMS = {"facebook": "facebook.com", "instagram": "instagram.com", "tiktok": "tiktok.com"}
FORMAT = "bestvideo*+bestaudio/best"


class RequestError(ValueError):
    pass


class Cancelled(Exception):
    pass


def validate_url(value):
    if not isinstance(value, str) or len(value) > 4096:
        raise RequestError("Paste a Facebook Reel, Instagram Reel, or TikTok video link.")
    try:
        url = urlsplit(value.strip())
        host = (url.hostname or "").lower()
        port = url.port
    except ValueError:
        raise RequestError("This video link is not valid.") from None
    if url.scheme != "https" or url.username or url.password or port not in (None, 443):
        raise RequestError("Use an HTTPS video link from a supported platform.")
    platform = next((p for p, d in PLATFORMS.items() if host == d or host.endswith("." + d)), None)
    if not platform:
        raise RequestError("Supported platforms: Facebook Reels, Instagram Reels, and TikTok.")
    path = url.path
    query = ""
    if platform == "facebook":
        video_id = parse_qs(url.query).get("v", [""])[0]
        if path.rstrip("/") == "/watch" and video_id.isdigit():
            query = urlencode({"v": video_id})
        elif not re.fullmatch(r"/(?:reel/\d+|reels/\d+|share/r/[A-Za-z0-9_-]+)/?", path):
            raise RequestError("Open the Facebook Reel itself and copy its link.")
    elif platform == "instagram":
        if not re.fullmatch(r"/(?:reel|reels|p)/[A-Za-z0-9_-]+/?", path):
            raise RequestError("Copy an individual Instagram Reel link.")
    elif not (
        re.fullmatch(r"/@[A-Za-z0-9_.-]+/video/\d+/?", path)
        or (host in ("vm.tiktok.com", "vt.tiktok.com") and re.fullmatch(r"/[A-Za-z0-9]+/?", path))
        or re.fullmatch(r"/t/[A-Za-z0-9]+/?", path)
    ):
        raise RequestError("Copy an individual TikTok video link.")
    return platform, urlunsplit(("https", host, path, query, ""))


def ffmpeg_location():
    search = os.pathsep.join([os.environ.get("PATH", ""), "/opt/homebrew/bin", "/usr/local/bin"])
    executable = shutil.which("ffmpeg", path=search)
    if not executable:
        raise RequestError("FFmpeg is missing. On macOS, run: brew install ffmpeg")
    return executable


def output_directory():
    directory = Path.home() / "Downloads" / "Instant"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


class QuietLogger:
    # Extractor messages may contain signed media URLs or account information.
    def debug(self, *_):
        pass

    def info(self, *_):
        pass

    def warning(self, *_):
        pass

    def error(self, *_):
        pass


def options(directory, quality="best"):
    if quality != "best" and (not isinstance(quality, str) or not re.fullmatch(r"[1-9]\d{1,4}", quality)):
        raise RequestError("Choose an available video quality.")
    selector = FORMAT if quality == "best" else f"bestvideo*[height<={quality}]+bestaudio/best[height<={quality}]"
    return {
        "format": selector,
        "format_sort": ["res", "fps", "br"],
        "merge_output_format": "mp4",
        # Merging covers separate tracks; remuxing also covers a single source
        # served as MOV, MKV, or WebM. This postprocessor always uses stream copy.
        "postprocessors": [{"key": "FFmpegVideoRemuxer", "preferedformat": "mp4"}],
        "outtmpl": str(Path(directory) / "%(title).140B [%(id)s].%(ext)s"),
        "windowsfilenames": True,
        "noplaylist": True,
        "overwrites": False,
        "continuedl": True,
        "socket_timeout": 25,
        "retries": 3,
        "fragment_retries": 3,
        "concurrent_fragment_downloads": 3,
        "ffmpeg_location": ffmpeg_location(),
        "quiet": True,
        "no_warnings": True,
        "logger": QuietLogger(),
        "cachedir": False,
        "usenetrc": False,
        "allowed_extractors": ["(?i)(facebook|instagram|tiktok).*"],
    }


def add_cookies(ydl, records, platform):
    if not isinstance(records, list) or len(records) > 300:
        raise RequestError("Invalid browser session data.")
    base = PLATFORMS[platform]
    for record in records:
        if not isinstance(record, dict):
            raise RequestError("Invalid browser session data.")
        domain = record.get("domain", "")
        if not isinstance(domain, str):
            continue
        clean = domain.lstrip(".").lower()
        if clean != base and not clean.endswith("." + base):
            continue
        name, value = record.get("name"), record.get("value")
        if not isinstance(name, str) or not isinstance(value, str) or len(name) + len(value) > 16384:
            continue
        expires = record.get("expirationDate")
        cookie = http.cookiejar.Cookie(
            version=0, name=name, value=value, port=None, port_specified=False,
            domain=domain, domain_specified=not record.get("hostOnly", False),
            domain_initial_dot=domain.startswith("."), path=record.get("path", "/"),
            path_specified=True, secure=bool(record.get("secure", True)),
            expires=int(expires) if isinstance(expires, (int, float)) else None,
            discard=bool(record.get("session", True)), comment=None, comment_url=None,
            rest={"HttpOnly": None} if record.get("httpOnly") else {}, rfc2109=False,
        )
        ydl.cookiejar.set_cookie(cookie)


def public_metadata(info, platform):
    if not info or info.get("_type") in ("playlist", "multi_video"):
        raise RequestError("Open a single video, rather than a profile or collection.")
    if info.get("is_live") or info.get("live_status") == "is_live":
        raise RequestError("Live streams are not supported. Open a published Reel or video.")
    formats = [f for f in info.get("formats", []) if f.get("vcodec") != "none" and not f.get("has_drm")]
    heights = sorted({int(f["height"]) for f in formats if f.get("height")}, reverse=True)
    qualities = []
    for height in heights:
        width = max((int(f.get("width") or 0) for f in formats if f.get("height") == height), default=0)
        qualities.append({"value": str(height), "label": f"{width} × {height}" if width else f"{height}px tall"})
    thumbnail = info.get("thumbnail")
    if not isinstance(thumbnail, str) or not thumbnail.startswith("https://"):
        thumbnail = None
    return {
        "title": str(info.get("title") or "Untitled video")[:300],
        "creator": str(info.get("uploader") or info.get("channel") or platform.title())[:150],
        "platform": platform,
        "duration": info.get("duration"),
        "thumbnail": thumbnail,
        "heights": heights,
        "qualities": qualities,
        "maxHeight": heights[0] if heights else None,
        "formatCount": len(formats),
    }


def friendly_error(error):
    # Do not forward extractor output: it can include cookies or signed URLs.
    if isinstance(error, RequestError):
        return str(error)
    message = str(error).lower()
    if "private" in message or "login" in message or "log in" in message or "cookies" in message:
        return "The platform requires access. Log in to the video in Chrome, enable Use Chrome login, and try again."
    if "429" in message or "rate" in message:
        return "The platform is limiting requests. Wait a few minutes, then try again."
    if "403" in message or "blocked" in message or "captcha" in message:
        return "The platform rejected this request. Open the video in Chrome and resolve any access challenge, then retry."
    if "unsupported" in message:
        return "This link is not supported by the current extractor. Use the video's direct link or update the companion."
    if "requested format" in message:
        return "That quality is no longer available. Inspect the video again or select Highest available."
    if "certificate" in message:
        return "TLS certificate verification failed. Check your system certificates and network configuration."
    if "no space left" in message or "disk full" in message:
        return "Your disk is full. Free space in Downloads/Instant and try again."
    if "permission denied" in message or "read-only file system" in message:
        return "The companion cannot write to Downloads/Instant. Check that folder's permissions."
    if "timed out" in message or "timeout" in message:
        return "The platform connection timed out. Check your connection and try again."
    return "The platform could not provide this video. Check access in Chrome; if it persists, update the companion."


def run_job(request, emit, cancelled: threading.Event, directory=None):
    platform, url = validate_url(request.get("url"))
    action = request.get("action")
    if action not in ("inspect", "download"):
        raise RequestError("Unknown media action.")
    target = Path(directory) if directory else (output_directory() if action == "download" else Path.home() / "Downloads" / "Instant")
    opts = options(target, request.get("quality", "best"))
    user_agent = request.get("userAgent")
    if isinstance(user_agent, str) and 0 < len(user_agent) < 1024 and not re.search(r"[\r\n\x00]", user_agent):
        opts["http_headers"] = {"User-Agent": user_agent}
    last_progress = 0.0
    final_paths = []

    def hook(data):
        nonlocal last_progress
        if cancelled.is_set():
            raise Cancelled()
        now = time.monotonic()
        if data["status"] == "downloading" and now - last_progress >= 0.3:
            last_progress = now
            total = data.get("total_bytes") or data.get("total_bytes_estimate")
            downloaded = data.get("downloaded_bytes", 0)
            emit("progress", {
                "stage": "downloading", "downloaded": downloaded, "total": total,
                "percent": min(100, downloaded * 100 / total) if total else None,
                "speed": data.get("speed"), "eta": data.get("eta"),
            })
        elif data["status"] == "finished":
            emit("progress", {"stage": "processing", "percent": None})

    def post_hook(data):
        if cancelled.is_set():
            raise Cancelled()
        if data["status"] == "started":
            emit("progress", {"stage": "processing", "percent": None})

    opts["progress_hooks"] = [hook]
    opts["postprocessor_hooks"] = [post_hook]
    opts["post_hooks"] = [final_paths.append]
    with YoutubeDL(opts) as ydl:
        add_cookies(ydl, request.get("cookies", []), platform)
        if cancelled.is_set():
            raise Cancelled()
        emit("progress", {"stage": "inspecting", "percent": None})
        info = ydl.extract_info(url, download=False)
        if cancelled.is_set():
            raise Cancelled()
        metadata = public_metadata(info, platform)
        if action == "inspect":
            return metadata
        result = ydl.process_ie_result(info, download=True)
        if cancelled.is_set():
            raise Cancelled()
        path = Path(final_paths[-1] if final_paths else result.get("filepath") or ydl.prepare_filename(result))
        resolved = path.resolve()
        if not resolved.is_relative_to(target.resolve()) or not resolved.is_file():
            raise RequestError("The download finished without a usable output file. Inspect and try again.")
        return {"filename": resolved.name, "path": str(resolved), "bytes": resolved.stat().st_size, "metadata": metadata}
