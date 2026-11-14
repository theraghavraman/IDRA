from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)
from idra.ui.widgets import button, card, section_title, spin, title


class StudioPage(QWidget):
    def __init__(self, host):
        super().__init__()
        self.host = host
        s = host.settings
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 16)
        layout.setSpacing(14)

        header = QVBoxLayout()
        header.setSpacing(3)
        header.addWidget(title("Recording studio"))
        sub = QLabel(
            "Configure display capture, privacy-minimized input telemetry, and optional isolated browser instrumentation."
        )
        sub.setObjectName("pageSubtitle")
        sub.setWordWrap(True)
        header.addWidget(sub)
        layout.addLayout(header)

        # Transport & Live Control Bar at the top for immediate access
        transport_card = card("bannerCard")
        transport_layout = QVBoxLayout(transport_card)
        transport_layout.setContentsMargins(16, 14, 16, 14)
        transport_layout.setSpacing(10)

        controls = QHBoxLayout()
        controls.setSpacing(10)
        self.start = button("Start recording", host.start_recording, primary=True)
        self.pause = button("Pause", host.pause_recording)
        self.resume = button("Resume", host.resume_recording)
        self.stop = button("Stop and finalize", host.stop_recording, danger=True)
        for b in (self.start, self.pause, self.resume, self.stop):
            b.setMinimumHeight(38)
            controls.addWidget(b)
        transport_layout.addLayout(controls)

        self.status = QLabel("IDLE - consent is requested before every recording")
        self.status.setObjectName("muted")
        self.status.setWordWrap(True)
        transport_layout.addWidget(self.status)
        layout.addWidget(transport_card)

        # Two-column configuration grid
        columns = QHBoxLayout()
        columns.setSpacing(14)

        # Left column: Session identity + Display & sampling
        left_card = card("sectionCard")
        left_layout = QVBoxLayout(left_card)
        left_layout.setContentsMargins(16, 14, 16, 16)
        left_layout.setSpacing(12)
        left_layout.addWidget(section_title("Session & Display Capture"))

        self.label = QLineEdit()
        self.label.setPlaceholderText("e.g., Spreadsheet Pivot Table Demonstration")
        self.label.setMaxLength(256)
        self.task = QPlainTextEdit()
        self.task.setPlaceholderText("Describe the authorized task and goal to record...")
        self.task.setMaximumHeight(88)

        self.backend = QComboBox()
        self.backend.addItem("Native screenshots (MSS)", "mss")
        self.backend.addItem("Linux X11 fallback (receive-time timestamps)", "ffmpeg_x11")
        idx = self.backend.findData(s.capture.backend)
        self.backend.setCurrentIndex(max(0, idx))

        self.monitor = QComboBox()
        self.monitor.addItem(f"Monitor {s.capture.monitor} - not yet probed", s.capture.monitor)
        monitor_row = QHBoxLayout()
        monitor_row.setSpacing(8)
        monitor_row.addWidget(self.monitor, 1)
        monitor_row.addWidget(button("Detect displays", self.detect_displays))

        options = QHBoxLayout()
        options.setSpacing(10)
        self.fps = spin(s.capture.fps, 1, 60)
        self.output_width = spin(s.capture.output_width, 64, 7680)
        self.interval = spin(s.capture.screenshot_interval_s, 0.1, 3600, True)
        for text, widget in (
            ("FPS", self.fps),
            ("Max width", self.output_width),
            ("Screenshot (s)", self.interval),
        ):
            lbl = QLabel(text)
            lbl.setObjectName("muted")
            options.addWidget(lbl)
            options.addWidget(widget)
        options.addStretch()

        left_form = QFormLayout()
        left_form.setVerticalSpacing(10)
        left_form.setHorizontalSpacing(14)
        left_form.addRow("Session label", self.label)
        left_form.addRow("Task prompt", self.task)
        left_form.addRow("Capture provider", self.backend)
        left_form.addRow("Display target", monitor_row)
        left_form.addRow("Sampling rate", options)
        left_layout.addLayout(left_form)
        left_layout.addStretch()

        # Right column: Input telemetry & Managed browser
        right_card = card("sectionCard")
        right_layout = QVBoxLayout(right_card)
        right_layout.setContentsMargins(16, 14, 16, 16)
        right_layout.setSpacing(12)
        right_layout.addWidget(section_title("Telemetry Channels & Browser Scope"))

        self.mouse = QCheckBox("Mouse movement, clicks and scrolling")
        self.mouse.setChecked(s.capture.capture_mouse)
        self.keyboard = QCheckBox(
            "Keyboard categories and global stop shortcut (no printable text)"
        )
        self.keyboard.setChecked(s.capture.capture_keyboard)
        self.context = QCheckBox(
            "Frontmost application metadata, where available (no window titles)"
        )
        self.context.setChecked(s.capture.capture_window_context)

        for cb in (self.mouse, self.keyboard, self.context):
            right_layout.addWidget(cb)

        right_layout.addSpacing(6)
        right_layout.addWidget(section_title("Managed Playwright Browser"))
        self.browser = QCheckBox("Launch an explicitly managed, temporary Chromium context")
        self.browser.setChecked(s.browser.enabled)
        right_layout.addWidget(self.browser)

        self.url = QLineEdit(s.browser.start_url)
        self.url.setPlaceholderText("about:blank or https://...")
        browser_form = QFormLayout()
        browser_form.setVerticalSpacing(8)
        browser_form.setHorizontalSpacing(12)
        browser_form.addRow("Starting URL", self.url)
        right_layout.addLayout(browser_form)

        privacy = QLabel(
            "Screen masks are configured in Settings. Password-field telemetry is excluded, "
            "but native screens can still display secrets. Pause before opening private content."
        )
        privacy.setObjectName("muted")
        privacy.setWordWrap(True)
        right_layout.addStretch()
        right_layout.addWidget(privacy)

        columns.addWidget(left_card, 3)
        columns.addWidget(right_card, 2)
        layout.addLayout(columns)

        # Task boundaries and notes card
        notes_card = card("sectionCard")
        notes_layout = QVBoxLayout(notes_card)
        notes_layout.setContentsMargins(16, 14, 16, 16)
        notes_layout.setSpacing(10)
        notes_layout.addWidget(section_title("Live Task Boundaries & Annotations"))

        note_row = QHBoxLayout()
        note_row.setSpacing(10)
        self.note = QLineEdit()
        self.note.setMaxLength(4000)
        self.note.setPlaceholderText(
            "Enter an explicit user annotation or sub-task label (do not include secrets)..."
        )
        note_row.addWidget(self.note, 1)
        self.note_buttons = [
            button("Add note", lambda: self.annotate(None)),
            button("Start task", lambda: self.annotate("start"), primary=True),
            button("Mark task complete", lambda: self.annotate("end")),
        ]
        for b in self.note_buttons:
            note_row.addWidget(b)
        notes_layout.addLayout(note_row)
        layout.addWidget(notes_card)
        layout.addStretch()

    def apply_to(self, settings):
        c = settings.capture
        c.backend = self.backend.currentData() or "mss"
        monitor_data = self.monitor.currentData()
        c.monitor = int(monitor_data) if monitor_data is not None else 1
        c.fps, c.output_width = int(self.fps.value()), int(self.output_width.value())
        c.screenshot_interval_s = float(self.interval.value())
        c.capture_mouse, c.capture_keyboard = self.mouse.isChecked(), self.keyboard.isChecked()
        c.capture_window_context = self.context.isChecked()
        settings.browser.enabled = self.browser.isChecked()
        settings.browser.start_url = self.url.text().strip() or "about:blank"

    def detect_displays(self):
        from idra.capture.sources import enumerate_monitors

        previous = self.monitor.currentData()

        def show(rows):
            self.monitor.clear()
            if not rows:
                self.monitor.addItem("Monitor 1 (default)", 1)
                return
            for row in rows:
                self.monitor.addItem(
                    f"Monitor {row['monitor']}: {row['width']} × {row['height']} at {row['left']},{row['top']}",
                    row["monitor"],
                )
            idx = self.monitor.findData(previous)
            if idx >= 0:
                self.monitor.setCurrentIndex(idx)

        self.host.run_job("Detecting displays", lambda c, p: enumerate_monitors(), show)

    def annotate(self, boundary):
        try:
            if not self.host.controller.annotate(self.note.text(), boundary):
                raise RuntimeError("Annotation queue is full; the annotation was not saved")
            self.note.clear()
        except Exception as exc:
            self.host.error(str(exc))

    def update_snapshot(self, s):
        state = s["state"]
        busy = self.host.blocking_job_active()
        self.start.setEnabled(
            state in {"IDLE", "COMPLETED", "FAILED", "INTERRUPTED"} and not busy
        )
        self.pause.setEnabled(state == "RECORDING" and not busy)
        self.resume.setEnabled(state == "PAUSED" and not busy)
        self.stop.setEnabled(state in {"STARTING", "RECORDING", "PAUSED"})
        for b in self.note_buttons:
            b.setEnabled(state in {"RECORDING", "PAUSED"})
        shortcut = (
            "Global Ctrl+Alt+Shift+F8 active"
            if s["global_stop_available"]
            else "Global shortcut off (use Stop button or in-app shortcut)"
        )
        self.status.setText(f"{state}  ·  {shortcut}  ·  Browser: {s['browser']}")
