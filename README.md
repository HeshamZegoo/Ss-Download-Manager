# Ss Download Manager

A Windows-first desktop download manager inspired by IDM-style download tools.

## Implemented in the current source

- Native PySide6 desktop interface.
- Real HTTP/HTTPS downloads with pause/resume; segmented multi-connection downloads when the server supports byte ranges, with a safe single-stream fallback.
- Persistent download history and retained partial download files.
- Per-download progress, speed, status, and search.
- Batch URL import (one URL per line), configurable per-file connection count, and a bounded active-download queue.
- Persistent default download-folder preference shared by manual, batch, clipboard, and browser-added downloads.
- Queue ordering controls, a configurable simultaneous-download limit, and a clipboard URL monitor with user confirmation.
- Scheduled download start times, an optional aggregate download speed cap, and system-tray notifications/background operation where supported.
- Upload queue with configurable concurrency, ordering, progress, cancellation, and pause/resume controls; SFTP and FTP/FTPS continue from the remote partial file when supported, while plain HTTP PUT restarts from the beginning.
- Automatic file categories (video, audio, images, archives, documents, programs, other).
- Choose destination folders and open completed files/folders.
- SHA-256 calculation and optional comparison against a supplied checksum.
- Video grabber for supported sites using yt-dlp, with progress reporting and cancellation.
- No application-imposed transfer speed cap by default.

## Run from source

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python main.py
```

## Uploading

Choose **Upload file**, select a local file, then choose HTTP PUT, SFTP, FTP, or FTPS. HTTP requires a destination URL that accepts PUT. SFTP requires an `sftp://username@host:22/remote/path` destination, a password, and a server host key already trusted in the local SSH `known_hosts` file. FTP/FTPS use `ftp://username@host:21/remote/path` or `ftps://username@host:21/remote/path`; prefer FTPS because plain FTP does not encrypt credentials or file contents. SFTP and FTP/FTPS resume from the remote file size when supported. Passwords are not saved.

## Browser integration (source preview)

The repository includes Chromium (Chrome, Edge, Brave) and Firefox extension source under `browser/`. The extensions add context-menu actions to send a link, the current page, or selected URL text to Ss Download Manager. They communicate through the native-messaging host; the desktop app polls its local inbox and adds validated HTTP(S) URLs to the queue. This avoids a local HTTP listener.

The native host executable is produced separately during final packaging:

```powershell
.\tools\build-native-host.ps1
```

Copy `dist\ssdm-native-host.exe` into the application install directory, load the matching extension directory as an unpacked extension, then register the host from a current-user PowerShell session. Pass all Chromium extension IDs (Chrome, Edge, and Brave) returned by each browser's extension details page:

```powershell
.\browser\install-browser-host.ps1 -InstallDir "C:\Program Files\Ss Download Manager" -ChromiumExtensionIds @("aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb")
```

Firefox uses the fixed extension ID `ss-download-manager@heshamzegoo`; the installer registers the host for Firefox as well. The native host manifest is generated for the actual install path. These source extensions are not yet store-signed or automatically installed; final application packaging will include host installation and browser-specific extension distribution. Browser downloads are not silently cancelled or duplicated: links are sent when the user chooses an Ss Download Manager context-menu action.

## Tests

```powershell
python -m unittest discover -s tests -v
```

GitHub Actions currently runs validation only. Windows EXE packaging is deliberately deferred until the requested feature set is implemented and tested.

## Still to implement

- Resumable HTTP uploads for servers implementing the tus protocol and polished theme/preferences controls.

## Limitations

Resume depends on the server supporting byte ranges and keeping the same resource. Scheduled tasks run only while the application remains running. HTTP upload requires a destination service that accepts PUT. Actual transfer speed depends on the user's network, remote server, and network path; the application does not bypass authentication, host policies, or ISP limits.
