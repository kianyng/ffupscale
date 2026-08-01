from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from render_job import RenderStatus

# -- Queue Styling --

STATUS_COLOURS = {
    RenderStatus.WAITING: "#999999",
    RenderStatus.RENDERING: "#3b82f6",
    RenderStatus.COMPLETED: "#22c55e",
    RenderStatus.FAILED: "#ef4444",
    RenderStatus.CANCELLED: "#f59e0b",
}


# -- Queue Job Row --


class QueueJobRow(QFrame):
    """Display one render job and its available actions."""

    action_requested = pyqtSignal(str)
    remove_requested = pyqtSignal(str)

    def __init__(self, job):
        super().__init__()

        self.job_id = job.job_id

        self.setObjectName("queueJob")
        self.setStyleSheet("""
            QFrame#queueJob {
                background-color: #242424;
                border: 1px solid #3a3a3a;
                border-radius: 10px;
            }
        """)

        self.filename_label = QLabel()
        self.filename_label.setStyleSheet("""
            font-size: 15px;
            font-weight: bold;
        """)

        self.details_label = QLabel()
        self.details_label.setStyleSheet("""
            color: #999999;
            font-size: 11px;
        """)

        self.status_label = QLabel()

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.hide()

        self.action_button = QPushButton()
        self.action_button.clicked.connect(
            lambda: self.action_requested.emit(self.job_id)
        )

        self.remove_button = QPushButton("Remove")
        self.remove_button.clicked.connect(
            lambda: self.remove_requested.emit(self.job_id)
        )

        text_layout = QVBoxLayout()
        text_layout.setSpacing(4)
        text_layout.addWidget(self.filename_label)
        text_layout.addWidget(self.details_label)
        text_layout.addWidget(self.status_label)
        text_layout.addWidget(self.progress_bar)

        button_layout = QVBoxLayout()
        button_layout.addWidget(self.action_button)
        button_layout.addWidget(self.remove_button)
        button_layout.addStretch()

        layout = QHBoxLayout(self)
        layout.setContentsMargins(
            15,
            12,
            15,
            12,
        )
        layout.setSpacing(15)
        layout.addLayout(
            text_layout,
            stretch=1,
        )
        layout.addLayout(button_layout)

        self.update_job(
            job,
            has_active_job=False,
        )

    def update_job(
        self,
        job,
        has_active_job,
    ):
        """Update text, progress and buttons for the job state."""

        self.filename_label.setText(job.filename)

        fps_text = "Original FPS" if job.fps is None else f"{job.fps:g} FPS"

        self.details_label.setText(
            f"{job.resolution_text} · {fps_text} · {job.encoder}"
        )

        status_colour = STATUS_COLOURS[job.status]

        self.status_label.setText(job.status.value)
        self.status_label.setStyleSheet(f"color: {status_colour};")

        self.progress_bar.setValue(job.progress)

        show_progress = job.status in {
            RenderStatus.RENDERING,
            RenderStatus.COMPLETED,
        }

        self.progress_bar.setVisible(show_progress)

        self.remove_button.setVisible(job.status != RenderStatus.RENDERING)

        if job.status == RenderStatus.WAITING:
            self.action_button.setText(
                "Render next" if has_active_job else "Render now"
            )
            self.action_button.setEnabled(True)

        elif job.status == RenderStatus.RENDERING:
            self.action_button.setText("Cancel")
            self.action_button.setEnabled(True)

        elif job.status == RenderStatus.COMPLETED:
            self.action_button.setText("Open folder")
            self.action_button.setEnabled(True)

        elif job.status in {
            RenderStatus.FAILED,
            RenderStatus.CANCELLED,
        }:
            self.action_button.setText("Retry")
            self.action_button.setEnabled(True)


# -- Queue Page --


class QueuePage(QWidget):
    """Display and control the complete render queue."""

    back_requested = pyqtSignal()
    start_queue_requested = pyqtSignal()
    stop_queue_requested = pyqtSignal()
    clear_completed_requested = pyqtSignal()

    job_action_requested = pyqtSignal(str)
    remove_job_requested = pyqtSignal(str)

    def __init__(self):
        super().__init__()

        self.queue_running = False
        self.job_rows = {}

        title = QLabel("Render queue")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("""
            font-size: 32px;
            font-weight: bold;
        """)

        self.summary_label = QLabel("No videos queued")
        self.summary_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.summary_label.setStyleSheet("""
            color: #999999;
        """)

        self.jobs_widget = QWidget()

        self.jobs_layout = QVBoxLayout(self.jobs_widget)
        self.jobs_layout.setContentsMargins(
            0,
            0,
            10,
            0,
        )
        self.jobs_layout.setSpacing(10)
        self.jobs_layout.addStretch()

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setWidget(self.jobs_widget)
        self.scroll_area.setStyleSheet("""
            QScrollArea {
                border: none;
                background: transparent;
            }

            QScrollArea > QWidget > QWidget {
                background: transparent;
            }
        """)

        self.back_button = QPushButton("Back")
        self.back_button.clicked.connect(self.back_requested.emit)

        self.clear_button = QPushButton("Clear completed")
        self.clear_button.clicked.connect(self.clear_completed_requested.emit)

        self.start_stop_button = QPushButton("Start queue")
        self.start_stop_button.clicked.connect(self.request_start_or_stop)

        button_layout = QHBoxLayout()
        button_layout.addWidget(self.back_button)
        button_layout.addWidget(self.clear_button)
        button_layout.addStretch()
        button_layout.addWidget(self.start_stop_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(
            30,
            20,
            30,
            30,
        )
        layout.setSpacing(20)
        layout.addWidget(title)
        layout.addWidget(self.summary_label)
        layout.addWidget(
            self.scroll_area,
            stretch=1,
        )
        layout.addLayout(button_layout)

    def set_jobs(
        self,
        jobs,
        queue_running=False,
    ):
        """Rebuild the displayed queue in its current order."""

        self.queue_running = queue_running
        self.job_rows.clear()

        while self.jobs_layout.count():
            item = self.jobs_layout.takeAt(0)

            widget = item.widget()

            if widget is not None:
                widget.deleteLater()

        has_active_job = any(job.status == RenderStatus.RENDERING for job in jobs)

        for job in jobs:
            row = QueueJobRow(job)

            row.update_job(
                job,
                has_active_job,
            )

            row.action_requested.connect(self.job_action_requested.emit)
            row.remove_requested.connect(self.remove_job_requested.emit)

            self.job_rows[job.job_id] = row
            self.jobs_layout.addWidget(row)

        self.jobs_layout.addStretch()

        waiting = sum(job.status == RenderStatus.WAITING for job in jobs)
        completed = sum(job.status == RenderStatus.COMPLETED for job in jobs)

        if not jobs:
            self.summary_label.setText("No videos queued")
        else:
            self.summary_label.setText(
                f"{len(jobs)} videos · {waiting} waiting · {completed} completed"
            )

        if queue_running:
            self.start_stop_button.setText("Stop queue")
            self.start_stop_button.setEnabled(True)
        else:
            self.start_stop_button.setText("Start queue")
            self.start_stop_button.setEnabled(waiting > 0)

        self.clear_button.setEnabled(completed > 0)

    def update_job(
        self,
        job,
        has_active_job,
    ):
        """Update one row without rebuilding the complete queue."""

        row = self.job_rows.get(job.job_id)

        if row is not None:
            row.update_job(
                job,
                has_active_job,
            )

    def request_start_or_stop(self):
        if self.queue_running:
            self.stop_queue_requested.emit()
        else:
            self.start_queue_requested.emit()
