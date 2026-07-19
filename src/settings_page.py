from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)


class SettingsPage(QWidget):
    """Collect encoding settings and report user actions to MainWindow."""

    # MainWindow owns navigation and FFmpeg, so this page communicates by signal.
    back_requested = pyqtSignal()
    render_requested = pyqtSignal(dict)
    cancel_requested = pyqtSignal()

    def __init__(self):
        super().__init__()

        self.is_rendering = False

        title = QLabel("Upscale settings")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("""
            font-size: 32px;
            font-weight: bold;
        """)

        self.video_name = QLabel("No video selected")
        self.video_name.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.resolution_box = QComboBox()
        # Item data holds the actual dimensions used by FFmpeg.
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

        custom_resolution_layout.addWidget(self.custom_width)

        custom_resolution_layout.addWidget(multiply_label)

        custom_resolution_layout.addWidget(self.custom_height)

        custom_resolution_layout.addStretch()

        self.custom_resolution_widget = QWidget()
        self.custom_resolution_widget.setLayout(custom_resolution_layout)

        self.custom_resolution_label = QLabel("Custom resolution:")

        self.fps_box = QComboBox()
        # String sentinels distinguish special options from numeric frame rates.
        self.fps_box.addItem(
            "Keep original",
            "original",
        )

        self.fps_box.addItem(
            "24 FPS",
            24,
        )

        self.fps_box.addItem(
            "30 FPS",
            30,
        )

        self.fps_box.addItem(
            "60 FPS",
            60,
        )

        self.fps_box.addItem(
            "120 FPS",
            120,
        )

        self.fps_box.addItem(
            "Custom",
            "custom",
        )

        self.custom_fps = QDoubleSpinBox()
        self.custom_fps.setRange(1.0, 240.0)
        self.custom_fps.setValue(60.0)
        self.custom_fps.setDecimals(3)
        self.custom_fps.setSingleStep(1.0)
        self.custom_fps.setSuffix(" FPS")

        self.custom_fps_label = QLabel("Custom frame rate:")

        self.fps_box.currentIndexChanged.connect(self.update_custom_fps_visibility)

        self.quality_box = QComboBox()

        self.quality_box.addItem(
            "Balanced",
            "balanced",
        )

        self.quality_box.addItem(
            "High",
            "high",
        )

        self.quality_box.addItem(
            "Near-lossless",
            "near_lossless",
        )

        self.encoder_box = QComboBox()

        self.encoder_box.addItem(
            "H.264 — best compatibility",
            "libx264",
        )

        self.encoder_box.addItem(
            "H.265 — smaller files",
            "libx265",
        )

        self.preset_box = QComboBox()

        self.preset_box.addItem(
            "Fast",
            "fast",
        )

        self.preset_box.addItem(
            "Medium",
            "medium",
        )

        self.preset_box.addItem(
            "Slow — better compression",
            "slow",
        )

        self.preset_box.setCurrentIndex(1)

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
            self.custom_fps_label,
            self.custom_fps,
        )

        settings_form.addRow(
            "Quality:",
            self.quality_box,
        )

        settings_form.addRow(
            "Encoder:",
            self.encoder_box,
        )

        settings_form.addRow(
            "Encoding speed:",
            self.preset_box,
        )

        self.back_button = QPushButton("Back")

        self.back_button.clicked.connect(self.back_requested.emit)

        self.back_button.setStyleSheet("""
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

        self.render_button.clicked.connect(self.request_render)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("%p%")
        self.progress_bar.hide()

        button_layout = QHBoxLayout()
        button_layout.addWidget(self.back_button, stretch=1)
        button_layout.addWidget(self.render_button, stretch=1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 20, 30, 30)
        layout.setSpacing(20)

        layout.addWidget(title)
        layout.addWidget(self.video_name)
        layout.addLayout(settings_form)
        layout.addStretch()

        layout.addWidget(self.progress_bar)
        layout.addLayout(button_layout)

        self.update_custom_resolution_visibility()
        self.update_custom_fps_visibility()

    def set_video(self, file_path):
        self.video_name.setText(Path(file_path).name)

    def update_custom_resolution_visibility(self):
        """Show custom dimensions only when Custom is selected."""

        custom_selected = self.resolution_box.currentData() is None

        self.custom_resolution_label.setVisible(custom_selected)

        self.custom_resolution_widget.setVisible(custom_selected)

    def update_custom_fps_visibility(self):
        """Show the FPS input only when Custom is selected."""

        custom_selected = self.fps_box.currentData() == "custom"

        self.custom_fps_label.setVisible(custom_selected)

        self.custom_fps.setVisible(custom_selected)

    def get_fps(self):
        """Return None to preserve FPS, or the selected numeric value."""

        selected_fps = self.fps_box.currentData()

        if selected_fps == "original":
            return None

        if selected_fps == "custom":
            return self.custom_fps.value()

        return selected_fps

    def get_resolution(self):
        """Return validated output dimensions from the preset or custom inputs."""

        preset_resolution = self.resolution_box.currentData()

        if preset_resolution is not None:
            return preset_resolution

        width = self.custom_width.value()
        height = self.custom_height.value()

        if width % 2 != 0 or height % 2 != 0:
            raise ValueError("Width and height must both be even numbers.")

        return width, height

    def get_settings(self):
        """Build the settings dictionary consumed by the FFmpeg backend."""

        width, height = self.get_resolution()

        return {
            "resolution": (width, height),
            "fps": self.get_fps(),
            "quality": self.quality_box.currentData(),
            "encoder": self.encoder_box.currentData(),
            "preset": self.preset_box.currentData(),
        }

    def request_render(self):
        """Treat the primary button as Render or Cancel based on page state."""

        if self.is_rendering:
            self.cancel_requested.emit()
            return

        try:
            settings = self.get_settings()
            self.render_requested.emit(settings)

        except ValueError as error:
            print(f"Invalid settings: {error}")

    def set_rendering(self, rendering):
        """Update controls when an FFmpeg process starts or stops."""

        self.is_rendering = rendering
        self.back_button.setEnabled(not rendering)

        if rendering:
            self.render_button.setText("Cancel")
            self.render_button.setEnabled(True)

            self.progress_bar.setValue(0)
            self.progress_bar.setFormat("%p%")
            self.progress_bar.show()
        else:
            self.render_button.setText("Render")
            self.render_button.setEnabled(True)

    def set_cancelling(self):
        """Prevent repeated cancellation requests while FFmpeg is stopping."""

        self.render_button.setText("Cancelling...")
        self.render_button.setEnabled(False)

    def set_progress(self, percentage):
        """Clamp FFmpeg progress to the range accepted by QProgressBar."""

        percentage = max(0, min(100, int(percentage)))
        self.progress_bar.setValue(percentage)
