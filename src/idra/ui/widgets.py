from __future__ import annotations
import json
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont, QImage, QPixmap
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QDoubleSpinBox,
    QFrame,
    QHeaderView,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

STATE_COLORS = {
    "COMPLETED": ("#10B981", "#07261E"),
    "RECORDING": ("#F87171", "#2D1215"),
    "STARTING": ("#FBBF24", "#2B1F0A"),
    "PAUSED": ("#FBBF24", "#2B1F0A"),
    "STOPPING": ("#60A5FA", "#0D213B"),
    "FAILED": ("#FB7185", "#2D0F18"),
    "INTERRUPTED": ("#F59E0B", "#2B1A08"),
    "IDLE": ("#94A3B8", "#131C2B"),
}


def title(text: str, subtitle: str | None = None) -> QLabel:
    label = QLabel(text)
    label.setObjectName("pageTitle")
    if subtitle:
        label.setToolTip(subtitle)
    return label


def page_header(heading: str, subtitle_text: str) -> QWidget:
    container = QWidget()
    container.setObjectName("pageHeader")
    layout = QVBoxLayout(container)
    layout.setContentsMargins(0, 0, 0, 6)
    layout.setSpacing(3)
    h = title(heading)
    sub = QLabel(subtitle_text)
    sub.setObjectName("pageSubtitle")
    sub.setWordWrap(True)
    layout.addWidget(h)
    layout.addWidget(sub)
    return container


def section_title(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("sectionTitle")
    return label


def card(object_name: str = "sectionCard") -> QFrame:
    frame = QFrame()
    frame.setObjectName(object_name)
    return frame


def button(text: str, callback, danger: bool = False, primary: bool = False) -> QPushButton:
    b = QPushButton(text)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    if danger:
        b.setObjectName("danger")
    elif primary:
        b.setObjectName("primary")
    b.clicked.connect(callback)
    return b


def spin(value, minimum, maximum, floating: bool = False):
    w = QDoubleSpinBox() if floating else QSpinBox()
    w.setRange(minimum, maximum)
    w.setValue(value)
    w.setMinimumWidth(96)
    return w


def mono_editor(text: str = "", *, read_only: bool = False, min_height: int | None = None, max_height: int | None = None) -> QPlainTextEdit:
    ed = QPlainTextEdit(text)
    ed.setObjectName("monoEditor")
    ed.setReadOnly(read_only)
    if min_height is not None:
        ed.setMinimumHeight(min_height)
    if max_height is not None:
        ed.setMaximumHeight(max_height)
    return ed


def table(headers: list[str]) -> QTableWidget:
    t = QTableWidget(0, len(headers))
    t.setHorizontalHeaderLabels(headers)
    t.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    t.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
    t.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    t.setShowGrid(False)
    t.verticalHeader().hide()
    t.verticalHeader().setDefaultSectionSize(38)
    t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
    t.horizontalHeader().setHighlightSections(False)
    t.setAlternatingRowColors(True)
    return t


def fill_table(t: QTableWidget, rows: list[dict], keys: list[str], *, ids: list | None = None):
    t.setRowCount(len(rows))
    bold_font = QFont()
    bold_font.setBold(True)
    for row_no, row in enumerate(rows):
        for col, key in enumerate(keys):
            raw_val = row.get(key, "")
            text = str(raw_val)
            item = QTableWidgetItem(text)
            if col == 0 and ids:
                item.setData(Qt.ItemDataRole.UserRole, ids[row_no])
            if key == "state" and text in STATE_COLORS:
                fg, bg = STATE_COLORS[text]
                item.setForeground(QColor(fg))
                item.setBackground(QColor(bg))
                item.setFont(bold_font)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            elif key in {"frame_count", "event_count", "duration", "time"}:
                item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            t.setItem(row_no, col, item)


def pretty(value) -> str:
    return json.dumps(value, indent=2, ensure_ascii=False, default=str)


def format_time(ns: int) -> str:
    seconds = max(0, int(ns // 1_000_000_000))
    return f"{seconds // 3600:02d}:{seconds // 60 % 60:02d}:{seconds % 60:02d}"


def image_pixmap(image, width: int = 640, height: int = 360) -> QPixmap:
    import cv2

    rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    q = QImage(
        rgb.data, rgb.shape[1], rgb.shape[0], rgb.strides[0], QImage.Format.Format_RGB888
    ).copy()
    return QPixmap.fromImage(q).scaled(
        width,
        height,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
