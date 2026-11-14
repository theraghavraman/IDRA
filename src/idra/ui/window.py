"""Six operational screens; all long-running services run in worker threads."""
from __future__ import annotations
import logging
import platform
import sys
import threading
import traceback
from datetime import datetime
from pathlib import Path
from uuid import uuid4
from PyQt6.QtCore import QObject, Qt, QThread, QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import QAction, QDesktopServices, QIcon, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QStyle,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)
from idra.app.controller import SessionController
from idra.app.settings import save_settings
from idra.events.models import Settings
from idra.logging.setup import configure
from idra.storage.repository import Repository
from idra.ui.dashboard import DashboardPage
from idra.ui.dataset import DatasetPage
from idra.ui.library import LibraryPage
from idra.ui.settings_page import SettingsPage
from idra.ui.studio import StudioPage
from idra.ui.timeline import TimelinePage
from idra.ui.workers import Worker

STYLE = """
QWidget {
    background: #0B0F17;
    color: #E2E8F0;
    font-family: -apple-system, BlinkMacSystemFont, "Inter", "Segoe UI", Roboto, sans-serif;
    font-size: 13px;
}
QMainWindow {
    background: #0B0F17;
}
QFrame#headerBar {
    background: #0F172A;
    border-bottom: 1px solid #1E293B;
}
QFrame#headerBar QLabel {
    background: transparent;
}
QFrame#sidebarPanel {
    background: #0D131F;
    border-right: 1px solid #1E293B;
}
QFrame#sidebarPanel QLabel {
    background: transparent;
}
QFrame#footerBar {
    background: #0F172A;
    border-top: 1px solid #1E293B;
}
QFrame#footerBar QLabel {
    background: transparent;
}
QLabel#appTitle {
    font-size: 19px;
    font-weight: 700;
    color: #F8FAFC;
    letter-spacing: 0.3px;
}
QLabel#appBadge {
    background: #132A23;
    color: #34D399;
    border: 1px solid #059669;
    border-radius: 10px;
    padding: 3px 10px;
    font-size: 11px;
    font-weight: 600;
}
QLabel#pageTitle {
    font-size: 22px;
    font-weight: 700;
    color: #F8FAFC;
    padding-top: 2px;
    padding-bottom: 2px;
    background: transparent;
}
QLabel#pageSubtitle {
    color: #94A3B8;
    font-size: 13px;
    background: transparent;
}
QLabel#sectionTitle {
    font-size: 14px;
    font-weight: 600;
    color: #F1F5F9;
    background: transparent;
}
QLabel#metricCaption {
    color: #64748B;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.6px;
    background: transparent;
}
QLabel#muted {
    color: #94A3B8;
    font-size: 12px;
    background: transparent;
}
QLabel#bannerPrimary {
    font-size: 14px;
    font-weight: 600;
    color: #F8FAFC;
    background: transparent;
}
QLabel#metricValue {
    font-size: 23px;
    font-weight: 700;
    color: #F8FAFC;
    padding-top: 4px;
    padding-bottom: 2px;
    background: transparent;
}
QLabel#statusPillNeutral {
    background: #131C2B;
    color: #CBD5E1;
    border: 1px solid #263348;
    border-radius: 12px;
    padding: 5px 12px;
    font-size: 12px;
    font-weight: 600;
}
QFrame#metricCard {
    background: #111827;
    border: 1px solid #1E293B;
    border-radius: 10px;
}
QFrame#metricCard:hover {
    border-color: #334155;
    background: #131C2E;
}
QFrame#metricCard QLabel {
    background: transparent;
}
QFrame#sectionCard {
    background: #111827;
    border: 1px solid #1E293B;
    border-radius: 10px;
}
QFrame#sectionCard QLabel, QFrame#sectionCard QCheckBox {
    background: transparent;
}
QFrame#bannerCard {
    background: #111A2E;
    border: 1px solid #263554;
    border-radius: 10px;
}
QFrame#bannerCard QLabel {
    background: transparent;
}
QLabel#previewBox {
    background: #070A10;
    border: 1px solid #1E293B;
    border-radius: 8px;
    color: #64748B;
    padding: 12px;
}
QPushButton {
    background: #1E293B;
    border: 1px solid #334155;
    border-radius: 7px;
    padding: 8px 15px;
    color: #F1F5F9;
    font-weight: 600;
}
QPushButton:hover {
    background: #283548;
    border-color: #475569;
}
QPushButton:pressed {
    background: #0F172A;
}
QPushButton:disabled {
    background: #111827;
    border-color: #1E293B;
    color: #475569;
}
QPushButton#primary {
    background: #059669;
    border: 1px solid #10B981;
    color: #FFFFFF;
}
QPushButton#primary:hover {
    background: #10B981;
    border-color: #34D399;
}
QPushButton#primary:disabled {
    background: #0F2922;
    border-color: #163E33;
    color: #476B5F;
}
QPushButton#danger {
    background: #991B1B;
    border: 1px solid #DC2626;
    color: #FEF2F2;
}
QPushButton#danger:hover {
    background: #B91C1C;
    border-color: #EF4444;
}
QPushButton#danger:disabled {
    background: #231418;
    border-color: #3B1C22;
    color: #6E4A50;
}
QLineEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {
    background: #090D14;
    border: 1px solid #263348;
    border-radius: 6px;
    padding: 7px 10px;
    color: #F1F5F9;
    selection-background-color: #059669;
}
QLineEdit:focus, QPlainTextEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {
    border: 1px solid #10B981;
    background: #0C121C;
}
QPlainTextEdit#monoEditor {
    font-family: "SF Mono", "JetBrains Mono", "Fira Code", Menlo, Consolas, monospace;
    font-size: 12px;
    background: #080C12;
    border: 1px solid #1E293B;
    border-radius: 8px;
    padding: 10px;
    color: #CBD5E1;
}
QListWidget#navigation {
    background: transparent;
    border: none;
    font-size: 13px;
    font-weight: 500;
    outline: none;
}
QListWidget#navigation::item {
    padding: 12px 14px;
    margin: 3px 8px;
    border-radius: 8px;
    color: #94A3B8;
}
QListWidget#navigation::item:hover {
    background: #131C2B;
    color: #E2E8F0;
}
QListWidget#navigation::item:selected {
    background: #0F2E24;
    border: 1px solid #059669;
    color: #34D399;
    font-weight: 700;
}
QTableWidget {
    background: #090D14;
    alternate-background-color: #0D131E;
    gridline-color: #1E293B;
    border: 1px solid #1E293B;
    border-radius: 8px;
    selection-background-color: #0F382B;
    selection-color: #F8FAFC;
    outline: none;
}
QHeaderView::section {
    background: #131C2B;
    color: #94A3B8;
    padding: 9px 10px;
    border: none;
    border-bottom: 1px solid #1E293B;
    font-size: 11px;
    font-weight: 700;
    text-transform: uppercase;
}
QGroupBox {
    background: #111827;
    border: 1px solid #1E293B;
    border-radius: 10px;
    margin-top: 14px;
    padding: 16px 14px 14px 14px;
    font-weight: 600;
    color: #F1F5F9;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 14px;
    padding: 0 6px;
    color: #34D399;
}
QProgressBar {
    border: 1px solid #1E293B;
    border-radius: 6px;
    background: #090D14;
    text-align: center;
    height: 16px;
    font-size: 11px;
    color: #CBD5E1;
}
QProgressBar::chunk {
    background: #10B981;
    border-radius: 5px;
}
QScrollArea {
    border: none;
    background: transparent;
}
QScrollBar:vertical {
    background: #0B0F17;
    width: 10px;
    margin: 0px;
}
QScrollBar::handle:vertical {
    background: #1E293B;
    min-height: 24px;
    border-radius: 5px;
}
QScrollBar::handle:vertical:hover {
    background: #334155;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}
QSplitter::handle {
    background: #1E293B;
    width: 2px;
    height: 2px;
}
QToolTip {
    color: #F8FAFC;
    background: #1E293B;
    border: 1px solid #334155;
    padding: 6px;
}
"""


class ConsentDialog(QDialog):
    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Recording consent")
        self.setMinimumWidth(610)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        heading = QLabel("Explicit Recording Authorization & Privacy Attestation")
        heading.setObjectName("sectionTitle")
        layout.addWidget(heading)

        card = QFrame()
        card.setObjectName("bannerCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(14, 12, 14, 12)
        message = QLabel(
            "The selected screen and enabled input metadata will be recorded locally.\n\n"
            "Printable keystrokes, clipboard contents and form values are not stored. "
            "Screenshots and video can still show passwords, messages and confidential documents. "
            "Fixed privacy masks are not a general-purpose secret detector.\n\n"
            f"Mouse: {settings.capture.capture_mouse}  |  Keyboard categories: {settings.capture.capture_keyboard}  |  "
            f"Managed browser: {settings.browser.enabled}  |  Masks: {len(settings.privacy.masks)}\n\n"
            "A managed browser generates normal browsing traffic. The recorder does not upload captured data."
        )
        message.setWordWrap(True)
        card_layout.addWidget(message)
        layout.addWidget(card)

        self.authorized = QCheckBox(
            "I am authorized to record this activity and any participants or content involved"
        )
        self.visual_risk = QCheckBox(
            "I understand the visible-content risk and will pause before opening private content"
        )
        layout.addWidget(self.authorized)
        layout.addWidget(self.visual_risk)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        ok_btn = self.buttons.button(QDialogButtonBox.StandardButton.Ok)
        ok_btn.setText("Consent and start recording")
        ok_btn.setObjectName("primary")
        ok_btn.setEnabled(False)
        self.authorized.toggled.connect(self.update_consent)
        self.visual_risk.toggled.connect(self.update_consent)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

    def update_consent(self):
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(
            self.authorized.isChecked() and self.visual_risk.isChecked()
        )


class MainWindow(QMainWindow):
    def __init__(self, settings: Settings, *, settings_path=None):
        super().__init__()
        self.settings, self.settings_path = settings, settings_path
        self.repository = Repository(settings.storage_root)
        self.controller = SessionController(settings, self.repository)
        self.jobs = {}
        self.selected_ids = []
        self.close_when_idle = False
        self.stop_inflight = False
        self.setWindowTitle("IDRA - Intelligent Data Recording Agent")
        self.resize(1380, 920)
        self.setMinimumSize(1120, 740)

        root = QWidget()
        base = QVBoxLayout(root)
        base.setContentsMargins(0, 0, 0, 0)
        base.setSpacing(0)

        # Modern Top Header Bar
        header_frame = QFrame()
        header_frame.setObjectName("headerBar")
        header_layout = QHBoxLayout(header_frame)
        header_layout.setContentsMargins(18, 12, 18, 12)
        header_layout.setSpacing(14)

        brand_col = QVBoxLayout()
        brand_col.setSpacing(2)
        brand_row = QHBoxLayout()
        brand_row.setSpacing(10)
        name = QLabel("IDRA  /  Recording workspace")
        name.setObjectName("appTitle")
        badge = QLabel("LOCAL-FIRST STUDIO")
        badge.setObjectName("appBadge")
        brand_row.addWidget(name)
        brand_row.addWidget(badge)
        brand_row.addStretch()
        privacy = QLabel(
            "LOCAL-FIRST   ·   No raw typed text   ·   No automatic uploads   ·   Review visual media before sharing"
        )
        privacy.setObjectName("muted")
        brand_col.addLayout(brand_row)
        brand_col.addWidget(privacy)
        header_layout.addLayout(brand_col, 1)

        self.status = QLabel("IDLE")
        self.status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status.setMinimumWidth(140)
        self._style_status_badge("IDLE")
        header_layout.addWidget(self.status)

        self.global_stop = QPushButton("STOP AND FINALIZE")
        self.global_stop.setObjectName("danger")
        self.global_stop.setCursor(Qt.CursorShape.PointingHandCursor)
        self.global_stop.clicked.connect(self.stop_recording)
        header_layout.addWidget(self.global_stop)
        base.addWidget(header_frame)

        # Main Workspace Area: Left Sidebar + Stacked Pages
        content = QHBoxLayout()
        content.setContentsMargins(0, 0, 0, 0)
        content.setSpacing(0)

        sidebar = QFrame()
        sidebar.setObjectName("sidebarPanel")
        sidebar.setFixedWidth(225)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(6, 14, 6, 14)
        sidebar_layout.setSpacing(6)

        nav_caption = QLabel("   NAVIGATION")
        nav_caption.setObjectName("metricCaption")
        sidebar_layout.addWidget(nav_caption)

        self.navigation = QListWidget()
        self.navigation.setObjectName("navigation")
        self.navigation.addItems(
            [
                "Dashboard",
                "Recording studio",
                "Session explorer",
                "Timeline",
                "Dataset studio",
                "Settings / diagnostics",
            ]
        )
        sidebar_layout.addWidget(self.navigation, 1)

        shortcut_hint = QLabel("Emergency Stop:\nCtrl+Alt+Shift+F8")
        shortcut_hint.setObjectName("muted")
        shortcut_hint.setContentsMargins(12, 8, 12, 4)
        sidebar_layout.addWidget(shortcut_hint)

        self.pages = QStackedWidget()
        self.dashboard = DashboardPage(self)
        self.studio = StudioPage(self)
        self.library = LibraryPage(self)
        self.timeline = TimelinePage(self)
        self.dataset = DatasetPage(self)
        self.settings_page = SettingsPage(self)
        for page in (
            self.dashboard,
            self.studio,
            self.library,
            self.timeline,
            self.dataset,
            self.settings_page,
        ):
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setWidget(page)
            self.pages.addWidget(scroll)

        content.addWidget(sidebar)
        content.addWidget(self.pages, 1)
        base.addLayout(content, 1)

        # Bottom Status & Progress Bar
        footer_frame = QFrame()
        footer_frame.setObjectName("footerBar")
        footer = QHBoxLayout(footer_frame)
        footer.setContentsMargins(18, 8, 18, 8)
        footer.setSpacing(14)

        self.operation = QLabel("Ready")
        self.operation.setObjectName("muted")
        self.progress = QProgressBar()
        self.progress.setRange(0, 1000)
        self.progress.setValue(0)
        self.progress.setMaximumWidth(320)
        self.cancel_button = QPushButton("Cancel operation")
        self.cancel_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cancel_button.clicked.connect(self.cancel_operations)
        footer.addWidget(self.operation, 1)
        footer.addWidget(self.progress)
        footer.addWidget(self.cancel_button)
        base.addWidget(footer_frame)

        self.setCentralWidget(root)
        self.navigation.currentRowChanged.connect(self._navigate)
        self.navigation.setCurrentRow(0)
        self.shortcut = QShortcut(QKeySequence("Ctrl+Alt+Shift+F8"), self)
        self.shortcut.activated.connect(self.stop_recording)
        self.tray = None
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray = QSystemTrayIcon(
                self.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon), self
            )
            menu = QMenu(self)
            show_action = QAction("Show recorder", self)
            show_action.triggered.connect(self.showNormal)
            stop_action = QAction("Stop and finalize recording", self)
            stop_action.triggered.connect(self.stop_recording)
            close_action = QAction("Quit", self)
            close_action.triggered.connect(self.close)
            for action in (show_action, stop_action, close_action):
                menu.addAction(action)
            self.tray.setContextMenu(menu)
            self.tray.setToolTip("IDRA - IDLE")
            self.tray.show()
        self.timer = QTimer(self)
        self.timer.setInterval(250)
        self.timer.timeout.connect(self.tick)
        self.timer.start()
        QTimer.singleShot(0, lambda: self.library.refresh(background=True))

    def _style_status_badge(self, state: str):
        styles = {
            "RECORDING": "background: #3B1219; color: #F87171; border: 1px solid #DC2626; border-radius: 12px; padding: 5px 14px; font-weight: 700;",
            "STARTING": "background: #2B1F0A; color: #FBBF24; border: 1px solid #D97706; border-radius: 12px; padding: 5px 14px; font-weight: 700;",
            "PAUSED": "background: #2B1F0A; color: #FBBF24; border: 1px solid #D97706; border-radius: 12px; padding: 5px 14px; font-weight: 700;",
            "STOPPING": "background: #0D213B; color: #60A5FA; border: 1px solid #2563EB; border-radius: 12px; padding: 5px 14px; font-weight: 700;",
            "COMPLETED": "background: #07261E; color: #34D399; border: 1px solid #059669; border-radius: 12px; padding: 5px 14px; font-weight: 700;",
            "FAILED": "background: #2D0F18; color: #FB7185; border: 1px solid #E11D48; border-radius: 12px; padding: 5px 14px; font-weight: 700;",
            "INTERRUPTED": "background: #2B1A08; color: #F59E0B; border: 1px solid #D97706; border-radius: 12px; padding: 5px 14px; font-weight: 700;",
        }
        default_style = "background: #131C2B; color: #94A3B8; border: 1px solid #263348; border-radius: 12px; padding: 5px 14px; font-weight: 700;"
        self.status.setStyleSheet(styles.get(state, default_style))

    def _navigate(self, index):
        self.pages.setCurrentIndex(index)
        if index == 3 and self.timeline.session_id and not self.blocking_job_active():
            self.timeline.reload()

    def show_page(self, index):
        self.navigation.setCurrentRow(index)

    def error(self, message):
        logging.getLogger("idra.ui").warning(
            "user_visible_error %s", str(message).split(":", 1)[0][:120]
        )
        if getattr(self, "_showing_error", False):
            self.operation.setText(str(message)[:300])
            return
        self._showing_error = True
        try:
            QMessageBox.warning(self, "IDRA", str(message))
        finally:
            self._showing_error = False

    def require_session(self):
        if not self.selected_ids:
            self.error("Select a session in Session explorer first")
            return None
        return self.selected_ids[0]

    def blocking_job_active(self):
        return any(job["blocking"] for job in self.jobs.values())

    def run_job(self, title, work, on_result=None, *, parallel=False):
        if not parallel and self.blocking_job_active():
            self.error(
                "Another operation is active. Cancel it before starting this operation."
            )
            return False
        token = uuid4().hex
        cancel = threading.Event()
        thread = QThread(self)
        worker = Worker(work, cancel)
        worker.moveToThread(thread)
        had_blocking = self.blocking_job_active()
        self.jobs[token] = {
            "thread": thread,
            "worker": worker,
            "cancel": cancel,
            "title": title,
            "blocking": not parallel,
        }
        thread.started.connect(worker.run)
        worker.progress.connect(
            lambda value, t=token: self._job_progress(t, value)
        )
        worker.result.connect(lambda result, t=token: self._job_result(t, result, on_result))
        worker.failed.connect(lambda message, t=token: self._job_error(t, message))
        worker.done.connect(thread.quit)
        worker.done.connect(worker.deleteLater)
        thread.finished.connect(lambda t=token: self._job_cleanup(t))
        thread.finished.connect(thread.deleteLater)
        if not parallel or not had_blocking:
            self.operation.setText(title)
            self.progress.setValue(0)
        thread.start()
        return True

    def _job_progress(self, token, value):
        job = self.jobs.get(token)
        if job and (job["blocking"] or not self.blocking_job_active()):
            self.progress.setValue(max(0, min(1000, int(value * 1000))))

    def _job_result(self, token, result, callback):
        if token in self.jobs:
            self.jobs[token]["blocking"] = False
        if callback:
            try:
                callback(result)
            except Exception as exc:
                self.error(f"Result display failed: {type(exc).__name__}: {exc}")

    def _job_error(self, token, message):
        was_start = False
        if token in self.jobs:
            was_start = self.jobs[token].get("title") == "Starting authorized recording"
            self.jobs[token]["blocking"] = False
        self.stop_inflight = False
        self.error(message)
        if was_start and not self.close_when_idle:
            self.library.refresh(background=True)

    def _job_cleanup(self, token):
        self.jobs.pop(token, None)
        blocking = next((j for j in self.jobs.values() if j["blocking"]), None)
        if blocking:
            self.operation.setText(blocking["title"])
        elif not self.jobs:
            self.operation.setText("Ready")
        if (
            self.close_when_idle
            and not self.jobs
            and self.controller.state.value
            not in {"STARTING", "RECORDING", "PAUSED", "STOPPING"}
        ):
            QTimer.singleShot(0, self.close)

    def cancel_operations(self):
        if self.controller.starting:
            self.controller.request_stop()
        for job in self.jobs.values():
            job["cancel"].set()
        self.operation.setText(
            "Cancellation requested; the current non-interruptible check may finish first"
        )

    def build_settings(self):
        settings = self.settings.model_copy(deep=True)
        self.settings_page.apply_to(settings)
        self.studio.apply_to(settings)
        return Settings.model_validate(settings.model_dump())

    def start_recording(self):
        if self.blocking_job_active() or self.controller.state.value not in {
            "IDLE",
            "COMPLETED",
            "FAILED",
            "INTERRUPTED",
        }:
            return
        try:
            settings = self.build_settings()
        except Exception as exc:
            self.error(str(exc))
            return
        if not self.check_macos_screen_permission():
            return
        consent = ConsentDialog(settings, self)
        if consent.exec() != QDialog.DialogCode.Accepted:
            return
        label = self.studio.label.text().strip() or "Session " + datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        task = self.studio.task.toPlainText()
        self.settings = settings
        self.repository = Repository(settings.storage_root)
        self.controller = SessionController(settings, self.repository)

        def work(cancel, progress):
            if cancel.is_set():
                raise RuntimeError("START_CANCELLED")
            return self.controller.start(label, task, consent=True)

        self.run_job("Starting authorized recording", work)

    def check_macos_screen_permission(self) -> bool:
        from idra.app.runtime import is_wayland_session

        if is_wayland_session() and self.studio.backend.currentData() == "mss":
            QMessageBox.warning(
                self,
                "Wayland session detected",
                "This Linux desktop is running Wayland, which does not let apps capture the whole screen "
                "directly. Recordings would be black or incomplete.\n\nLog out, choose the 'Xorg' / "
                "'on Xorg' session on the login screen (the gear icon), log back in and start IDRA again.",
            )
            return False
        if platform.system() != "Darwin":
            return True
        from idra.app import runtime
        from idra.diagnostics.checks import mac_permissions

        try:
            granted = mac_permissions().get("screen_recording")
        except Exception:
            granted = None
        if granted is not False:
            return True
        runtime.request_screen_recording()
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Information)
        box.setWindowTitle("Screen Recording permission needed")
        box.setText("macOS has not given IDRA permission to record the screen yet.")
        box.setInformativeText(
            "Open System Settings > Privacy & Security > Screen Recording, switch IDRA on, "
            "then quit IDRA (Cmd+Q) and open it again."
        )
        open_button = box.addButton(
            "Open System Settings", QMessageBox.ButtonRole.AcceptRole
        )
        box.addButton(QMessageBox.StandardButton.Close)
        box.exec()
        if box.clickedButton() is open_button:
            QDesktopServices.openUrl(QUrl(runtime.SETTINGS_PANES["screen_recording"]))
        return False

    def pause_recording(self):
        if self.controller.state.value == "RECORDING":
            self.run_job("Pausing recording", lambda c, p: self.controller.pause())

    def resume_recording(self):
        if self.controller.state.value == "PAUSED":
            self.run_job("Resuming recording", lambda c, p: self.controller.resume())

    def stop_recording(self):
        if self.controller.state.value not in {"STARTING", "RECORDING", "PAUSED"}:
            return
        self.controller.request_stop()
        if getattr(self.controller, "starting", False) or self.stop_inflight:
            return
        self.stop_inflight = True

        def finished(manifest):
            self.stop_inflight = False
            if manifest and manifest.state.value == "FAILED":
                self.error(
                    "Recording was preserved as FAILED. Inspect its manifest and diagnostics; do not treat it as completed."
                )
            if not self.close_when_idle:
                self.library.refresh(background=True)

        self.run_job(
            "Finalizing media and journals",
            lambda c, p: self.controller.stop(),
            finished,
            parallel=True,
        )

    def save_configuration(self):
        if self.controller.state.value in {
            "STARTING",
            "RECORDING",
            "PAUSED",
            "STOPPING",
        }:
            self.error("Stop the recording before changing stored configuration")
            return
        try:
            settings = self.build_settings()
        except Exception as exc:
            self.error(str(exc))
            return
        if (
            settings.privacy.browser_labels
            or settings.privacy.browser_titles
            or settings.privacy.url_detail == "path"
        ):
            if (
                QMessageBox.question(
                    self,
                    "Expanded metadata privacy",
                    "You enabled optional labels, titles or URL paths. These can contain private information. Save this explicit opt-in?",
                )
                != QMessageBox.StandardButton.Yes
            ):
                return

        def work(cancel, progress):
            save_settings(settings, self.settings_path)
            return Repository(settings.storage_root)

        def show(repository):
            self.settings, self.repository = settings, repository
            self.controller = SessionController(settings, repository)
            self.settings_page.result.setPlainText(
                "Settings saved. Starting URLs are persisted only as origins to avoid saving URL secrets."
            )

        self.run_job("Saving settings", work, show)

    def tick(self):
        try:
            snapshot = self.controller.snapshot()
        except OSError:
            self.status.setText("STORAGE UNAVAILABLE")
            self._style_status_badge("FAILED")
            self.controller.request_stop()
            return
        state = snapshot["state"]
        self.status.setText(state)
        self._style_status_badge(state)
        self.global_stop.setEnabled(state in {"STARTING", "RECORDING", "PAUSED"})
        self.dashboard.update_snapshot(snapshot)
        self.studio.update_snapshot(snapshot)
        self.cancel_button.setEnabled(bool(self.jobs))
        if self.tray:
            self.tray.setToolTip("IDRA - " + state)
        if snapshot["stop_requested"] and state in {"STARTING", "RECORDING", "PAUSED"}:
            self.stop_recording()

    def closeEvent(self, event):
        active = self.controller.state.value in {
            "STARTING",
            "RECORDING",
            "PAUSED",
            "STOPPING",
        }
        if active:
            if (
                not self.close_when_idle
                and QMessageBox.question(
                    self,
                    "Stop before quitting",
                    "Stop and finalize this recording before quitting?",
                )
                != QMessageBox.StandardButton.Yes
            ):
                event.ignore()
                return
            self.close_when_idle = True
            self.stop_recording()
            event.ignore()
            return
        if self.jobs:
            # Only user-started blocking work (export, recovery, deletion...) deserves a prompt;
            # read-only background listings are cancelled silently and the window closes when idle.
            if (
                not self.close_when_idle
                and self.blocking_job_active()
                and QMessageBox.question(
                    self,
                    "Cancel operations",
                    "Cancel active operations and close after they release their resources?",
                )
                != QMessageBox.StandardButton.Yes
            ):
                event.ignore()
                return
            self.close_when_idle = True
            self.cancel_operations()
            event.ignore()
            return
        self.timer.stop()
        if self.tray:
            self.tray.hide()
        event.accept()


class _ErrorBridge(QObject):
    """Carries unexpected errors from any thread to a non-fatal dialog on the GUI thread."""

    raised = pyqtSignal(str)


def _install_exception_hooks(app, get_window):
    logger = logging.getLogger("idra.crash")
    bridge = _ErrorBridge()

    def show(message):
        window = get_window()
        if window is not None:
            window.error(message)

    bridge.raised.connect(show)

    def report(exc_type, exc, tb, where):
        logger.error(
            "unhandled_exception where=%s type=%s\n%s",
            where,
            exc_type.__name__,
            "".join(traceback.format_exception(exc_type, exc, tb))[-6000:],
        )
        bridge.raised.emit(
            f"An unexpected internal error occurred ({exc_type.__name__}). IDRA kept running; "
            "any active recording continues. Details were written to the application log."
        )

    def excepthook(exc_type, exc, tb):
        if issubclass(exc_type, KeyboardInterrupt):
            app.quit()
            return
        report(exc_type, exc, tb, "main")

    def thread_hook(args):
        if args.exc_type is SystemExit:
            return
        report(
            args.exc_type,
            args.exc_value,
            args.exc_traceback,
            getattr(args.thread, "name", "thread"),
        )

    # A custom sys.excepthook also stops PyQt6 from calling qFatal()/abort() on slot exceptions.
    sys.excepthook = excepthook
    threading.excepthook = thread_hook
    return bridge


def _app_icon() -> QIcon | None:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    for candidate in (
        base / "idra" / "resources" / "idra.png",
        base / "resources" / "idra.png",
    ):
        if candidate.is_file():
            return QIcon(str(candidate))
    return None


def _usable_repository(settings: Settings) -> tuple[Repository, str | None]:
    try:
        return Repository(settings.storage_root), None
    except Exception as exc:
        fallback = str(Path.home() / "IDRA-recordings")
        if (
            Path(settings.storage_root).expanduser().resolve()
            == Path(fallback).resolve()
        ):
            raise
        problem = (
            f"The storage folder {settings.storage_root} is unavailable ({type(exc).__name__}). "
            f"IDRA is using {fallback} for this session. Reconnect the drive or choose another folder "
            "in Settings, then save."
        )
        settings.storage_root = fallback
        return Repository(fallback), problem


def launch(settings: Settings, settings_path=None, warnings=None) -> int:
    from idra.app.runtime import enable_fault_log, prepare_process

    prepare_process()
    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setApplicationName("IDRA")
    app.setApplicationDisplayName("IDRA")
    app.setOrganizationName("IDRA")
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    icon = _app_icon()
    if icon is not None:
        app.setWindowIcon(icon)
    holder = {"window": None}
    bridge = _install_exception_hooks(app, lambda: holder["window"])
    notices = [w for w in (warnings or []) if w]
    try:
        repository, problem = _usable_repository(settings)
    except Exception as exc:
        QMessageBox.critical(
            None,
            "IDRA cannot start",
            f"No usable storage folder could be created ({type(exc).__name__}: {exc}).\n\n"
            "Check that your home folder is writable and has free space.",
        )
        return 1
    if problem:
        notices.append(problem)
    configure(repository.root / "logs")
    enable_fault_log(repository.root / "logs")
    logging.getLogger("idra").info(
        "launch platform=%s machine=%s frozen=%s",
        platform.system(),
        platform.machine(),
        bool(getattr(sys, "frozen", False)),
    )
    window = MainWindow(settings, settings_path=settings_path)
    holder["window"] = window
    window._error_bridge = bridge
    window.show()
    for notice in notices:
        QTimer.singleShot(300, lambda n=notice: window.error(n))
    return app.exec()
