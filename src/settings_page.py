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

        self.custom_width = QSpinBox()
        self.custom_width.setRange(16, 16384)
        self.custom_width.setValue(1920)
        self.custom_width.setSuffix(" px")
        self.custom_width.setSingleStep(2)

        self.custom_height = QSpinBox()
        self.custom_height.setRange(16, 8640)
        self.custom_height.setValue(1080)
        self.custom_height.setSuffix(" px")
        self.custom_height.setSingleStep(2)

        custom_resolution_layout = QHBoxLayout()
        custom_resolution_layout.setContentsMargins(0, 0, 0, 0)
        custom_resolution_layout.setSpacing(3)

        multiply_label = QLabel("×")

        custom_resolution_layout.addWidget(
            self.custom_width
        )

        custom_resolution_layout.addWidget(
            multiply_label
        )

        custom_resolution_layout.addWidget(
            self.custom_height
        )

        custom_resolution_layout.addStretch()

        self.custom_resolution_widget = QWidget()
        self.custom_resolution_widget.setLayout(
            custom_resolution_layout
        )

        self.custom_resolution_label = QLabel(
            "Custom resolution:"
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
            self.custom_resolution_label,
            self.custom_resolution_widget,
        )

        self.resolution_box.currentIndexChanged.connect(
            self.update_custom_resolution_visibility
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
        back_button.setStyleSheet("""
            QPushButton {
                font-size: 15px;
                font-weight: bold;
                padding: 8px;
            }
        """)

        self.render_button = QPushButton("Render")
        self.render_button.setStyleSheet("""
            QPushButton {
                font-size: 15px;
                font-weight: bold;
                padding: 8px;
            }
        """)

        button_layout = QHBoxLayout()
        button_layout.addWidget(back_button, stretch=1)
        button_layout.addWidget(self.render_button, stretch=1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 20, 30, 30)
        layout.setSpacing(20)

        layout.addWidget(title)
        layout.addWidget(self.video_name)
        layout.addLayout(settings_form)
        layout.addStretch()
        layout.addLayout(button_layout)

        self.update_custom_resolution_visibility()

    def set_video(self, file_path):
        self.video_name.setText(
            Path(file_path).name
        )

    def update_custom_resolution_visibility(self):
        custom_selected = (
            self.resolution_box.currentData() is None
        )

        self.custom_resolution_label.setVisible(
            custom_selected
        )

        self.custom_resolution_widget.setVisible(
            custom_selected
        )

    def get_resolution(self):
        preset_resolution = (
          self.resolution_box.currentData()
        )

        if preset_resolution is not None:
            return preset_resolution

        width = self.custom_width.value()
        height = self.custom_height.value()

        if width % 2 != 0 or height % 2 != 0:
            raise ValueError(
                "Width and height must both be even numbers."
            )

        return width, height