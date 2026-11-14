import itertools
from pathlib import Path
from uuid import uuid4
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)
from idra.events.models import SegmentationConfig
from idra.storage.files import SessionLock, contained
from idra.ui.widgets import button, card, mono_editor, pretty, section_title, spin, title


class DatasetPage(QWidget):
    def __init__(self, host):
        super().__init__()
        self.host = host
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 16)
        layout.setSpacing(14)

        header = QHBoxLayout()
        header_left = QVBoxLayout()
        header_left.setSpacing(3)
        header_left.addWidget(title("Dataset studio"))
        sub = QLabel(
            "Segment sessions into computer-use trajectories, validate schema & media integrity, and export deterministic splits."
        )
        sub.setObjectName("pageSubtitle")
        sub.setWordWrap(True)
        header_left.addWidget(sub)
        header.addLayout(header_left, 1)

        self.selection = QLabel("Select one or more sessions in Session explorer")
        self.selection.setObjectName("statusPillNeutral")
        self.selection.setWordWrap(True)
        header.addWidget(self.selection)
        layout.addLayout(header)

        top_columns = QHBoxLayout()
        top_columns.setSpacing(14)

        # Left card: Segmentation & Splits
        seg_card = card("sectionCard")
        seg_layout = QVBoxLayout(seg_card)
        seg_layout.setContentsMargins(16, 14, 16, 16)
        seg_layout.setSpacing(12)
        seg_layout.addWidget(section_title("Trajectory Segmentation & Splits"))

        form = QFormLayout()
        form.setVerticalSpacing(10)
        form.setHorizontalSpacing(14)
        self.inactivity = spin(30, 0.1, 86400, True)
        self.stride = spin(1, 1, 10000)
        self.max_actions = spin(1000, 1, 10000)
        self.navigation = QCheckBox(
            "Use observed browser-navigation starts as segment boundaries"
        )
        self.split_unit = QComboBox()
        self.split_unit.addItems(["session", "task"])
        self.ratios = QLineEdit("0.8,0.1,0.1")
        self.seed = QLineEdit("idra-v1")

        form.addRow("Inactivity threshold (s)", self.inactivity)
        form.addRow("Frame-context sampling stride", self.stride)
        form.addRow("Maximum actions per trajectory", self.max_actions)
        form.addRow("Navigation boundary", self.navigation)
        form.addRow("Split unit", self.split_unit)
        form.addRow("Train / val / test ratios", self.ratios)
        form.addRow("Deterministic split seed", self.seed)
        seg_layout.addLayout(form)
        seg_layout.addStretch()

        # Right card: Media Attestation, Validation & Export Actions
        policy_card = card("sectionCard")
        policy_layout = QVBoxLayout(policy_card)
        policy_layout.setContentsMargins(16, 14, 16, 16)
        policy_layout.setSpacing(12)
        policy_layout.addWidget(section_title("Export Policy & Quality Validation"))

        self.media = QCheckBox(
            "Include canonical video and sampled screenshots (off by default)"
        )
        self.reviewed = QCheckBox(
            "I reviewed the visual media and authorize its inclusion"
        )
        self.reviewed.setEnabled(False)
        self.media.toggled.connect(self.reviewed.setEnabled)
        self.incomplete = QCheckBox(
            "Allow interrupted sessions that pass hard quality checks; task success remains unconfirmed"
        )
        self.full_decode = QCheckBox(
            "Count/decode all video frames during validation (slower)"
        )
        for w in (self.media, self.reviewed, self.incomplete, self.full_decode):
            policy_layout.addWidget(w)

        policy_layout.addStretch()
        actions = QHBoxLayout()
        actions.setSpacing(10)
        actions.addWidget(button("Preview trajectories", self.preview))
        actions.addWidget(button("Validate selected", self.validate))
        actions.addWidget(button("Export dataset", self.export, primary=True))
        policy_layout.addLayout(actions)

        top_columns.addWidget(seg_card, 1)
        top_columns.addWidget(policy_card, 1)
        layout.addLayout(top_columns)

        # Output Console Card
        console_card = card("sectionCard")
        console_layout = QVBoxLayout(console_card)
        console_layout.setContentsMargins(14, 12, 14, 14)
        console_layout.setSpacing(6)
        console_lbl = QLabel("TRAJECTORY PREVIEW / VALIDATION / EXPORT REPORT (JSON)")
        console_lbl.setObjectName("metricCaption")
        self.result = mono_editor(read_only=True, min_height=220)
        console_layout.addWidget(console_lbl)
        console_layout.addWidget(self.result, 1)
        layout.addWidget(console_card, 1)

        # Media Processing Studio
        group = QGroupBox("Media processing - original recording is retained")
        mf = QFormLayout(group)
        mf.setVerticalSpacing(10)
        mf.setHorizontalSpacing(14)
        self.operation = QComboBox()
        self.operation.addItems(["inspect", "transcode", "extract", "clip"])
        self.media_width = spin(0, 0, 7680)
        self.every_n = spin(5, 1, 10000)
        self.deduplicate = QCheckBox("Skip consecutive identical sampled frames")
        self.clip_start = spin(0, 0, 1e9, True)
        self.clip_duration = spin(5, 0.1, 1e9, True)
        mf.addRow("Operation", self.operation)
        mf.addRow("Output width (0 = original)", self.media_width)
        mf.addRow("Extract every Nth frame", self.every_n)
        mf.addRow("Exact-pixel deduplication", self.deduplicate)
        mf.addRow("Clip start in video playback seconds", self.clip_start)
        mf.addRow("Clip duration (s)", self.clip_duration)
        mf.addRow(button("Run on first selected session", self.process))
        layout.addWidget(group)

    def update_selection(self, ids):
        self.selection.setText(
            f"{len(ids)} selected session(s): " + ", ".join(ids)
            if ids
            else "Select one or more sessions in Session explorer"
        )

    def configuration(self):
        return SegmentationConfig(
            inactivity_s=self.inactivity.value(),
            frame_stride=int(self.stride.value()),
            max_actions=int(self.max_actions.value()),
            navigation_boundaries=self.navigation.isChecked(),
        )

    def preview(self):
        sid = self.host.require_session()
        if not sid:
            return
        config = self.configuration()

        def work(cancel, progress):
            from idra.segmentation.trajectories import trajectories

            directory = self.host.repository.path(sid)
            with SessionLock(directory):
                manifest = self.host.repository.load(sid)
                stream = trajectories(directory, manifest, config)
                try:
                    return {
                        "preview_only": True,
                        "first_3_trajectories": [
                            t.model_dump(mode="json")
                            for t in itertools.islice(stream, 3)
                        ],
                    }
                finally:
                    stream.close()

        self.host.run_job(
            "Preparing trajectory preview",
            work,
            lambda r: self.result.setPlainText(pretty(r)),
        )

    def validate(self):
        ids = list(self.host.selected_ids)
        if not ids:
            self.host.error("Select sessions first")
            return
        full = self.full_decode.isChecked()

        def work(cancel, progress):
            from idra.datasets.quality import validate_session

            results = []
            for i, sid in enumerate(ids):
                if cancel.is_set():
                    from idra.media.ffmpeg import Cancelled

                    raise Cancelled("Validation cancelled between sessions")
                results.append(
                    validate_session(self.host.repository, sid, full_decode=full)
                )
                progress((i + 1) / len(ids))
            return results

        self.host.run_job(
            "Validating sessions", work, lambda r: self.result.setPlainText(pretty(r))
        )

    def export(self):
        ids = list(self.host.selected_ids)
        if not ids:
            self.host.error("Select sessions first")
            return
        if self.media.isChecked() and not self.reviewed.isChecked():
            self.host.error(
                "Review the visual media and check the authorization box before including it"
            )
            return
        parent = QFileDialog.getExistingDirectory(
            self, "Choose the parent folder for a new dataset"
        )
        if not parent:
            return
        name, ok = QInputDialog.getText(
            self,
            "Dataset folder",
            "New folder name",
            text="dataset_" + uuid4().hex[:8],
        )
        if not ok or not name:
            return
        if Path(name).name != name or name in {".", ".."} or "\\" in name or ":" in name:
            self.host.error("Use a simple folder name without path separators")
            return
        try:
            ratios = tuple(float(v.strip()) for v in self.ratios.text().split(","))
            config = self.configuration()
        except ValueError as exc:
            self.host.error(str(exc))
            return
        options = dict(
            config=config,
            include_media=self.media.isChecked(),
            media_reviewed=self.reviewed.isChecked(),
            allow_incomplete=self.incomplete.isChecked(),
            split_unit=self.split_unit.currentText(),
            ratios=ratios,
            seed=self.seed.text(),
        )

        def work(cancel, progress):
            from idra.datasets.export import export_dataset

            return export_dataset(
                self.host.repository,
                ids,
                Path(parent) / name,
                cancel=cancel,
                progress=progress,
                **options,
            )

        self.host.run_job(
            "Exporting and verifying dataset",
            work,
            lambda r: self.result.setPlainText(pretty(r)),
        )

    def process(self):
        sid = self.host.require_session()
        if not sid:
            return
        operation = self.operation.currentText()
        width = int(self.media_width.value()) or None
        every_n, dedup = int(self.every_n.value()), self.deduplicate.isChecked()
        start, duration = self.clip_start.value(), self.clip_duration.value()
        settings = self.host.settings.model_copy(deep=True)

        def work(cancel, progress):
            from idra.media.ffmpeg import inspect_video, transcode
            from idra.media.images import extract_frames

            directory = self.host.repository.path(sid)
            with SessionLock(directory):
                m = self.host.repository.load(sid)
                if not m.media:
                    raise ValueError("No finalized canonical video is available")
                source = contained(directory, m.media)
                destination = (
                    directory
                    / "processed"
                    / (uuid4().hex + ("" if operation == "extract" else ".mp4"))
                )
                if operation == "inspect":
                    result = inspect_video(
                        source, settings.ffprobe, count_frames=True
                    )
                elif operation == "extract":
                    result = extract_frames(
                        source,
                        destination,
                        every_n=every_n,
                        width=width,
                        deduplicate=dedup,
                        cancel=cancel,
                        progress=progress,
                        min_free_mb=settings.min_free_mb,
                    )
                else:
                    result = transcode(
                        source,
                        destination,
                        ffmpeg=settings.ffmpeg,
                        ffprobe=settings.ffprobe,
                        width=width,
                        start_s=start if operation == "clip" else None,
                        duration_s=duration if operation == "clip" else None,
                        cancel=cancel,
                        progress=progress,
                    )
                self.host.repository.add_operation(sid, operation, result)
                return result

        self.host.run_job(
            "Processing recorded media",
            work,
            lambda r: self.result.setPlainText(pretty(r)),
        )
