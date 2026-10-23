# Instant for Windows Chrome

Version **0.2.0** adds a Windows companion installer. The Chrome extension is shared with macOS: Facebook Reels, Instagram Reels, TikTok, your own Chrome login, MP4 output, and original encoded media. There is no screen recording or hosted backend.

## Install on Windows 10 or 11

1. Download the project ZIP and **extract it** to a permanent folder, for example `C:\Users\YourName\Apps\InstantVideoDownloader`. Keep the complete folder; do not run it from inside the ZIP.
2. Install **Python 3.11 or newer with the Python launcher** and **FFmpeg/FFprobe**. With Windows Package Manager, run these in Terminal:

   ```powershell
   winget install --id Python.Python.3.12 --exact --source winget
   winget install --id Gyan.FFmpeg --exact --source winget
   ```

   If `winget` is missing, install/update Microsoft's **App Installer** through Microsoft Store, or install Python from [python.org](https://www.python.org/downloads/windows/) and FFmpeg from a build linked by [ffmpeg.org](https://ffmpeg.org/download.html#build-windows). The Python installer should include the **Python launcher**. For a portable FFmpeg setup, place both `ffmpeg.exe` and `ffprobe.exe` in `tools\ffmpeg\bin` inside this project.

3. Open `chrome://extensions`, enable **Developer mode**, choose **Load unpacked**, and select the project's **extension** folder.
4. Copy the extension's 32-letter **ID** from that page.
5. Double-click **Install-Windows.bat** in the extracted project folder, paste the ID when asked, and wait for **Registered companion**. Alternatively, open Terminal in the project folder and run:

   ```powershell
   py -3 scripts/install_companion.py --extension-id YOUR_EXTENSION_ID
   ```

6. Restart Chrome after installing prerequisites, pin **Instant**, open it, and select **Reconnect**. It should show **FFmpeg ready · companion 0.2.0**.

The companion registration is per user and needs no administrator privileges. Windows or your package manager may request permission for installing Python/FFmpeg themselves. No PowerShell execution-policy changes are needed.

## Download a video

Open a Reel/TikTok in your own signed-in Chrome profile, open Instant, then **Find video**. Leave **Use Chrome login** enabled for account access. Choose quality and playback mode, then **Download original**.

- **Original quality** is the default and keeps the best source codecs the platform exposes. VLC can play codecs that Windows Media Player may not support.
- **Media Player · H.264 + AAC** selects the best compatible source the platform offers. It may have a lower resolution than Original quality; the menu shows the available resolutions. It does not re-encode or upscale. These files include `[H264]` in their names and do not overwrite the original-codec downloads.
- Downloads go in **Downloads\Instant**, respecting the Windows Downloads folder if it was redirected to another drive. **Show in Explorer** selects a completed file.
- Session cookies are transferred only to the local companion, in memory, for the selected platform. They are not exported to a file or saved in extension storage. Passwords are not collected.

## What gets installed

The installer creates `.venv\Scripts\python.exe` and Python dependencies in the project. It writes a native-host manifest under:

```text
%LOCALAPPDATA%\InstantVideoDownloader\NativeMessagingHosts\com.instantvideodownloader.companion.json
```

Chrome finds it through the default value of this **current-user** registry key, in the 32-bit lookup view Chrome checks:

```text
HKEY_CURRENT_USER\Software\Google\Chrome\NativeMessagingHosts\com.instantvideodownloader.companion
```

The manifest permits only your extension's ID and launches `companion\native-host-windows.bat`. This uses Chrome's [official Windows native-host pattern](https://github.com/GoogleChrome/chrome-extensions-samples/tree/main/api-samples/nativeMessaging/host), starts the project's own Python, and uses binary stdin/stdout for native messages. It resolves paths relative to itself and works independently of Chrome's working directory.

Keep the project in place. If it moves, reload the extension from its new location and rerun the installer with the ID Chrome currently shows. No always-running server is installed.

## Troubleshooting

- **`py` is not recognized:** install Python with its launcher, then open a new Terminal window. Confirm `py -3 --version` shows 3.11 or newer.
- **FFmpeg missing:** restart Chrome so it gets the updated PATH. The companion also checks WinGet's links/package folders and `tools\ffmpeg\bin`. That local folder must contain **both** FFmpeg and FFprobe.
- **Companion not found:** rerun the installer with the current ID. A managed browser can prohibit unpacked extensions or native messaging; those policies need to be handled by your administrator rather than altered by this app.
- **Only sound or no picture:** use VLC for the original codecs, or choose **Media Player · H.264 + AAC** before downloading. Merely renaming a file cannot change its codecs.
- **The platform rejects a request:** open the video in the same Chrome profile, resolve any account challenge, and retry. The browser's login does not guarantee a separate media request will be accepted.
- **Moved/copied a macOS installation:** do not reuse its `.venv`. Extract a fresh Windows copy and run the Windows installer to create the Windows environment.

To uninstall, remove the extension, delete this application's manifest folder, and delete only its registry entry:

```powershell
reg delete "HKCU\Software\Google\Chrome\NativeMessagingHosts\com.instantvideodownloader.companion" /f /reg:32
```

You can then remove the project folder. Downloaded videos stay in Downloads\Instant.

## Windows development checks

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
npm ci
npm run check
npm run test:background
npx playwright install chromium
npm run test:browser
npm run package
```

`npm run package` creates `dist\InstantVideoDownloader-windows.zip` and the macOS archive. These contain source/installers, not Python, FFmpeg, accounts, or a prebuilt executable.

The automated workflow runs Linux and Windows checks. Windows-specific tests exercise the actual batch host with Unicode JSON and binary framing, in addition to the shared download/merge tests. Browser UI tests simulate Chrome APIs and check Windows labels separately. Real authenticated downloads, Explorer behavior, and extension registration in a user's installed Windows Chrome remain acceptance checks on a Windows machine until actually verified; a passing simulated Windows branch does not establish those behaviors.
