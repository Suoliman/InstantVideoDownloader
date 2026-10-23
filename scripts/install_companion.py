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


def windows_registry_path(browser):
    vendor = r"Google\Chrome" if browser == "chrome" else "Chromium"
    return rf"Software\{vendor}\NativeMessagingHosts\{HOST}"


def register_windows_manifest(destination, browser):
    import winreg
    access = winreg.KEY_SET_VALUE | winreg.KEY_WOW64_32KEY
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, windows_registry_path(browser), 0, access) as key:
        winreg.SetValueEx(key, "", 0, winreg.REG_SZ, str(destination))


def write_native_host(directory, python, extension_id, browser="chrome", platform=None, register=True):
    platform = platform or sys.platform
    directory = directory.resolve()
    directory.mkdir(parents=True, exist_ok=True)
    if platform == "win32":
        # The ASCII-only launcher resolves its Python and script relative to
        # itself; it never embeds a user's Unicode/percent/exclamation path.
        launcher = ROOT / "companion" / "native-host-windows.bat"
        if not launcher.is_file():
            raise ValueError("The Windows native host launcher is missing. Download the complete project.")
    else:
        launcher = directory / "instant-video-host"
        launcher.write_text("#!/bin/sh\nexec " + shlex.quote(str(python)) + " " + shlex.quote(str(ROOT / "companion/host.py")) + ' "$@"\n')
        launcher.chmod(0o700)
    manifest = {
        "name": HOST, "description": "Instant local media downloader",
        "path": str(launcher), "type": "stdio",
        "allowed_origins": [f"chrome-extension://{extension_id}/"],
    }
    destination = directory / (HOST + ".json")
    destination.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    if platform == "win32":
        if register:
            register_windows_manifest(destination, browser)
    else:
        destination.chmod(0o600)
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--extension-id", help="32-letter ID from chrome://extensions")
    parser.add_argument("--interactive", action="store_true", help="Prompt for the extension ID")
    parser.add_argument("--browser", choices=("chrome", "chromium"), default="chrome")
    parser.add_argument("--manifest-dir", type=Path, help="Override the native-host manifest location (for testing)")
    parser.add_argument("--skip-deps", action="store_true", help="Reuse an already installed .venv")
    parser.add_argument("--no-register", action="store_true", help="Write to --manifest-dir without updating the Windows registry (for testing)")
    args = parser.parse_args()
    if args.interactive and not args.extension_id:
        print("Load the extension/ folder using Load unpacked in chrome://extensions first.")
        args.extension_id = input("Paste the extension's 32-letter ID: ").strip()
    if not args.extension_id or not re.fullmatch(r"[a-p]{32}", args.extension_id):
        parser.error("The extension ID must be 32 lowercase letters a–p.")
    if sys.version_info < (3, 11):
        parser.error("Python 3.11 or newer is required.")
    if sys.platform not in ("darwin", "linux", "win32"):
        parser.error("This installer supports Windows, macOS, and Linux.")
    if args.no_register and not args.manifest_dir:
        parser.error("--no-register requires --manifest-dir.")
    environment = ROOT / ".venv"
    python = environment / "Scripts" / "python.exe" if sys.platform == "win32" else environment / "bin" / "python"
    if not args.skip_deps:
        if not python.is_file():
            venv.EnvBuilder(with_pip=True).create(environment)
        subprocess.run([str(python), "-m", "pip", "install", "-r", str(ROOT / "requirements.txt")], check=True)
    if not python.is_file():
        parser.error("Create .venv and install requirements.txt first, or omit --skip-deps.")
    subprocess.run([str(python), "-c", "from companion.core import ffmpeg_location, ffprobe_location; print('FFmpeg:', ffmpeg_location()); print('FFprobe:', ffprobe_location())"], cwd=ROOT, check=True)
    if args.manifest_dir:
        directory = args.manifest_dir.expanduser().resolve()
    elif sys.platform == "win32":
        local = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        directory = local / "InstantVideoDownloader" / "NativeMessagingHosts"
    elif sys.platform == "darwin":
        browser = "Google/Chrome" if args.browser == "chrome" else "Chromium"
        directory = Path.home() / "Library/Application Support" / browser / "NativeMessagingHosts"
    else:
        browser = "google-chrome" if args.browser == "chrome" else "chromium"
        directory = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / browser / "NativeMessagingHosts"
    try:
        destination = write_native_host(directory, python, args.extension_id, args.browser, register=not args.no_register)
    except (OSError, ValueError) as error:
        parser.exit(1, f"Could not register the local companion: {error}\n")
    print(f"{'Prepared (registry unchanged)' if args.no_register else 'Registered companion'}: {destination}")
    print("Reopen the extension and select Reconnect. Keep this project at its current path.")


if __name__ == "__main__":
    main()
