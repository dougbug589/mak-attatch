from PyQt6.QtCore import Qt, pyqtSignal, QThread, QRect, QSize, QPoint
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QFrame, QLabel, QScrollArea, QSizePolicy, QWidget, QLayout, QLayoutItem,
)

from core import tmdb


class ImageLoader(QThread):
    loaded = pyqtSignal(int, QPixmap)

    def __init__(self, index: int, url: str):
        super().__init__()
        self.index = index
        self.url = url

    def run(self):
        try:
            resp = tmdb._fetch(self.url)
            pixmap = QPixmap()
            pixmap.loadFromData(resp.content)
            self.loaded.emit(self.index, pixmap)
        except Exception:  # nosec B110
            pass


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

        info = QLabel(f"{poster['width']}x{poster['height']}")
        info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        info.setStyleSheet("font-size: 11px;")
        layout.addWidget(info)

        lang = poster.get("lang") or "??"
        lang_label = QLabel(lang.upper())
        lang_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lang_label.setStyleSheet("font-size: 10px;")
        layout.addWidget(lang_label)

        self.loader = None
        self._selected = False
        self._load_thumb()

    def _load_thumb(self):
        self.loader = ImageLoader(0, self.poster["thumb_url"])
        self.loader.loaded.connect(self._on_loaded)
        self.loader.start()

    def _on_loaded(self, _idx, pixmap):
        self.thumb.setPixmap(
            pixmap.scaled(self.thumb.size(), Qt.AspectRatioMode.KeepAspectRatio,
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
        for card in self.cards:
            same = card.poster.get("id") and card.poster["id"] == poster.get("id")
            card.set_selected(same)
            if same:
                self._selected_card = card

    def wait_for_loaders(self):
        for card in self.cards:
            if card.loader is not None and card.loader.isRunning():
                card.loader.wait()

    def clear(self):
        self._selected_card = None
        for card in self.cards:
            if card.loader is not None and card.loader.isRunning():
                card.loader.wait()
            card.setParent(None)
            card.deleteLater()
        self.cards.clear()


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
            wid = item.widget()
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
