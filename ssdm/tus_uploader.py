"""Resumable uploads for servers implementing the tus 1.0 protocol."""
from __future__ import annotations

import base64
import threading
import time
from pathlib import Path
from typing import Callable
from urllib.parse import urljoin

import requests


class TusUploadJob:
    def __init__(
        self,
        source: str,
        endpoint_url: str,
        progress: Callable[[int, int, float], None],
        finished: Callable[[str], None],
        failed: Callable[[str], None],
        *,
        upload_url: str | None = None,
        session_created: Callable[[str], None] | None = None,
        chunk_size: int = 1024 * 1024,
        timeout: tuple[int, int] = (20, 120),
    ) -> None:
        self.source = Path(source)
        self.endpoint_url = endpoint_url
        self.upload_url = upload_url
        self.progress = progress
        self.finished = finished
        self.failed = failed
        self.session_created = session_created or (lambda _url: None)
        self.chunk_size = chunk_size
        self.timeout = timeout
        self._cancel = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._cancel.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def cancel(self):
        self._cancel.set()

    def _create_session(self, total: int) -> str:
        metadata = base64.b64encode(f"filename {self.source.name}".encode()).decode()
        response = requests.post(
            self.endpoint_url,
            headers={
                "Tus-Resumable": "1.0.0",
                "Upload-Length": str(total),
                "Upload-Metadata": metadata,
            },
            timeout=self.timeout,
            allow_redirects=False,
        )
        if response.status_code != 201:
            raise RuntimeError(f"TUS session creation failed: HTTP {response.status_code}")
        location = response.headers.get("Location")
        if not location:
            raise RuntimeError("TUS server did not return a Location header")
        self.upload_url = urljoin(self.endpoint_url, location)
        self.session_created(self.upload_url)
        return self.upload_url

    def _run(self):
        try:
            if not self.source.is_file():
                raise FileNotFoundError(str(self.source))
            total = self.source.stat().st_size
            if not self.upload_url:
                self._create_session(total)
            headers = {"Tus-Resumable": "1.0.0"}
            head = requests.head(self.upload_url, headers=headers, timeout=self.timeout)
            if head.status_code in (404, 410):
                self.upload_url = None
                self._create_session(total)
                head = requests.head(self.upload_url, headers=headers, timeout=self.timeout)
            if head.status_code not in (200, 204):
                raise RuntimeError(f"TUS status check failed: HTTP {head.status_code}")
            offset = int(head.headers.get("Upload-Offset", "0"))
            if offset < 0 or offset > total:
                raise RuntimeError(f"TUS server returned invalid upload offset: {offset}")
            sent = offset
            started = time.monotonic()
            last_time, last_sent = started, sent
            with self.source.open("rb") as stream:
                stream.seek(offset)
                while sent < total:
                    if self._cancel.is_set():
                        return
                    chunk = stream.read(min(self.chunk_size, total - sent))
                    if not chunk:
                        break
                    response = requests.patch(
                        self.upload_url,
                        data=chunk,
                        headers={
                            "Tus-Resumable": "1.0.0",
                            "Upload-Offset": str(sent),
                            "Content-Type": "application/offset+octet-stream",
                        },
                        timeout=self.timeout,
                    )
                    if response.status_code != 204:
                        raise RuntimeError(f"TUS chunk upload failed: HTTP {response.status_code}")
                    new_offset = int(response.headers.get("Upload-Offset", "-1"))
                    if new_offset != sent + len(chunk):
                        raise RuntimeError("TUS server returned an unexpected upload offset")
                    sent = new_offset
                    now = time.monotonic()
                    speed = (sent - last_sent) / max(now - last_time, 0.001)
                    self.progress(sent, total, speed)
                    last_time, last_sent = now, sent
            if self._cancel.is_set():
                return
            if sent != total:
                raise RuntimeError(f"TUS upload incomplete: {sent} of {total} bytes")
            self.progress(total, total, 0.0)
            self.finished(str(self.source))
        except Exception as exc:
            if not self._cancel.is_set():
                self.failed(str(exc))
