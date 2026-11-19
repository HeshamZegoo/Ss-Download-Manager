from __future__ import annotations

import hashlib
from datetime import datetime
import json
import os
import sys
import time
import uuid
import webbrowser
from pathlib import Path
from urllib.parse import urlparse

from PySide6.QtCore import Qt, QTimer, Signal, QObject
from PySide6.QtGui import QAction, QDesktopServices
from PySide6.QtCore import QUrl, QSettings
from PySide6.QtWidgets import (
    QApplication, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QDateTimeEdit,
    QFormLayout, QHBoxLayout, QHeaderView, QLineEdit, QMainWindow,
    QMessageBox, QPushButton, QProgressBar, QTableWidget, QTableWidgetItem, QInputDialog,
    QToolBar, QVBoxLayout, QWidget, QLabel, QSystemTrayIcon, QMenu
)

from .downloader import DownloadJob, filename_from_url, set_download_speed_limit
from .uploader import UploadJob
from .video import VideoDownloadJob

APP_NAME = "Ss Download Manager"


def data_dir() -> Path:
    base = Path(os.environ.get("APPDATA", Path.home())) / "SsDownloadManager"
    base.mkdir(parents=True, exist_ok=True)
    return base


class JobSignals(QObject):
    progress = Signal(str, int, object, float)
    finished = Signal(str, str)
    failed = Signal(str, str)
    paused = Signal(str)
    upload_progress = Signal(str, int, int, float)
    upload_finished = Signal(str)
    upload_failed = Signal(str, str)
    video_progress = Signal(str, float, str)
    video_finished = Signal(str, str)
    video_failed = Signal(str, str)


class AddDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add download")
        self.setMinimumWidth(520)
        self.url = QLineEdit()
        self.url.setPlaceholderText("https://example.com/file.zip")
        self.folder = QLineEdit(str(Path.home() / "Downloads"))
        browse = QPushButton("Browse…")
        browse.clicked.connect(self.choose_folder)
        folder_row = QHBoxLayout()
        folder_row.addWidget(self.folder, 1)
        folder_row.addWidget(browse)
        form = QFormLayout()
        form.addRow("Download URL", self.url)
        form.addRow("Save folder", folder_row)
        self.setLayout(QVBoxLayout())
        self.layout().addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Add download")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        self.layout().addWidget(buttons)

    def choose_folder(self):
        path = QFileDialog.getExistingDirectory(self, "Choose download folder", self.folder.text())
        if path:
            self.folder.setText(path)

    def values(self):
        return self.url.text().strip(), self.folder.text().strip()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(1100, 700)
        self.setMinimumSize(820, 520)
        self.records = []
        self.jobs = {}
        self.upload_jobs = {}
        self.video_jobs = {}
        self.pausing_all = False
        self.settings = QSettings("SsDM", "SsDownloadManager")
        self.max_connections = self.settings.value("max_connections", 8, type=int)
        self.max_active_downloads = self.settings.value("max_active_downloads", 3, type=int)
        self.speed_limit_kbps = self.settings.value("speed_limit_kbps", 0, type=int)
        set_download_speed_limit(self.speed_limit_kbps)
        self.clipboard_monitoring = False
        self.signals = JobSignals()
        self.signals.progress.connect(self.on_progress)
        self.signals.finished.connect(self.on_finished)
        self.signals.failed.connect(self.on_failed)
        self.signals.paused.connect(self.on_paused)
        self.signals.upload_progress.connect(self.on_upload_progress)
        self.signals.upload_finished.connect(self.on_upload_finished)
        self.signals.upload_failed.connect(self.on_upload_failed)
        self.signals.video_progress.connect(self.on_video_progress)
        self.signals.video_finished.connect(self.on_video_finished)
        self.signals.video_failed.connect(self.on_video_failed)
        self.store = data_dir() / "downloads.json"
        self._load()

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(["File name", "Category", "Status", "Progress", "Downloaded", "Speed", "Location"])
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for col in range(1, 7):
            self.table.horizontalHeader().setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        self.setCentralWidget(self.table)

        toolbar = QToolBar("Downloads")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)
        for label, handler in [
            ("＋ Add URL", self.add_download),
            ("＋ Batch URLs", self.add_batch_downloads),
            ("Connections", self.configure_connections),
            ("Queue limit", self.configure_queue_limit),
            ("Speed limit", self.configure_speed_limit),
            ("Move up", self.move_selected_up),
            ("Move down", self.move_selected_down),
            ("Schedule", self.schedule_selected),
            ("Clipboard monitor: Off", self.toggle_clipboard_monitor),
            ("↑ Upload file", self.upload_file),
            ("Video grabber", self.grab_video),
            ("Cancel video", self.cancel_video),
            ("Cancel upload", self.cancel_upload),
            ("▶ Resume", self.resume_selected),
            ("Ⅱ Pause", self.pause_selected),
            ("■ Pause all", self.pause_all),
            ("✕ Remove", self.remove_selected),
            ("Verify SHA-256", self.verify_selected),
            ("Open file", self.open_selected),
            ("Open folder", self.open_folder_selected),
        ]:
            action = QAction(label, self)
            action.triggered.connect(handler)
            toolbar.addAction(action)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Search downloads…")
        self.search.textChanged.connect(self.refresh)
        self.statusBar().showMessage("Ready")
        self.setStyleSheet("""
            QMainWindow { background: #f3f5fb; }
            QTableWidget { background: white; border: 1px solid #e0e5f0; gridline-color: #edf0f6; }
            QHeaderView::section { background: #eef1f8; padding: 9px; border: 0; font-weight: 600; }
            QToolBar { background: white; border: 0; border-bottom: 1px solid #e0e5f0; spacing: 8px; padding: 8px; }
            QToolButton { padding: 8px 10px; border-radius: 7px; }
            QToolButton:hover { background: #e8edff; }
            QLineEdit { padding: 8px; border: 1px solid #d9deeb; border-radius: 7px; }
        """)
        self.addToolBarBreak()
        search_bar = QToolBar("Search")
        search_bar.addWidget(QLabel("  Filter: "))
        search_bar.addWidget(self.search)
        self.addToolBar(search_bar)
        self.refresh()
        self.tray = None
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray = QSystemTrayIcon(self)
            self.tray.setToolTip(APP_NAME)
            tray_menu = QMenu()
            show_action = tray_menu.addAction("Show Ss Download Manager")
            show_action.triggered.connect(self.showNormal)
            tray_menu.addSeparator()
            exit_action = tray_menu.addAction("Exit")
            exit_action.triggered.connect(QApplication.quit)
            self.tray.setContextMenu(tray_menu)
            self.tray.show()
        self.queue_timer = QTimer(self)
        self.queue_timer.setInterval(5000)
        self.queue_timer.timeout.connect(self._schedule_queue)
        self.queue_timer.start()

    def closeEvent(self, event):
        if self.tray and self.tray.isVisible():
            self.hide()
            self.tray.showMessage(APP_NAME, "Still running in the system tray.",
                                  QSystemTrayIcon.MessageIcon.Information, 3000)
            event.ignore()
            return
        event.accept()

    def _load(self):
        try:
            self.records = json.loads(self.store.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            self.records = []
        for record in self.records:
            record.setdefault("id", uuid.uuid4().hex)
            record.setdefault("downloaded", 0)
            record.setdefault("total", None)
            record.setdefault("speed", 0)
            record.setdefault("category", _category(record.get("name", "")))
            if record.get("status") == "Downloading":
                record["status"] = "Paused"

    def _save(self):
        self.store.parent.mkdir(parents=True, exist_ok=True)
        temp = self.store.with_suffix(".tmp")
        temp.write_text(json.dumps(self.records, indent=2), encoding="utf-8")
        temp.replace(self.store)

    def add_download(self):
        dialog = AddDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        url, folder = dialog.values()
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            QMessageBox.warning(self, "Invalid URL", "Enter a valid HTTP or HTTPS URL.")
            return
        if not folder:
            QMessageBox.warning(self, "Missing folder", "Choose where to save the file.")
            return
        name = filename_from_url(url)
        destination = str(Path(folder).expanduser() / name)
        if any(r["destination"] == destination for r in self.records):
            QMessageBox.warning(self, "Already added", "This destination is already in the download list.")
            return
        record = {"id": uuid.uuid4().hex, "url": url, "name": name, "destination": destination,
                  "status": "Queued", "downloaded": 0, "total": None, "speed": 0,
                  "category": _category(name)}
        self.records.insert(0, record)
        self._save()
        self.refresh()
        self._start(record)

    def _start(self, record):
        job_id = record["id"]
        if job_id in self.jobs:
            return
        if len(self.jobs) >= self.max_active_downloads:
            record["status"] = "Queued"
            self._save()
            self.refresh()
            return
        record["status"] = "Downloading"
        job = DownloadJob(
            record["url"], record["destination"],
            lambda done, total, speed, jid=job_id: self.signals.progress.emit(jid, done, total, speed),
            lambda path, jid=job_id: self.signals.finished.emit(jid, path),
            lambda error, jid=job_id: self.signals.failed.emit(jid, error),
            lambda jid=job_id: self.signals.paused.emit(jid),
            max_connections=self.max_connections,
        )
        self.jobs[job_id] = job
        self._save()
        job.start()
        self.refresh()

    def configure_speed_limit(self):
        value, ok = QInputDialog.getInt(
            self, "Download speed limit", "Aggregate limit in KiB/s (0 = unlimited):",
            self.speed_limit_kbps, 0, 10_000_000, 64
        )
        if ok:
            self.speed_limit_kbps = value
            self.settings.setValue("speed_limit_kbps", value)
            set_download_speed_limit(value)
            label = "Unlimited" if value == 0 else f"{value} KiB/s"
            self.statusBar().showMessage(f"Download speed limit: {label}", 5000)

    def configure_queue_limit(self):
        value, ok = QInputDialog.getInt(
            self, "Active downloads", "Maximum simultaneous files:",
            self.max_active_downloads, 1, 32, 1
        )
        if ok:
            self.max_active_downloads = value
            self.settings.setValue("max_active_downloads", value)
            self._schedule_queue()
            self.statusBar().showMessage(f"Maximum active downloads: {value}", 5000)

    def _schedule_queue(self):
        if self.pausing_all:
            return
        active = len(self.jobs)
        now = datetime.now()
        waiting = sorted(
            (r for r in self.records if r.get("status") == "Queued" or
             (r.get("status") == "Scheduled" and _schedule_due(r, now))),
            key=lambda r: r.get("priority", 0), reverse=True,
        )
        for record in waiting[:max(0, self.max_active_downloads - active)]:
            self._start(record)

    def schedule_selected(self):
        record = self._selected()
        if not record or record.get("status") in ("Downloading", "Completed"):
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("Schedule download")
        layout = QVBoxLayout(dialog)
        editor = QDateTimeEdit(dialog)
        editor.setCalendarPopup(True)
        editor.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        editor.setDateTime(editor.dateTime().currentDateTime().addSecs(300))
        layout.addWidget(QLabel("Start this download at:"))
        layout.addWidget(editor)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        record["scheduled_at"] = editor.dateTime().toString("yyyy-MM-ddTHH:mm:ss")
        record["status"] = "Scheduled"
        self._save()
        self.refresh()

    def move_selected_up(self):
        self._move_selected(-1)

    def move_selected_down(self):
        self._move_selected(1)

    def _move_selected(self, direction):
        record = self._selected()
        if not record or record.get("status") != "Queued":
            return
        index = self.records.index(record)
        target = index + direction
        if 0 <= target < len(self.records):
            other = self.records[target]
            self.records[target], self.records[index] = record, other
            self._save()
            self.refresh()

    def configure_connections(self):
        value, ok = QInputDialog.getInt(
            self, "Download connections", "Maximum parallel connections per file:",
            self.max_connections, 1, 32, 1
        )
        if ok:
            self.max_connections = value
            self.settings.setValue("max_connections", value)
            self.statusBar().showMessage(f"New downloads will use up to {value} connections", 5000)

    def toggle_clipboard_monitor(self):
        self.clipboard_monitoring = not self.clipboard_monitoring
        clipboard = QApplication.clipboard()
        if self.clipboard_monitoring:
            clipboard.dataChanged.connect(self.on_clipboard_changed)
            self.statusBar().showMessage("Clipboard URL monitoring enabled", 5000)
        else:
            try:
                clipboard.dataChanged.disconnect(self.on_clipboard_changed)
            except (RuntimeError, TypeError):
                pass
            self.statusBar().showMessage("Clipboard URL monitoring disabled", 5000)
        for action in self.findChildren(QAction):
            if action.text().startswith("Clipboard monitor:"):
                action.setText("Clipboard monitor: On" if self.clipboard_monitoring else "Clipboard monitor: Off")

    def on_clipboard_changed(self):
        if not self.clipboard_monitoring:
            return
        text = QApplication.clipboard().text().strip()
        parsed = urlparse(text)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            return
        if any(record.get("url") == text for record in self.records):
            return
        answer = QMessageBox.question(
            self, "Download detected", f"Add this copied URL to downloads?\\n{text}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if answer == QMessageBox.StandardButton.Yes:
            folder = str(Path.home() / "Downloads")
            name = filename_from_url(text)
            destination = str(Path(folder) / name)
            record = {
                "id": uuid.uuid4().hex, "url": text, "name": name,
                "destination": destination, "status": "Queued",
                "downloaded": 0, "total": None, "speed": 0, "category": _category(name),
            }
            self.records.insert(0, record)
            self._save()
            self.refresh()
            self._start(record)

    def add_batch_downloads(self):
        urls, ok = QInputDialog.getMultiLineText(
            self, "Batch downloads", "Paste one HTTP(S) URL per line:"
        )
        if not ok:
            return
        folder = QFileDialog.getExistingDirectory(
            self, "Choose download folder", str(Path.home() / "Downloads")
        )
        if not folder:
            return
        added = []
        known = {r["destination"] for r in self.records}
        for raw in urls.splitlines():
            url = raw.strip()
            parsed = urlparse(url)
            if parsed.scheme not in ("http", "https") or not parsed.netloc:
                continue
            name = filename_from_url(url)
            destination = str(Path(folder).expanduser() / name)
            if destination in known:
                continue
            known.add(destination)
            record = {
                "id": uuid.uuid4().hex, "url": url, "name": name,
                "destination": destination, "status": "Queued",
                "downloaded": 0, "total": None, "speed": 0, "category": _category(name),
            }
            self.records.insert(0, record)
            added.append(record)
        self._save()
        self.refresh()
        for record in added:
            self._start(record)
        self.statusBar().showMessage(f"Added {len(added)} valid downloads", 5000)

    def grab_video(self):
        url, ok = QInputDialog.getText(
            self, "Video grabber", "Video page URL (supported sites via yt-dlp):"
        )
        if not ok or not url.strip():
            return
        parsed = urlparse(url.strip())
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            QMessageBox.warning(self, "Invalid URL", "Enter a valid HTTP(S) video page URL.")
            return
        folder = QFileDialog.getExistingDirectory(
            self, "Save video to", str(Path.home() / "Videos")
        )
        if not folder:
            return
        video_id = uuid.uuid4().hex
        job = VideoDownloadJob(
            url.strip(), folder,
            lambda percent, speed, uid=video_id: self.signals.video_progress.emit(uid, percent, speed),
            lambda path, uid=video_id: self.signals.video_finished.emit(uid, path),
            lambda error, uid=video_id: self.signals.video_failed.emit(uid, error),
        )
        self.video_jobs[video_id] = job
        self.statusBar().showMessage("Video download started…")
        job.start()

    def cancel_video(self):
        if not self.video_jobs:
            self.statusBar().showMessage("No active video downloads", 3000)
            return
        video_id = next(reversed(self.video_jobs))
        job = self.video_jobs.pop(video_id)
        job.cancel()
        self.statusBar().showMessage("Video download cancelled", 4000)

    def on_video_progress(self, video_id, percent, speed):
        if video_id in self.video_jobs:
            self.statusBar().showMessage(f"Video: {percent:.1f}% · {speed}")

    def on_video_finished(self, video_id, path):
        self.video_jobs.pop(video_id, None)
        file_path = Path(path)
        try:
            size = file_path.stat().st_size
        except OSError:
            size = 0
        self.records.insert(0, {
            "id": video_id, "url": "", "name": file_path.name,
            "destination": str(file_path), "status": "Completed",
            "downloaded": size, "total": size, "speed": 0,
            "category": "Video", "source": "Video grabber",
        })
        self._save()
        self.refresh()
        self.statusBar().showMessage("Video download completed", 5000)
        if self.tray:
            self.tray.showMessage(APP_NAME, f"{file_path.name} downloaded.",
                                  QSystemTrayIcon.MessageIcon.Information, 5000)

    def on_video_failed(self, video_id, error):
        self.video_jobs.pop(video_id, None)
        QMessageBox.warning(self, "Video download failed", error)

    def upload_file(self):
        source, _ = QFileDialog.getOpenFileName(self, "Choose file to upload")
        if not source:
            return
        destination, ok = QInputDialog.getText(
            self, "Upload destination", "HTTP(S) PUT destination URL (WebDAV or pre-signed URL):"
        )
        if not ok or not destination.strip():
            return
        parsed = urlparse(destination.strip())
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            QMessageBox.warning(self, "Invalid destination", "Enter a valid HTTP or HTTPS upload URL.")
            return
        upload_id = uuid.uuid4().hex
        job = UploadJob(
            source, destination.strip(),
            lambda sent, total, speed, uid=upload_id: self.signals.upload_progress.emit(uid, sent, total, speed),
            lambda path, uid=upload_id: self.signals.upload_finished.emit(uid),
            lambda error, uid=upload_id: self.signals.upload_failed.emit(uid, error),
        )
        self.upload_jobs[upload_id] = job
        self.statusBar().showMessage(f"Uploading {Path(source).name}…")
        job.start()

    def cancel_upload(self):
        if not self.upload_jobs:
            self.statusBar().showMessage("No active uploads", 3000)
            return
        upload_id = next(reversed(self.upload_jobs))
        job = self.upload_jobs.pop(upload_id)
        job.cancel()
        self.statusBar().showMessage(f"Cancelled upload: {job.source.name}", 5000)

    def on_upload_progress(self, upload_id, sent, total, speed):
        job = self.upload_jobs.get(upload_id)
        if job:
            percent = (sent / total * 100) if total else 0
            self.statusBar().showMessage(
                f"Uploading {job.source.name}: {percent:.1f}% · {_human(speed)}/s"
            )

    def on_upload_finished(self, upload_id):
        job = self.upload_jobs.pop(upload_id, None)
        if job:
            QMessageBox.information(self, "Upload complete", f"{job.source.name} was uploaded successfully.")
            self.statusBar().showMessage("Upload completed", 5000)

    def on_upload_failed(self, upload_id, error):
        self.upload_jobs.pop(upload_id, None)
        QMessageBox.warning(self, "Upload failed", error)
        self.statusBar().showMessage("Upload failed", 5000)

    def _selected(self):
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return None
        visible = [r for r in self.records if self.search.text().lower() in r["name"].lower()]
        index = rows[0].row()
        return visible[index] if index < len(visible) else None

    def resume_selected(self):
        record = self._selected()
        if record and record["status"] in ("Paused", "Failed", "Queued"):
            self._start(record)

    def pause_selected(self):
        record = self._selected()
        if record and record["id"] in self.jobs:
            self.jobs[record["id"]].pause()
            record["status"] = "Paused"
            record["speed"] = 0
            self._save()
            self.refresh()

    def pause_all(self):
        self.pausing_all = True
        for record in self.records:
            if record["status"] == "Queued":
                record["status"] = "Paused"
            if record["id"] in self.jobs:
                self.jobs[record["id"]].pause()
                record["status"] = "Paused"
                record["speed"] = 0
        if not self.jobs:
            self.pausing_all = False
        self._save()
        self.refresh()

    def remove_selected(self):
        record = self._selected()
        if not record:
            return
        job = self.jobs.pop(record["id"], None)
        if job:
            job.cancel(delete_partial=True)
        else:
            Path(record["destination"] + ".part").unlink(missing_ok=True)
        self.records.remove(record)
        self._save()
        self.refresh()
        self._schedule_queue()

    def verify_selected(self):
        record = self._selected()
        if not record or record.get("status") != "Completed":
            QMessageBox.information(self, "SHA-256 verification", "Select a completed download first.")
            return
        path = Path(record["destination"])
        digest = hashlib.sha256()
        try:
            with path.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
        except OSError as exc:
            QMessageBox.warning(self, "Verification failed", str(exc))
            return
        actual = digest.hexdigest()
        expected, ok = QInputDialog.getText(
            self, "SHA-256 checksum", "Optional expected SHA-256 (leave blank to calculate only):"
        )
        if not ok:
            return
        if expected.strip():
            matched = actual.lower() == expected.strip().lower()
            QMessageBox.information(
                self, "Checksum result",
                ("MATCH\n" if matched else "MISMATCH\n") + f"SHA-256: {actual}"
            )
        else:
            QMessageBox.information(self, "SHA-256", actual)

    def open_selected(self):
        record = self._selected()
        if record and record["status"] == "Completed":
            QDesktopServices.openUrl(QUrl.fromLocalFile(record["destination"]))

    def open_folder_selected(self):
        record = self._selected()
        if record:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(record["destination"]).parent)))

    def on_progress(self, job_id, done, total, speed):
        record = self._by_id(job_id)
        if not record:
            return
        record["downloaded"], record["total"], record["speed"] = done, total, speed
        self.refresh()

    def on_paused(self, job_id):
        self.jobs.pop(job_id, None)
        if self.pausing_all and not self.jobs:
            self.pausing_all = False
        record = self._by_id(job_id)
        if record:
            record['status'] = 'Paused'
            record['speed'] = 0
        self._save()
        self.refresh()
        self._schedule_queue()

    def on_finished(self, job_id, path):
        self.jobs.pop(job_id, None)
        record = self._by_id(job_id)
        if record:
            record["status"] = "Completed"
            record["speed"] = 0
            record["destination"] = path
            if record["total"] is None:
                try:
                    record["total"] = Path(path).stat().st_size
                    record["downloaded"] = record["total"]
                except OSError:
                    pass
        self._save()
        self.refresh()
        self.statusBar().showMessage("Download completed", 5000)
        if self.tray:
            self.tray.showMessage(APP_NAME, f"{Path(path).name} downloaded successfully.",
                                  QSystemTrayIcon.MessageIcon.Information, 5000)
        self._schedule_queue()

    def on_failed(self, job_id, error):
        self.jobs.pop(job_id, None)
        record = self._by_id(job_id)
        if record:
            record["status"] = "Failed"
            record["speed"] = 0
            record["error"] = error
        self._save()
        self.refresh()
        if self.tray:
            self.tray.showMessage(APP_NAME, f"Download failed: {error}",
                                  QSystemTrayIcon.MessageIcon.Warning, 7000)
        else:
            QMessageBox.warning(self, "Download failed", error)
        self._schedule_queue()

    def _by_id(self, job_id):
        return next((r for r in self.records if r["id"] == job_id), None)

    def refresh(self):
        query = self.search.text().lower() if hasattr(self, "search") else ""
        visible = [r for r in self.records if query in r["name"].lower()]
        self.table.setRowCount(len(visible))
        for row, record in enumerate(visible):
            values = [
                record["name"], record.get("category", "Other"), record["status"],
                f"{(record['downloaded'] / record['total'] * 100):.1f}%" if record.get("total") else "—",
                _human(record.get("downloaded", 0)),
                _speed(record.get("speed", 0)),
                str(Path(record["destination"]).parent),
            ]
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                if col == 0:
                    item.setToolTip(record.get("url", ""))
                self.table.setItem(row, col, item)
        self.statusBar().showMessage(f"{len(self.records)} downloads · {sum(r['status'] == 'Downloading' for r in self.records)} active")


def _schedule_due(record, now):
    value = record.get("scheduled_at")
    if not value:
        return True
    try:
        return datetime.fromisoformat(value) <= now
    except ValueError:
        return True


def _category(name):
    ext = Path(name).suffix.lower()
    groups = {
        "Video": {".mp4", ".mkv", ".avi", ".mov", ".webm", ".m4v"},
        "Audio": {".mp3", ".wav", ".flac", ".aac", ".ogg", ".m4a"},
        "Images": {".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".bmp"},
        "Archives": {".zip", ".rar", ".7z", ".tar", ".gz", ".bz2"},
        "Documents": {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".txt"},
        "Programs": {".exe", ".msi", ".msix", ".apk", ".deb", ".rpm"},
    }
    return next((category for category, extensions in groups.items() if ext in extensions), "Other")


def _human(size):
    value = float(size or 0)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} TB"


def _speed(value):
    return f"{_human(value)}/s" if value else "—"


def main():
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
