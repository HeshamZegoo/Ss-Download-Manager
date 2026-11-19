from __future__ import annotations

import hashlib
from datetime import datetime
import json
import os
import sys
import time
import traceback
import uuid
import webbrowser
from pathlib import Path
from urllib.parse import urlparse

from PySide6.QtCore import Qt, QTimer, Signal, QObject, Slot
from PySide6.QtGui import QAction, QDesktopServices, QIcon
from PySide6.QtCore import QUrl, QSettings
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWidgets import (
    QApplication, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QDateTimeEdit,
    QFormLayout, QHBoxLayout, QHeaderView, QLineEdit, QMainWindow,
    QMessageBox, QPushButton, QProgressBar, QTableWidget, QTableWidgetItem, QInputDialog,
    QToolBar, QVBoxLayout, QWidget, QLabel, QSystemTrayIcon, QMenu, QTextEdit, QCheckBox
)

from .downloader import DownloadJob, filename_from_url, set_download_speed_limit
from .uploader import UploadJob
from .sftp_uploader import SFTPUploadJob
from .ftp_uploader import FTPUploadJob
from .tus_uploader import TusUploadJob
from .video import VideoDownloadJob

APP_NAME = "Ss Download Manager"
DEVELOPER_NAME = "HeshamZegoo"
COPYRIGHT_NOTICE = "Copyright © 2026 HeshamZegoo"


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
    upload_session = Signal(str, str)
    video_progress = Signal(str, float, str)
    video_finished = Signal(str, str)
    video_failed = Signal(str, str)


class AddDialog(QDialog):
    def __init__(self, parent=None, default_folder=None):
        super().__init__(parent)
        self.setWindowTitle("Add download")
        self.setMinimumWidth(520)
        self.url = QLineEdit()
        self.url.setPlaceholderText("https://example.com/file.zip")
        self.folder = QLineEdit(str(default_folder or (Path.home() / "Downloads")))
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


class LinkGrabberDialog(QDialog):
    def __init__(self, window, urls=""):
        super().__init__(None, Qt.WindowType.Window)
        self.window = window
        self.setWindowTitle("Link Grabber — Ss Download Manager")
        self.setWindowIcon(window.windowIcon())
        self.setMinimumSize(560, 390)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        layout = QVBoxLayout(self)
        title = QLabel("Link Grabber")
        title.setStyleSheet("font-size:18px;font-weight:700")
        layout.addWidget(title)
        hint = QLabel("Copy one or more HTTP/HTTPS links and they will appear here automatically. Choose where to save them.")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        layout.addWidget(QLabel("Links to download"))
        self.urls = QTextEdit()
        self.urls.setPlaceholderText("https://example.com/file.zip")
        self.urls.setPlainText(urls)
        layout.addWidget(self.urls, 1)
        layout.addWidget(QLabel("Download location"))
        folder_row = QHBoxLayout()
        self.folder = QLineEdit()
        default_folder = window.grabber_download_dir if window.grabber_remember_location else str(window.default_download_dir)
        self.folder.setText(default_folder)
        browse = QPushButton("Browse")
        browse.clicked.connect(self.choose_folder)
        folder_row.addWidget(self.folder, 1)
        folder_row.addWidget(browse)
        layout.addLayout(folder_row)
        self.remember = QCheckBox("Remember this location")
        self.remember.setChecked(window.grabber_remember_location)
        layout.addWidget(self.remember)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel = QPushButton("Cancel")
        add = QPushButton("Add to downloads")
        add.setDefault(True)
        cancel.clicked.connect(self.reject)
        add.clicked.connect(self.add_downloads)
        buttons.addWidget(cancel)
        buttons.addWidget(add)
        layout.addLayout(buttons)

    def choose_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Choose download location", self.folder.text())
        if folder:
            self.folder.setText(folder)

    def add_downloads(self):
        self.window.add_grabber_downloads(self.urls.toPlainText(), self.folder.text(), self.remember.isChecked())
        self.accept()

    def reject(self):
        self.window._grabber_open = False
        self.window._last_clipboard_text = ""
        super().reject()


class HtmlBridge(QObject):
    def __init__(self, window):
        super().__init__(window)
        self.window = window

    @Slot(result=str)
    def getGrabberFolder(self):
        return str(self.window.grabber_download_dir if self.window.grabber_remember_location else self.window.default_download_dir)

    @Slot(result=bool)
    def getGrabberRememberLocation(self):
        return bool(self.window.grabber_remember_location)

    @Slot(str, result=str)
    def chooseDownloadFolder(self, current):
        return self.window.choose_grabber_folder(current)

    @Slot(str, str, bool)
    def addGrabberDownloads(self, urls, folder, remember):
        self.window.add_grabber_downloads(urls, folder, remember)

    @Slot()
    def grabberClosed(self):
        self.window._grabber_open = False
        self.window._last_clipboard_text = ""

    @Slot()
    def requestRefresh(self):
        self.window.refresh()

    @Slot(str, str, int)
    def addDownload(self, url, category, connections):
        self.window.add_download_from_html(url, category, connections)

    @Slot(str, str)
    def action(self, record_id, action):
        self.window.select_record_by_id(record_id)
        if action == "pause":
            self.window.pause_selected()
        elif action == "resume":
            self.window.resume_selected()
        elif action == "delete":
            self.window.remove_selected()
        elif action == "schedule":
            self.window.schedule_selected()

    @Slot()
    def pauseAll(self):
        self.window.pause_all()

    @Slot()
    def clearDone(self):
        self.window.clear_completed()

    @Slot()
    def uploadFile(self):
        self.window.upload_file()

    @Slot()
    def grabVideo(self):
        self.window.grab_video()

    @Slot()
    def options(self):
        self.window.configure_connections()

    @Slot()
    def toggleTheme(self):
        self.window.toggle_theme()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        icon_path = Path(__file__).parent / "assets" / "SsDownloadManager.png"
        if icon_path.is_file():
            self.setWindowIcon(QIcon(str(icon_path)))
        self.resize(1100, 700)
        self.setMinimumSize(820, 520)
        self.records = []
        self.jobs = {}
        self.upload_jobs = {}
        self.upload_passwords = {}
        self.video_jobs = {}
        self.pausing_all = False
        self.settings = QSettings("SsDM", "SsDownloadManager")
        self.max_active_uploads = self.settings.value("max_active_uploads", 2, type=int)
        self.dark_mode = self.settings.value("dark_mode", False, type=bool)
        self.default_download_dir = Path(self.settings.value("download_dir", str(Path.home() / "Downloads"))).expanduser()
        self.default_download_dir.mkdir(parents=True, exist_ok=True)
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
        self.signals.upload_session.connect(self.on_upload_session)
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
        self.table.hide()
        self.table.setParent(self)
        self.web_view = QWebEngineView(self)
        self.web_channel = QWebChannel(self.web_view.page())
        self.html_bridge = HtmlBridge(self)
        self.web_channel.registerObject("bridge", self.html_bridge)
        self.web_view.page().setWebChannel(self.web_channel)
        self.web_view.loadFinished.connect(lambda ok: self.refresh() if ok else None)
        self.setCentralWidget(self.web_view)
        ui_file = Path(__file__).parent / "ui" / "idm-modern.html"
        self.web_view.setUrl(QUrl.fromLocalFile(str(ui_file.resolve())))

        toolbar = QToolBar("Downloads")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)
        toolbar.hide()
        for label, handler in [
            ("＋ Add URL", self.add_download),
            ("＋ Batch URLs", self.add_batch_downloads),
            ("Download folder", self.configure_download_folder),
            ("Connections", self.configure_connections),
            ("Queue limit", self.configure_queue_limit),
            ("Upload queue limit", self.configure_upload_queue_limit),
            ("Speed limit", self.configure_speed_limit),
            ("Toggle dark mode", self.toggle_theme),
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

        help_menu = self.menuBar().addMenu("Help")
        about_action = QAction("About Ss Download Manager", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Search downloads…")
        self.search.textChanged.connect(self.refresh)
        self.statusBar().showMessage("Ready")
        self.apply_theme()

        search_bar = QToolBar("Search")
        search_bar.addWidget(QLabel("  Filter: "))
        search_bar.addWidget(self.search)
        self.addToolBar(search_bar)
        search_bar.hide()
        self.refresh()
        self.tray = None
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray = QSystemTrayIcon(self)
            self.tray.setToolTip(APP_NAME)
            tray_menu = QMenu()
            show_action = tray_menu.addAction("Show Ss Download Manager")
            show_action.triggered.connect(self.show_main_window)
            grabber_action = tray_menu.addAction("Open Link Grabber")
            grabber_action.triggered.connect(self.open_link_grabber)
            tray_menu.addSeparator()
            exit_action = tray_menu.addAction("Exit")
            exit_action.triggered.connect(QApplication.quit)
            self.tray.setContextMenu(tray_menu)
            self.tray.show()
        self.queue_timer = QTimer(self)
        self.queue_timer.setInterval(5000)
        self.queue_timer.timeout.connect(self._schedule_queue)
        self.queue_timer.start()

        # Browser extensions hand URLs to this inbox through the native host.
        self.browser_inbox = data_dir() / "browser_inbox.jsonl"
        self.browser_poll = QTimer(self)
        self.browser_poll.setInterval(700)
        self.browser_poll.timeout.connect(self._ingest_browser_inbox)
        self.browser_poll.start()
        self._last_clipboard_text = ""
        self._grabber_open = False
        self._pending_grabber_urls = ""
        self.grabber_remember_location = self.settings.value("grabber_remember_location", False, type=bool)
        self.grabber_download_dir = self.settings.value("grabber_download_dir", str(self.default_download_dir))
        QApplication.clipboard().dataChanged.connect(self._on_clipboard_changed)

    def _on_clipboard_changed(self):
        if self._grabber_open:
            return
        try:
            clip_text = QApplication.clipboard().text().strip()
        except Exception:
            return
        if not clip_text or clip_text == self._last_clipboard_text:
            return
        self._last_clipboard_text = clip_text
        # Accept one URL per line and URLs separated by spaces or tabs.
        import re
        candidates = re.findall(r"https?://[^\\s<>\"']+", clip_text)
        urls = list(dict.fromkeys(u.rstrip(".,);]") for u in candidates))
        if not urls:
            return
        self._grabber_open = True
        QTimer.singleShot(120, lambda: self._show_standalone_grabber("\\n".join(urls)))

    def _show_standalone_grabber(self, urls):
        if not self._grabber_open:
            return
        dialog = LinkGrabberDialog(self, urls)
        self._grabber_dialog = dialog
        dialog.finished.connect(lambda _result: self._grabber_dialog_closed())
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def _grabber_dialog_closed(self):
        self._grabber_open = False
        self._last_clipboard_text = ""
        self._grabber_dialog = None

    def open_link_grabber(self):
        self._grabber_open = True
        self._show_standalone_grabber("")

    def _display_grabber(self):
        folder = self.grabber_download_dir if self.grabber_remember_location else str(self.default_download_dir)
        self.web_view.page().runJavaScript(
            "window.ssdmSetGrabberFolder(" + json.dumps(str(folder)) + ", "
            + json.dumps(bool(self.grabber_remember_location)) + ");"
        )
        self.web_view.page().runJavaScript(
            "if(window.ssdmOpenGrabber) window.ssdmOpenGrabber("
            + json.dumps(self._pending_grabber_urls, ensure_ascii=False) + ");"
        )

    def choose_grabber_folder(self, current):
        start = current or str(self.default_download_dir)
        folder = QFileDialog.getExistingDirectory(self, "Choose download folder", start)
        return folder or ""

    def add_grabber_downloads(self, raw_urls, folder, remember):
        urls = []
        for line in raw_urls.splitlines():
            url = line.strip()
            parsed = urlparse(url)
            if parsed.scheme in ("http", "https") and parsed.netloc and url not in urls:
                urls.append(url)
        if not urls:
            QMessageBox.warning(self, "Link Grabber", "No valid HTTP or HTTPS links were found.")
            self._grabber_open = False
            return
        target = Path(folder).expanduser() if folder.strip() else self.default_download_dir
        try:
            target.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            QMessageBox.warning(self, "Link Grabber", f"Cannot use this folder: {exc}")
            self._grabber_open = False
            return
        if remember:
            self.grabber_remember_location = True
            self.grabber_download_dir = str(target)
            self.settings.setValue("grabber_remember_location", True)
            self.settings.setValue("grabber_download_dir", str(target))
        else:
            self.grabber_remember_location = False
            self.settings.setValue("grabber_remember_location", False)
        added = 0
        for url in urls:
            name = filename_from_url(url)
            destination = str(target / name)
            if any(r.get("url") == url and r.get("destination") == destination for r in self.records):
                continue
            if Path(destination).exists() or any(r.get("destination") == destination for r in self.records):
                destination = str(target / f"{Path(name).stem}-{uuid.uuid4().hex[:8]}{Path(name).suffix}")
            record = {
                "id": uuid.uuid4().hex, "url": url, "name": name, "destination": destination,
                "status": "Queued", "downloaded": 0, "total": None, "speed": 0,
                "category": _category(name), "source": "link-grabber",
            }
            self.records.insert(0, record)
            added += 1
        if added:
            self._save()
            self.refresh()
            self._schedule_queue()
            self.statusBar().showMessage(f"Added {added} link(s) from Link Grabber", 5000)
        self._grabber_open = False
        self._last_clipboard_text = ""

    def show_about(self):
        QMessageBox.about(
            self,
            f"About {APP_NAME}",
            f"<h3>{APP_NAME}</h3>"
            f"<p>Developed by <b>{DEVELOPER_NAME}</b></p>"
            f"<p>{COPYRIGHT_NOTICE}</p>"
            f"<p><a href='https://github.com/HeshamZegoo/Ss-Download-Manager'>GitHub project</a></p>"
        )

    def show_main_window(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

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
            elif record.get("transfer_type") == "upload" and record.get("status") == "Uploading":
                record["status"] = "Interrupted"
                record["speed"] = 0
                record["error"] = "The application closed before this upload finished; restart it manually."

    def _save(self):
        self.store.parent.mkdir(parents=True, exist_ok=True)
        temp = self.store.with_suffix(".tmp")
        temp.write_text(json.dumps(self.records, indent=2), encoding="utf-8")
        temp.replace(self.store)


    def _ingest_browser_inbox(self):
        processing = self.browser_inbox.with_suffix(".processing")
        if self.browser_inbox.exists():
            try:
                self.browser_inbox.replace(processing)
            except OSError:
                return
        elif not processing.exists():
            return
        added = 0
        try:
            lines = processing.read_text(encoding="utf-8").splitlines()
            for line in lines:
                try:
                    item = json.loads(line)
                    url = str(item.get("url", "")).strip()
                    parsed = urlparse(url)
                    if parsed.scheme not in ("http", "https") or not parsed.netloc:
                        continue
                    if any(r.get("url") == url for r in self.records):
                        continue
                    name = filename_from_url(url)
                    folder = self.default_download_dir
                    destination = str(folder / name)
                    if any(r.get("destination") == destination for r in self.records):
                        destination = str(folder / f"{Path(name).stem}-{uuid.uuid4().hex[:8]}{Path(name).suffix}")
                    record = {
                        "id": uuid.uuid4().hex, "url": url, "name": name,
                        "destination": destination, "status": "Queued",
                        "downloaded": 0, "total": None, "speed": 0,
                        "category": _category(name), "source": item.get("source", "browser"),
                    }
                    self.records.insert(0, record)
                    added += 1
                except (ValueError, TypeError, AttributeError):
                    continue
        finally:
            processing.unlink(missing_ok=True)
        if added:
            self._save()
            self.refresh()
            self.statusBar().showMessage(f"Added {added} link(s) from browser", 5000)
            self._schedule_queue()

    def add_download(self):
        dialog = AddDialog(self, self.default_download_dir)
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
            max_connections=int(record.get("connections", self.max_connections)),
        )
        self.jobs[job_id] = job
        self._save()
        job.start()
        self.refresh()

    def toggle_theme(self):
        self.dark_mode = not self.dark_mode
        self.settings.setValue("dark_mode", self.dark_mode)
        self.apply_theme()

    def apply_theme(self):
        if self.dark_mode:
            self.setStyleSheet("""
                QMainWindow { background: #151a22; color: #e8edf5; }
                QWidget { color: #e8edf5; }
                QTableWidget { background: #202733; alternate-background-color: #252e3b; color: #e8edf5; border: 1px solid #354153; gridline-color: #303b4b; selection-background-color: #344d70; }
                QHeaderView::section { background: #273242; color: #f2f5fa; padding: 9px; border: 0; font-weight: 600; }
                QToolBar { background: #1d2633; color: #e8edf5; border: 0; border-bottom: 1px solid #354153; spacing: 8px; padding: 8px; }
                QToolButton { color: #e8edf5; padding: 8px 10px; border-radius: 7px; }
                QToolButton:hover { background: #34445a; }
                QLineEdit, QComboBox, QDateTimeEdit { background: #202a37; color: #f2f5fa; border: 1px solid #435168; border-radius: 7px; padding: 8px; }
                QPushButton { background: #2d3d52; color: #f5f7fb; border: 1px solid #455872; border-radius: 7px; padding: 7px 12px; }
                QPushButton:hover { background: #3b506c; }
                QStatusBar { background: #1d2633; color: #cbd5e1; }
                QMenu { background: #202a37; color: #e8edf5; border: 1px solid #435168; }
                QMenu::item:selected { background: #34445a; }
            """)
        else:
            self.setStyleSheet("""
                QMainWindow { background: #f3f5fb; color: #1d2939; }
                QTableWidget { background: white; color: #1d2939; border: 1px solid #e0e5f0; gridline-color: #edf0f6; selection-background-color: #dce7ff; }
                QHeaderView::section { background: #eef1f8; color: #1d2939; padding: 9px; border: 0; font-weight: 600; }
                QToolBar { background: white; color: #1d2939; border: 0; border-bottom: 1px solid #e0e5f0; spacing: 8px; padding: 8px; }
                QToolButton { color: #1d2939; padding: 8px 10px; border-radius: 7px; }
                QToolButton:hover { background: #e8edff; }
                QLineEdit, QComboBox, QDateTimeEdit { background: white; color: #1d2939; border: 1px solid #d9deeb; border-radius: 7px; padding: 8px; }
                QPushButton { background: #eef2fa; color: #1d2939; border: 1px solid #d9deeb; border-radius: 7px; padding: 7px 12px; }
                QPushButton:hover { background: #e1e9f8; }
                QStatusBar { background: #f3f5fb; color: #475467; }
            """)

    def configure_download_folder(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Choose default download folder", str(self.default_download_dir)
        )
        if folder:
            self.default_download_dir = Path(folder).expanduser()
            self.default_download_dir.mkdir(parents=True, exist_ok=True)
            self.settings.setValue("download_dir", str(self.default_download_dir))
            self.statusBar().showMessage(f"Default download folder: {self.default_download_dir}", 5000)

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
            (r for r in self.records if r.get("transfer_type") != "upload" and
             (r.get("status") == "Queued" or
              (r.get("status") == "Scheduled" and _schedule_due(r, now)))),
            key=lambda r: r.get("priority", 0), reverse=True,
        )
        for record in waiting[:max(0, self.max_active_downloads - active)]:
            self._start(record)
        self._schedule_upload_queue()

    def schedule_selected(self):
        record = self._selected()
        if not record or record.get("transfer_type") == "upload" or record.get("status") in ("Downloading", "Completed"):
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

    def configure_upload_queue_limit(self):
        value, ok = QInputDialog.getInt(
            self, "Active uploads", "Maximum simultaneous uploads:",
            self.max_active_uploads, 1, 16, 1
        )
        if ok:
            self.max_active_uploads = value
            self.settings.setValue("max_active_uploads", value)
            self._schedule_upload_queue()
            self.statusBar().showMessage(f"Maximum active uploads: {value}", 5000)

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
            folder = str(self.default_download_dir)
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
            self, "Choose download folder", str(self.default_download_dir)
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
        protocol, ok = QInputDialog.getItem(
            self, "Upload protocol", "Choose upload destination type:",
            ["HTTP PUT / WebDAV", "TUS resumable", "SFTP", "FTP", "FTPS"], 0, False
        )
        if not ok:
            return
        destination, ok = QInputDialog.getText(
            self, "Upload destination",
            "HTTP(S) PUT URL:" if protocol.startswith("HTTP") else
            ("TUS endpoint URL (server must implement tus 1.0):" if protocol == "TUS resumable" else
             ("SFTP URL (host key must already be trusted): sftp://user@host:22/remote/path"
              if protocol == "SFTP" else
              "FTP/FTPS URL: ftp://user@host:21/remote/path or ftps://user@host:21/remote/path"))
        )
        if not ok or not destination.strip():
            return
        parsed = urlparse(destination.strip())
        if protocol.startswith("HTTP"):
            if parsed.scheme not in ("http", "https") or not parsed.netloc:
                QMessageBox.warning(self, "Invalid destination", "Enter a valid HTTP or HTTPS URL.")
                return
            password = ""
        elif protocol == "TUS resumable":
            if parsed.scheme not in ("http", "https") or not parsed.netloc:
                QMessageBox.warning(self, "Invalid destination", "Enter a valid HTTP(S) TUS endpoint.")
                return
            password = ""
        elif protocol == "SFTP":
            if parsed.scheme != "sftp" or not parsed.hostname or not parsed.username or not parsed.path:
                QMessageBox.warning(self, "Invalid destination", "Use sftp://username@host:22/remote/path")
                return
            password, ok = QInputDialog.getText(
                self, "SFTP authentication", "Password (not saved):",
                QLineEdit.EchoMode.Password
            )
            if not ok:
                return
        else:
            if parsed.scheme != protocol.lower() or not parsed.hostname or not parsed.path:
                QMessageBox.warning(self, "Invalid destination", f"Use {protocol.lower()}://username@host:21/remote/path")
                return
            password, ok = QInputDialog.getText(
                self, f"{protocol} authentication", "Password (not saved):",
                QLineEdit.EchoMode.Password
            )
            if not ok:
                return
        upload_id = uuid.uuid4().hex
        self.upload_passwords[upload_id] = password
        size = Path(source).stat().st_size
        self.records.insert(0, {
            "id": upload_id, "url": destination.strip(), "name": Path(source).name,
            "destination": source,
            "status": "Queued", "downloaded": 0,
            "total": size, "speed": 0, "category": "Upload",
            "transfer_type": "upload", "upload_protocol": protocol,
        })
        self._save()
        self.refresh()
        self.statusBar().showMessage(f"Queued upload: {Path(source).name}")
        self._schedule_upload_queue()

    def cancel_upload(self):
        if not self.upload_jobs:
            self.statusBar().showMessage("No active uploads", 3000)
            return
        upload_id = next(reversed(self.upload_jobs))
        job = self.upload_jobs.pop(upload_id)
        job.cancel()
        record = self._by_id(upload_id)
        if record:
            record["status"] = "Cancelled"
            record["speed"] = 0
        self.upload_passwords.pop(upload_id, None)
        self._save()
        self.refresh()
        self._schedule_upload_queue()
        self.statusBar().showMessage(f"Cancelled upload: {job.source.name}", 5000)

    def on_upload_session(self, upload_id, upload_url):
        record = self._by_id(upload_id)
        if record:
            record["upload_session_url"] = upload_url
            self._save()

    def on_upload_progress(self, upload_id, sent, total, speed):
        job = self.upload_jobs.get(upload_id)
        record = self._by_id(upload_id)
        if record:
            record["downloaded"] = sent
            record["total"] = total
            record["speed"] = speed
            self.refresh()
        if job:
            percent = (sent / total * 100) if total else 0
            self.statusBar().showMessage(
                f"Uploading {job.source.name}: {percent:.1f}% · {_human(speed)}/s"
            )

    def on_upload_finished(self, upload_id):
        job = self.upload_jobs.pop(upload_id, None)
        record = self._by_id(upload_id)
        if record:
            record["status"] = "Completed"
            record.pop("upload_session_url", None)
            record["downloaded"] = record.get("total") or 0
            record["speed"] = 0
        self._save()
        self.refresh()
        self.upload_passwords.pop(upload_id, None)
        if job:
            QMessageBox.information(self, "Upload complete", f"{job.source.name} was uploaded successfully.")
            self.statusBar().showMessage("Upload completed", 5000)
        self._schedule_upload_queue()

    def on_upload_failed(self, upload_id, error):
        self.upload_jobs.pop(upload_id, None)
        record = self._by_id(upload_id)
        if record:
            record["status"] = "Failed"
            record["speed"] = 0
            record["error"] = error
        self._save()
        self.refresh()
        QMessageBox.warning(self, "Upload failed", error)
        self.statusBar().showMessage("Upload failed", 5000)
        self._schedule_upload_queue()

    def _selected(self):
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return None
        visible = [r for r in self.records if self.search.text().lower() in r["name"].lower()]
        index = rows[0].row()
        return visible[index] if index < len(visible) else None

    def resume_selected(self):
        record = self._selected()
        if not record:
            return
        if record.get("transfer_type") == "upload":
            if record.get("status") in ("Paused", "Interrupted", "Failed", "Cancelled"):
                self._resume_upload_record(record)
        elif record["status"] in ("Paused", "Failed", "Queued"):
            self._start(record)

    def _resume_upload_record(self, record):
        protocol = record.get("upload_protocol", "HTTP PUT / WebDAV")
        password = self.upload_passwords.get(record["id"], "")
        if protocol in ("SFTP", "FTP", "FTPS") and not password:
            password, ok = QInputDialog.getText(
                self, f"{protocol} authentication", "Re-enter password (not saved):",
                QLineEdit.EchoMode.Password
            )
            if not ok:
                return
        self.upload_passwords[record["id"]] = password
        record["status"] = "Queued"
        record["speed"] = 0
        record.pop("error", None)
        self._save()
        self.refresh()
        self._schedule_upload_queue()

    def _schedule_upload_queue(self):
        active = len(self.upload_jobs)
        waiting = [r for r in self.records
                   if r.get("transfer_type") == "upload" and r.get("status") == "Queued"]
        for record in waiting[:max(0, self.max_active_uploads - active)]:
            self._start_upload_record(record)

    def _start_upload_record(self, record):
        upload_id = record["id"]
        if upload_id in self.upload_jobs:
            return
        protocol = record.get("upload_protocol", "HTTP PUT / WebDAV")
        password = self.upload_passwords.get(upload_id, "")
        if protocol in ("SFTP", "FTP", "FTPS") and not password:
            password, ok = QInputDialog.getText(
                self, f"{protocol} authentication", "Password (not saved):",
                QLineEdit.EchoMode.Password
            )
            if not ok:
                record["status"] = "Paused"
                self._save()
                self.refresh()
                return
            self.upload_passwords[upload_id] = password
        callbacks = (
            lambda sent, total, speed, uid=upload_id: self.signals.upload_progress.emit(uid, sent, total, speed),
            lambda path, uid=upload_id: self.signals.upload_finished.emit(uid),
            lambda error, uid=upload_id: self.signals.upload_failed.emit(uid, error),
        )
        if protocol == "HTTP PUT / WebDAV":
            job = UploadJob(record["destination"], record["url"], *callbacks)
        elif protocol == "TUS resumable":
            job = TusUploadJob(
                record["destination"], record["url"], *callbacks,
                upload_url=record.get("upload_session_url"),
                session_created=lambda url, uid=upload_id: self.signals.upload_session.emit(uid, url),
            )
        elif protocol == "SFTP":
            job = SFTPUploadJob(record["destination"], record["url"], password, *callbacks)
        else:
            job = FTPUploadJob(record["destination"], record["url"], password, *callbacks)
        self.upload_jobs[upload_id] = job
        record["status"] = "Uploading"
        self._save()
        self.refresh()
        job.start()

    def pause_selected(self):
        record = self._selected()
        if not record:
            return
        if record.get("transfer_type") == "upload" and record["id"] in self.upload_jobs:
            job = self.upload_jobs.pop(record["id"])
            job.cancel()
            record["status"] = "Paused"
            record["speed"] = 0
            self._save()
            self.refresh()
        elif record["id"] in self.jobs:
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
            if record.get("transfer_type") == "upload" and record["id"] in self.upload_jobs:
                upload = self.upload_jobs.pop(record["id"])
                upload.cancel()
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
        upload = self.upload_jobs.pop(record["id"], None)
        if upload:
            upload.cancel()
        self.upload_passwords.pop(record["id"], None)
        job = self.jobs.pop(record["id"], None)
        if job:
            job.cancel(delete_partial=True)
        elif record.get("transfer_type") != "upload":
            Path(record["destination"] + ".part").unlink(missing_ok=True)
        self.records.remove(record)
        self._save()
        self.refresh()
        self._schedule_queue()

    def verify_selected(self):
        record = self._selected()
        if not record or record.get("transfer_type") == "upload" or record.get("status") != "Completed":
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
                _human(record.get("downloaded", 0)), _speed(record.get("speed", 0)),
                str(Path(record["destination"]).parent),
            ]
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                if col == 0:
                    item.setToolTip(record.get("url", ""))
                self.table.setItem(row, col, item)
        if hasattr(self, "web_view"):
            payload = [{
                "id": r.get("id"), "name": r.get("name"), "category": r.get("category", "Other"),
                "status": r.get("status"), "downloaded": r.get("downloaded", 0),
                "total": r.get("total"), "speed": r.get("speed", 0),
                "destination": r.get("destination", ""), "error": r.get("error", ""),
                "connections": r.get("connections", self.max_connections),
            } for r in self.records]
            encoded = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
            theme = "dark" if self.dark_mode else "light"
            self.web_view.page().runJavaScript(
                "document.documentElement.dataset.theme = '" + theme + "'; "
                "if(window.ssdmRender) window.ssdmRender(" + encoded + ");"
            )
        self.statusBar().showMessage(f"{len(self.records)} downloads · {sum(r['status'] == 'Downloading' for r in self.records)} active")

    def select_record_by_id(self, record_id):
        visible = [r for r in self.records if self.search.text().lower() in r["name"].lower()]
        index = next((i for i, r in enumerate(visible) if r.get("id") == record_id), -1)
        self.table.clearSelection()
        if index >= 0:
            self.table.selectRow(index)

    def add_download_from_html(self, url, category, connections):
        parsed = urlparse(url.strip())
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            QMessageBox.warning(self, "Invalid URL", "Enter a valid HTTP or HTTPS URL.")
            return
        name = filename_from_url(url)
        destination = str(self.default_download_dir / name)
        if any(r.get("destination") == destination for r in self.records):
            destination = str(self.default_download_dir / f"{Path(name).stem}-{uuid.uuid4().hex[:8]}{Path(name).suffix}")
        record = {
            "id": uuid.uuid4().hex, "url": url.strip(), "name": name, "destination": destination,
            "status": "Queued", "downloaded": 0, "total": None, "speed": 0,
            "category": {"Compressed": "Archives", "Music": "Audio"}.get(category, category if category in ("Archives", "Documents", "Audio", "Video", "Programs", "Images") else _category(name)), "connections": max(1, min(int(connections), 32)),
        }
        self.records.insert(0, record)
        self._save()
        self.refresh()
        self._start(record)

    def clear_completed(self):
        done = [r for r in self.records if r.get("status") == "Completed"]
        for record in done:
            self.records.remove(record)
        self._save()
        self.refresh()


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

    def log_uncaught_exception(exc_type, exc_value, exc_traceback):
        details = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
        try:
            (data_dir() / "startup-error.log").write_text(details, encoding="utf-8")
        except OSError:
            pass
        try:
            QMessageBox.critical(
                None, f"{APP_NAME} error",
                "The application encountered an unexpected error. "
                "A diagnostic log was saved in %APPDATA%\\SsDownloadManager\\startup-error.log."
            )
        except Exception:
            pass
        sys.__excepthook__(exc_type, exc_value, exc_traceback)

    sys.excepthook = log_uncaught_exception
    try:
        window = MainWindow()
        if "--background" in sys.argv:
            window.hide()
        else:
            window.show()
        sys.exit(app.exec())
    except Exception:
        details = traceback.format_exc()
        try:
            (data_dir() / "startup-error.log").write_text(details, encoding="utf-8")
        except OSError:
            pass
        QMessageBox.critical(
            None, f"{APP_NAME} could not start",
            "Startup failed. Details were saved to %APPDATA%\\SsDownloadManager\\startup-error.log."
        )
        raise
