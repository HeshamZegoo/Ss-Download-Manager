"""Threaded HTTP downloader with pause/resume and persistent partial files."""
from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Callable
from urllib.parse import unquote, urlparse

import requests


class DownloadError(Exception):
    pass


def filename_from_url(url: str) -> str:
    name = unquote(Path(urlparse(url).path).name)
    return name or "download.bin"


class DownloadJob:
    """A resumable single-stream HTTP download.

    A .part file is retained on pause or interruption. Resume uses Range and
    validates the server's Content-Range response before appending bytes.
    """

    def __init__(
        self,
        url: str,
        destination: str,
        progress: Callable[[int, int | None, float], None],
        finished: Callable[[str], None],
        failed: Callable[[str], None],
        paused: Callable[[], None] | None = None,
        chunk_size: int = 256 * 1024,
    ) -> None:
        self.url = url
        self.destination = Path(destination)
        self.part_path = Path(str(self.destination) + ".part")
        self.progress = progress
        self.finished = finished
        self.failed = failed
        self.paused = paused or (lambda: None)
        self.chunk_size = chunk_size
        self._pause = False
        self._cancel = False
        self._thread = None
        self._response = None

    def start(self) -> None:
        import threading
        if self._thread and self._thread.is_alive():
            return
        self._pause = False
        self._cancel = False
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def pause(self) -> None:
        # Let the current chunk finish so the partial file remains consistent.
        self._pause = True

    def cancel(self, delete_partial: bool = False) -> None:
        self._cancel = True
        self._pause = False
        response = self._response
        if response is not None:
            response.close()
        if delete_partial:
            try:
                self.part_path.unlink(missing_ok=True)
            except OSError:
                pass

    def _run(self) -> None:
        try:
            offset = self.part_path.stat().st_size if self.part_path.exists() else 0
            headers = {"User-Agent": "SsDownloadManager/0.1", "Accept-Encoding": "identity"}
            if offset:
                headers["Range"] = f"bytes={offset}-"

            with requests.get(self.url, headers=headers, stream=True, timeout=(20, 30), allow_redirects=True) as response:
                self._response = response
                if offset and response.status_code == 206:
                    content_range = response.headers.get("Content-Range", "")
                    if not content_range.startswith(f"bytes {offset}-"):
                        raise DownloadError("The server returned an invalid Range response; restart this download.")
                    mode = "ab"
                    total = _total_from_content_range(content_range)
                elif offset and response.status_code == 200:
                    # Server ignored Range. Restart safely rather than corrupting the file.
                    offset = 0
                    mode = "wb"
                    total = _int_header(response.headers.get("Content-Length"))
                elif response.status_code == 206:
                    mode = "wb"
                    total = _total_from_content_range(response.headers.get("Content-Range", ""))
                else:
                    response.raise_for_status()
                    mode = "wb"
                    total = _int_header(response.headers.get("Content-Length"))

                received = offset
                started = time.monotonic()
                last_time = started
                last_bytes = received
                with open(self.part_path, mode) as output:
                    for chunk in response.iter_content(chunk_size=self.chunk_size):
                        if self._cancel or self._pause:
                            break
                        if not chunk:
                            continue
                        output.write(chunk)
                        received += len(chunk)
                        now = time.monotonic()
                        if now - last_time >= 0.35:
                            speed = (received - last_bytes) / max(now - last_time, 0.001)
                            self.progress(received, total, speed)
                            last_time, last_bytes = now, received
                    output.flush()
                    os.fsync(output.fileno())

            self._response = None
            if self._cancel:
                return
            if self._pause:
                self.progress(received, total, 0.0)
                self.paused()
                return
            if total is not None and received != total:
                raise DownloadError(f"Download ended early ({received} of {total} bytes). You can resume it.")
            self.destination.parent.mkdir(parents=True, exist_ok=True)
            os.replace(self.part_path, self.destination)
            self.progress(received, total, 0.0)
            self.finished(str(self.destination))
        except Exception as exc:
            self._response = None
            if not self._cancel and not self._pause:
                self.failed(str(exc))


def _int_header(value: str | None) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _total_from_content_range(value: str) -> int | None:
    try:
        return int(value.rsplit("/", 1)[1])
    except (IndexError, ValueError):
        return None
