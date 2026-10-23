# instant.

A personal Chrome extension for **Facebook Reels, Instagram Reels, and TikTok**. Download the actual media streams at the highest available quality, using your existing Chrome login. Supports **Windows and macOS** with a local Python companion. There is no hosted backend, subscription, or screen recording.

## Install on Windows

See the [Windows setup guide](WINDOWS.md). Install Python 3.11+ with its launcher and FFmpeg, load the `extension/` folder in Chrome, then run **Install-Windows.bat**. It prompts for your extension ID and registers the companion for your Windows user.

The extension automatically displays Windows setup commands, **Show in Explorer**, and **Media Player · H.264 + AAC**. Original-quality downloads and Chrome login reuse work through the same shared media pipeline; there is no separate browser extension to maintain.

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

The installer also supports Linux (`--browser chromium` for Chromium). Windows has its own launcher and per-user registry registration, described in [WINDOWS.md](WINDOWS.md). Native Windows Chrome and physical Mac acceptance should be distinguished from the Linux/fixture checks described below.

## Save a video

1. Open the individual video in Chrome. Sign in normally if it requires your account.
2. Open Instant. It fills in the current tab's supported video URL; you can paste another link instead.
3. Leave **Use Chrome login** enabled to use that platform's cookies from the current Chrome profile. Turn it off for anonymous extraction.
4. Select **Find video**, choose a **Playback** mode and quality, then **Download original**. For QuickTime or Finder preview, select **QuickTime / Finder · H.264 + AAC**. **Original quality** keeps the platform's highest source codecs and may require VLC or IINA.
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

Downloads are saved as **MP4**. Separate tracks are merged directly into MP4; a combined source in another container is repackaged into MP4 using stream copy. This changes the container without re-encoding or reducing resolution, frame rate, or bitrate. An existing MP4 source is kept intact. If a source codec cannot be stored in MP4, the operation reports an error rather than re-encoding or selecting a lower-quality source. Playback support still depends on the source codecs and your macOS version. The highest source can contain a platform watermark; this app does not promise watermark removal.

**Original quality** remains the default. **QuickTime / Finder** explicitly selects the best source offered as H.264 video with AAC audio. A compatible source may have a lower resolution than the highest original source; the quality menu shows only the resolutions offered for the selected playback mode. There is no codec conversion or hidden fallback. If no compatible source is offered, QuickTime download is unavailable. QuickTime files use a separate `[QuickTime].mp4` filename so an older incompatible MP4 is not reused.

Before reporting success, FFprobe checks the saved file for a real video track and any expected audio track. QuickTime mode also checks for standard 8-bit, 4:2:0 H.264 with the `avc1` tag and AAC audio. The result displays actual codecs and warns if the original uses codecs outside this preset. These checks do not replace playback testing in QuickTime on a physical Mac.

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

### Audio-only playback in QuickTime (v0.1.2)

Finder's **MPEG-4 movie** label is normal for an MP4. The container can hold video codecs that QuickTime cannot decode on your Mac; changing MKV to MP4 does not change those codecs. Without probing the affected file, audio-only playback alone does not establish whether its video track is unsupported, missing, or damaged.

1. Update **both `extension/` and `companion/`** in the existing project folder. If you cloned it, run `git pull origin main`. If you downloaded a ZIP, copy the latest source files into the existing installed folder without removing `.venv`.
2. Open `chrome://extensions` and click **Reload** on Instant. In the popup, confirm **companion 0.1.2** appears. If the version is still older, the registered companion points to a different folder: rerun `python3 scripts/install_companion.py --extension-id YOUR_EXTENSION_ID` from the updated project, using the ID Chrome currently shows, then reload again.
3. Inspect the video and select **QuickTime / Finder · H.264 + AAC** in **Playback**.
4. Download again. The new filename includes `[QuickTime]`; the existing original file is preserved.

To watch the existing original immediately, try VLC or IINA. To diagnose its tracks without exposing links or session data, substitute the actual local filename in:

```sh
ffprobe -v error -show_entries stream=codec_type,codec_name,codec_tag_string,pix_fmt,width,height -of default=noprint_wrappers=1 "video.mp4"
```

If the platform offers no H.264/AAC version, this app keeps the original stream option rather than re-encoding it. A new encoding would require a separate, explicit quality tradeoff.

### Update to MP4 output (v0.1.1)

The first version merged separate tracks into MKV. Version **0.1.1** saves MP4 while preserving the original video and audio streams.

1. Update the project in its existing folder (`git pull origin main` if you cloned it, or replace its source files with the latest download).
2. Open `chrome://extensions` and click **Reload** on Instant. This restarts the companion so it loads the updated code.
3. Inspect and download the video again. The new file will end in `.mp4` in `~/Downloads/Instant`. Existing MKV files are left in place.

If you move the project or change its extension ID, rerun `python3 scripts/install_companion.py --extension-id YOUR_EXTENSION_ID` with the current ID.

To repackage an already downloaded MKV without downloading it again, run this from its folder, substituting the actual filenames:

```sh
ffmpeg -n -i "video.mkv" -map 0:v:0 -map "0:a:0?" -c copy -movflags +faststart "video.mp4"
```

This keeps the MKV and copies its encoded streams into a new MP4 without quality loss. It requires MP4-compatible source codecs; renaming the file extension alone does not convert its container.

### Troubleshooting

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

The Python integration tests generate real H.264, AV1, and AAC sources, serve them locally, and download/merge them with the production companion. Only social-site extraction is substituted with fixture metadata. Tests compare encoded packet hashes and decode a video frame to verify the outputs. They check that Original quality retains the higher-resolution AV1 source while QuickTime explicitly selects the available H.264/AAC alternative, without re-encoding either source. Tests also reject audio-only files and missing expected audio. Other tests cover URL boundaries, platform cookie isolation, error redaction, native framing, and installation.

`npm run test:extension` is an additional real extension/native-host browser check for a browser that permits unpacked extensions. It is blocked in the current cloud Chromium by administrator policy (`ExtensionInstallBlocklist: ["*"]`); the policy is left intact. The default browser UI checks do not install an extension or bypass that restriction.

Build source-only Windows and macOS installation archives with `npm run package`. They exclude environments, test artifacts, downloaded media, and FFmpeg binaries. GitHub Actions runs the shared tests on Windows and Linux, including the real batch-host protocol smoke on Windows. The standalone `test:extension` harness currently uses Linux's isolated Chromium configuration; use the documented manual Chrome checks on Windows/macOS.

Live authenticated platform extraction requires a real logged-in Chrome profile on your Mac and is a separate acceptance check. It is not claimed by the fixture tests. To verify: inspect and download one accessible Reel/video from each platform, confirm audio and resolution with `ffprobe`, and compare the highest offered format against the source metadata. Never commit session cookies or test accounts.
