"""SFTP upload worker with strict SSH host-key verification."""
from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Callable
from urllib.parse import unquote, urlparse

import paramiko


class SFTPUploadJob:
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
        self._client = None

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._cancel.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def cancel(self):
        self._cancel.set()
        if self._client:
            try:
                self._client.close()
            except Exception:
                pass

    def _run(self):
        try:
            if not self.source.is_file():
                raise FileNotFoundError(str(self.source))
            parsed = urlparse(self.destination_url)
            if parsed.scheme != "sftp" or not parsed.hostname or not parsed.username or not parsed.path:
                raise ValueError("Use sftp://username@host:22/remote/path")
            total = self.source.stat().st_size
            sent_state = [0]
            last_sample = [time.monotonic(), 0]
            client = paramiko.SSHClient()
            client.load_system_host_keys()
            client.set_missing_host_key_policy(paramiko.RejectPolicy())
            self._client = client
            client.connect(
                hostname=parsed.hostname, port=parsed.port or 22,
                username=unquote(parsed.username), password=self.password,
                timeout=20, banner_timeout=20, auth_timeout=20,
                allow_agent=True, look_for_keys=True,
            )
            if self._cancel.is_set():
                return
            sftp = client.open_sftp()
            remote_path = unquote(parsed.path)

            try:
                remote_size = sftp.stat(remote_path).st_size
            except (OSError, IOError):
                remote_size = 0
            if remote_size > total:
                raise ValueError("Remote partial file is larger than the local file; remove it and retry")
            sent_state[0] = remote_size
            if remote_size < total:
                mode = "r+b" if remote_size else "wb"
                with self.source.open("rb") as local, sftp.open(remote_path, mode) as remote:
                    local.seek(remote_size)
                    remote.seek(remote_size)
                    while True:
                        if self._cancel.is_set():
                            raise OSError("Upload cancelled")
                        chunk = local.read(256 * 1024)
                        if not chunk:
                            break
                        remote.write(chunk)
                        sent_state[0] += len(chunk)
                        now = time.monotonic()
                        speed = (sent_state[0] - last_sample[1]) / max(now - last_sample[0], 0.001)
                        last_sample[:] = [now, sent_state[0]]
                        self.progress(sent_state[0], total, speed)
                    remote.flush()
            if self._cancel.is_set():
                return
            self.progress(total, total, 0.0)
            self.finished(str(self.source))
        except Exception as exc:
            if not self._cancel.is_set():
                self.failed(str(exc))
        finally:
            if self._client:
                try:
                    self._client.close()
                except Exception:
                    pass
                self._client = None
