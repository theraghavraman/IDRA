import json
import platform

from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from idra.events.models import PrivacyConfig
from idra.ui.widgets import button, card, mono_editor, pretty, section_title, spin, title


class SettingsPage(QWidget):
    def __init__(self, host):
        super().__init__()
        self.host = host
        self.last_diagnostics = None
        s = host.settings
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 16)
        layout.setSpacing(14)

        header = QVBoxLayout()
        header.setSpacing(3)
        header.addWidget(title("Settings, privacy and diagnostics"))
        sub = QLabel(
            "Configure private local storage, executable paths, pixel masks, retention policies, and system diagnostics."
        )
        sub.setObjectName("pageSubtitle")
        sub.setWordWrap(True)
        header.addWidget(sub)
        layout.addLayout(header)

        columns = QHBoxLayout()
        columns.setSpacing(14)

        # Left card: Storage & Executables
        left_card = card("sectionCard")
        left_layout = QVBoxLayout(left_card)
        left_layout.setContentsMargins(16, 14, 16, 16)
        left_layout.setSpacing(12)
        left_layout.addWidget(section_title("Storage, Executables & Retention"))

        self.root = QLineEdit(s.storage_root)
        root_row = QHBoxLayout()
        root_row.setSpacing(8)
        root_row.addWidget(self.root, 1)
        root_row.addWidget(button("Browse...", self.browse_storage))

        self.ffmpeg, self.ffprobe = QLineEdit(s.ffmpeg), QLineEdit(s.ffprobe)
        self.browser_executable = QLineEdit(s.browser.executable or "")
        self.browser_executable.setPlaceholderText(
            "Blank uses Playwright's installed Chromium"
        )
        self.free_mb = spin(s.min_free_mb, 1, 1048576)
        self.retention = spin(s.retention_days, 0, 36500)
        self.display = QLineEdit(s.capture.x11_display or "")
        self.display.setPlaceholderText(
            "Blank uses the local DISPLAY environment (X11 fallback only)"
        )
        self.region = QLineEdit(
            f"{s.capture.region_left},{s.capture.region_top},{s.capture.region_width},{s.capture.region_height}"
        )

        left_form = QFormLayout()
        left_form.setVerticalSpacing(10)
        left_form.setHorizontalSpacing(14)
        left_form.addRow("Local storage", root_row)
        for name, widget in [
            ("FFmpeg executable", self.ffmpeg),
            ("FFprobe executable", self.ffprobe),
            ("Managed Chromium", self.browser_executable),
            ("Stop reserve (MiB)", self.free_mb),
            ("Retention days (0=off)", self.retention),
            ("X11 display", self.display),
            ("X11 region (l,t,w,h)", self.region),
        ]:
            left_form.addRow(name, widget)
        left_layout.addLayout(left_form)
        left_layout.addStretch()

        # Right card: Privacy Redaction & Pixel Masks
        right_card = card("sectionCard")
        right_layout = QVBoxLayout(right_card)
        right_layout.setContentsMargins(16, 14, 16, 16)
        right_layout.setSpacing(12)
        right_layout.addWidget(section_title("Privacy Minimization & Pixel Masks"))

        self.url_detail = QComboBox()
        self.url_detail.addItem("Origin only (safer)", "origin")
        self.url_detail.addItem("Include path (can contain secrets)", "path")
        self.url_detail.setCurrentIndex(
            max(0, self.url_detail.findData(s.privacy.url_detail))
        )
        self.labels = QCheckBox(
            "Opt in to accessible labels from non-input elements; labels may contain private text"
        )
        self.labels.setChecked(s.privacy.browser_labels)
        self.titles = QCheckBox(
            "Opt in to browser page titles; titles may contain private text"
        )
        self.titles.setChecked(s.privacy.browser_titles)
        self.masks = mono_editor(
            pretty([m.model_dump() for m in s.privacy.masks]), max_height=110
        )
        self.masks.setPlaceholderText('[{"x":0.7,"y":0.0,"width":0.3,"height":0.2}]')

        right_form = QFormLayout()
        right_form.setVerticalSpacing(10)
        right_form.setHorizontalSpacing(14)
        right_form.addRow("Recorded URL detail", self.url_detail)
        right_form.addRow("Browser metadata", self.labels)
        right_form.addRow("", self.titles)
        right_form.addRow("Solid pixel masks (JSON)", self.masks)
        right_layout.addLayout(right_form)

        note = QLabel(
            "Masks cover fixed image regions before storage. There is no general-purpose password/secret detector for pixels. "
            "No raw text, clipboard or full DOM capture is supported."
        )
        note.setObjectName("muted")
        note.setWordWrap(True)
        right_layout.addStretch()
        right_layout.addWidget(note)

        columns.addWidget(left_card, 1)
        columns.addWidget(right_card, 1)
        layout.addLayout(columns)

        # Actions & Diagnostics Card
        ops_card = card("sectionCard")
        ops_layout = QVBoxLayout(ops_card)
        ops_layout.setContentsMargins(16, 14, 16, 14)
        ops_layout.setSpacing(10)

        actions = QHBoxLayout()
        actions.setSpacing(10)
        actions.addWidget(button("Save settings", host.save_configuration, primary=True))
        actions.addWidget(button("Inspect configuration", self.inspect))
        actions.addWidget(button("Preview retention cleanup", self.cleanup))
        actions.addStretch()
        ops_layout.addLayout(actions)

        diagnostics = QHBoxLayout()
        diagnostics.setSpacing(10)
        diagnostics.addWidget(
            button("Run diagnostics (no capture)", lambda: self.diagnose(False))
        )
        diagnostics.addWidget(
            button("Probe screen with consent", lambda: self.diagnose(True))
        )
        diagnostics.addWidget(button("Save diagnostic report", self.save_report))
        diagnostics.addStretch()
        ops_layout.addLayout(diagnostics)

        if platform.system() == "Darwin":
            permissions = QHBoxLayout()
            permissions.setSpacing(10)
            perm_lbl = QLabel("macOS Privacy & Security:")
            perm_lbl.setObjectName("muted")
            permissions.addWidget(perm_lbl)
            for text, key in (
                ("Screen Recording", "screen_recording"),
                ("Accessibility", "accessibility"),
                ("Input Monitoring", "input_monitoring"),
            ):
                permissions.addWidget(
                    button(
                        text + "...",
                        lambda _=False, k=key: self.request_permission(k),
                    )
                )
            permissions.addStretch()
            ops_layout.addLayout(permissions)
            hint = QLabel(
                "Each button asks macOS to list IDRA and opens the matching System Settings pane. "
                "Turn IDRA on there, then quit and reopen IDRA. Screen Recording is required; "
                "Accessibility/Input Monitoring are needed for mouse/keyboard metadata."
            )
            hint.setObjectName("muted")
            hint.setWordWrap(True)
            ops_layout.addWidget(hint)

        layout.addWidget(ops_card)

        console_card = card("sectionCard")
        console_layout = QVBoxLayout(console_card)
        console_layout.setContentsMargins(14, 12, 14, 14)
        console_layout.setSpacing(6)
        console_lbl = QLabel("DIAGNOSTICS & CONFIGURATION INSPECTOR (JSON)")
        console_lbl.setObjectName("metricCaption")
        self.result = mono_editor(read_only=True, min_height=220)
        console_layout.addWidget(console_lbl)
        console_layout.addWidget(self.result, 1)
        layout.addWidget(console_card, 1)

    def browse_storage(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Select private local recordings folder", self.root.text().strip()
        )
        if folder:
            self.root.setText(folder)

    def apply_to(self, settings):
        settings.storage_root = self.root.text().strip()
        if not settings.storage_root:
            raise ValueError("Storage path cannot be empty")
        settings.ffmpeg, settings.ffprobe = (
            self.ffmpeg.text().strip(),
            self.ffprobe.text().strip(),
        )
        settings.browser.executable = self.browser_executable.text().strip() or None
        settings.min_free_mb, settings.retention_days = (
            int(self.free_mb.value()),
            int(self.retention.value()),
        )
        settings.capture.x11_display = self.display.text().strip() or None
        parts = [v.strip() for v in self.region.text().split(",")]
        if len(parts) != 4:
            raise ValueError(
                "X11 region must be four comma-separated integers: left,top,width,height"
            )
        try:
            left, top, width, height = [int(v) for v in parts]
        except ValueError as exc:
            raise ValueError(
                "X11 region must be four comma-separated integers: left,top,width,height"
            ) from exc
        settings.capture.region_left, settings.capture.region_top = left, top
        settings.capture.region_width, settings.capture.region_height = width, height
        raw_masks = self.masks.toPlainText().strip() or "[]"
        try:
            parsed_masks = json.loads(raw_masks)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Solid pixel masks must be valid JSON: {exc.msg}") from exc
        settings.privacy = PrivacyConfig(
            masks=parsed_masks,
            browser_labels=self.labels.isChecked(),
            browser_titles=self.titles.isChecked(),
            url_detail=self.url_detail.currentData() or "origin",
        )

    def request_permission(self, key):
        from idra.app import runtime

        try:
            {
                "screen_recording": runtime.request_screen_recording,
                "accessibility": runtime.request_accessibility,
                "input_monitoring": runtime.request_input_monitoring,
            }[key]()
        except Exception:
            pass
        QDesktopServices.openUrl(QUrl(runtime.SETTINGS_PANES[key]))
        self.result.setPlainText(
            "System Settings was opened. Enable IDRA in the list, then quit IDRA (Cmd+Q) "
            "and open it again; macOS applies these permissions only after a restart."
        )

    def inspect(self):
        try:
            self.result.setPlainText(
                pretty(self.host.build_settings().model_dump(mode="json"))
            )
        except Exception as exc:
            self.host.error(str(exc))

    def diagnose(self, probe):
        if (
            probe
            and QMessageBox.question(
                self,
                "Screen probe consent",
                "Capture and immediately discard one screen frame to test this configuration? It will not be saved.",
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        try:
            settings = self.host.build_settings()
        except Exception as exc:
            self.host.error(str(exc))
            return
        from idra.diagnostics.checks import diagnose

        def show(report):
            self.last_diagnostics = report
            self.result.setPlainText(pretty(report))

        self.host.run_job(
            "Checking dependencies and permissions",
            lambda c, p: diagnose(settings, probe_screen=probe),
            show,
        )

    def save_report(self):
        if self.last_diagnostics is None:
            self.host.error("Run diagnostics before saving a report")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Save diagnostic report", "idra-diagnostics.json", "JSON (*.json)"
        )
        if path:
            from pathlib import Path

            from idra.storage.files import atomic_json

            report = self.last_diagnostics
            self.host.run_job(
                "Saving diagnostic report",
                lambda c, p: atomic_json(Path(path), report),
            )

    def cleanup(self):
        days = int(self.retention.value())
        if days <= 0:
            self.host.error("Set a positive retention period to preview candidates")
            return

        def show(rows):
            self.result.setPlainText(
                pretty({"retention_days": days, "candidates": rows})
            )
            if not rows:
                return
            if (
                QMessageBox.question(
                    self,
                    "Confirm retention deletion",
                    f"Delete all {len(rows)} completed/failed/interrupted sessions older than {days} days? Secure erasure of SSDs/backups is not guaranteed.",
                )
                != QMessageBox.StandardButton.Yes
            ):
                return

            def remove(cancel, progress):
                count = 0
                for row in rows:
                    if cancel.is_set():
                        break
                    self.host.repository.delete(row["id"], confirmed=True)
                    count += 1
                    progress(count / len(rows))
                return {"deleted": count}

            self.host.run_job(
                "Applying confirmed retention deletion",
                remove,
                lambda r: self.result.setPlainText(pretty(r)),
            )

        self.host.run_job(
            "Previewing retention candidates",
            lambda c, p: self.host.repository.retention_candidates(days),
            show,
        )
