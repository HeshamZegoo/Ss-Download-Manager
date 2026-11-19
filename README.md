# Ss Download Manager

**Developer:** [HeshamZegoo](https://github.com/HeshamZegoo)  
**Copyright:** Copyright © 2026 HeshamZegoo

A Windows-first desktop download manager inspired by IDM-style download tools.

## Implemented in the current source

- Original HTML/CSS desktop interface hosted in Qt WebEngine, with Python download engine integration.
- Real HTTP/HTTPS downloads with pause/resume; segmented multi-connection downloads when the server supports byte ranges, with a safe single-stream fallback.
- Persistent download history and retained partial download files.
- Per-download progress, speed, status, and search.
- Batch URL import (one URL per line), configurable per-file connection count, and a bounded active-download queue.
- Persistent default download-folder preference shared by manual, batch, clipboard, and browser-added downloads, plus light/dark themes.
- Queue ordering controls, a configurable simultaneous-download limit, and a clipboard URL monitor with user confirmation.
- Scheduled download start times, an optional aggregate download speed cap, and system-tray notifications/background operation where supported.
- Upload queue with configurable concurrency, ordering, progress, cancellation, and pause/resume controls; SFTP and FTP/FTPS continue from the remote partial file when supported, while plain HTTP PUT restarts from the beginning.
- Resumable HTTP uploads using the tus 1.0 protocol, including persisted upload-session URLs so interrupted transfers can continue after restarting the app.
- Automatic file categories (video, audio, images, archives, documents, programs, other).
- Choose destination folders and open completed files/folders.
- SHA-256 calculation and optional comparison against a supplied checksum.
- Video grabber for supported sites using yt-dlp, with progress reporting and cancellation.
- No application-imposed transfer speed cap by default.

- BitTorrent support for magnet links and .torrent files, with DHT/LSD/UPnP/NAT-PMP, persisted fast-resume data, pause/resume/removal, peer/seed statistics, ETA, configurable active torrent queue, and independent download/upload bandwidth limits (0 = unlimited).

## Run from source

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python main.py
```

## Uploading

Choose **Upload file**, select a local file, then choose HTTP PUT, TUS resumable, SFTP, FTP, or FTPS. HTTP PUT requires a destination URL that accepts PUT. TUS requires a server endpoint implementing the tus 1.0 protocol; its session URL is stored in the local transfer history to support restart recovery. Treat that URL as sensitive because some TUS servers use it as a capability to continue the upload. SFTP requires an `sftp://username@host:22/remote/path` destination, a password, and a server host key already trusted in the local SSH `known_hosts` file. FTP/FTPS use `ftp://username@host:21/remote/path` or `ftps://username@host:21/remote/path`; prefer FTPS because plain FTP does not encrypt credentials or file contents. SFTP and FTP/FTPS resume from the remote file size when supported. Passwords are not saved.

## Windows setup

The release artifact includes `Ss-Download-Manager-Setup.exe`. Run it once: it installs the desktop app, native messaging host, browser extension files, Start Menu shortcut, optional desktop shortcut, and registers the native bridge for Chrome, Edge, Brave, and Firefox.

**One browser-security step remains:** Chromium browsers require the user to enable Developer mode and click **Load unpacked**, then select the installed `browser\\chromium` folder. Firefox requires **Load Temporary Add-on** and selecting `browser\\firefox\\manifest.json`; temporary Firefox add-ons are removed when Firefox closes. Permanent Firefox distribution requires Mozilla signing. This confirmation is enforced by browser security; a normal desktop installer cannot silently bypass it. The installer writes exact instructions to `Browser-Setup.txt`.

The extensions add toolbar and context-menu actions to send the current page, a link, or selected URL text to Ss Download Manager. They can also watch newly created HTTP(S) browser downloads and hand the URL to the desktop application through native messaging. The browser's download is cancelled only after the desktop native host confirms receipt. This behavior requires the extension to be loaded and the desktop app/native host to be installed.

## Tests

```powershell
python -m unittest discover -s tests -v
```

Pushes to `main` run source validation and tests only. The Windows EXE/setup packaging job is deliberately manual (`workflow_dispatch`) and is reserved for the final release step after all requested features and tests are complete.

## Limitations

Resume depends on the server supporting byte ranges and keeping the same resource. Scheduled tasks run only while the application remains running. HTTP upload requires a destination service that accepts PUT. Actual transfer speed depends on the user's network, remote server, and network path; the application does not bypass authentication, host policies, or ISP limits.
