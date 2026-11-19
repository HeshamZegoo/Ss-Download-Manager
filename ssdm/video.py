"""Video download worker powered by yt-dlp."""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Callable

import yt_dlp


class VideoDownloadJob:
    def __init__(self, url: str, folder: str,
                 progress: Callable[[float, str], None],
                 finished: Callable[[str], None],
                 failed: Callable[[str], None]) -> None:
        self.url = url
        self.folder = Path(folder)
        self.progress = progress
        self.finished = finished
        self.failed = failed
        self._cancel = threading.Event()
        self._thread = None

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._cancel.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def cancel(self):
        self._cancel.set()

    def _run(self):
        try:
            self.folder.mkdir(parents=True, exist_ok=True)

            def hook(data):
                if self._cancel.is_set():
                    raise yt_dlp.utils.DownloadError("Cancelled by user")
                status = data.get("status")
                if status == "downloading":
                    total = data.get("total_bytes") or data.get("total_bytes_estimate") or 0
                    downloaded = data.get("downloaded_bytes", 0)
                    percent = (downloaded / total * 100) if total else 0.0
                    speed = data.get("speed") or 0
                    self.progress(percent, f"{speed / 1024:.1f} KiB/s" if speed else "—")
                elif status == "finished":
                    self.progress(100.0, "Merging / finalizing…")

            options = {
                "format": "bestvideo*+bestaudio/best",
                "outtmpl": str(self.folder / "%(title).180B [%(id)s].%(ext)s"),
                "merge_output_format": "mp4",
                "noplaylist": True,
                "progress_hooks": [hook],
                "quiet": True,
                "no_warnings": True,
                "continuedl": True,
                "overwrites": False,
            }
            with yt_dlp.YoutubeDL(options) as ydl:
                info = ydl.extract_info(self.url, download=True)
                if self._cancel.is_set():
                    return
                path = info.get("filepath") or ydl.prepare_filename(info)
            self.finished(str(path))
        except Exception as exc:
            if not self._cancel.is_set():
                self.failed(str(exc))
