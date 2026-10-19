#!/usr/bin/env python3
"""Install a per-user native host. Requires no elevated privileges."""

import argparse
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import venv

ROOT = Path(__file__).resolve().parent.parent
HOST = "com.instantvideodownloader.companion"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--extension-id", required=True, help="32-letter ID from chrome://extensions")
    parser.add_argument("--browser", choices=("chrome", "chromium"), default="chrome")
    parser.add_argument("--manifest-dir", type=Path, help="Override the native-host manifest location (for testing)")
    parser.add_argument("--skip-deps", action="store_true", help="Reuse an already installed .venv")
    args = parser.parse_args()
    if not re.fullmatch(r"[a-p]{32}", args.extension_id):
        parser.error("The extension ID must be 32 lowercase letters a–p.")
    if sys.platform not in ("darwin", "linux"):
        parser.error("This installer currently supports macOS and Linux.")
    environment = ROOT / ".venv"
    python = environment / "bin" / "python"
    if not args.skip_deps:
        if not python.is_file():
            venv.EnvBuilder(with_pip=True).create(environment)
        subprocess.run([str(python), "-m", "pip", "install", "-r", str(ROOT / "requirements.txt")], check=True)
    if not python.is_file():
        parser.error("Create .venv and install requirements.txt first, or omit --skip-deps.")
    subprocess.run([str(python), "-c", "from companion.core import ffmpeg_location, ffprobe_location; print('FFmpeg:', ffmpeg_location()); print('FFprobe:', ffprobe_location())"], cwd=ROOT, check=True)
    if args.manifest_dir:
        directory = args.manifest_dir.expanduser().resolve()
    elif sys.platform == "darwin":
        browser = "Google/Chrome" if args.browser == "chrome" else "Chromium"
        directory = Path.home() / "Library/Application Support" / browser / "NativeMessagingHosts"
    else:
        browser = "google-chrome" if args.browser == "chrome" else "chromium"
        directory = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / browser / "NativeMessagingHosts"
    directory.mkdir(parents=True, exist_ok=True)
    launcher = directory / "instant-video-host"
    launcher.write_text("#!/bin/sh\nexec " + shlex.quote(str(python)) + " " + shlex.quote(str(ROOT / "companion/host.py")) + ' "$@"\n')
    launcher.chmod(0o700)
    manifest = {
        "name": HOST, "description": "Instant local media downloader",
        "path": str(launcher), "type": "stdio",
        "allowed_origins": [f"chrome-extension://{args.extension_id}/"],
    }
    destination = directory / (HOST + ".json")
    destination.write_text(json.dumps(manifest, indent=2) + "\n")
    destination.chmod(0o600)
    print(f"Registered companion: {destination}")
    print("Reopen the extension and select Reconnect. Keep this project at its current path.")


if __name__ == "__main__":
    main()
