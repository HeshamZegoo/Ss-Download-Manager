# Ss Download Manager

A Windows-first desktop download manager inspired by IDM-style download tools.

## Implemented in the current source

- Native PySide6 desktop interface.
- Real HTTP/HTTPS downloads with pause/resume; segmented multi-connection downloads when the server supports byte ranges, with a safe single-stream fallback.
- Persistent download history and retained partial download files.
- Per-download progress, speed, status, and search.
- Batch URL import (one URL per line), configurable per-file connection count, and a bounded active-download queue.
- Queue ordering controls, a configurable simultaneous-download limit, and a clipboard URL monitor with user confirmation.
- Scheduled download start times, an optional aggregate download speed cap, and system-tray notifications/background operation where supported.
- Upload cancellation and progress reporting.
- Automatic file categories (video, audio, images, archives, documents, programs, other).
- Choose destination folders and open completed files/folders.
- SHA-256 calculation and optional comparison against a supplied checksum.
- Real HTTP(S) PUT uploads with progress reporting; supports compatible WebDAV endpoints and pre-signed upload URLs.
- No application-imposed transfer speed cap by default.

## Run from source

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python main.py
```

## Uploading

Choose **Upload file**, select a local file, then provide an HTTP(S) destination URL that accepts PUT. For authenticated services, use an authorized or pre-signed URL. FTP/SFTP and credential profiles are not implemented yet.

## Tests

```powershell
python -m unittest discover -s tests -v
```

GitHub Actions currently runs validation only. Windows EXE packaging is deliberately deferred until the requested feature set is implemented and tested.

## Still to implement

- Browser extensions / browser integration and video extraction.
- FTP/SFTP upload, upload queue/history, and resumable uploads.
- Notifications, system tray/background mode, and polished settings/preferences.

## Limitations

Resume depends on the server supporting byte ranges and keeping the same resource. HTTP upload requires a destination service that accepts PUT. Actual transfer speed depends on the user's network, remote server, and network path; the application does not bypass authentication, host policies, or ISP limits.
