import os
import tempfile
import uuid
from pathlib import Path

from PyQt6.QtCore import QObject, QThread, QTimer, QUrl, pyqtSignal, pyqtSlot, Qt
from PyQt6.QtDBus import QDBusConnection, QDBusInterface, QDBusMessage
from PyQt6.QtGui import QAction, QIcon, QKeySequence, QPixmap, QShortcut, QDragEnterEvent, QDropEvent
from PyQt6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDialog, QFileDialog, QHBoxLayout,
    QHeaderView, QInputDialog, QLabel,     QLineEdit, QListWidget, QListWidgetItem,
    QMainWindow, QMenu, QMessageBox, QPushButton, QSplitter, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget, QProgressBar, QSizePolicy, QToolBar,
    QToolButton,
)

import config
from core import attacher, autoattach, parser, scanner, tmdb


class PortalFilePicker(QObject):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._conn = QDBusConnection.sessionBus()
        self._callback = None
        self._timeout = None
        self._multiple = False
        self._req_path = None
        self._active = False

    def pick(self, callback, title="Select Image", start_dir="", multiple=False,
             filters=None, directory=False):
        if self._active:
            return
        self._active = True
        self._callback = callback
        self._multiple = multiple
        if not self._conn.isConnected():
            self._fallback(title, start_dir, filters, directory)
            return
        iface = QDBusInterface(
            "org.freedesktop.portal.Desktop",
            "/org/freedesktop/portal/desktop",
            "org.freedesktop.portal.FileChooser",
            self._conn,
        )
        token = "makattatch%s" % uuid.uuid4().hex
        if multiple:
            accept = "Use Videos"
        elif "video" in title.lower():
            accept = "Use Video"
        elif directory:
            accept = "Use Folder"
        else:
            accept = "Use Image"
        opts = {
            "handle_token": token,
            "title": title,
            "multiple": multiple,
            "accept_label": accept,
        }
        if directory:
            opts["directory"] = True
        if start_dir:
            opts["current_folder"] = QUrl.fromLocalFile(start_dir).toString()
        reply = iface.call("OpenFile", "", title, opts)
        if reply.type() != QDBusMessage.MessageType.ReplyMessage or not reply.arguments():
            self._fallback(title, start_dir, filters, directory)
            return
        self._req_path = reply.arguments()[0]
        if not self._conn.connect(
            "org.freedesktop.portal.Desktop",
            self._req_path,
            "org.freedesktop.portal.Request",
            "Response",
            self._on_response,
        ):
            self._fallback(title, start_dir, filters, directory)
            return
        self._timeout = QTimer(self)
        self._timeout.setSingleShot(True)
        self._timeout.timeout.connect(lambda: self._finish(None))
        self._timeout.start(60 * 60 * 1000)

    def _fallback(self, title, start_dir, filters, directory=False):
        parent = self.parent() if isinstance(self.parent(), QWidget) else None
        if directory:
            path = QFileDialog.getExistingDirectory(parent, title, start_dir or "")
            self._finish(path or None)
        elif self._multiple:
            paths, _ = QFileDialog.getOpenFileNames(
                parent, title, start_dir or "", filters or ""
            )
            self._finish(paths or None)
        else:
            path, _ = QFileDialog.getOpenFileName(
                parent, title, start_dir or "", filters or ""
            )
            self._finish(path or None)

    @pyqtSlot("uint", "QVariantMap")
    def _on_response(self, status, results):
        if not self._active:
            return
        if self._timeout:
            self._timeout.stop()
        if status != 0:
            self._finish(None)
            return
        uris = results.get("uris")
        if uris is None:
            self._finish(None)
            return
        if hasattr(uris, "variant"):
            uris = uris.variant()
        if isinstance(uris, str):
            uris = [uris]
        if not uris:
            self._finish(None)
            return
        paths = []
        for uri in uris:
            if hasattr(uri, "variant"):
                uri = uri.variant()
            qurl = QUrl(str(uri))
            if qurl.isValid() and qurl.isLocalFile():
                paths.append(qurl.toLocalFile())
        if not paths:
            self._finish(None)
            return
        self._finish(paths if self._multiple else paths[0])

    def _finish(self, path):
        cb, self._callback = self._callback, None
        if self._timeout:
            self._timeout.stop()
            self._timeout = None
        if self._active and self._conn.isConnected() and self._req_path:
            self._conn.disconnect(
                "org.freedesktop.portal.Desktop",
                self._req_path,
                "org.freedesktop.portal.Request",
                "Response",
                self._on_response,
            )
        self._req_path = None
        self._active = False
        if cb:
            cb(path)


class ApiKeyDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("TMDB API Key")
        self.setMinimumSize(400, 150)
        self.setMaximumSize(600, 200)

        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("Enter your TMDB API key:"))

        url_label = QLabel('Get one free at <a href="https://www.themoviedb.org/settings/api">https://www.themoviedb.org/settings/api</a>')
        url_label.setOpenExternalLinks(True)
        url_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse | Qt.TextInteractionFlag.LinksAccessibleByMouse)
        layout.addWidget(url_label)

        self.key_input = QLineEdit()
        self.key_input.setPlaceholderText("Paste API key here...")
        self.key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.key_input.setReadOnly(False)
        self.key_input.setContextMenuPolicy(Qt.ContextMenuPolicy.DefaultContextMenu)
        existing = config.get("tmdb_api_key")
        if existing:
            self.key_input.setText(existing)
            self.key_input.selectAll()
        layout.addWidget(self.key_input)

        btn = QPushButton("Save")
        btn.clicked.connect(self._save)
        layout.addWidget(btn)

    def showEvent(self, event):
        super().showEvent(event)
        self.key_input.setFocus()
        self.key_input.selectAll()

    def _save(self):
        key = self.key_input.text().strip()
        if not key:
            QMessageBox.warning(self, "Error", "API key cannot be empty")
            return
        config.set("tmdb_api_key", key)
        self.accept()


class SearchWorker(QThread):
    finished = pyqtSignal(list)
    error = pyqtSignal(str)

    def __init__(self, query: str):
        super().__init__()
        self.query = query

    def run(self):
        try:
            results = tmdb.search(self.query)
            self.finished.emit(results)
        except Exception as e:
            self.error.emit(str(e))


class PosterWorker(QThread):
    finished = pyqtSignal(list)
    error = pyqtSignal(str)

    def __init__(self, media_id: int, media_type: str):
        super().__init__()
        self.media_id = media_id
        self.media_type = media_type

    def run(self):
        try:
            posters = tmdb.get_posters(self.media_id, self.media_type)
            self.finished.emit(posters)
        except Exception as e:
            self.error.emit(str(e))


class BatchWorker(QThread):
    progress = pyqtSignal(int, int, str)
    finished = pyqtSignal(list)

    def __init__(self, video_paths: list, poster_path: str, metadata: dict = None,
                 cleanup_poster: bool = False, to_mkv: bool = False):
        super().__init__()
        self.video_paths = video_paths
        self.poster_path = poster_path
        self.metadata = metadata
        self.cleanup_poster = cleanup_poster
        self.to_mkv = to_mkv
        self.results = []

    def run(self):
        results = []
        total = len(self.video_paths)
        try:
            for i, path in enumerate(self.video_paths):
                self.progress.emit(i + 1, total, Path(path).name)
                try:
                    out = attacher.full_attach(path, self.poster_path,
                                               metadata=self.metadata,
                                               to_mkv=self.to_mkv)
                    results.append({"path": path, "out": out, "ok": True})
                except Exception as e:
                    results.append({"path": path, "out": str(e), "ok": False})
        finally:
            if self.cleanup_poster and self.poster_path and os.path.exists(self.poster_path):
                try:
                    os.unlink(self.poster_path)
                except OSError:
                    pass
        self.results = results
        self.finished.emit(results)


class ConvertWorker(QThread):
    progress = pyqtSignal(int, int, str)
    finished = pyqtSignal(list)

    def __init__(self, video_paths: list):
        super().__init__()
        self.video_paths = video_paths
        self.results = []

    def run(self):
        results = []
        total = len(self.video_paths)
        for i, path in enumerate(self.video_paths):
            self.progress.emit(i + 1, total, Path(path).name)
            try:
                out = attacher.remux_to_mkv(path)
                results.append({"path": path, "out": out, "ok": True, "error": ""})
            except Exception as e:
                results.append({"path": path, "out": path, "ok": False, "error": str(e)})
        self.results = results
        self.finished.emit(results)


class ScanWorker(QThread):
    progress = pyqtSignal(str)
    finished = pyqtSignal(list)
    error = pyqtSignal(str)

    def __init__(self, root: str):
        super().__init__()
        self.root = root

    def run(self):
        try:
            files = scanner.iter_video_files(self.root)
            self.progress.emit(f"Scanning {self.root}...")
            groups = scanner.classify(files)
            self.finished.emit(groups)
        except Exception as e:
            self.error.emit(str(e))


class ResolveWorker(QThread):
    progress = pyqtSignal(str)
    finished = pyqtSignal(list)
    error = pyqtSignal(str)

    def __init__(self, groups: list, api_delay: float = 0.25):
        super().__init__()
        self.groups = groups
        self.api_delay = api_delay

    def run(self):
        try:
            def cb(current, total, group):
                self.progress.emit(f"Resolving {current}/{total}: {group.title}")

            resolved = autoattach.resolve_groups(self.groups, api_delay=self.api_delay, progress=cb)
            self.finished.emit(resolved)
        except Exception as e:
            self.error.emit(str(e))


class AutoAttachWorker(QThread):
    progress = pyqtSignal(str)
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, resolved: list, scrape_metadata: bool = False,
                 skip_existing: bool = True, api_delay: float = 0.25,
                 to_mkv: bool = False):
        super().__init__()
        self.resolved = resolved
        self.scrape_metadata = scrape_metadata
        self.skip_existing = skip_existing
        self.api_delay = api_delay
        self.to_mkv = to_mkv

    def run(self):
        def cb(done, total, filepath, status):
            self.progress.emit(f"Attaching {done}/{total}: {Path(filepath).name}")

        try:
            summary = autoattach.attach_groups(
                self.resolved,
                skip_existing=self.skip_existing,
                scrape_metadata=self.scrape_metadata,
                api_delay=self.api_delay,
                to_mkv=self.to_mkv,
                progress=cb,
            )
            self.finished.emit(summary)
        except Exception as e:
            self.error.emit(str(e))


class PosterPreviewDialog(QDialog):
    poster_selected = pyqtSignal(dict)

    def __init__(self, poster: dict, parent=None):
        super().__init__(parent)
        self.poster = poster
        self.setWindowTitle("Poster Preview")
        self.setMinimumSize(500, 700)

        layout = QVBoxLayout(self)

        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout.addWidget(self.image_label)

        info = QLabel(f"Resolution: {poster['width']}x{poster['height']}  |  Language: {poster.get('lang') or '??'}")
        info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(info)

        btn = QPushButton("Select This Poster")
        btn.clicked.connect(lambda: (self.poster_selected.emit(self.poster), self.accept()))
        layout.addWidget(btn)

        self._loader = None
        self._load()

    def done(self, result):
        if self._loader is not None and self._loader.isRunning():
            self._loader.wait(5000)
        super().done(result)

    def _load(self):
        self._loader = PosterPreviewDialog._ImageLoader(self.poster["url"])
        self._loader.loaded.connect(self._on_loaded)
        self._loader.start()

    def _on_loaded(self, pixmap):
        self.image_label.setPixmap(
            pixmap.scaled(self.image_label.size(), Qt.AspectRatioMode.KeepAspectRatio,
                          Qt.TransformationMode.SmoothTransformation)
        )

    class _ImageLoader(QThread):
        loaded = pyqtSignal(QPixmap)

        def __init__(self, url):
            super().__init__()
            self.url = url

        def run(self):
            try:
                resp = tmdb._fetch(self.url)
                pixmap = QPixmap()
                pixmap.loadFromData(resp.content)
                self.loaded.emit(pixmap)
            except Exception:  # nosec B110
                pass


class PosterPickDialog(QDialog):
    poster_selected = pyqtSignal(dict)

    def __init__(self, match: dict, parent=None):
        super().__init__(parent)
        self.match = match
        self.setWindowTitle(f"Pick Poster — {match['title']}")
        self.setMinimumSize(720, 520)

        from .poster_grid import PosterGrid

        layout = QVBoxLayout(self)
        self.status = QLabel("Loading posters...")
        layout.addWidget(self.status)

        self.grid = PosterGrid()
        self.grid.setMinimumHeight(360)
        self.grid.poster_selected.connect(self._on_picked)
        layout.addWidget(self.grid, 1)

        btn = QPushButton("Cancel")
        btn.clicked.connect(self.reject)
        layout.addWidget(btn)

        self._worker = PosterWorker(match["id"], match["media_type"])
        self._worker.finished.connect(self._on_loaded)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def done(self, result):
        if self._worker is not None and self._worker.isRunning():
            self._worker.wait(5000)
        super().done(result)

    def _on_loaded(self, posters):
        self.grid.load_posters(posters)
        if posters:
            self.status.setText(f"{len(posters)} posters — click one to use it")
        else:
            self.status.setText("No posters found")

    def _on_error(self, err):
        self.status.setText(f"Error loading posters: {err}")

    def _on_picked(self, poster: dict):
        self.poster_selected.emit(poster)
        self.accept()


class ScanReviewDialog(QDialog):
    def __init__(self, resolved: list, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Review Scan")
        self.setMinimumSize(760, 480)
        self.resolved = resolved

        layout = QVBoxLayout(self)

        title = QLabel("Review what will be attached before continuing.")
        title.setStyleSheet("font-weight: bold;")
        layout.addWidget(title)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(
            ["Video", "Title", "Season", "Status", "Poster"]
        )
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.itemSelectionChanged.connect(self._on_row_selected)
        for i, entry in enumerate(self.resolved):
            g = entry["group"]
            match = entry["match"]
            row = self.table.rowCount()
            self.table.insertRow(row)
            files_cell = QTableWidgetItem(f"{len(g.files)} files")
            if match:
                title_cell = QTableWidgetItem(match["title"])
                season_cell = QTableWidgetItem(
                    str(g.season) if g.season is not None else "—"
                )
                status_cell = QTableWidgetItem("OK")
            else:
                title_cell = QTableWidgetItem(g.title)
                season_cell = QTableWidgetItem(
                    str(g.season) if g.season is not None else "—"
                )
                status_cell = QTableWidgetItem("No match")
                status_cell.setForeground(Qt.GlobalColor.red)
            if entry["status"] == "error":
                status_cell = QTableWidgetItem("Error")
                status_cell.setForeground(Qt.GlobalColor.red)
            poster_cell = QTableWidgetItem(
                "Custom" if entry.get("poster") else ("Default" if match else "—")
            )
            files_cell.setData(Qt.ItemDataRole.UserRole, i)
            self.table.setItem(row, 0, files_cell)
            self.table.setItem(row, 1, title_cell)
            self.table.setItem(row, 2, season_cell)
            self.table.setItem(row, 3, status_cell)
            self.table.setItem(row, 4, poster_cell)
        layout.addWidget(self.table, 1)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        self.choose_btn = QPushButton("Choose Poster...")
        self.choose_btn.setEnabled(False)
        self.choose_btn.clicked.connect(self._choose_poster)
        button_row.addWidget(self.choose_btn)
        layout.addLayout(button_row)

        self.skip_unmatched = QCheckBox("Skip unmatched files")
        self.skip_unmatched.setChecked(True)
        layout.addWidget(self.skip_unmatched)

        self.embed_meta = QCheckBox(
            "Embed metadata (title, overview, genres, cast)"
        )
        layout.addWidget(self.embed_meta)

        self.convert_mkv = QCheckBox("Convert MP4 to MKV (lossless remux)")
        self.convert_mkv.setChecked(bool(config.get("convert_to_mkv")))
        self.convert_mkv.setToolTip(
            "Stream-copy remux into MKV before attaching, keeps the original file"
        )
        layout.addWidget(self.convert_mkv)

        self.summary = QLabel()
        layout.addWidget(self.summary)
        self._update_summary()

        btn_row = QHBoxLayout()
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        btn_row.addWidget(cancel)
        btn_row.addStretch(1)
        self.attach_all = QPushButton("Attach All")
        self.attach_all.setDefault(True)
        self.attach_all.clicked.connect(self.accept)
        btn_row.addWidget(self.attach_all)
        layout.addLayout(btn_row)

    def _update_summary(self):
        ok = sum(1 for e in self.resolved if e["status"] == "ok")
        unmatched = sum(1 for e in self.resolved if e["status"] == "no-match")
        errs = sum(1 for e in self.resolved if e["status"] == "error")
        self.summary.setText(f"{ok} matched, {unmatched} unmatched, {errs} errors")

    def _on_row_selected(self):
        row = self.table.currentRow()
        entry = self._entry_at(row) if row >= 0 else None
        self.choose_btn.setEnabled(
            bool(entry) and entry["status"] == "ok" and entry.get("match") is not None
        )

    def _entry_at(self, row: int):
        if 0 <= row < self.table.rowCount():
            item = self.table.item(row, 0)
            if item is not None:
                idx = item.data(Qt.ItemDataRole.UserRole)
                if isinstance(idx, int) and 0 <= idx < len(self.resolved):
                    return self.resolved[idx]
        return None

    def _choose_poster(self):
        entry = self._entry_at(self.table.currentRow())
        if not entry or entry["status"] != "ok":
            return
        dlg = PosterPickDialog(entry["match"], self)
        dlg.poster_selected.connect(self._on_poster_picked)
        dlg.exec()

    def _on_poster_picked(self, poster: dict):
        row = self.table.currentRow()
        entry = self._entry_at(row)
        if not entry:
            return
        entry["poster"] = poster
        cell = self.table.item(row, 4)
        if cell is not None:
            cell.setText("Custom")
        self.summary.setText("Custom poster chosen — Attach All will use it")


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("mak-attatch")
        self.setMinimumSize(900, 700)
        icon_path = Path(__file__).resolve().parent.parent / "assets" / "logo.png"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

        self.video_path = ""
        self.video_paths = []
        self.selected_video_paths = set()
        self.current_posters = []
        self.selected_poster = None
        self.local_poster_path = None
        self._portal_pick = PortalFilePicker(self)
        self._last_image_dir = None
        self.current_media = None
        self._active_workers: list = []

        self.setAcceptDrops(True)

        self._build_toolbar()
        self.status_label = QLabel("Ready")
        self.statusBar().addWidget(self.status_label, 1)

        QShortcut(QKeySequence("Ctrl+O"), self, self._browse_video)
        QShortcut(QKeySequence("Ctrl+F"), self, self._scan_folder)
        QShortcut(QKeySequence("Ctrl+A"), self, self._attach)

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setSpacing(12)

        if not config.get("tmdb_api_key"):
            QTimer.singleShot(0, self._setup_api_key)

        root.addWidget(self._build_search_row())

        splitter = QSplitter(Qt.Orientation.Horizontal)
        left = QWidget()
        left_lay = QVBoxLayout(left)
        left_lay.setContentsMargins(0, 0, 0, 0)
        left_lay.addWidget(self._build_results())
        left_lay.addWidget(self._build_poster_area())
        splitter.addWidget(left)
        splitter.addWidget(self._build_files_panel())
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([700, 300])
        root.addWidget(splitter, 1)

        root.addWidget(self._build_bottom())

    def _build_toolbar(self):
        toolbar = QToolBar("Main")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        scan_act = QAction("Scan Folder", self)
        scan_act.setShortcut(QKeySequence("Ctrl+F"))
        scan_act.triggered.connect(self._scan_folder)
        toolbar.addAction(scan_act)
        toolbar.addSeparator()

        browse_act = QAction("Browse Video", self)
        browse_act.setShortcut(QKeySequence("Ctrl+O"))
        browse_act.triggered.connect(self._browse_video)
        toolbar.addAction(browse_act)

        multi_act = QAction("Browse Multiple", self)
        multi_act.triggered.connect(self._browse_multi)
        toolbar.addAction(multi_act)

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        toolbar.addWidget(spacer)

        settings_act = QAction("Settings", self)
        settings_act.triggered.connect(self._open_settings)
        toolbar.addAction(settings_act)

    def _track_worker(self, worker):
        active = self.__dict__.get("_active_workers")
        if active is None:
            active = self.__dict__["_active_workers"] = []
        active.append(worker)

        def release(w=worker):
            try:
                active.remove(w)
            except ValueError:
                pass

        worker.finished.connect(release)

    def closeEvent(self, event):
        active = self.__dict__.get("_active_workers") or []
        for worker in list(active):
            worker.wait(5000)
        super().closeEvent(event)

    def _setup_api_key(self):
        if ApiKeyDialog(self).exec() != QDialog.DialogCode.Accepted:
            pass

    def _build_search_row(self) -> QWidget:
        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Type movie/show name...")
        self.search_input.returnPressed.connect(self._search)
        lay.addWidget(self.search_input, 1)

        self.search_btn = QPushButton("Search")
        self.search_btn.clicked.connect(self._search)
        lay.addWidget(self.search_btn)

        return w

    def _build_files_panel(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)

        self.files_label = QLabel("Files (0)")
        lay.addWidget(self.files_label)

        self.file_list = QListWidget()
        self.file_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.file_list.itemClicked.connect(self._on_file_clicked)
        self.file_list.itemSelectionChanged.connect(self._on_file_selection_changed)
        self.file_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.file_list.customContextMenuRequested.connect(self._file_context_menu)
        lay.addWidget(self.file_list, 1)

        hint = QLabel("Drop videos here, browse, or Scan a folder for posters.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #6c7086;")
        lay.addWidget(hint)

        return w

    def _file_context_menu(self, pos):
        menu = QMenu(self)
        remove_act = menu.addAction("Remove from list")
        clear_act = menu.addAction("Clear list")
        chosen = menu.exec(self.file_list.mapToGlobal(pos))
        if chosen is remove_act:
            item = self.file_list.itemAt(pos)
            if item is not None:
                path = item.data(Qt.ItemDataRole.UserRole)
                if path in self.video_paths:
                    self.video_paths.remove(path)
                    self.selected_video_paths.discard(path)
                    self.file_list.takeItem(self.file_list.row(item))
                    self._refresh_file_rows()
        elif chosen is clear_act:
            self._clear_files()

    def _build_results(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)

        lay.addWidget(QLabel("Search Results:"))

        self.results_list = QListWidget()
        self.results_list.setMaximumHeight(150)
        self.results_list.itemClicked.connect(self._on_result_selected)
        self.results_list.itemDoubleClicked.connect(self._on_result_selected)
        lay.addWidget(self.results_list)

        return w

    def _build_poster_area(self) -> QWidget:
        from .poster_grid import PosterGrid

        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)

        lay.addWidget(QLabel("Posters:"))

        self.poster_grid = PosterGrid()
        self.poster_grid.poster_selected.connect(self._on_poster_clicked)
        lay.addWidget(self.poster_grid)

        img_row = QHBoxLayout()
        self.local_img_btn = QPushButton("Use Local Image")
        self.local_img_btn.clicked.connect(self._browse_image)
        img_row.addWidget(self.local_img_btn)
        self.local_img_label = QLabel("")
        img_row.addWidget(self.local_img_label, 1)
        lay.addLayout(img_row)

        return w

    def _build_bottom(self) -> QWidget:
        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)

        self.progress = QProgressBar()
        self.progress.setMaximumWidth(200)
        self.progress.hide()
        lay.addWidget(self.progress)

        self.attach_btn = QPushButton("Attach Poster")
        self.attach_btn.setEnabled(False)
        self.attach_btn.clicked.connect(self._attach)
        lay.addWidget(self.attach_btn)

        self.meta_check = QCheckBox("Scrape metadata")
        self.meta_check.setToolTip("Embed TMDB metadata (title, overview, rating, credits)")
        lay.addWidget(self.meta_check)

        self.mkv_check = QCheckBox("Convert MP4 to MKV")
        self.mkv_check.setChecked(bool(config.get("convert_to_mkv")))
        self.mkv_check.setToolTip(
            "Lossless remux (stream copy) before attaching; keeps the original file"
        )
        self.mkv_check.toggled.connect(
            lambda checked: config.set("convert_to_mkv", checked)
        )
        lay.addWidget(self.mkv_check)

        self.remove_btn = QPushButton("Remove Poster")
        self.remove_btn.clicked.connect(self._remove)
        lay.addWidget(self.remove_btn)

        self.convert_btn = QPushButton("Convert to MKV")
        self.convert_btn.setToolTip(
            "Lossless remux (stream copy) the selected files to MKV, keeps the originals"
        )
        self.convert_btn.clicked.connect(self._convert)
        lay.addWidget(self.convert_btn)

        more = QToolButton()
        more.setText("More")
        more.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        more_menu = QMenu(self)
        self.remove_meta_btn = more_menu.addAction("Remove Metadata")
        self.remove_meta_btn.setToolTip("Strip all title/tags metadata from the video")
        self.remove_meta_btn.triggered.connect(self._remove_metadata)
        self.scrape_meta_btn = more_menu.addAction("Scrape Metadata")
        self.scrape_meta_btn.setToolTip(
            "Write TMDB metadata (title, overview, rating, credits) without attaching a poster"
        )
        self.scrape_meta_btn.triggered.connect(self._scrape_metadata)
        more.setMenu(more_menu)
        lay.addWidget(more)

        return w

    def _scan_folder(self):
        if getattr(self, "_scanning", False):
            return
        self._portal_pick.pick(
            self._on_folder_picked, "Select Folder to Scan", directory=True
        )

    def _on_folder_picked(self, path):
        if not path:
            return
        self._scanning = True
        self.status_label.setText(f"Scanning {path}...")
        self._scan_worker = ScanWorker(path)
        self._scan_worker.progress.connect(lambda msg: self.status_label.setText(msg))
        self._scan_worker.finished.connect(self._on_scan_done)
        self._scan_worker.error.connect(self._on_scan_error)
        self._track_worker(self._scan_worker)
        self._scan_worker.start()

    def _on_scan_error(self, err):
        self._scanning = False
        self.status_label.setText(f"Scan failed: {err}")
        QMessageBox.critical(self, "Error", f"Scan failed:\n{err}")

    def _on_scan_done(self, groups):
        self._scanning = False
        if not groups:
            self.status_label.setText("No videos found")
            QMessageBox.information(self, "Scan", "No videos found in that folder.")
            return
        count = sum(len(g.files) for g in groups)
        self.status_label.setText(f"Found {count} files, resolving titles...")
        self._resolve_worker = ResolveWorker(
            groups, api_delay=config.get("scan_api_delay") or 0.25
        )
        self._resolve_worker.progress.connect(lambda msg: self.status_label.setText(msg))
        self._resolve_worker.finished.connect(self._on_resolve_done)
        self._resolve_worker.error.connect(self._on_scan_error)
        self._track_worker(self._resolve_worker)
        self._resolve_worker.start()

    def _on_resolve_done(self, resolved):
        ok = sum(1 for e in resolved if e["status"] == "ok")
        self.status_label.setText(f"Matched {ok}/{len(resolved)} titles")
        dlg = ScanReviewDialog(resolved, self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        entries = [e for e in resolved if e["status"] == "ok"]
        if not dlg.skip_unmatched.isChecked():
            entries = [e for e in resolved if e["status"] != "error"]
        if not entries:
            self.status_label.setText("Nothing to attach")
            return
        paths = [p for e in entries for p in e["group"].files]
        self._append_paths(paths)
        skip = config.get("scan_skip_existing")
        self.progress.show()
        self.progress.setRange(0, 0)
        self.status_label.setText(f"Attaching posters to {len(paths)} files...")
        self._auto_worker = AutoAttachWorker(
            entries,
            scrape_metadata=dlg.embed_meta.isChecked(),
            skip_existing=skip,
            api_delay=config.get("scan_api_delay") or 0.25,
            to_mkv=dlg.convert_mkv.isChecked(),
        )
        self._auto_worker.progress.connect(lambda msg: self.status_label.setText(msg))
        self._auto_worker.finished.connect(self._on_auto_done)
        self._auto_worker.error.connect(self._on_auto_error)
        self._track_worker(self._auto_worker)
        self._auto_worker.start()

    def _on_auto_error(self, err):
        self.progress.hide()
        self.status_label.setText(f"Auto-attach failed: {err}")
        QMessageBox.critical(self, "Error", f"Auto-attach failed:\n{err}")

    def _on_auto_done(self, summary):
        self.progress.hide()
        self._refresh_file_rows()
        ok, fail, skipped = summary["ok"], summary["fail"], summary["skipped"]
        self.status_label.setText(
            f"Auto-attach: {ok} ok, {skipped} skipped, {fail} failed"
        )
        if fail:
            detail = "\n".join(summary["errors"][:10])
            QMessageBox.warning(
                self, "Auto-Attach Complete",
                f"{ok} attached, {skipped} skipped.\n{fail} failed.\n\n{detail}",
            )
        else:
            QMessageBox.information(
                self, "Done",
                f"Posters attached to {ok} files"
                + (f", {skipped} skipped" if skipped else "") + ".",
            )

    def _browse_video(self):
        last_dir = config.get("last_dir") or str(Path.home())
        self._portal_pick.pick(
            self._on_video_picked,
            "Select Video",
            last_dir,
            filters="Video Files (*.mkv *.mp4 *.avi *.mov *.webm *.flv *.wmv *.ts *.m4v *.mpeg *.mpg);;All Files (*)",
        )

    def _on_video_picked(self, path):
        if path:
            self._load_video(path)

    def _browse_multi(self):
        last_dir = config.get("last_dir") or str(Path.home())
        self._portal_pick.pick(
            self._on_videos_picked,
            "Select Videos",
            last_dir,
            multiple=True,
            filters="Video Files (*.mkv *.mp4 *.avi *.mov *.webm *.flv *.wmv *.ts *.m4v *.mpeg *.mpg);;All Files (*)",
        )

    def _on_videos_picked(self, paths):
        if paths:
            self._load_videos(paths)

    def _search(self):
        query = self.search_input.text().strip()
        if not query:
            return

        self.search_btn.setEnabled(False)
        self.search_btn.setText("Searching...")
        self.status_label.setText("Searching...")

        self._search_worker = SearchWorker(query)
        self._search_worker.finished.connect(self._on_search_done)
        self._search_worker.error.connect(self._on_search_error)
        self._track_worker(self._search_worker)
        self._search_worker.start()

    def _on_search_done(self, results):
        self.search_btn.setEnabled(True)
        self.search_btn.setText("Search")
        self.results_list.clear()

        if not results:
            self.status_label.setText("No results found")
            return

        for r in results:
            label = f"{r['title']} ({r['year']}) [{r['media_type']}]"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, r)
            self.results_list.addItem(item)

        self.status_label.setText(f"Found {len(results)} results")

    def _on_search_error(self, err):
        self.search_btn.setEnabled(True)
        self.search_btn.setText("Search")
        self.status_label.setText(f"Search failed: {err}")

    def _on_result_selected(self, item: QListWidgetItem):
        data = item.data(Qt.ItemDataRole.UserRole)
        self.current_media = {"id": data["id"], "media_type": data["media_type"]}
        self.status_label.setText(f"Loading posters for {data['title']}...")

        self._poster_worker = PosterWorker(data["id"], data["media_type"])
        self._poster_worker.finished.connect(self._on_posters_loaded)
        self._poster_worker.error.connect(self._on_search_error)
        self._track_worker(self._poster_worker)
        self._poster_worker.start()

    def _on_posters_loaded(self, posters):
        self.current_posters = posters
        self.poster_grid.load_posters(posters)
        self.status_label.setText(f"Loaded {len(posters)} posters")

    def _on_poster_clicked(self, poster: dict):
        self.poster_grid.select_by_poster(poster)
        dlg = PosterPreviewDialog(poster, self)
        dlg.poster_selected.connect(self._on_poster_selected)
        dlg.exec()

    def _on_poster_selected(self, poster: dict):
        self.selected_poster = poster
        self.local_poster_path = None
        self.local_img_label.setText("")
        self.attach_btn.setEnabled(True)
        self.status_label.setText(f"Selected poster: {poster['width']}x{poster['height']}")

    def _browse_image(self):
        self._portal_pick.pick(
            self._on_local_image_picked,
            "Select Image",
            self._last_image_dir or "",
            filters="Images (*.jpg *.jpeg *.png *.bmp *.webp *.gif *.tiff *.svg *.ico);;All Files (*)",
        )

    def _on_local_image_picked(self, path):
        if not path or not os.path.exists(path):
            return
        self.local_poster_path = path
        self._last_image_dir = str(Path(path).parent)
        self.selected_poster = None
        self.attach_btn.setEnabled(True)
        self.local_img_label.setText(Path(path).name)
        self.status_label.setText(f"Local image: {Path(path).name}")

    def _attach(self):
        targets = self._active_targets()
        if not targets:
            QMessageBox.warning(self, "Error", "No video file selected")
            return
        if not self.selected_poster and not self.local_poster_path:
            QMessageBox.warning(self, "Error", "No poster selected")
            return

        self.progress.show()
        self.progress.setRange(0, 0)
        self.attach_btn.setEnabled(False)
        self.status_label.setText("Preparing poster...")

        poster_path = None
        metadata = None
        used_batch = False
        try:
            if self.local_poster_path:
                poster_path = self.local_poster_path
            else:
                fd, poster_path = tempfile.mkstemp(suffix=".jpg")
                os.close(fd)
                os.chmod(poster_path, 0o600)
                tmdb.download_image(self.selected_poster["url"], poster_path)

            if self.meta_check.isChecked() and self.current_media:
                self.status_label.setText("Scraping metadata...")
                metadata = tmdb.get_details(
                    self.current_media["id"], self.current_media["media_type"]
                )

            if len(targets) == 1:
                target = targets[0]
                out = attacher.full_attach(target, poster_path, metadata=metadata,
                                           to_mkv=self.mkv_check.isChecked())
                if out != target:
                    if target in self.selected_video_paths:
                        self.selected_video_paths.discard(target)
                        self.selected_video_paths.add(out)
                    if self.video_path == target:
                        self.video_path = out
                    for i, p in enumerate(self.video_paths):
                        if p == target:
                            self.video_paths[i] = out
                    self._refresh_file_rows()
                    target = out
                name = Path(target).name
                self.status_label.setText(f"Poster attached to {name}!")
                QMessageBox.information(self, "Done", f"Poster attached to {name}!")
            else:
                used_batch = True
                self._batch_attach(targets, poster_path, metadata,
                                   to_mkv=self.mkv_check.isChecked())
        except Exception as e:
            self.status_label.setText(f"Error: {e}")
            QMessageBox.critical(self, "Error", f"Attachment failed:\n{e}")
        finally:
            if not used_batch:
                if poster_path and poster_path != self.local_poster_path and os.path.exists(poster_path):
                    os.unlink(poster_path)
                self.progress.hide()
                self.attach_btn.setEnabled(True)

    def _batch_attach(self, targets, poster_path, metadata=None, to_mkv=False):
        self.progress.setRange(0, len(targets))
        self.progress.setValue(0)
        self.status_label.setText(f"Attaching to 1/{len(targets)}...")

        self._batch_worker = BatchWorker(
            targets, poster_path, metadata,
            cleanup_poster=(poster_path != self.local_poster_path),
            to_mkv=to_mkv,
        )
        self._batch_worker.progress.connect(self._on_batch_progress)
        self._batch_worker.finished.connect(self._on_batch_done)
        self._track_worker(self._batch_worker)
        self._batch_worker.start()

    def _on_batch_progress(self, current, total, filename):
        self.progress.setValue(current)
        self.status_label.setText(f"Attaching {current}/{total}: {filename}")

    def _replace_path(self, old: str, new: str):
        if old in self.selected_video_paths:
            self.selected_video_paths.discard(old)
            self.selected_video_paths.add(new)
        if self.video_path == old:
            self.video_path = new
        try:
            self.video_paths[self.video_paths.index(old)] = new
        except ValueError:
            pass

    def _on_batch_done(self, results):
        self.progress.hide()
        self.attach_btn.setEnabled(True)
        for r in results:
            if r["ok"] and r["out"] != r["path"]:
                self._replace_path(r["path"], r["out"])
        self._refresh_file_rows()
        ok = sum(1 for r in results if r["ok"])
        fail = len(results) - ok
        if fail:
            detail = "\n".join(
                f"{Path(r['path']).name}: {r['out']}" for r in results if not r["ok"]
            )[:2000]
            QMessageBox.warning(self, "Batch Complete",
                                f"Attached to {ok} files.\n{fail} failed.\n\n{detail}")
        else:
            QMessageBox.information(self, "Done",
                                    f"Poster attached to all {ok} files!")
        self.status_label.setText(f"Batch: {ok} succeeded, {fail} failed")

    def _convert(self):
        targets = self._active_targets()
        if not targets:
            QMessageBox.warning(self, "Error", "No video file selected")
            return
        self.progress.show()
        self.progress.setRange(0, len(targets))
        self.progress.setValue(0)
        self.convert_btn.setEnabled(False)
        self.status_label.setText(f"Converting 1/{len(targets)}...")
        self._convert_worker = ConvertWorker(targets)
        self._convert_worker.progress.connect(self._on_convert_progress)
        self._convert_worker.finished.connect(self._on_convert_done)
        self._track_worker(self._convert_worker)
        self._convert_worker.start()

    def _on_convert_progress(self, current, total, filename):
        self.progress.setValue(current)
        self.status_label.setText(f"Converting {current}/{total}: {filename}")

    def _on_convert_done(self, results):
        self.progress.hide()
        self.convert_btn.setEnabled(True)
        for r in results:
            if r["ok"] and r["out"] != r["path"]:
                self._replace_path(r["path"], r["out"])
        self._refresh_file_rows()
        ok = sum(1 for r in results if r["ok"])
        fail = len(results) - ok
        if fail:
            detail = "\n".join(
                f"{Path(r['path']).name}: {r['error']}" for r in results if not r["ok"]
            )[:2000]
            QMessageBox.warning(
                self, "Convert Complete",
                f"Converted {ok} file(s) to MKV.\n{fail} skipped/failed.\n\n{detail}",
            )
        else:
            QMessageBox.information(self, "Done",
                                    f"Converted {ok} file(s) to MKV!")
        self.status_label.setText(f"Convert: {ok} converted, {fail} skipped/failed")

    def _remove(self):
        targets = self._active_targets()
        if not targets:
            QMessageBox.warning(self, "Error", "No video file selected")
            return

        count = len(targets)
        msg = f"Remove poster from this video?" if count == 1 else f"Remove poster from {count} files?"
        reply = QMessageBox.question(
            self, "Confirm", msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        if count == 1:
            try:
                attacher.remove_poster(targets[0])
                name = Path(targets[0]).name
                self.status_label.setText(f"Poster removed from {name}")
                QMessageBox.information(self, "Done", f"Poster removed from {name}!")
            except Exception as e:
                self.status_label.setText("Error removing poster")
                QMessageBox.critical(self, "Error", f"Failed to remove poster:\n{e}")
        else:
            self._batch_remove(targets)

    def _batch_remove(self, targets):
        self.progress.show()
        self.progress.setRange(0, len(targets))
        self.progress.setValue(0)
        self.attach_btn.setEnabled(False)
        ok = 0
        fail = 0
        for i, path in enumerate(targets):
            self.progress.setValue(i + 1)
            self.status_label.setText(f"Removing {i + 1}/{len(targets)}: {Path(path).name}")
            try:
                attacher.remove_poster(path)
                ok += 1
            except Exception:
                fail += 1
        self.progress.hide()
        self.attach_btn.setEnabled(True)
        if fail:
            QMessageBox.warning(self, "Done", f"Removed from {ok} files.\n{fail} failed.")
        else:
            QMessageBox.information(self, "Done", f"Poster removed from all {ok} files!")
        self.status_label.setText(f"Remove: {ok} succeeded, {fail} failed")

    def _open_settings(self):
        if ApiKeyDialog(self).exec() == QDialog.DialogCode.Accepted:
            self.status_label.setText("Settings saved")

    def _remove_metadata(self):
        videos = self._active_targets()
        if not videos:
            QMessageBox.warning(self, "No Files", "Select a video file first.")
            return
        msg = (f"Remove all metadata from {len(videos)} file(s)?\n"
               "Poster artwork will be kept.")
        if QMessageBox.question(self, "Remove Metadata", msg) != QMessageBox.StandardButton.Yes:
            return
        try:
            fail = self._batch_remove_metadata(videos)
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))
            return
        ok = len(videos) - len(fail)
        if fail:
            QMessageBox.warning(self, "Done", f"Removed metadata from {ok} files.\n{fail} failed.")
        else:
            QMessageBox.information(self, "Done", f"Metadata removed from all {ok} files!")
        self.status_label.setText(f"Remove metadata: {ok} succeeded, {len(fail)} failed")

    def _batch_remove_metadata(self, videos):
        fail = []
        for v in videos:
            try:
                attacher.remove_metadata(v)
            except Exception as e:
                fail.append(f"{v}\n  {e}")
        return fail

    def _scrape_metadata(self):
        videos = self._active_targets()
        if not videos:
            QMessageBox.warning(self, "No Files", "Select a video file first.")
            return
        msg = (f"Scrape and write TMDB metadata for {len(videos)} file(s)?\n"
               "Poster artwork will be kept.")
        if QMessageBox.question(self, "Scrape Metadata", msg) != QMessageBox.StandardButton.Yes:
            return

        self.progress.show()
        self.progress.setRange(0, len(videos))
        self.progress.setValue(0)
        self.scrape_meta_btn.setEnabled(False)
        self.status_label.setText("Scraping metadata...")
        try:
            fail = self._batch_scrape_metadata(videos)
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))
            return
        finally:
            self.progress.hide()
            self.scrape_meta_btn.setEnabled(True)
        ok = len(videos) - len(fail)
        if fail:
            QMessageBox.warning(self, "Done", f"Metadata written to {ok} files.\n{fail} failed.")
        else:
            QMessageBox.information(self, "Done", f"Metadata written to all {ok} files!")
        self.status_label.setText(f"Scrape metadata: {ok} succeeded, {len(fail)} failed")

    def _batch_scrape_metadata(self, videos):
        fail = []
        for i, v in enumerate(videos):
            self.progress.setValue(i + 1)
            self.status_label.setText(f"Scraping {i + 1}/{len(videos)}: {Path(v).name}")
            try:
                metadata = tmdb.details_for_path(v, self.current_media)
                attacher.write_metadata(v, metadata)
            except Exception as e:
                fail.append(f"{Path(v).name}: {e}")
        return fail

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if parser.is_video(url.toLocalFile()):
                    event.acceptProposedAction()
                    return

    def dropEvent(self, event: QDropEvent):
        videos = [url.toLocalFile() for url in event.mimeData().urls()
                  if parser.is_video(url.toLocalFile())]
        if not videos:
            return
        if len(videos) == 1:
            self._load_video(videos[0])
        else:
            self._load_videos(videos)

    def _active_targets(self):
        if self.selected_video_paths:
            return [p for p in self.video_paths if p in self.selected_video_paths]
        return self.video_paths or ([self.video_path] if self.video_path else [])

    def _on_file_clicked(self, item: QListWidgetItem):
        path = item.data(Qt.ItemDataRole.UserRole)
        if not path:
            return
        parsed = parser.parse_filename(path)
        self.search_input.setText(parser.build_search_query(parsed))

    def _on_file_selection_changed(self):
        selected = {
            item.data(Qt.ItemDataRole.UserRole)
            for item in self.file_list.selectedItems()
            if item.data(Qt.ItemDataRole.UserRole)
        }
        if selected == self.selected_video_paths:
            return
        self.selected_video_paths = selected
        if selected:
            self.status_label.setText(
                f"{len(selected)} file(s) selected — attach/remove apply to these only")
        elif self.video_paths:
            self.status_label.setText(
                f"No files selected — operations apply to all {len(self.video_paths)} files")

    def _load_video(self, path):
        self.video_path = path
        self.video_paths = [path]
        self.selected_video_paths = set()
        config.set("last_dir", str(Path(path).parent))
        self._append_paths([path], replace=True)
        parsed = parser.parse_filename(path)
        self.search_input.setText(parser.build_search_query(parsed))
        self._search()

    def _load_videos(self, paths):
        self.video_path = paths[0]
        self.video_paths = paths
        self.selected_video_paths = set()
        config.set("last_dir", str(Path(paths[0]).parent))
        self._append_paths(paths, replace=True)
        parsed = parser.parse_filename(paths[0])
        self.search_input.setText(parser.build_search_query(parsed))
        self._search()

    def _append_paths(self, paths, replace=False):
        if replace:
            self.video_paths = list(paths)
            self.file_list.clear()
            new_paths = list(paths)
        else:
            existing = set(self.video_paths)
            new_paths = [p for p in paths if p not in existing]
            if not new_paths:
                self._refresh_file_rows()
                return
            self.video_paths.extend(new_paths)
        self.selected_video_paths = set()
        self._refresh_file_rows()

    def _clear_files(self):
        self.video_paths = []
        self.video_path = ""
        self.selected_video_paths = set()
        self.file_list.clear()
        self.files_label.setText("Files (0)")

    def _refresh_file_rows(self):
        self.file_list.clear()
        common = ""
        if self.video_paths:
            try:
                common = os.path.commonpath(self.video_paths)
            except ValueError:
                common = ""
        for p in self.video_paths:
            rel = os.path.relpath(p, common) if common else p
            if rel in ("", "."):
                rel = os.path.basename(p)
            if len(rel) >= len(p):
                rel = p
            has = scanner.has_poster(p)
            item = QListWidgetItem(f"{'✓' if has else ' '}  {rel}")
            item.setData(Qt.ItemDataRole.UserRole, p)
            item.setData(Qt.ItemDataRole.UserRole + 1, has)
            if has:
                item.setToolTip("Poster already attached")
            self.file_list.addItem(item)
        self.files_label.setText(f"Files ({len(self.video_paths)})")
