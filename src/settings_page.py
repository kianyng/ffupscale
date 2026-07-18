from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
    QHBoxLayout,
)


class SettingsPage(QWidget):
    back_requested = pyqtSignal()

    def __init__(self):
        super().__init__()

        title = QLabel("Upscale settings")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("""
            font-size: 32px;
            font-weight: bold;
        """)

        self.video_name = QLabel("No video selected")
        self.video_name.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )

        self.resolution_box = QComboBox()

        self.resolution_box.addItem(
            "1280 × 720",
            (1280, 720),
        )

        self.resolution_box.addItem(
            "1920 × 1080",
            (1920, 1080),
        )

        self.resolution_box.addItem(
            "2560 × 1440",
            (2560, 1440),
        )

        self.resolution_box.addItem(
            "3840 × 2160",
            (3840, 2160),
        )

        self.resolution_box.addItem(
            "Custom",
            None,
        )

        self.fps_box = QComboBox()
        self.fps_box.addItems([
            "Keep original",
            "30 FPS",
            "60 FPS",
            "120 FPS",
        ])

        self.quality_box = QComboBox()
        self.quality_box.addItems([
            "Balanced",
            "High",
            "Near-lossless",
        ])

        settings_form = QFormLayout()
        settings_form.addRow(
            "Resolution:",
            self.resolution_box,
        )
        settings_form.addRow(
            "Frame rate:",
            self.fps_box,
        )
        settings_form.addRow(
            "Quality:",
            self.quality_box,
        )

        back_button = QPushButton("Back")
        back_button.clicked.connect(
            self.back_requested.emit
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 20, 30, 30)
        layout.setSpacing(20)

        layout.addWidget(title)
        layout.addWidget(self.video_name)
        layout.addLayout(settings_form)
        layout.addStretch()
        layout.addWidget(back_button)

    def set_video(self, file_path):
        self.video_name.setText(
            Path(file_path).name
        )