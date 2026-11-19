# Ss Download Manager

A Windows-first desktop download manager inspired by IDM-style download tools.

## Implemented

- Native desktop interface built with PySide6.
- Real HTTP/HTTPS file downloads with pause/resume using HTTP Range when supported.
- Persistent download history and partial download files.
- Per-download progress, transfer speed, and status.
- Choose destination folder, search history, open completed files and folders.
- Real HTTP(S) PUT file upload with progress reporting. This supports endpoints such as WebDAV servers and pre-signed upload URLs that accept PUT.
- No application-imposed upload speed cap by default.

## Requirements

- Python 3.11+
- Windows 10/11 (development also works on Linux/macOS)
- See `requirements.txt`

## Run from source

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python main.py
```

## Uploading

Choose **Upload file**, select a local file, then provide an HTTP(S) destination URL that accepts a PUT request. For authenticated services, the endpoint must provide an authorized or pre-signed URL; this initial UI does not yet expose credential profiles or FTP/SFTP.

## Validation

```powershell
python -m unittest discover -s tests -v
```

GitHub Actions currently runs validation only. Windows EXE packaging is deliberately deferred until the requested feature set is implemented and tested.

## Planned / not yet implemented

Multi-connection segmented downloads, speed limiter controls, download priorities and concurrency settings, batch URL import, clipboard monitoring, scheduler, browser integration, video extraction, FTP/SFTP upload, upload queue/history, categories, checksum verification, notifications, and tray/background operation.

## Important limitations

Resume depends on the remote server supporting byte-range requests and keeping the same resource. Upload requires a destination service that accepts HTTP PUT; this app does not bypass authentication, host policies, ISP limits, or network restrictions. The program itself does not cap transfer speed by default, but actual throughput is limited by the connection, remote server, and network path.
