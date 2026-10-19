# instant.

A personal Chrome extension for **Facebook Reels, Instagram Reels, and TikTok**. Download the actual media streams at the highest available quality, using your existing Chrome login. Built for macOS with a local Python companion. There is no hosted backend, subscription, or screen recording.

## Install on your Mac

You need Chrome, Python **3.11 or newer**, and FFmpeg. With [Homebrew](https://brew.sh):

```sh
brew install python ffmpeg
```

1. Download or clone this project to a permanent folder on your Mac.
2. Open `chrome://extensions`, turn on **Developer mode**, choose **Load unpacked**, and select the project's **extension** folder.
3. Copy the extension's 32-letter **ID** from that page.
4. Open Terminal in the project folder and run the command below, replacing `YOUR_EXTENSION_ID` with that ID:

   ```sh
   python3 scripts/install_companion.py --extension-id YOUR_EXTENSION_ID
   ```

5. Pin **Instant** to Chrome's toolbar, open it, and select **Reconnect**. The status should say **Local companion connected** and **FFmpeg ready**.

The installer creates `.venv` in this project and registers a per-user Chrome native messaging host in `~/Library/Application Support/Google/Chrome/NativeMessagingHosts/`. It needs no administrator privileges. **Keep the project at the installed path**; rerun the installer if you move it or change the extension ID.

The installer also supports Linux (`--browser chromium` for Chromium). Windows is not implemented. macOS installation is implemented but has not been exercised on a physical Mac in the cloud test environment.

## Save a video

1. Open the individual video in Chrome. Sign in normally if it requires your account.
2. Open Instant. It fills in the current tab's supported video URL; you can paste another link instead.
3. Leave **Use Chrome login** enabled to use that platform's cookies from the current Chrome profile. Turn it off for anonymous extraction.
4. Select **Find video**, choose **Highest available** or a resolution limit, then **Download original**.
5. Files appear in `~/Downloads/Instant`. **Show in Finder** reveals a completed download.

Downloads continue when you close the popup. Reopen it to check progress or cancel. Cancellation waits for the current network request or merge operation to return. Partial downloads can be resumed by downloading the same video again. Process state does not survive a Chrome restart.

Supported link examples:

```text
https://www.facebook.com/reel/123456789/
https://www.facebook.com/share/r/SHARE_ID/
https://www.instagram.com/reel/REEL_ID/
https://www.tiktok.com/@creator/video/123456789
https://vm.tiktok.com/SHORT_ID/
```

Open the individual Reel if a share link is not recognized. Profiles, collections, and live streams are outside this version's scope. YouTube is excluded.

## What highest quality means

The companion uses **yt-dlp** to extract the versions a platform exposes to your session. It prioritizes resolution, frame rate, and bitrate, downloads the original encoded video and audio, and uses **FFmpeg stream copy** when they need merging. It does not capture your screen, upscale, or re-encode. Quality options show actual dimensions, so a portrait `1080 × 1920` video is not misleadingly labeled “1920p.”

A combined source keeps its original container. Separate tracks are merged into **MKV** to preserve the source codecs; [VLC](https://www.videolan.org/vlc/) or IINA can play these on macOS. QuickTime may not support the resulting container or codec. The highest source can contain a platform watermark; this app does not promise watermark removal.

**The platform may not expose the creator's original upload.** Your Chrome session establishes account access; it does not guarantee that a platform will accept a request from a separate downloader. Platforms can apply challenges, rate limits, regional restrictions, or change their extraction behavior. The extension reports failures instead of silently producing lower-quality recordings. Browser fingerprinting or device-bound access can still prevent a download. Protected/DRM content is not supported.

## How your login is used

Chrome's cookies API reads cookies only for the selected platform and current profile when you click **Find video** or **Download original**. Chrome sends them directly to the local companion through **native messaging**, together with its User-Agent. The companion places the cookies in an in-memory cookie jar for that operation, where the extractor uses domain-scoped cookies for platform requests.

There is no listening HTTP server, external application backend, password collection, analytics, or cookie export file. Cookies and extraction payloads are not written to extension storage or application logs. Only interface state and sanitized video metadata are kept in Chrome's temporary session storage. The operating system can still page process memory as it does for other applications. Media requests go to the platforms and their media delivery services; thumbnail images also load directly from their source.

Permissions:

| Permission | Purpose |
| --- | --- |
| `activeTab` | Use the video link in the current tab after you open Instant |
| `cookies` and the three platform host permissions | Reuse the selected platform's current Chrome session |
| `nativeMessaging` | Connect directly to your local media downloader |
| `storage` | Restore interface/progress state when you reopen the popup |
| `contextMenus` | Inspect a video from the platform page's context menu |

The native host is registered for your specific extension ID. No content script is injected into your pages. Session access can be disabled per request with **Use Chrome login**.

## Update and troubleshoot

- **Companion not found:** rerun the installer with the ID currently shown in `chrome://extensions`, then reconnect. Check that the project has not moved.
- **FFmpeg missing:** run `brew install ffmpeg`. The companion checks both Apple Silicon (`/opt/homebrew/bin`) and Intel (`/usr/local/bin`) Homebrew locations.
- **Login or access error:** open that specific video in the same Chrome profile, resolve any challenge, enable login reuse, and retry.
- **Extraction failure after a platform update:** inspect for a new yt-dlp release, update the pins in `requirements.txt` deliberately, and rerun the installer. This is an ongoing maintenance dependency; the app does not auto-update executable code.
- **No Finder action after reconnecting:** open `~/Downloads/Instant` directly. The companion remembers the last downloaded file only for its current connection.

To remove the companion registration, delete `com.instantvideodownloader.companion.json` and `instant-video-host` from Chrome's `NativeMessagingHosts` directory, then remove the extension. Downloaded videos remain in Downloads/Instant.

## Development and checks

The extension is plain JavaScript with Manifest V3. It needs no bundler or remote scripts. Python handles native messaging, extraction, download progress, and merging.

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
npm ci
npm run check
npm run test:background
.venv/bin/python -m unittest discover -s tests -v
```

For the browser checks, install Playwright's Chromium (`npx playwright install chromium`) or set `CHROMIUM_PATH` to a compatible installed Chromium binary. Then:

```sh
npm run test:browser
```

The browser UI suite uses a simulated Chrome API and the actual popup code; it checks inspection/download wiring, quality selection, progress, cancellation, title escaping, and layout. Background tests exercise the actual service worker code with mocked Chrome transport to verify cookie scoping, anonymous operation, state persistence, and disconnect handling.

The Python integration tests generate two real video qualities plus an audio track, serve them locally, and download/merge them with the production companion. Only social-site extraction is substituted with fixture metadata. Tests compare encoded video packet hashes to prove that merging has not re-encoded the video. Other tests cover URL boundaries, platform cookie isolation, error redaction, native framing, and installation.

`npm run test:extension` is an additional real extension/native-host browser check for a browser that permits unpacked extensions. It is blocked in the current cloud Chromium by administrator policy (`ExtensionInstallBlocklist: ["*"]`); the policy is left intact. The default browser UI checks do not install an extension or bypass that restriction.

Build a source-only macOS installation archive with `npm run package`. It excludes environments, test artifacts, and downloaded media.

Live authenticated platform extraction requires a real logged-in Chrome profile on your Mac and is a separate acceptance check. It is not claimed by the fixture tests. To verify: inspect and download one accessible Reel/video from each platform, confirm audio and resolution with `ffprobe`, and compare the highest offered format against the source metadata. Never commit session cookies or test accounts.
