#!/usr/bin/env python3
"""Chrome native messaging entry point. stdout is reserved for framed JSON."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import struct
import subprocess
import sys
import threading

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from companion.core import Cancelled, RequestError, ffmpeg_location, ffprobe_location, friendly_error, run_job

HOST_NAME = "com.instantvideodownloader.companion"
MAX_MESSAGE = 1024 * 1024


def read_message(stream):
    header = stream.read(4)
    if not header:
        return None
    if len(header) != 4:
        raise RequestError("Incomplete native message.")
    length = struct.unpack("=I", header)[0]
    if not 0 < length <= MAX_MESSAGE:
        raise RequestError("Native message is too large.")
    payload = stream.read(length)
    if len(payload) != length:
        raise RequestError("Incomplete native message.")
    value = json.loads(payload)
    if not isinstance(value, dict):
        raise RequestError("Invalid native message.")
    return value


def write_message(stream, message):
    payload = json.dumps(message, ensure_ascii=False, allow_nan=False).encode("utf-8")
    if len(payload) > MAX_MESSAGE:
        raise RequestError("Native response is too large.")
    stream.write(struct.pack("=I", len(payload)) + payload)
    stream.flush()


def main():
    write_lock = threading.Lock()
    busy = threading.Lock()
    cancelled = threading.Event()
    last_download = None
    executor = ThreadPoolExecutor(max_workers=1)

    def send(request_id, kind, data):
        with write_lock:
            try:
                write_message(sys.stdout.buffer, {"id": request_id, "type": kind, "data": data})
            except (BrokenPipeError, OSError):
                cancelled.set()

    def work(request):
        nonlocal last_download
        try:
            result = run_job(request, lambda kind, data: send(request["id"], kind, data), cancelled)
            if request["action"] == "download":
                last_download = result["path"]
            send(request["id"], "result", result)
        except Exception as error:
            was_cancelled = cancelled.is_set() or isinstance(error, Cancelled)
            send(request["id"], "error", {"message": "Cancelled. Partial media files can be resumed by downloading again." if was_cancelled else friendly_error(error), "cancelled": was_cancelled})
        finally:
            request.pop("cookies", None)
            busy.release()

    try:
        while (request := read_message(sys.stdin.buffer)) is not None:
            request_id = request.get("id")
            if not isinstance(request_id, str) or len(request_id) > 100:
                continue
            action = request.get("action")
            if action == "ping":
                import yt_dlp.version
                try:
                    ffmpeg_location()
                    ffprobe_location()
                    send(request_id, "result", {"version": "0.1.2", "extractorVersion": yt_dlp.version.__version__, "ffmpeg": True, "capabilities": ["quicktime-source", "verify-media"]})
                except RequestError as error:
                    send(request_id, "error", {"message": str(error)})
            elif action == "cancel":
                cancelled.set()
                send(request_id, "result", {"ok": True})
            elif action == "open_folder":
                if last_download and Path(last_download).is_file():
                    command = ["open", "-R", last_download] if sys.platform == "darwin" else ["xdg-open", str(Path(last_download).parent)]
                    try:
                        subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        send(request_id, "result", {"ok": True})
                    except OSError:
                        send(request_id, "error", {"message": "Open Downloads/Instant in your file manager."})
                else:
                    send(request_id, "error", {"message": "Your videos are saved in Downloads/Instant."})
            elif action in ("inspect", "download"):
                if busy.acquire(blocking=False):
                    cancelled.clear()
                    executor.submit(work, request)
                else:
                    send(request_id, "error", {"message": "A video is already being processed."})
            else:
                send(request_id, "error", {"message": "Unknown companion action."})
    except (RequestError, ValueError, OSError):
        pass
    finally:
        cancelled.set()
        executor.shutdown(wait=True, cancel_futures=True)


if __name__ == "__main__":
    main()
