from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)
from idra.events.models import State
from idra.storage.files import contained
from idra.ui.widgets import (
    button,
    card,
    fill_table,
    image_pixmap,
    mono_editor,
    pretty,
    section_title,
    table,
    title,
)


class LibraryPage(QWidget):
    def __init__(self, host):
        super().__init__()
        self.host = host
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 16)
        layout.setSpacing(14)

        header = QVBoxLayout()
        header.setSpacing(3)
        header.addWidget(title("Session explorer"))
        sub = QLabel(
            "Browse, search, inspect, recover interrupted recordings, and manage local session storage."
        )
        sub.setObjectName("pageSubtitle")
        sub.setWordWrap(True)
        header.addWidget(sub)
        layout.addLayout(header)

        toolbar_card = card("sectionCard")
        toolbar_layout = QVBoxLayout(toolbar_card)
        toolbar_layout.setContentsMargins(14, 12, 14, 12)
        toolbar_layout.setSpacing(10)

        bar = QHBoxLayout()
        bar.setSpacing(8)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Filter by session label, task prompt, or UUID...")
        self.search.returnPressed.connect(self.refresh)
        bar.addWidget(self.search, 1)
        self.state_filter = QComboBox()
        self.state_filter.addItems(["ALL", "COMPLETED", "INTERRUPTED", "FAILED", "RECORDING", "PAUSED"])
        self.state_filter.currentTextChanged.connect(lambda *_: self.refresh())
        bar.addWidget(self.state_filter)
        bar.addWidget(button("Search / refresh", self.refresh, primary=True))
        bar.addWidget(button("Rescan storage", lambda: self.refresh(True)))
        toolbar_layout.addLayout(bar)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        for text, callback, danger in [
            ("Open folder", self.open_folder, False),
            ("Timeline / play", lambda: host.show_page(3), False),
            ("Recover interrupted", self.recover, False),
            ("Delete selected", self.delete, True),
        ]:
            actions.addWidget(button(text, callback, danger))
        actions.addStretch()
        self.page_note = QLabel(
            "Showing up to 500 sessions. Use CLI list --offset for additional pages."
        )
        self.page_note.setObjectName("muted")
        actions.addWidget(self.page_note)
        toolbar_layout.addLayout(actions)
        layout.addWidget(toolbar_card)

        table_card = card("sectionCard")
        table_layout = QVBoxLayout(table_card)
        table_layout.setContentsMargins(14, 12, 14, 12)
        table_layout.setSpacing(8)
        table_layout.addWidget(section_title("Recorded Sessions"))
        self.sessions = table(
            ["Created", "Label", "State", "Duration (s)", "Frames", "Events"]
        )
        self.sessions.setMinimumHeight(210)
        self.sessions.itemSelectionChanged.connect(self.selection_changed)
        self.sessions.cellDoubleClicked.connect(lambda *_: self.host.show_page(3))
        table_layout.addWidget(self.sessions, 1)
        layout.addWidget(table_card, 2)

        inspector_card = card("sectionCard")
        inspector_layout = QVBoxLayout(inspector_card)
        inspector_layout.setContentsMargins(14, 12, 14, 14)
        inspector_layout.setSpacing(8)

        split = QSplitter(Qt.Orientation.Horizontal)

        meta_pane = QWidget()
        meta_layout = QVBoxLayout(meta_pane)
        meta_layout.setContentsMargins(0, 0, 6, 0)
        meta_layout.setSpacing(6)
        meta_lbl = QLabel("SESSION MANIFEST & PROVENANCE (JSON)")
        meta_lbl.setObjectName("metricCaption")
        self.metadata = mono_editor(read_only=True, min_height=180)
        meta_layout.addWidget(meta_lbl)
        meta_layout.addWidget(self.metadata, 1)

        preview_pane = QWidget()
        preview_layout = QVBoxLayout(preview_pane)
        preview_layout.setContentsMargins(6, 0, 0, 0)
        preview_layout.setSpacing(6)
        preview_lbl = QLabel("CANONICAL VIDEO FRAME 0 PREVIEW")
        preview_lbl.setObjectName("metricCaption")
        self.preview = QLabel("Select a session for metadata and a recorded-frame preview")
        self.preview.setObjectName("previewBox")
        self.preview.setMinimumSize(360, 190)
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setWordWrap(True)
        preview_layout.addWidget(preview_lbl)
        preview_layout.addWidget(self.preview, 1)

        split.addWidget(meta_pane)
        split.addWidget(preview_pane)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 2)
        inspector_layout.addWidget(split, 1)
        layout.addWidget(inspector_card, 2)

    def refresh(self, rescan=False, background=False):
        query = self.search.text()
        state = self.state_filter.currentText()

        def work(cancel, progress):
            if rescan:
                self.host.repository.scan()
            return self.host.repository.list(query, state=state)

        # A read-only listing never needs to block recording controls.
        self.host.run_job(
            "Loading sessions", work, self.populate, parallel=background and not rescan
        )

    def populate(self, rows):
        for row in rows:
            row["duration"] = round(row["duration_ns"] / 1e9, 2)
        fill_table(
            self.sessions,
            rows,
            ["created_at", "label", "state", "duration", "frame_count", "event_count"],
            ids=[r["id"] for r in rows],
        )
        self.host.dashboard.update_recent(rows)
        if rows:
            self.sessions.selectRow(0)
        else:
            self.selection_changed()

    def selected_ids(self):
        return [
            self.sessions.item(r, 0).data(Qt.ItemDataRole.UserRole)
            for r in sorted({i.row() for i in self.sessions.selectedIndexes()})
        ]

    def selection_changed(self):
        ids = self.selected_ids()
        self.host.selected_ids = ids
        self.host.dataset.update_selection(ids)
        self.host.timeline.set_session(ids[0] if ids else None)
        if not ids:
            self.metadata.clear()
            self.preview.clear()
            self.preview.setText("Select a session for metadata and a recorded-frame preview")
            return
        sid = ids[0]

        def work(cancel, progress):
            m = self.host.repository.load(sid)
            image = None
            if m.media:
                from idra.media.images import read_frame

                try:
                    image = read_frame(
                        contained(self.host.repository.path(sid), m.media), 0
                    )
                except RuntimeError:
                    pass
            return sid, m.model_dump(mode="json"), image

        def show(result):
            selected, manifest, image = result
            if selected not in self.host.selected_ids:
                return
            self.metadata.setPlainText(pretty(manifest))
            if image is not None:
                self.preview.setPixmap(image_pixmap(image, 460, 240))
            else:
                self.preview.clear()
                self.preview.setText("No readable finalized media preview")

        self.host.run_job("Loading session preview", work, show, parallel=True)

    def open_folder(self):
        sid = self.host.require_session()
        if sid:
            QDesktopServices.openUrl(
                QUrl.fromLocalFile(str(self.host.repository.path(sid)))
            )

    def recover(self):
        sid = self.host.require_session()
        if not sid:
            return
        if (
            QMessageBox.question(
                self,
                "Recover session",
                "Preserve incomplete tails, rebuild indexes and mark this session INTERRUPTED?",
            )
            != QMessageBox.StandardButton.Yes
        ):
            return

        def work(cancel, progress):
            from idra.storage.recovery import recover

            m = self.host.repository.load(sid)
            if m.state == State.COMPLETED:
                raise ValueError("Completed sessions do not need crash recovery")
            return recover(self.host.repository, sid)

        def on_recovered(report):
            self.metadata.setPlainText(pretty(report))
            self.refresh(background=True)

        self.host.run_job("Recovering session", work, on_recovered)

    def delete(self):
        ids = self.selected_ids()
        if not ids:
            return
        text = (
            f"Permanently remove {len(ids)} selected session(s), including media and events? "
            "This is not guaranteed secure erasure on SSDs or backups."
        )
        if (
            QMessageBox.question(self, "Delete recordings", text)
            != QMessageBox.StandardButton.Yes
        ):
            return
        query = self.search.text()

        def work(cancel, progress):
            for index, sid in enumerate(ids):
                if cancel.is_set():
                    break
                self.host.repository.delete(sid, confirmed=True)
                progress((index + 1) / len(ids))
            return self.host.repository.list(query)

        self.host.run_job("Deleting selected sessions", work, self.populate)
