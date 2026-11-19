from __future__ import annotations

import json
import re
import time
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal

try:
    import libtorrent as lt
except ImportError:  # Keep HTTP downloads usable if the optional engine is unavailable.
    lt = None


class TorrentManager(QObject):
    """Small libtorrent session wrapper with persistent fast-resume data."""

    changed = Signal(list)
    error = Signal(str)

    def __init__(self, state_dir: Path, parent=None):
        super().__init__(parent)
        if lt is None:
            raise RuntimeError("The bundled libtorrent engine is unavailable.")
        self.state_dir = Path(state_dir) / "torrents"
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.session = lt.session({
            "enable_dht": True,
            "enable_lsd": True,
            "enable_upnp": True,
            "enable_natpmp": True,
            "alert_mask": int(lt.alert.category_t.error_notification
                              | lt.alert.category_t.status_notification
                              | lt.alert.category_t.storage_notification),
        })
        self.limits = {"max_active": 3, "download_kib": 0, "upload_kib": 0}
        self.handles = {}
        self.meta = {}
        self._last_save = 0.0
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self._tick)
        self._restore()
        self.timer.start()

    def set_limits(self, max_active=3, download_kib=0, upload_kib=0):
        """Set the global torrent queue and bandwidth limits; zero means unlimited."""
        max_active = max(1, min(int(max_active), 64))
        download_kib = max(0, int(download_kib))
        upload_kib = max(0, int(upload_kib))
        settings = {
            "active_downloads": max_active,
            "download_rate_limit": download_kib * 1024,
            "upload_rate_limit": upload_kib * 1024,
        }
        self.session.apply_settings(settings)
        self.limits = {
            "max_active": max_active,
            "download_kib": download_kib,
            "upload_kib": upload_kib,
        }

    @staticmethod
    def valid_magnet(uri: str) -> bool:
        return uri.strip().lower().startswith("magnet:?") and "xt=urn:btih:" in uri.lower()

    def add(self, source: str, save_path: str):
        source = str(source).strip()
        folder = Path(save_path).expanduser()
        folder.mkdir(parents=True, exist_ok=True)
        if source.lower().startswith("magnet:"):
            if not self.valid_magnet(source):
                raise ValueError("This magnet link does not contain a valid BitTorrent info-hash.")
            params = lt.parse_magnet_uri(source)
            params.save_path = str(folder)
            handle = self.session.add_torrent(params)
        else:
            torrent_file = Path(source).expanduser()
            if not torrent_file.is_file() or torrent_file.suffix.lower() != ".torrent":
                raise ValueError("Choose a valid .torrent file or paste a magnet link.")
            params = {"ti": lt.torrent_info(str(torrent_file)), "save_path": str(folder)}
            handle = self.session.add_torrent(params)
        info_hash = str(handle.info_hash())
        if info_hash not in self.handles:
            self.handles[info_hash] = handle
            self.meta[info_hash] = {"save_path": str(folder), "source": source}
            self._write_index()
        self._emit_status()
        return info_hash

    def pause(self, info_hash: str):
        handle = self.handles.get(info_hash)
        if handle and handle.is_valid():
            handle.pause()
            handle.save_resume_data()

    def resume(self, info_hash: str):
        handle = self.handles.get(info_hash)
        if handle and handle.is_valid():
            handle.resume()

    def remove(self, info_hash: str, delete_files=False):
        handle = self.handles.pop(info_hash, None)
        self.meta.pop(info_hash, None)
        if handle and handle.is_valid():
            flags = lt.options_t.delete_files if delete_files else lt.options_t.delete_partfile
            self.session.remove_torrent(handle, flags)
        (self.state_dir / (self._safe_hash(info_hash) + ".fastresume")).unlink(missing_ok=True)
        self._write_index()
        self._emit_status()

    def _safe_hash(self, value: str) -> str:
        return re.sub(r"[^a-fA-F0-9]", "", value)[:64] or "unknown"

    def _write_index(self):
        index = {key: value for key, value in self.meta.items()}
        temp = self.state_dir / "index.json.tmp"
        temp.write_text(json.dumps(index, indent=2), encoding="utf-8")
        temp.replace(self.state_dir / "index.json")

    def _restore(self):
        index_file = self.state_dir / "index.json"
        try:
            self.meta = json.loads(index_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            self.meta = {}
        for info_hash, meta in list(self.meta.items()):
            resume = self.state_dir / (self._safe_hash(info_hash) + ".fastresume")
            if not resume.is_file():
                continue
            try:
                params = lt.read_resume_data(lt.bdecode(resume.read_bytes()))
                params.save_path = meta["save_path"]
                handle = self.session.add_torrent(params)
                self.handles[info_hash] = handle
            except Exception as exc:
                self.error.emit(f"Could not restore torrent {info_hash}: {exc}")

    def _tick(self):
        try:
            for alert in self.session.pop_alerts():
                if isinstance(alert, lt.save_resume_data_alert):
                    info_hash = str(alert.handle.info_hash())
                    path = self.state_dir / (self._safe_hash(info_hash) + ".fastresume")
                    path.write_bytes(lt.bencode(alert.params))
                elif isinstance(alert, lt.save_resume_data_failed_alert):
                    self.error.emit(str(alert.message()))
                elif isinstance(alert, lt.torrent_error_alert):
                    self.error.emit(str(alert.message()))
            self._emit_status()
            if time.monotonic() - self._last_save > 30:
                self._last_save = time.monotonic()
                for handle in self.handles.values():
                    if handle.is_valid():
                        handle.save_resume_data()
        except Exception as exc:
            self.error.emit(str(exc))

    def _emit_status(self):
        rows = []
        for info_hash, handle in list(self.handles.items()):
            if not handle.is_valid():
                continue
            status = handle.status()
            total = int(getattr(status, "total_wanted", 0) or 0)
            done = int(getattr(status, "total_wanted_done", 0) or 0)
            rows.append({
                "id": info_hash,
                "name": str(getattr(status, "name", "") or info_hash),
                "progress": float(getattr(status, "progress", 0.0) or 0.0) * 100,
                "downloaded": done,
                "total": total,
                "download_rate": int(getattr(status, "download_rate", 0) or 0),
                "upload_rate": int(getattr(status, "upload_rate", 0) or 0),
                "eta_seconds": (
                    max(0, int((total - done) / int(getattr(status, "download_rate", 0))))
                    if int(getattr(status, "download_rate", 0) or 0) > 0 and total > done else
                    (0 if total > 0 and done >= total else None)
                ),
                "seeds": int(getattr(status, "num_seeds", 0) or 0),
                "peers": int(getattr(status, "num_peers", 0) or 0),
                "state": str(getattr(status, "state", "unknown")),
                "save_path": self.meta.get(info_hash, {}).get("save_path", ""),
            })
        self.changed.emit(rows)

    def shutdown(self):
        self.timer.stop()
        for handle in self.handles.values():
            if handle.is_valid():
                handle.save_resume_data()
        self._write_index()
