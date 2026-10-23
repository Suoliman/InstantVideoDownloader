# Development workflow

- Use the existing checkout. Cloud tasks already run in isolation; do not create a worktree unless the user requests one.
- This is a personal Windows/macOS Chrome extension plus a local native messaging companion, not a hosted service. Linux is also supported for development.
- Python 3.11+, FFmpeg/ffprobe, and `.venv` with `requirements.txt` are required. Node is only for development/browser checks.
- Run `npm run check`, `npm run test:background`, `.venv/bin/python -m unittest discover -s tests -v`, and `npm run test:browser` after relevant changes. Browser tests accept `CHROMIUM_PATH`. Default browser checks simulate Chrome APIs; `npm run test:extension` requires a browser that permits unpacked extensions. Do not modify managed browser policies.
- Keep extraction/download URLs, cookies, passwords, and authentication headers out of logs, screenshots, fixtures, and storage. Only the selected platform's cookies may be passed to the local companion in memory for the requested operation.
- Preserve source quality. Download original streams and merge with stream copy. Do not substitute recording, upscaling, or re-encoding.
- Live site access and native Windows/macOS Chrome installation must be reported separately from Linux/local fixture checks. Do not describe simulated Windows unit tests as a Windows machine validation.
- Windows Python is `.venv/Scripts/python.exe`; native registration uses this application's HKCU Chrome key. The ASCII-only batch host uses relative paths and binary stdio. Do not embed cookies or credentials in launchers or the registry.
