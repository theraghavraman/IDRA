from PyQt6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLabel, QVBoxLayout, QWidget
from idra.ui.widgets import card, fill_table, format_time, section_title, table, title

METRIC_DEFINITIONS = [
    ("duration", "SESSION TIME", "Elapsed monotonic clock"),
    ("frames", "ENCODED FRAMES", "H.264 MKV stream"),
    ("mouse", "MOUSE / SCROLL EVENTS", "Normalized pointer actions"),
    ("keyboard", "KEY CATEGORIES", "Zero printable characters"),
    ("shots", "SCREENSHOTS", "Sampled PNG keyframes"),
    ("disk", "DISK FREE", "Available local volume"),
    ("drops", "DROPPED FRAMES / EVENTS", "Bounded queue pressure"),
    ("browser", "MANAGED BROWSER", "Ephemeral Playwright state"),
]


class DashboardPage(QWidget):
    def __init__(self, host):
        super().__init__()
        self.host = host
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 16)
        layout.setSpacing(14)

        header = QVBoxLayout()
        header.setSpacing(3)
        header.addWidget(title("Recording overview"))
        hint = QLabel(
            "Live telemetry from the local capture and journal pipeline. "
            "All recorded sessions and media remain strictly on this computer."
        )
        hint.setObjectName("pageSubtitle")
        hint.setWordWrap(True)
        header.addWidget(hint)
        layout.addLayout(header)

        status_card = card("bannerCard")
        status_layout = QHBoxLayout(status_card)
        status_layout.setContentsMargins(16, 12, 16, 12)
        status_layout.setSpacing(18)

        left_col = QVBoxLayout()
        left_col.setSpacing(4)
        live_tag = QLabel("PIPELINE TELEMETRY")
        live_tag.setObjectName("metricCaption")
        self.detail = QLabel("No active recording")
        self.detail.setObjectName("bannerPrimary")
        self.detail.setWordWrap(True)
        left_col.addWidget(live_tag)
        left_col.addWidget(self.detail)

        right_col = QVBoxLayout()
        right_col.setSpacing(4)
        privacy_tag = QLabel("PRIVACY & INTEGRITY POSTURE")
        privacy_tag.setObjectName("metricCaption")
        self.health = QLabel(
            "Privacy: no raw typed text or clipboard is stored. Visible screen content still needs review."
        )
        self.health.setObjectName("muted")
        self.health.setWordWrap(True)
        right_col.addWidget(privacy_tag)
        right_col.addWidget(self.health)

        status_layout.addLayout(left_col, 1)
        status_layout.addLayout(right_col, 1)
        layout.addWidget(status_card)

        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(12)
        self.cards = {}
        for i, (key, caption, subtext) in enumerate(METRIC_DEFINITIONS):
            metric_frame = QFrame()
            metric_frame.setObjectName("metricCard")
            col = QVBoxLayout(metric_frame)
            col.setContentsMargins(14, 12, 14, 12)
            col.setSpacing(4)
            label = QLabel(caption)
            label.setObjectName("metricCaption")
            number = QLabel("Not started")
            number.setObjectName("metricValue")
            sub = QLabel(subtext)
            sub.setObjectName("muted")
            col.addWidget(label)
            col.addWidget(number)
            col.addWidget(sub)
            grid.addWidget(metric_frame, i // 4, i % 4)
            self.cards[key] = number
        layout.addLayout(grid)

        recent_card = card("sectionCard")
        recent_layout = QVBoxLayout(recent_card)
        recent_layout.setContentsMargins(16, 14, 16, 16)
        recent_layout.setSpacing(10)
        recent_header = QHBoxLayout()
        recent_header.addWidget(section_title("Recent sessions"))
        recent_header.addStretch()
        recent_hint = QLabel("Double-click in Session explorer to inspect timeline")
        recent_hint.setObjectName("muted")
        recent_header.addWidget(recent_hint)
        recent_layout.addLayout(recent_header)

        self.recent = table(["Created", "Label", "State", "Frames", "Events"])
        self.recent.setMinimumHeight(220)
        recent_layout.addWidget(self.recent, 1)
        layout.addWidget(recent_card, 1)

    def update_snapshot(self, s):
        c = s["counts"]
        values = {
            "duration": format_time(s["duration_ns"]),
            "frames": str(c.get("encoded_frames", 0)),
            "mouse": str(
                sum(c.get(k, 0) for k in ("mouse_move", "mouse_button_down", "mouse_button_up", "scroll"))
            ),
            "keyboard": str(c.get("key_press", 0) + c.get("key_release", 0)),
            "shots": str(c.get("screenshots", 0)),
            "disk": f"{s['disk_free_bytes'] / 1024**3:.1f} GiB",
            "drops": f"{c.get('dropped_frames', 0)} / {c.get('dropped_events', 0)}",
            "browser": s["browser"],
        }
        for key, value in values.items():
            self.cards[key].setText(value)
        g = s["geometry"]
        self.detail.setText(
            f"{s['state']}  ·  {g.get('output_width', '?')} × {g.get('output_height', '?')} px  ·  "
            f"Queued frames: {c.get('pending_frames', 0)}  ·  Queued records: {c.get('pending_records', 0)}"
        )
        if s["failure_codes"]:
            self.health.setText("Failures: " + "; ".join(s["failure_codes"]))
            self.health.setStyleSheet("color: #FB7185; font-weight: 600;")
        else:
            self.health.setText(
                "Privacy: no raw typed text or clipboard is stored. Review visible content before exporting media."
            )
            self.health.setStyleSheet("")

    def update_recent(self, rows):
        fill_table(
            self.recent,
            rows[:20],
            ["created_at", "label", "state", "frame_count", "event_count"],
        )
