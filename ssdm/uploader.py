"""Real HTTP(S) upload worker.

Supports HTTP PUT targets such as WebDAV endpoints and pre-signed object-storage
URLs. Authentication and destination permissions are controlled by the server.
"""
from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Callable

import requests


class UploadError(Exception):
    """Raised when an HTTP upload cannot be completed."""


class UploadJob:
    def __init__(
        self,
        source: str,
        destination_url: str,
        progress: Callable[[int, int, float], None],
        finished: Callable[[str], None],
        failed: Callable[[str], None],
        *,
        headers: dict[str, str] | None = None,
        chunk_size: int = 256 * 1024,
        timeout: tuple[int, int] = (20, 120),
    ) -> None:
        self.source = Path(source)
        self.destination_url = destination_url
        self.progress = progress
        self.finished = finished
        self.failed = failed
        self.headers = dict(headers or {})
        self.chunk_size = chunk_size
        self.timeout = timeout
        self._cancel = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._cancel.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def cancel(self) -> None:
        self._cancel.set()

    def _run(self) -> None:
        try:
            if not self.source.is_file():
                raise UploadError(f"File does not exist: {self.source}")
            total = self.source.stat().st_size
            sent = 0
            started = time.monotonic()
            last_time = started
            last_sent = 0

            def body():
                nonlocal sent, last_time, last_sent
                with self.source.open("rb") as stream:
                    while not self._cancel.is_set():
                        chunk = stream.read(self.chunk_size)
                        if not chunk:
                            break
                        sent += len(chunk)
                        now = time.monotonic()
                        if now - last_time >= 0.25:
                            speed = (sent - last_sent) / max(now - last_time, 0.001)
                            self.progress(sent, total, speed)
                            last_time, last_sent = now, sent
                        yield chunk
                if self._cancel.is_set():
                    raise UploadError("Upload cancelled")

            headers = dict(self.headers)
            headers.setdefault("Content-Length", str(total))
            headers.setdefault("Content-Type", "application/octet-stream")
            response = requests.put(
                self.destination_url,
                data=body(),
                headers=headers,
                timeout=self.timeout,
                allow_redirects=True,
            )
            if self._cancel.is_set():
                return
            if not response.ok:
                raise UploadError(f"Upload failed: HTTP {response.status_code} {response.reason}")
            if sent != total:
                raise UploadError(f"Upload was interrupted ({sent} of {total} bytes sent).")
            self.progress(sent, total, 0.0)
            self.finished(str(self.source))
        except Exception as exc:
            if not self._cancel.is_set():
                self.failed(str(exc))
