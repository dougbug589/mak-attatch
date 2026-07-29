import os
import tempfile
from pathlib import Path

from PyQt6.QtCore import QThread, QTimer, pyqtSignal, Qt
from PyQt6.QtGui import QIcon, QPixmap, QDragEnterEvent, QDropEvent
from PyQt6.QtWidgets import (
    QComboBox, QDialog, QFileDialog, QHBoxLayout, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QMainWindow,
    QMessageBox, QPushButton, QSplitter, QVBoxLayout, QWidget,
    QProgressBar, QSizePolicy,
)

import config
from core import attacher, parser, tmdb


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

    def __init__(self, video_paths: list, poster_path: str):
        super().__init__()
        self.video_paths = video_paths
        self.poster_path = poster_path

    def run(self):
        results = []
        total = len(self.video_paths)
        for i, path in enumerate(self.video_paths):
            self.progress.emit(i + 1, total, Path(path).name)
            try:
                out = attacher.full_attach(path, self.poster_path)
                results.append({"path": path, "out": out, "ok": True})
            except Exception as e:
                results.append({"path": path, "out": str(e), "ok": False})
        self.finished.emit(results)


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
            except Exception:
                pass


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("mak-attatch")
        self.setMinimumSize(900, 700)
        icon_path = Path(__file__).resolve().parent.parent / "assets" / "P.png"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

        self.video_path = ""
        self.video_paths = []
        self.current_posters = []
        self.selected_poster = None
        self.local_poster_path = None

        self.setAcceptDrops(True)

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setSpacing(12)

        if not config.get("tmdb_api_key"):
            QTimer.singleShot(0, self._setup_api_key)

        root.addWidget(self._build_top())
        root.addWidget(self._build_results())
        root.addWidget(self._build_poster_area())
        root.addWidget(self._build_bottom())

    def _setup_api_key(self):
        if ApiKeyDialog(self).exec() != QDialog.DialogCode.Accepted:
            pass

    def _build_top(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)

        row1 = QHBoxLayout()

        self.file_btn = QPushButton("Browse Video")
        self.file_btn.clicked.connect(self._browse_video)
        row1.addWidget(self.file_btn)

        self.multi_btn = QPushButton("Browse Multiple")
        self.multi_btn.clicked.connect(self._browse_multi)
        row1.addWidget(self.multi_btn)

        self.file_label = QLabel("No file selected")
        row1.addWidget(self.file_label, 1)
        lay.addLayout(row1)

        self.file_list = QListWidget()
        self.file_list.setMaximumHeight(80)
        self.file_list.hide()
        lay.addWidget(self.file_list)

        row2 = QHBoxLayout()

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Type movie/show name...")
        self.search_input.returnPressed.connect(self._search)
        row2.addWidget(self.search_input, 1)

        self.search_btn = QPushButton("Search")
        self.search_btn.clicked.connect(self._search)
        row2.addWidget(self.search_btn)

        self.settings_btn = QPushButton("Settings")
        self.settings_btn.clicked.connect(self._open_settings)
        row2.addWidget(self.settings_btn)
        lay.addLayout(row2)

        return w

    def _build_results(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)

        lay.addWidget(QLabel("Search Results:"))

        self.results_list = QListWidget()
        self.results_list.setMaximumHeight(150)
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

        self.status_label = QLabel("")
        lay.addWidget(self.status_label, 1)

        self.progress = QProgressBar()
        self.progress.setMaximumWidth(200)
        self.progress.hide()
        lay.addWidget(self.progress)

        self.attach_btn = QPushButton("Attach Poster")
        self.attach_btn.setEnabled(False)
        self.attach_btn.clicked.connect(self._attach)
        lay.addWidget(self.attach_btn)

        self.remove_btn = QPushButton("Remove Poster")
        self.remove_btn.clicked.connect(self._remove)
        lay.addWidget(self.remove_btn)

        return w

    def _browse_video(self):
        last_dir = config.get("last_dir") or str(Path.home())
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Video",
            last_dir,
            "Video Files (*.mkv *.mp4 *.avi *.mov *.webm *.flv *.wmv *.ts *.m4v *.mpeg *.mpg);;All Files (*)",
        )
        if path:
            self._load_video(path)

    def _browse_multi(self):
        last_dir = config.get("last_dir") or str(Path.home())
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Select Videos",
            last_dir,
            "Video Files (*.mkv *.mp4 *.avi *.mov *.webm *.flv *.wmv *.ts *.m4v *.mpeg *.mpg);;All Files (*)",
        )
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
        self.status_label.setText("Search failed")

    def _on_result_selected(self, item: QListWidgetItem):
        data = item.data(Qt.ItemDataRole.UserRole)
        self.status_label.setText(f"Loading posters for {data['title']}...")

        self._poster_worker = PosterWorker(data["id"], data["media_type"])
        self._poster_worker.finished.connect(self._on_posters_loaded)
        self._poster_worker.error.connect(self._on_search_error)
        self._poster_worker.start()

    def _on_posters_loaded(self, posters):
        self.current_posters = posters
        self.poster_grid.load_posters(posters)
        self.status_label.setText(f"Loaded {len(posters)} posters")

    def _on_poster_clicked(self, poster: dict):
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
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Image", "",
            "Images (*.jpg *.jpeg *.png *.bmp *.webp *.gif *.tiff);;All Files (*)"
        )
        if path:
            self.local_poster_path = path
            self.selected_poster = None
            self.attach_btn.setEnabled(True)
            self.local_img_label.setText(Path(path).name)
            self.status_label.setText(f"Local image: {Path(path).name}")

    def _attach(self):
        if not self.video_paths:
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
        try:
            if self.local_poster_path:
                poster_path = self.local_poster_path
            else:
                fd, poster_path = tempfile.mkstemp(suffix=".jpg")
                os.close(fd)
                os.chmod(poster_path, 0o600)
                tmdb.download_image(self.selected_poster["url"], poster_path)

            if len(self.video_paths) == 1:
                out = attacher.full_attach(self.video_paths[0], poster_path)
                if out != self.video_paths[0]:
                    self.video_path = out
                    self.video_paths = [out]
                    self.file_label.setText(out)
                self.status_label.setText("Poster attached successfully!")
                QMessageBox.information(self, "Done", "Poster attached successfully!")
            else:
                self._batch_attach(poster_path)
        except Exception as e:
            self.status_label.setText(f"Error: {e}")
            QMessageBox.critical(self, "Error", f"Attachment failed:\n{e}")
        finally:
            if poster_path and poster_path != self.local_poster_path and os.path.exists(poster_path):
                os.unlink(poster_path)
            if len(self.video_paths) <= 1:
                self.progress.hide()
                self.attach_btn.setEnabled(True)

    def _batch_attach(self, poster_path):
        self.progress.setRange(0, len(self.video_paths))
        self.progress.setValue(0)
        self.status_label.setText(f"Attaching to 1/{len(self.video_paths)}...")

        self._batch_worker = BatchWorker(self.video_paths, poster_path)
        self._batch_worker.progress.connect(self._on_batch_progress)
        self._batch_worker.finished.connect(self._on_batch_done)
        self._batch_worker.start()

    def _on_batch_progress(self, current, total, filename):
        self.progress.setValue(current)
        self.status_label.setText(f"Attaching {current}/{total}: {filename}")

    def _on_batch_done(self, results):
        self.progress.hide()
        self.attach_btn.setEnabled(True)
        ok = sum(1 for r in results if r["ok"])
        fail = len(results) - ok
        if fail:
            QMessageBox.warning(self, "Batch Complete",
                                f"Attached to {ok} files.\n{fail} failed.")
        else:
            QMessageBox.information(self, "Done",
                                    f"Poster attached to all {ok} files!")
        self.status_label.setText(f"Batch: {ok} succeeded, {fail} failed")

    def _remove(self):
        if not self.video_paths:
            QMessageBox.warning(self, "Error", "No video file selected")
            return

        count = len(self.video_paths)
        msg = f"Remove poster from this video?" if count == 1 else f"Remove poster from {count} files?"
        reply = QMessageBox.question(
            self, "Confirm", msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        if count == 1:
            try:
                attacher.remove_poster(self.video_paths[0])
                self.status_label.setText("Poster removed")
                QMessageBox.information(self, "Done", "Poster removed!")
            except Exception as e:
                self.status_label.setText("Error removing poster")
                QMessageBox.critical(self, "Error", f"Failed to remove poster:\n{e}")
        else:
            self._batch_remove()

    def _batch_remove(self):
        self.progress.show()
        self.progress.setRange(0, len(self.video_paths))
        self.progress.setValue(0)
        self.attach_btn.setEnabled(False)
        ok = 0
        fail = 0
        for i, path in enumerate(self.video_paths):
            self.progress.setValue(i + 1)
            self.status_label.setText(f"Removing {i + 1}/{len(self.video_paths)}: {Path(path).name}")
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

    def _load_video(self, path):
        self.video_path = path
        self.video_paths = [path]
        self.file_label.setText(path)
        self.file_list.hide()
        self.file_list.clear()
        config.set("last_dir", str(Path(path).parent))
        parsed = parser.parse_filename(path)
        self.search_input.setText(parser.build_search_query(parsed))
        self._search()

    def _load_videos(self, paths):
        self.video_path = paths[0]
        self.video_paths = paths
        self.file_label.setText(f"{len(paths)} files selected")
        self.file_list.clear()
        for p in paths:
            self.file_list.addItem(Path(p).name)
        self.file_list.show()
        config.set("last_dir", str(Path(paths[0]).parent))
        parsed = parser.parse_filename(paths[0])
        self.search_input.setText(parser.build_search_query(parsed))
        self._search()
