"""Operating-system integration. No network access or session data."""

import os
from pathlib import Path
import shutil
import subprocess
import sys

PROJECT = Path(__file__).resolve().parent.parent


def tool_search_path(platform=None):
    platform = platform or sys.platform
    directories = [os.environ.get("PATH", ""), str(PROJECT / "tools" / "ffmpeg" / "bin"), str(PROJECT / "tools" / "ffmpeg")]
    if platform == "win32":
        local = os.environ.get("LOCALAPPDATA")
        if local:
            winget = Path(local) / "Microsoft" / "WinGet"
            directories.append(str(winget / "Links"))
            packages = winget / "Packages"
            for pattern in ("Gyan.FFmpeg_*/ffmpeg-*/bin", "Gyan.FFmpeg.Essentials_*/ffmpeg-*/bin"):
                directories.extend(str(p) for p in sorted(packages.glob(pattern), reverse=True))
        program_files = os.environ.get("ProgramFiles")
        if program_files:
            directories.append(str(Path(program_files) / "ffmpeg" / "bin"))
    else:
        directories.extend(("/opt/homebrew/bin", "/usr/local/bin"))
    return os.pathsep.join(directories)


def find_tool(name, platform=None):
    platform = platform or sys.platform
    executable = name + ".exe" if platform == "win32" else name
    return shutil.which(executable, path=tool_search_path(platform))


def tool_install_hint(platform=None):
    platform = platform or sys.platform
    if platform == "win32":
        return "Install FFmpeg with: winget install --id Gyan.FFmpeg --exact --source winget. Then restart Chrome. You can also put ffmpeg.exe and ffprobe.exe in tools/ffmpeg/bin inside the project."
    if platform == "darwin":
        return "On macOS, run: brew install ffmpeg"
    return "Install FFmpeg and FFprobe using your system package manager."


def downloads_directory(platform=None):
    platform = platform or sys.platform
    if platform == "win32":
        # Respect redirected Downloads folders, including locations on another drive.
        import winreg
        try:
            key_path = r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders"
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
                value, _ = winreg.QueryValueEx(key, "{374DE290-123F-4565-9164-39C4925E467B}")
                if isinstance(value, str) and value:
                    expanded = Path(os.path.expandvars(value))
                    if expanded.is_absolute():
                        return expanded
        except OSError:
            pass
    return Path.home() / "Downloads"


def reveal_command(path, platform=None):
    platform = platform or sys.platform
    path = str(path)
    if platform == "win32":
        windows = Path(os.environ.get("WINDIR", r"C:\Windows"))
        return [str(windows / "explorer.exe"), "/select,", path]
    if platform == "darwin":
        return ["open", "-R", path]
    return ["xdg-open", str(Path(path).parent)]


def quiet_process_options(platform=None):
    platform = platform or sys.platform
    return {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)} if platform == "win32" else {}


def configure_binary_stdio(platform=None, stdin=None, stdout=None):
    if (platform or sys.platform) == "win32":
        import msvcrt
        # Windows text mode would translate bytes 0x0a/0x0d and corrupt the
        # four-byte native-message length or JSON payload, even with .buffer.
        for stream in (stdin or sys.stdin, stdout or sys.stdout):
            msvcrt.setmode(stream.fileno(), os.O_BINARY)
