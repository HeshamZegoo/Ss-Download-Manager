"""FTP and explicit FTPS upload worker with restart support when REST STOR is available."""
from __future__ import annotations

import ftplib
import ssl
import ssl
import threading
import time
from pathlib import Path
from typing import Callable
from urllib.parse import unquote, urlparse


class FTPUploadJob:
    def __init__(self, source: str, destination_url: str, password: str,
                 progress: Callable[[int, int, float], None],
                 finished: Callable[[str], None],
                 failed: Callable[[str], None]) -> None:
        self.source = Path(source)
        self.destination_url = destination_url
        self.password = password
        self.progress = progress
        self.finished = finished
        self.failed = failed
        self._cancel = threading.Event()
        self._thread = None
        self._ftp = None

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._cancel.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def cancel(self):
        self._cancel.set()
        if self._ftp:
            try:
                self._ftp.abort()
            except Exception:
                try:
                    self._ftp.close()
                except Exception:
                    pass

    def _run(self):
        try:
            if not self.source.is_file():
                raise FileNotFoundError(str(self.source))
            parsed = urlparse(self.destination_url)
            if parsed.scheme not in ("ftp", "ftps") or not parsed.hostname or not parsed.path:
                raise ValueError("Use ftp://user@host:21/remote/file or ftps://user@host:21/remote/file")
            total = self.source.stat().st_size
            ftp = (ftplib.FTP_TLS(context=ssl.create_default_context(), timeout=30)
                   if parsed.scheme == "ftps" else ftplib.FTP(timeout=30))
            self._ftp = ftp
            ftp.connect(parsed.hostname, parsed.port or 21)
            username = unquote(parsed.username or "anonymous")
            ftp.login(username, self.password if parsed.username else "anonymous@")
            if parsed.scheme == "ftps":
                ftp.prot_p()
            remote_path = unquote(parsed.path)
            parent, filename = remote_path.rsplit("/", 1) if "/" in remote_path else ("", remote_path)
            if not filename:
                raise ValueError("Remote destination must include a filename")
            if parent:
                ftp.cwd(parent)
            offset = 0
            try:
                offset = ftp.size(filename) or 0
            except ftplib.all_errors:
                offset = 0
            if offset > total:
                raise ValueError("Remote partial file is larger than the local file; remove it and retry")
            sent = offset
            last = [time.monotonic(), sent]

            def report(block):
                nonlocal sent
                if self._cancel.is_set():
                    raise OSError("Upload cancelled")
                sent += len(block)
                now = time.monotonic()
                speed = (sent - last[1]) / max(now - last[0], 0.001)
                last[:] = [now, sent]
                self.progress(sent, total, speed)

            with self.source.open("rb") as stream:
                stream.seek(offset)
                if offset == total:
                    pass
                else:
                    ftp.storbinary(f"STOR {filename}", stream, blocksize=256 * 1024,
                                   callback=report, rest=offset if offset else None)
            if self._cancel.is_set():
                return
            if sent != total:
                raise IOError(f"Upload incomplete: {sent} of {total} bytes")
            self.progress(total, total, 0.0)
            self.finished(str(self.source))
        except Exception as exc:
            if not self._cancel.is_set():
                self.failed(str(exc))
        finally:
            if self._ftp:
                try:
                    self._ftp.quit()
                except Exception:
                    try:
                        self._ftp.close()
                    except Exception:
                        pass
                self._ftp = None
