from PyQt6.QtCore import QObject, QPoint, QRect, QRunnable, QSize, Qt, QThreadPool, pyqtSignal
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtWidgets import (
    QFrame,
    QLabel,
    QLayout,
    QScrollArea,
    QWidget,
)

from mak_attatch.core import tmdb

from .main_window import OPERATION_ERRORS

# Popular titles have 100-300 posters. One thread per thumbnail used to start
# that many concurrent requests on one shared HTTP session; a small pool keeps
# it bounded and lets queued-but-unneeded loads be skipped.
_POOL_THREADS = 6
_pool: QThreadPool | None = None


def _image_pool() -> QThreadPool:
    global _pool
    if _pool is None:
        _pool = QThreadPool()
        _pool.setMaxThreadCount(_POOL_THREADS)
    return _pool


class ImageRequest(QObject):
    """A pending image download; cancel() makes a queued load a no-op."""

    loaded = pyqtSignal(QImage)

    def __init__(self, url: str):
        super().__init__()
        self.url = url
        self.cancelled = False

    def cancel(self):
        self.cancelled = True


def _fetch_image_bytes(url: str) -> bytes:
    """Download at most tmdb.MAX_IMAGE_SIZE bytes (previews were unbounded)."""
    resp = tmdb._fetch(url, stream=True)
    try:
        data = bytearray()
        for chunk in resp.iter_content(65536):
            data += chunk
            if len(data) > tmdb.MAX_IMAGE_SIZE:
                raise tmdb.TMDBError("Image exceeded size limit")
        return bytes(data)
    finally:
        resp.close()


class _ImageTask(QRunnable):
    def __init__(self, request: ImageRequest):
        super().__init__()
        self.request = request

    def run(self):
        req = self.request
        if req.cancelled:
            return
        try:
            data = _fetch_image_bytes(req.url)
        except OPERATION_ERRORS:
            return
        # QImage (unlike QPixmap) may be built off the GUI thread; the
        # receiver converts it to a pixmap on the GUI thread.
        image = QImage()
        if req.cancelled or not image.loadFromData(data):
            return
        try:
            req.loaded.emit(image)
        except RuntimeError:
            pass  # the request object was already deleted


def load_image(url: str, slot) -> ImageRequest:
    """Fetch an image on the shared pool and deliver a QImage to ``slot``."""
    req = ImageRequest(url)
    req.loaded.connect(slot)
    _image_pool().start(_ImageTask(req))
    return req


class PosterCard(QFrame):
    clicked = pyqtSignal(dict)

    def __init__(self, poster: dict, parent=None):
        super().__init__(parent)
        self.poster = poster
        self.setFixedSize(180, 270)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet("""
            PosterCard {
                border: 2px solid transparent;
                border-radius: 6px;
            }
        """)

        layout = QFlowLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)

        self.thumb = QLabel()
        self.thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.thumb.setFixedSize(168, 230)
        layout.addWidget(self.thumb)

        info = QLabel(f"{poster.get('width', 0)}x{poster.get('height', 0)}")
        info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        info.setStyleSheet("font-size: 11px;")
        layout.addWidget(info)

        lang = poster.get("lang") or "??"
        lang_label = QLabel(lang.upper())
        lang_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lang_label.setStyleSheet("font-size: 10px;")
        layout.addWidget(lang_label)

        self._selected = False
        self.request = load_image(self.poster["thumb_url"], self._on_loaded)

    def _on_loaded(self, image: QImage):
        self.thumb.setPixmap(
            QPixmap.fromImage(image).scaled(
                self.thumb.size(), Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation)
        )

    def set_selected(self, selected: bool):
        self._selected = selected
        border = "#cba6f7" if selected else "transparent"
        self.setStyleSheet(
            f"PosterCard {{ border: 2px solid {border}; border-radius: 6px; }}"
        )

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.poster)
        super().mousePressEvent(event)


class PosterGrid(QScrollArea):
    poster_selected = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setMinimumHeight(350)
        self.setStyleSheet("QScrollArea { border: none; }")

        self.container = QWidget()
        self.flow = QFlowLayout(self.container)
        self.setWidget(self.container)

        self.cards: list[PosterCard] = []
        self._selected_card: PosterCard | None = None

    def load_posters(self, posters: list[dict]):
        self.clear()
        for p in posters:
            card = PosterCard(p)
            card.clicked.connect(self.poster_selected.emit)
            self.flow.addWidget(card)
            self.cards.append(card)

    def select_by_poster(self, poster: dict):
        key = poster.get("file_path") or poster.get("thumb_url")
        for card in self.cards:
            card_key = card.poster.get("file_path") or card.poster.get("thumb_url")
            same = bool(key) and card_key == key
            card.set_selected(same)
            if same:
                self._selected_card = card

    def clear(self):
        self._selected_card = None
        cards, self.cards = self.cards, []
        for card in cards:
            # Queued thumbnail loads for removed cards are skipped; running
            # ones finish in the pool and their result is simply dropped.
            card.request.cancel()
            self.flow.removeWidget(card)
            card.setParent(None)
            card.deleteLater()

class QFlowLayout(QLayout):
    def __init__(self, parent=None, spacing=10):
        super().__init__(parent)
        self._spacing = spacing
        self._items = []

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, index):
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index):
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._do_layout(QRect(0, 0, width, 0), test_only=True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do_layout(rect, test_only=False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize(0, 0)
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        return size

    def _do_layout(self, rect, test_only):
        x = rect.x()
        y = rect.y()
        line_height = 0

        for item in self._items:
            space_x = self._spacing
            space_y = self._spacing
            next_x = x + item.sizeHint().width() + space_x
            if next_x - space_x > rect.right() and line_height > 0:
                x = rect.x()
                y = y + line_height + space_y
                next_x = x + item.sizeHint().width() + space_x
                line_height = 0
            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), item.sizeHint()))
            x = next_x
            line_height = max(line_height, item.sizeHint().height())

        return y + line_height - rect.y()
