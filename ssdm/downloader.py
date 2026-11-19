"""Resumable HTTP downloader with safe segmented range downloads."""
from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable
from urllib.parse import unquote, urlparse

import requests


_limit_lock = threading.Lock()
_limit_kbps = 0
_next_transfer_time = 0.0


def set_download_speed_limit(kbps: int):
    """Set an aggregate download cap in KiB/s; zero means unlimited."""
    global _limit_kbps, _next_transfer_time
    with _limit_lock:
        _limit_kbps = max(0, int(kbps))
        _next_transfer_time = time.monotonic()


def _throttle_download(amount: int, stopped) -> bool:
    global _next_transfer_time
    with _limit_lock:
        limit = _limit_kbps
        if limit <= 0:
            return not stopped()
        now = time.monotonic()
        start = max(now, _next_transfer_time)
        _next_transfer_time = start + amount / (limit * 1024)
    while True:
        if stopped():
            return False
        remaining = start - time.monotonic()
        if remaining <= 0:
            return True
        time.sleep(min(remaining, 0.1))


class DownloadError(Exception):
    pass


def filename_from_url(url: str) -> str:
    name = unquote(Path(urlparse(url).path).name)
    return name or "download.bin"


class DownloadJob:
    def __init__(
        self, url: str, destination: str,
        progress: Callable[[int, int | None, float], None],
        finished: Callable[[str], None], failed: Callable[[str], None],
        paused: Callable[[], None] | None = None,
        chunk_size: int = 256 * 1024,
        max_connections: int = 8,
    ) -> None:
        self.url = url
        self.destination = Path(destination)
        self.part_path = Path(str(self.destination) + ".part")
        self.progress, self.finished, self.failed = progress, finished, failed
        self.paused = paused or (lambda: None)
        self.chunk_size = chunk_size
        self.max_connections = max(1, min(int(max_connections), 32))
        self._pause = threading.Event()
        self._cancel = threading.Event()
        self._thread = None
        self._response = None
        self._active = set()
        self._lock = threading.Lock()

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._pause.clear()
        self._cancel.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def pause(self):
        self._pause.set()
        with self._lock:
            active = list(self._active)
        for response in active:
            try:
                response.close()
            except Exception:
                pass

    def cancel(self, delete_partial=False):
        self._cancel.set()
        self._pause.clear()
        with self._lock:
            active = list(self._active)
        for response in active:
            try:
                response.close()
            except Exception:
                pass
        if delete_partial:
            for path in [self.part_path, *self.part_path.parent.glob(self.part_path.name + ".seg*"),
                         Path(str(self.part_path) + ".meta")]:
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    # On Windows an open worker file may remain locked until its thread exits.
                    pass

    def _track(self, response):
        with self._lock:
            self._active.add(response)

    def _untrack(self, response):
        with self._lock:
            self._active.discard(response)

    def _run(self):
        try:
            self.destination.parent.mkdir(parents=True, exist_ok=True)
            # Probe range support and total length without downloading the body.
            with requests.get(
                self.url, headers={"Range": "bytes=0-0", "Accept-Encoding": "identity",
                                   "User-Agent": "SsDownloadManager/1.0"},
                stream=True, timeout=(20, 30), allow_redirects=True,
            ) as probe:
                supports_ranges = probe.status_code == 206
                cr = probe.headers.get("Content-Range", "")
                total = _total_from_content_range(cr) if supports_ranges else _int_header(probe.headers.get("Content-Length"))
                probe.close()
            if self.max_connections > 1 and supports_ranges and total and total > self.chunk_size:
                self._run_segmented(total)
            else:
                self._run_single()
        except Exception as exc:
            if self._cancel.is_set():
                return
            if self._pause.is_set():
                self.paused()
                return
            self.failed(str(exc))

    def _run_single(self):
        offset = self.part_path.stat().st_size if self.part_path.exists() else 0
        headers = {"User-Agent": "SsDownloadManager/1.0", "Accept-Encoding": "identity"}
        if offset:
            headers["Range"] = f"bytes={offset}-"
        with requests.get(self.url, headers=headers, stream=True, timeout=(20, 30), allow_redirects=True) as response:
            self._track(response)
            if offset and response.status_code == 206:
                cr = response.headers.get("Content-Range", "")
                if not cr.startswith(f"bytes {offset}-"):
                    raise DownloadError("Invalid Range response; restart this download.")
                mode, total = "ab", _total_from_content_range(cr)
            elif offset and response.status_code == 200:
                offset, mode = 0, "wb"
                total = _int_header(response.headers.get("Content-Length"))
            else:
                response.raise_for_status()
                mode = "wb"
                total = _total_from_content_range(response.headers.get("Content-Range", "")) or _int_header(response.headers.get("Content-Length"))
            received, last_time, last_bytes = offset, time.monotonic(), offset
            with self.part_path.open(mode) as output:
                for chunk in response.iter_content(self.chunk_size):
                    if self._cancel.is_set() or self._pause.is_set():
                        break
                    if not chunk:
                        continue
                    if not _throttle_download(len(chunk), lambda: self._cancel.is_set() or self._pause.is_set()):
                        break
                    output.write(chunk)
                    received += len(chunk)
                    now = time.monotonic()
                    if now - last_time >= .3:
                        self.progress(received, total, (received-last_bytes)/(now-last_time))
                        last_time, last_bytes = now, received
                output.flush()
                os.fsync(output.fileno())
            self._untrack(response)
        if self._cancel.is_set():
            return
        if self._pause.is_set():
            self.progress(received, total, 0.0)
            self.paused()
            return
        if total is not None and received != total:
            raise DownloadError(f"Download ended early ({received} of {total} bytes). Resume is available.")
        os.replace(self.part_path, self.destination)
        self.progress(received, total, 0.0)
        self.finished(str(self.destination))

    def _run_segmented(self, total):
        count = min(self.max_connections, max(2, (total + self.chunk_size - 1)//self.chunk_size))
        ranges = []
        meta_path = Path(str(self.part_path) + ".meta")
        identity = hashlib.sha256(self.url.encode("utf-8")).hexdigest()
        try:
            previous = json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            previous = {}
        expected_meta = {"count": count, "total": total, "url": identity}
        if previous != expected_meta:
            for stale in self.part_path.parent.glob(self.part_path.name + ".seg*"):
                stale.unlink(missing_ok=True)
            meta_path.write_text(json.dumps(expected_meta), encoding="utf-8")
        for index in range(count):
            start = total * index // count
            end = total * (index + 1) // count - 1
            path = Path(str(self.part_path) + f".seg{index}")
            if path.exists():
                size = path.stat().st_size
                if size > end-start+1:
                    path.unlink()
                    size = 0
            else:
                size = 0
            ranges.append((index, start, end, path, size))
        initial = sum(item[4] for item in ranges)
        transferred = [initial]
        transfer_lock = threading.Lock()
        started = time.monotonic()
        last_report = [started, initial]

        def worker(item):
            index, start, end, path, existing = item
            position = start + existing
            if position > end:
                return
            headers = {"Range": f"bytes={position}-{end}", "Accept-Encoding": "identity",
                       "User-Agent": "SsDownloadManager/1.0"}
            with requests.get(self.url, headers=headers, stream=True, timeout=(20, 30), allow_redirects=True) as response:
                self._track(response)
                if response.status_code != 206:
                    raise DownloadError("Server stopped supporting byte ranges; restart this download.")
                expected_prefix = f"bytes {position}-"
                returned_range = response.headers.get("Content-Range", "")
                if returned_range != f"bytes {position}-{end}/{total}":
                    raise DownloadError("Server returned an invalid segment range.")
                with path.open("ab" if existing else "wb") as output:
                    for chunk in response.iter_content(self.chunk_size):
                        if self._cancel.is_set() or self._pause.is_set():
                            break
                        if not chunk:
                            continue
                        if not _throttle_download(len(chunk), lambda: self._cancel.is_set() or self._pause.is_set()):
                            break
                        output.write(chunk)
                        with transfer_lock:
                            transferred[0] += len(chunk)
                            now = time.monotonic()
                            if now - last_report[0] >= .3:
                                speed = (transferred[0]-last_report[1])/(now-last_report[0])
                                self.progress(transferred[0], total, speed)
                                last_report[:] = [now, transferred[0]]
                    output.flush()
                    os.fsync(output.fileno())
                self._untrack(response)

        with ThreadPoolExecutor(max_workers=count) as pool:
            futures = [pool.submit(worker, item) for item in ranges]
            for future in futures:
                future.result()
        if self._cancel.is_set():
            return
        if self._pause.is_set():
            self.progress(transferred[0], total, 0.0)
            self.paused()
            return
        for _, start, end, path, _ in ranges:
            expected = end-start+1
            if not path.exists() or path.stat().st_size != expected:
                raise DownloadError("A download segment is incomplete. Resume to continue.")
        with self.part_path.open("wb") as output:
            for _, _, _, path, _ in ranges:
                with path.open("rb") as source:
                    while True:
                        block = source.read(1024 * 1024)
                        if not block:
                            break
                        output.write(block)
            output.flush()
            os.fsync(output.fileno())
        for _, _, _, path, _ in ranges:
            path.unlink(missing_ok=True)
        meta_path.unlink(missing_ok=True)
        if self.part_path.stat().st_size != total:
            raise DownloadError("Final file size does not match the server's advertised size.")
        os.replace(self.part_path, self.destination)
        self.progress(total, total, 0.0)
        self.finished(str(self.destination))


def _int_header(value):
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _total_from_content_range(value):
    try:
        return int(value.rsplit("/", 1)[1])
    except (IndexError, ValueError):
        return None
