from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QSlider,
    QSplitter,
    QVBoxLayout,
    QWidget,
)
from idra.storage.files import contained
from idra.storage.repository import connect_index, neighboring_frames, query_events
from idra.ui.widgets import (
    button,
    card,
    fill_table,
    image_pixmap,
    mono_editor,
    pretty,
    section_title,
    spin,
    table,
    title,
)


class TimelinePage(QWidget):
    def __init__(self, host):
        super().__init__()
        self.host, self.session_id, self.offset = host, None, 0
        self.events = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 16)
        layout.setSpacing(14)

        header = QHBoxLayout()
        header_left = QVBoxLayout()
        header_left.setSpacing(3)
        header_left.addWidget(title("Timeline and event inspector"))
        sub = QLabel(
            "Inspect every recorded event alongside its synchronized video frame and monotonic timestamp."
        )
        sub.setObjectName("pageSubtitle")
        sub.setWordWrap(True)
        header_left.addWidget(sub)
        header.addLayout(header_left, 1)

        self.selection = QLabel("Select a session in Session explorer")
        self.selection.setObjectName("statusPillNeutral")
        header.addWidget(self.selection, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(header)

        self.player = None
        try:
            from PyQt6.QtMultimedia import QMediaPlayer
            from PyQt6.QtMultimediaWidgets import QVideoWidget

            media_card = card("sectionCard")
            media_layout = QVBoxLayout(media_card)
            media_layout.setContentsMargins(14, 12, 14, 12)
            media_layout.setSpacing(8)
            media_layout.addWidget(section_title("Session Video Playback"))

            video = QVideoWidget()
            video.setMinimumHeight(210)
            self.player = QMediaPlayer(self)
            self.player.setVideoOutput(video)
            self.player.errorOccurred.connect(
                lambda *_: self.selection.setText(
                    "Video playback unavailable: " + self.player.errorString()
                )
            )
            media_layout.addWidget(video)

            playbar = QHBoxLayout()
            playbar.setSpacing(8)
            playbar.addWidget(button("Play", self.player.play, primary=True))
            playbar.addWidget(button("Pause playback", self.player.pause))
            self.seek = QSlider(Qt.Orientation.Horizontal)
            self.seek.sliderMoved.connect(self.player.setPosition)
            self.player.positionChanged.connect(self.seek.setValue)
            self.player.durationChanged.connect(
                lambda duration: self.seek.setRange(0, min(duration, 2_147_483_647))
            )
            playbar.addWidget(self.seek, 1)
            media_layout.addLayout(playbar)
            layout.addWidget(media_card)
        except ImportError:
            fallback = QLabel(
                "Qt Multimedia is unavailable; decoded frame inspection remains available."
            )
            fallback.setObjectName("muted")
            layout.addWidget(fallback)

        filter_card = card("sectionCard")
        filter_layout = QVBoxLayout(filter_card)
        filter_layout.setContentsMargins(14, 12, 14, 12)
        filter_layout.setSpacing(10)

        filters = QHBoxLayout()
        filters.setSpacing(8)
        self.kind = QComboBox()
        self.kind.addItems(
            [
                "All types",
                "mouse_move",
                "mouse_button_down",
                "mouse_button_up",
                "scroll",
                "key_press",
                "key_release",
                "browser_navigation",
                "browser_action",
                "window_context",
                "annotation",
                "task_boundary",
                "state_change",
            ]
        )
        self.start = spin(0, 0, 1e9, True)
        self.end = spin(0, 0, 1e9, True)
        filters.addWidget(QLabel("Event type"))
        filters.addWidget(self.kind)
        for name, field in (("Start s", self.start), ("End s (0=all)", self.end)):
            lbl = QLabel(name)
            lbl.setObjectName("muted")
            filters.addWidget(lbl)
            filters.addWidget(field)
        filters.addStretch()
        filters.addWidget(button("Apply", lambda: self.reload(reset=True), primary=True))
        filters.addWidget(button("Previous", self.previous))
        filters.addWidget(button("Next", self.next))
        filter_layout.addLayout(filters)

        self.event_table = table(
            ["Session time (s)", "Event type", "Source", "Coordinates", "Timing basis"]
        )
        self.event_table.setMinimumHeight(200)
        self.event_table.cellClicked.connect(self.inspect_event)
        self.event_table.currentCellChanged.connect(self._on_current_cell_changed)
        filter_layout.addWidget(self.event_table, 1)
        layout.addWidget(filter_card, 1)

        inspector_card = card("sectionCard")
        inspector_layout = QVBoxLayout(inspector_card)
        inspector_layout.setContentsMargins(14, 12, 14, 12)
        inspector_layout.setSpacing(8)

        details = QSplitter(Qt.Orientation.Horizontal)

        left_pane = QWidget()
        left_layout = QVBoxLayout(left_pane)
        left_layout.setContentsMargins(0, 0, 6, 0)
        left_layout.setSpacing(6)
        detail_lbl = QLabel("EVENT RECORD PAYLOAD (JSON)")
        detail_lbl.setObjectName("metricCaption")
        self.detail = mono_editor(read_only=True, min_height=180)
        left_layout.addWidget(detail_lbl)
        left_layout.addWidget(self.detail, 1)

        right_pane = QWidget()
        right_layout = QVBoxLayout(right_pane)
        right_layout.setContentsMargins(6, 0, 0, 0)
        right_layout.setSpacing(6)
        frame_lbl = QLabel("SYNCHRONIZED RECORDED FRAME")
        frame_lbl.setObjectName("metricCaption")
        self.frame = QLabel(
            "Select an event to inspect its preceding/following recorded frame"
        )
        self.frame.setObjectName("previewBox")
        self.frame.setMinimumSize(360, 180)
        self.frame.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.frame.setWordWrap(True)
        self.mapping = QLabel(
            "Session time includes pauses. Seeking uses the stored frame-to-video mapping, not a direct session-seconds conversion."
        )
        self.mapping.setObjectName("muted")
        self.mapping.setWordWrap(True)
        right_layout.addWidget(frame_lbl)
        right_layout.addWidget(self.frame, 1)
        right_layout.addWidget(self.mapping)

        details.addWidget(left_pane)
        details.addWidget(right_pane)
        details.setStretchFactor(0, 3)
        details.setStretchFactor(1, 2)
        inspector_layout.addWidget(details, 1)
        layout.addWidget(inspector_card, 1)

    def _on_current_cell_changed(self, current_row, current_col, previous_row, previous_col):
        if current_row >= 0 and current_row != previous_row:
            self.inspect_event(current_row, current_col)

    def set_session(self, sid):
        if sid != self.session_id:
            self.session_id, self.offset = sid, 0
            self.events = []
            self.event_table.setRowCount(0)
            self.detail.clear()
            self.frame.clear()
            self.frame.setText("Select and load an event")
            if self.player:
                self.player.stop()
                self.player.setSource(QUrl())
        self.selection.setText(
            "Session: " + sid if sid else "Select a session in Session explorer"
        )

    def reload(self, reset=False):
        if not self.session_id:
            self.host.error("Select a session in Session explorer first")
            return
        if reset:
            self.offset = 0
        sid, offset = self.session_id, self.offset
        kind = None if self.kind.currentIndex() == 0 else self.kind.currentText()
        begin = round(self.start.value() * 1e9)
        end = round(self.end.value() * 1e9) if self.end.value() else None

        def work(cancel, progress):
            directory = self.host.repository.path(sid)
            manifest = self.host.repository.load(sid)
            return sid, query_events(directory, kind, begin, end, 500, offset), manifest

        def show(result):
            selected, events, manifest = result
            if selected != self.session_id:
                return
            if not events and offset > 0:
                self.offset = max(0, offset - 500)
                return
            self.events = events
            rows = [
                {
                    "time": round(e.t_ns / 1e9, 6),
                    "type": e.type,
                    "source": e.source,
                    "coordinates": ""
                    if e.payload.x is None
                    else f"{e.payload.x}, {e.payload.y}",
                    "timing": e.timestamp_kind,
                }
                for e in events
            ]
            fill_table(
                self.event_table,
                rows,
                ["time", "type", "source", "coordinates", "timing"],
            )
            self.selection.setText(
                f"Session {sid}  ·  Events {offset + 1 if events else 0}–{offset + len(events)}"
            )
            if self.player and manifest.media:
                url = QUrl.fromLocalFile(
                    str(contained(self.host.repository.path(sid), manifest.media))
                )
                if self.player.source() != url:
                    self.player.setSource(url)

        self.host.run_job("Loading timeline", work, show)

    def previous(self):
        self.offset = max(0, self.offset - 500)
        self.reload()

    def next(self):
        if len(self.events) == 500:
            self.offset += 500
            self.reload()

    def inspect_event(self, row, column=0):
        if row < 0 or row >= len(self.events) or not self.session_id:
            return
        event, sid = self.events[row], self.session_id
        self.detail.setPlainText(pretty(event.model_dump(mode="json")))

        def work(cancel, progress):
            directory = self.host.repository.path(sid)
            m = self.host.repository.load(sid)
            with connect_index(directory, readonly=True) as conn:
                before, after = neighboring_frames(conn, event.t_ns)
            f = before or after
            image = None
            if f and m.media:
                from idra.media.images import read_frame

                image = read_frame(contained(directory, m.media), f.index)
            return sid, f, image

        def show(result):
            selected, f, image = result
            if selected != self.session_id:
                return
            if f and image is not None:
                self.frame.setPixmap(image_pixmap(image, 420, 240))
                self.mapping.setText(
                    f"Frame {f.index}  ·  Capture {f.t_ns / 1e9:.6f}s  ·  "
                    f"Nominal PTS {f.pts_ns / 1e9:.6f}s  ·  Timing: {f.timestamp_kind}"
                )
                if self.player:
                    self.player.setPosition(f.pts_ns // 1_000_000)
            else:
                self.frame.clear()
                self.frame.setText(
                    "No recorded frame is available within the matching time window"
                )

        self.host.run_job("Decoding event frame", work, show)
